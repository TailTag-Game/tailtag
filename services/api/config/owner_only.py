"""Owner-only file access for local files that hold Staging secrets or bindings.

The operator tooling and the simulator keep identical copies of this module
(a test compares them byte for byte). Standard library only.

POSIX accepts a folder that is a real directory, owned by the current user,
with mode 0o700, and a file that is a regular, non-symlink file owned by the
current user with mode 0o600. Windows accepts the same shape expressed as
owner SID, access list, and reparse points: the owner is the current user, and
every allow entry names the current user, SYSTEM, or Administrators (see the
"Windows owner-only rule" in
docs/specs/2026-10-15-windows-owner-only-files-and-process-trees.md).

Every refusal is one ``OwnerOnlyError`` that carries no path and no detail.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import BinaryIO

if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

__all__ = ["OwnerOnlyError", "create_private_file", "open_owner_only_file"]

if sys.platform == "win32":
    _FAILURES = (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        OverflowError,
        ctypes.ArgumentError,
    )
else:
    _FAILURES = (OSError, ValueError)


class OwnerOnlyError(OSError):
    """A file or folder is not private to its owner, or a private file could not be made."""


def open_owner_only_file(path: Path, *, max_bytes: int) -> BinaryIO:
    """Open ``path`` for reading as bytes, only if it and its folder are owner-only.

    Every check runs on the objects that are then read, so the bytes returned
    are the bytes of the object that was checked. Callers decode the bytes
    themselves.
    """
    try:
        if sys.platform == "win32":
            return _open_windows(path, max_bytes)
        return _open_posix(path, max_bytes)
    except _FAILURES:
        raise OwnerOnlyError from None


def create_private_file(path: Path) -> int:
    """Create a new owner-only file and return a writable descriptor for it.

    The name must not exist: an existing file, symlink, or dangling link is
    refused rather than followed or reused.
    """
    try:
        if sys.platform == "win32":
            return _create_windows(path)
        return os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
    except _FAILURES:
        raise OwnerOnlyError from None


def _open_posix(path: Path, max_bytes: int) -> BinaryIO:
    parent = path.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise OwnerOnlyError
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > max_bytes
        ):
            raise OwnerOnlyError
        stream = os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise
    return stream


if sys.platform == "win32":
    # Win32 values, named as in the Windows SDK headers.
    _READ_CONTROL = 0x00020000
    _FILE_READ_ATTRIBUTES = 0x80
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_ALL_ACCESS = 0x001F01FF
    _FILE_SHARE_READ = 0x1
    _FILE_SHARE_WRITE = 0x2
    _CREATE_NEW = 1
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x80
    _FILE_ATTRIBUTE_DIRECTORY = 0x10
    _FILE_ATTRIBUTE_REPARSE_POINT = 0x400
    _FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    _FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    _FILE_TYPE_DISK = 1
    _TOKEN_QUERY = 0x8
    _TOKEN_USER = 1
    _SE_FILE_OBJECT = 1
    _OWNER_SECURITY_INFORMATION = 0x1
    _DACL_SECURITY_INFORMATION = 0x4
    _SE_DACL_PRESENT = 0x4
    _SE_DACL_PROTECTED = 0x1000
    _ACL_REVISION = 2
    _ACL_SIZE_INFORMATION = 2
    _ACL_HEADER_SIZE = 8
    _ACE_HEADER_AND_MASK_SIZE = 8
    _ACCESS_ALLOWED_ACE_TYPE = 0
    _ACCESS_DENIED_ACE_TYPE = 1
    _MINIMUM_SID_SIZE = 8
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    def _sid(authority: int, *subauthorities: int) -> bytes:
        """Build the binary form of S-1-<authority>-<subauthorities...>."""
        return (
            bytes([1, len(subauthorities)])
            + authority.to_bytes(6, "big")
            + b"".join(value.to_bytes(4, "little") for value in subauthorities)
        )

    _SYSTEM_SID = _sid(5, 18)
    _ADMINISTRATORS_SID = _sid(5, 32, 544)

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", wintypes.BOOL),
        ]

    class _FileInformation(ctypes.Structure):
        """BY_HANDLE_FILE_INFORMATION."""

        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    class _AclSizeInformation(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    class _AceHeader(ctypes.Structure):
        _fields_ = [
            ("AceType", ctypes.c_ubyte),
            ("AceFlags", ctypes.c_ubyte),
            ("AceSize", wintypes.WORD),
        ]

    def _declare(library: ctypes.WinDLL, name: str, restype: object, *argtypes: object):
        """Return a Win32 function with its prototype set; no function is called untyped."""
        function = getattr(library, name)
        function.argtypes = list(argtypes)
        function.restype = restype
        return function

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _pointer = ctypes.c_void_p
    _dword = wintypes.DWORD

    _create_file = _declare(
        _kernel32,
        "CreateFileW",
        _pointer,
        wintypes.LPCWSTR,
        _dword,
        _dword,
        _pointer,
        _dword,
        _dword,
        _pointer,
    )
    _close_handle = _declare(_kernel32, "CloseHandle", wintypes.BOOL, _pointer)
    _delete_file = _declare(_kernel32, "DeleteFileW", wintypes.BOOL, wintypes.LPCWSTR)
    _get_file_type = _declare(_kernel32, "GetFileType", _dword, _pointer)
    _get_file_information = _declare(
        _kernel32, "GetFileInformationByHandle", wintypes.BOOL, _pointer, _pointer
    )
    _get_current_process = _declare(_kernel32, "GetCurrentProcess", _pointer)
    _local_free = _declare(_kernel32, "LocalFree", _pointer, _pointer)
    _open_process_token = _declare(
        _advapi32, "OpenProcessToken", wintypes.BOOL, _pointer, _dword, _pointer
    )
    _get_token_information = _declare(
        _advapi32,
        "GetTokenInformation",
        wintypes.BOOL,
        _pointer,
        ctypes.c_int,
        _pointer,
        _dword,
        _pointer,
    )
    _get_security_info = _declare(
        _advapi32,
        "GetSecurityInfo",
        _dword,
        _pointer,
        ctypes.c_int,
        _dword,
        _pointer,
        _pointer,
        _pointer,
        _pointer,
        _pointer,
    )
    _get_descriptor_control = _declare(
        _advapi32,
        "GetSecurityDescriptorControl",
        wintypes.BOOL,
        _pointer,
        _pointer,
        _pointer,
    )
    _get_acl_information = _declare(
        _advapi32,
        "GetAclInformation",
        wintypes.BOOL,
        _pointer,
        _pointer,
        _dword,
        ctypes.c_int,
    )
    _get_ace = _declare(_advapi32, "GetAce", wintypes.BOOL, _pointer, _dword, _pointer)
    _is_valid_sid = _declare(_advapi32, "IsValidSid", wintypes.BOOL, _pointer)
    _get_length_sid = _declare(_advapi32, "GetLengthSid", _dword, _pointer)
    _initialize_acl = _declare(
        _advapi32, "InitializeAcl", wintypes.BOOL, _pointer, _dword, _dword
    )
    _add_access_allowed_ace = _declare(
        _advapi32,
        "AddAccessAllowedAce",
        wintypes.BOOL,
        _pointer,
        _dword,
        _dword,
        _pointer,
    )
    _initialize_descriptor = _declare(
        _advapi32, "InitializeSecurityDescriptor", wintypes.BOOL, _pointer, _dword
    )
    _set_descriptor_owner = _declare(
        _advapi32,
        "SetSecurityDescriptorOwner",
        wintypes.BOOL,
        _pointer,
        _pointer,
        wintypes.BOOL,
    )
    _set_descriptor_dacl = _declare(
        _advapi32,
        "SetSecurityDescriptorDacl",
        wintypes.BOOL,
        _pointer,
        wintypes.BOOL,
        _pointer,
        wintypes.BOOL,
    )
    _set_descriptor_control = _declare(
        _advapi32,
        "SetSecurityDescriptorControl",
        wintypes.BOOL,
        _pointer,
        wintypes.WORD,
        wintypes.WORD,
    )

    def _ok(result: int | None) -> int:
        """Return a Win32 result, raising the last error when it is zero."""
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def _valid_handle(handle: int | None) -> int:
        """Return a handle from CreateFileW, raising the last error when it is invalid."""
        if handle is None or handle == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def _sid_buffer(sid: bytes):
        return (ctypes.c_char * len(sid)).from_buffer_copy(sid)

    def _sid_bytes(pointer: int | None) -> bytes:
        """Copy a validated SID out of memory the system owns."""
        if not pointer:
            raise OwnerOnlyError
        _ok(_is_valid_sid(pointer))
        return ctypes.string_at(pointer, _get_length_sid(pointer))

    def _token_user_sid() -> bytes:
        """Return the SID of the current process token's user."""
        token = ctypes.c_void_p()
        _ok(
            _open_process_token(
                _get_current_process(), _TOKEN_QUERY, ctypes.byref(token)
            )
        )
        try:
            buffer = ctypes.create_string_buffer(1024)
            size = wintypes.DWORD()
            _ok(
                _get_token_information(
                    token, _TOKEN_USER, buffer, len(buffer), ctypes.byref(size)
                )
            )
            # TOKEN_USER starts with the SID pointer; the SID itself lies in `buffer`.
            return _sid_bytes(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])
        finally:
            _close_handle(token)

    def _read_security(handle: int) -> tuple[bytes, int, list[tuple[int, bytes]]]:
        """Read owner, control bits, and (type, SID) for every entry of a handle's DACL.

        Anything that is not a well-formed list of basic allow and deny entries
        is refused here, before an entry's SID is trusted.
        """
        owner = ctypes.c_void_p()
        dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        status = _get_security_info(
            handle,
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION | _DACL_SECURITY_INFORMATION,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if status:
            raise ctypes.WinError(status)
        try:
            control = wintypes.WORD()
            revision = wintypes.DWORD()
            _ok(
                _get_descriptor_control(
                    descriptor, ctypes.byref(control), ctypes.byref(revision)
                )
            )
            # A missing or NULL DACL grants everyone full access.
            if not control.value & _SE_DACL_PRESENT or not dacl.value:
                raise OwnerOnlyError
            owner_sid = _sid_bytes(owner.value)
            entries = _read_entries(dacl.value)
        finally:
            _local_free(descriptor)
        return owner_sid, control.value, entries

    def _read_entries(acl: int) -> list[tuple[int, bytes]]:
        information = _AclSizeInformation()
        _ok(
            _get_acl_information(
                acl,
                ctypes.byref(information),
                ctypes.sizeof(information),
                _ACL_SIZE_INFORMATION,
            )
        )
        entries: list[tuple[int, bytes]] = []
        for index in range(information.AceCount):
            pointer = ctypes.c_void_p()
            _ok(_get_ace(acl, index, ctypes.byref(pointer)))
            address = pointer.value
            if address is None:
                raise OwnerOnlyError
            header = _AceHeader.from_address(address)
            offset = address - acl
            if (
                header.AceType
                not in (_ACCESS_ALLOWED_ACE_TYPE, _ACCESS_DENIED_ACE_TYPE)
                or header.AceSize < _ACE_HEADER_AND_MASK_SIZE + _MINIMUM_SID_SIZE
                or offset < _ACL_HEADER_SIZE
                or offset + header.AceSize > information.AclBytesInUse
            ):
                raise OwnerOnlyError
            # Both basic entry types are a header, a 4-byte mask, then the SID.
            raw = ctypes.string_at(address, header.AceSize)
            area = (
                ctypes.c_char * (len(raw) - _ACE_HEADER_AND_MASK_SIZE)
            ).from_buffer_copy(raw, _ACE_HEADER_AND_MASK_SIZE)
            _ok(_is_valid_sid(area))
            length = _get_length_sid(area)
            if length > len(area):
                raise OwnerOnlyError
            entries.append((header.AceType, area.raw[:length]))
        return entries

    def _check_owner_and_entries(
        token_sid: bytes, owner: bytes, entries: list[tuple[int, bytes]]
    ) -> None:
        allowed = (token_sid, _SYSTEM_SID, _ADMINISTRATORS_SID)
        if owner != token_sid:
            raise OwnerOnlyError
        # Deny entries only remove access; every allow entry must be an allowed SID.
        for ace_type, sid in entries:
            if ace_type == _ACCESS_ALLOWED_ACE_TYPE and sid not in allowed:
                raise OwnerOnlyError

    def _open_handle(path: Path, access: int, share: int, flags: int) -> int:
        return _valid_handle(
            _create_file(
                os.fspath(path),
                access,
                share,
                None,
                _OPEN_EXISTING,
                flags | _FILE_FLAG_OPEN_REPARSE_POINT,
                None,
            )
        )

    def _verify(
        handle: int, token_sid: bytes, *, directory: bool, max_bytes: int = 0
    ) -> None:
        """Apply the type, owner, access list, and size checks to one open handle.

        ``max_bytes`` applies to files only.
        """
        information = _FileInformation()
        _ok(_get_file_information(handle, ctypes.byref(information)))
        attributes = information.dwFileAttributes
        if (
            attributes & _FILE_ATTRIBUTE_REPARSE_POINT
            or bool(attributes & _FILE_ATTRIBUTE_DIRECTORY) != directory
        ):
            raise OwnerOnlyError
        if not directory:
            size = (information.nFileSizeHigh << 32) | information.nFileSizeLow
            if _get_file_type(handle) != _FILE_TYPE_DISK or size > max_bytes:
                raise OwnerOnlyError
        owner, _, entries = _read_security(handle)
        _check_owner_and_entries(token_sid, owner, entries)

    def _open_windows(path: Path, max_bytes: int) -> BinaryIO:
        token_sid = _token_user_sid()
        # Holding the folder without FILE_SHARE_DELETE keeps it from being renamed
        # or deleted until the file has been opened and checked.
        parent = _open_handle(
            path.parent,
            _READ_CONTROL | _FILE_READ_ATTRIBUTES,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            _FILE_FLAG_BACKUP_SEMANTICS,
        )
        try:
            _verify(parent, token_sid, directory=True)
            handle = _open_handle(
                path, _GENERIC_READ | _READ_CONTROL, _FILE_SHARE_READ, 0
            )
            try:
                _verify(handle, token_sid, directory=False, max_bytes=max_bytes)
                descriptor = msvcrt.open_osfhandle(
                    handle, os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT
                )
            except BaseException:
                _close_handle(handle)
                raise
        finally:
            _close_handle(parent)
        try:
            return os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise

    def _create_windows(path: Path) -> int:
        token_sid = _token_user_sid()
        sids = [
            _sid_buffer(sid) for sid in (token_sid, _SYSTEM_SID, _ADMINISTRATORS_SID)
        ]
        acl = ctypes.create_string_buffer(
            _ACL_HEADER_SIZE + sum(_ACE_HEADER_AND_MASK_SIZE + len(sid) for sid in sids)
        )
        _ok(_initialize_acl(acl, len(acl), _ACL_REVISION))
        for sid in sids:
            _ok(_add_access_allowed_ace(acl, _ACL_REVISION, _FILE_ALL_ACCESS, sid))
        # An absolute descriptor: the user as owner and a protected DACL (no inheritance).
        descriptor = ctypes.create_string_buffer(64)  # SECURITY_DESCRIPTOR is 40 bytes
        _ok(_initialize_descriptor(descriptor, 1))
        _ok(_set_descriptor_owner(descriptor, sids[0], False))
        _ok(_set_descriptor_dacl(descriptor, True, acl, False))
        _ok(_set_descriptor_control(descriptor, _SE_DACL_PROTECTED, _SE_DACL_PROTECTED))
        attributes = _SecurityAttributes(
            ctypes.sizeof(_SecurityAttributes), ctypes.addressof(descriptor), False
        )
        handle = _valid_handle(
            _create_file(
                os.fspath(path),
                _GENERIC_WRITE | _READ_CONTROL,
                0,
                ctypes.byref(attributes),
                _CREATE_NEW,
                _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
                None,
            )
        )
        try:
            # A file system without security support ignores the descriptor above,
            # so read the owner and DACL back instead of trusting the request.
            owner, control, entries = _read_security(handle)
            _check_owner_and_entries(token_sid, owner, entries)
            if not control & _SE_DACL_PROTECTED:
                raise OwnerOnlyError
            return msvcrt.open_osfhandle(
                handle, os.O_WRONLY | os.O_BINARY | os.O_NOINHERIT
            )
        except BaseException:
            _close_handle(handle)
            _delete_file(os.fspath(path))
            raise
