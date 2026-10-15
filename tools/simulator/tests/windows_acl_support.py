"""Independent Windows access-list reader for simulator privacy assertions.

A deliberately small copy of the reader in services/api/tests/windows_acl_support.py:
the two uv projects cannot share test code. It reads owner, protection and
entries back as SDDL so assertions do not depend on the code under test.
"""

import csv
import ctypes
import re
import subprocess
import sys
from pathlib import Path

ALIASES = {"SY": "S-1-5-18", "BA": "S-1-5-32-544"}
SYSTEM_SID = "S-1-5-18"
ADMINISTRATORS_SID = "S-1-5-32-544"
FULL_CONTROL = {"FA", "GA", "0x1f01ff"}


def token_user_sid() -> str:
    output = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return next(csv.reader([output.strip()]))[1]


def _read_sddl(path: Path) -> str:
    if sys.platform != "win32":
        raise RuntimeError("Windows access lists are only available on Windows")
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = advapi32.GetNamedSecurityInfoW
    get_info.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    get_info.restype = ctypes.c_uint32
    to_string = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW
    to_string.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    to_string.restype = ctypes.c_int
    local_free = kernel32.LocalFree
    local_free.argtypes = [ctypes.c_void_p]
    local_free.restype = ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    status = get_info(
        str(path), 1, 0x1 | 0x4, None, None, None, None, ctypes.byref(descriptor)
    )
    if status != 0:
        raise ctypes.WinError(status)
    try:
        text = ctypes.c_void_p()
        if not to_string(descriptor, 1, 0x1 | 0x4, ctypes.byref(text), None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return ctypes.wstring_at(text.value)
        finally:
            local_free(text)
    finally:
        local_free(descriptor)


def assert_private_access(path: Path) -> None:
    """The file is owned by the token user with a protected, exact three-entry list."""
    sddl = _read_sddl(path)
    owner = re.search(r"O:(S-[0-9-]+|[A-Z]{2})", sddl)
    dacl = re.search(r"D:([A-Z]*)((?:\(.*\))*)", sddl)
    assert owner is not None and dacl is not None, sddl
    entries = re.findall(
        r"\(([^;()]*);([^;()]*);([^;()]*);([^;()]*);([^;()]*);([^;()]*)",
        dacl.group(2),
    )
    sids = [ALIASES.get(str(sid), str(sid)) for *_, sid in entries]
    assert ALIASES.get(owner.group(1), owner.group(1)) == token_user_sid(), sddl
    assert "P" in dacl.group(1), f"DACL is not protected: {sddl}"
    assert sorted(sids) == sorted([token_user_sid(), SYSTEM_SID, ADMINISTRATORS_SID]), (
        sddl
    )
    assert all(
        kind == "A" and rights in FULL_CONTROL for kind, _, rights, *_ in entries
    )
