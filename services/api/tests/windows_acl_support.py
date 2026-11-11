"""Windows access-list fixtures and an independent reader for owner-only tests.

Every function raises on non-Windows platforms; ctypes is touched only inside
functions so the module imports (and type-checks) everywhere. Fixtures set the
owner explicitly to the process token's user SID, because an elevated token may
default new objects to an Administrators owner.
"""

from __future__ import annotations

import csv
import ctypes
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

SYSTEM_SID = "S-1-5-18"
ADMINISTRATORS_SID = "S-1-5-32-544"

_SE_FILE_OBJECT = 1
_OWNER_INFORMATION = 0x1
_DACL_INFORMATION = 0x4
_PROTECTED_DACL_INFORMATION = 0x80000000


@dataclass(frozen=True)
class Ace:
    kind: str
    flags: str
    rights: str
    sid: str


@dataclass(frozen=True)
class Access:
    owner: str
    protected: bool
    entries: tuple[Ace, ...]


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Windows access lists are only available on Windows")


def token_user_sid() -> str:
    """Return the current user's SID, from a system tool independent of the code under test."""
    _require_windows()
    output = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return next(csv.reader([output.strip()]))[1]


def apply_security(path: Path, sddl: str) -> None:
    """Apply an SDDL owner and a protected DACL (or NULL DACL) to a file or folder."""
    if sys.platform != "win32":
        raise RuntimeError("Windows access lists are only available on Windows")
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    convert = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    convert.restype = ctypes.c_int
    get_owner = advapi32.GetSecurityDescriptorOwner
    get_owner.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    get_owner.restype = ctypes.c_int
    get_dacl = advapi32.GetSecurityDescriptorDacl
    get_dacl.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    get_dacl.restype = ctypes.c_int
    set_info = advapi32.SetNamedSecurityInfoW
    set_info.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    set_info.restype = ctypes.c_uint32
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p

    descriptor = ctypes.c_void_p()
    if not convert(sddl, 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        owner = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        present = ctypes.c_int()
        defaulted = ctypes.c_int()
        if not get_owner(descriptor, ctypes.byref(owner), ctypes.byref(defaulted)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not get_dacl(
            descriptor,
            ctypes.byref(present),
            ctypes.byref(dacl),
            ctypes.byref(defaulted),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        status = set_info(
            str(path),
            _SE_FILE_OBJECT,
            _OWNER_INFORMATION | _DACL_INFORMATION | _PROTECTED_DACL_INFORMATION,
            owner,
            None,
            dacl,
            None,
        )
        if status != 0:
            raise ctypes.WinError(status)
    finally:
        local_free(descriptor)


def make_owner_only(
    path: Path,
    *,
    container: bool = False,
    owner: str | None = None,
    leading_aces: str = "",
    extra_aces: str = "",
) -> None:
    """Give an object the exact allowed set, protected, with an explicit owner."""
    sid = token_user_sid()
    inherit = "OICI" if container else ""
    allowed = "".join(f"(A;{inherit};FA;;;{who})" for who in (sid, "SY", "BA"))
    apply_security(path, f"O:{owner or sid}D:P{leading_aces}{allowed}{extra_aces}")


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


def read_access(path: Path) -> Access:
    """Read owner, protection, and entries back, independent of the code under test."""
    owner, protected, raw = _binary_access(path)
    kinds = {0: "A", 1: "D"}
    return Access(
        owner,
        protected,
        tuple(
            Ace(kinds.get(kind, f"type-{kind}"), f"0x{flags:x}", f"0x{mask:x}", sid)
            for kind, flags, mask, sid in raw
        ),
    )


def make_junction(link: Path, target: Path) -> None:
    """Create a directory junction; it needs no privilege."""
    _require_windows()
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        check=True,
        capture_output=True,
    )


def require_symlinks(scratch: Path) -> None:
    """Skip the calling test when this account cannot create symlinks."""
    _require_windows()
    probe = scratch / ".symlink-probe"
    try:
        os.symlink(scratch, probe, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks needs an elevated Windows account")
    probe.rmdir()


def protect_tree(*paths: Path) -> None:
    """Make each existing path owner-only; a directory also gets inheritable entries."""
    for path in paths:
        make_owner_only(path, container=path.is_dir())
