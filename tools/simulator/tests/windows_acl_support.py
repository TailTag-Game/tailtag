"""Independent Windows access-list reader for simulator privacy assertions.

A deliberately small copy of the reader in services/api/tests/windows_acl_support.py:
the two uv projects cannot share test code. It reads the binary security
descriptor, so assertions do not depend on the code under test.
"""

import csv
import ctypes
import subprocess
import sys
from pathlib import Path

SYSTEM_SID = "S-1-5-18"
ADMINISTRATORS_SID = "S-1-5-32-544"
# FILE_ALL_ACCESS, or GENERIC_ALL stored unmapped.
FULL_CONTROL = {0x1F01FF, 0x10000000}


def token_user_sid() -> str:
    output = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return next(csv.reader([output.strip()]))[1]


def _binary_access(path: Path) -> tuple[str, bool, list[tuple[int, int, int, str]]]:
    """Read owner SID, DACL protection and basic ACEs from the binary descriptor.

    SIDs come from ConvertSidToStringSidW, never from SDDL text, because SDDL
    prints well-known aliases (LA, DA, ...) instead of the SID string.
    """
    if sys.platform != "win32":
        raise RuntimeError("Windows access lists are only available on Windows")
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = advapi32.GetNamedSecurityInfoW
    get_info.argtypes = [ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint32] + [
        ctypes.c_void_p
    ] * 5
    get_info.restype = ctypes.c_uint32
    get_control = advapi32.GetSecurityDescriptorControl
    get_control.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    get_control.restype = ctypes.c_int
    acl_information = advapi32.GetAclInformation
    acl_information.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    acl_information.restype = ctypes.c_int
    get_ace = advapi32.GetAce
    get_ace.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    get_ace.restype = ctypes.c_int
    sid_to_string = advapi32.ConvertSidToStringSidW
    sid_to_string.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    sid_to_string.restype = ctypes.c_int
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p

    def sid_text(sid: int | None) -> str:
        text = ctypes.c_void_p()
        if not sid or not sid_to_string(sid, ctypes.byref(text)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.wstring_at(text.value)
        finally:
            local_free(text)

    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    status = get_info(
        str(path),
        1,
        0x1 | 0x4,
        ctypes.byref(owner),
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if status != 0:
        raise ctypes.WinError(status)
    try:
        control = ctypes.c_uint16()
        revision = ctypes.c_uint32()
        if not get_control(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise ctypes.WinError(ctypes.get_last_error())
        assert dacl.value, "a NULL DACL grants everyone access"
        size = (ctypes.c_uint32 * 3)()  # AceCount, AclBytesInUse, AclBytesFree
        if not acl_information(dacl, size, ctypes.sizeof(size), 2):
            raise ctypes.WinError(ctypes.get_last_error())
        entries: list[tuple[int, int, int, str]] = []
        for index in range(size[0]):
            ace = ctypes.c_void_p()
            if not get_ace(dacl, index, ctypes.byref(ace)):
                raise ctypes.WinError(ctypes.get_last_error())
            assert ace.value is not None
            header = ctypes.string_at(ace.value, 8)  # type, flags, size, mask
            entries.append(
                (
                    header[0],
                    header[1],
                    int.from_bytes(header[4:8], "little"),
                    sid_text(ace.value + 8),  # SID follows a basic ACE's mask
                )
            )
        return sid_text(owner.value), bool(control.value & 0x1000), entries
    finally:
        local_free(descriptor)


def assert_private_access(path: Path) -> None:
    """The file is owned by the token user with a protected, exact three-entry list."""
    owner, protected, entries = _binary_access(path)
    assert owner == token_user_sid(), owner
    assert protected, "DACL is not protected"
    assert sorted(sid for *_, sid in entries) == sorted(
        [token_user_sid(), SYSTEM_SID, ADMINISTRATORS_SID]
    ), entries
    assert all(kind == 0 and mask in FULL_CONTROL for kind, _, mask, _ in entries), (
        entries
    )
