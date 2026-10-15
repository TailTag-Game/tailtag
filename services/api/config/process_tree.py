"""Start a child so that it and everything it starts can be stopped together.

The operator tooling and the simulator keep identical copies of this module
(a test compares them byte for byte). Standard library only.

POSIX starts the child in its own session and signals the process group.
Windows starts the child suspended in a new process group, puts it in a Job
Object that kills its members when the job closes, and only then lets it run,
so no descendant can exist outside the job (see "Process trees" in
docs/specs/2026-10-15-windows-owner-only-files-and-process-trees.md).

Usage, with no ``await`` between the spawn and ``attach``::

    process = await asyncio.create_subprocess_exec(*argv, **spawn_options())
    tree = ProcessTree()
    tree.attach(process.pid)
    try:
        ...
    finally:
        tree.kill()
        await process.wait()
        tree.close()
"""

from __future__ import annotations

import contextlib
import os
import signal
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

__all__ = ["ProcessTree", "spawn_options"]


def spawn_options() -> dict[str, object]:
    """Return keyword arguments for ``subprocess.Popen`` or ``asyncio.create_subprocess_exec``."""
    if sys.platform == "win32":
        # CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP
        return {"creationflags": 0x00000004 | 0x00000200}
    return {"start_new_session": True}


class ProcessTree:
    """The group of processes started from one child, stopped together."""

    def __init__(self) -> None:
        self._pid: int | None = None
        self._job: int | None = None

    def attach(self, pid: int) -> None:
        """Contain the freshly spawned child ``pid``; on Windows, let it run afterwards.

        Raises ``OSError`` after terminating the child when it cannot be contained.
        """
        if sys.platform == "win32":
            self._job = _attach_to_new_job(pid)
        else:
            self._pid = pid

    def terminate(self) -> None:
        """Ask the tree to stop; Windows has no graceful group signal, so it stops it."""
        if sys.platform == "win32":
            self._terminate_job()
        else:
            self._signal_group(signal.SIGTERM)

    def kill(self) -> None:
        """Stop the whole tree now. Quiet when the tree has already ended."""
        if sys.platform == "win32":
            self._terminate_job()
        else:
            self._signal_group(signal.SIGKILL)

    def close(self) -> None:
        """Release the tree; on Windows, closing the job also kills any survivor."""
        if sys.platform == "win32" and self._job is not None:
            job, self._job = self._job, None
            _close_handle(job)

    def _signal_group(self, number: signal.Signals) -> None:
        if self._pid is not None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._pid, number)

    def _terminate_job(self) -> None:
        if sys.platform == "win32" and self._job is not None:
            # Fails when the job is already empty, which is the goal state.
            _terminate_job_object(self._job, 1)


if sys.platform == "win32":
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100
    _THREAD_SUSPEND_RESUME = 0x0002
    _THREAD_QUERY_LIMITED_INFORMATION = 0x0800
    _TH32CS_SNAPTHREAD = 0x00000004
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _ERROR_NO_MORE_FILES = 18
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class _BasicLimitInformation(ctypes.Structure):
        """JOBOBJECT_BASIC_LIMIT_INFORMATION."""

        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        """JOBOBJECT_EXTENDED_LIMIT_INFORMATION (IO_COUNTERS is six 64-bit counters)."""

        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", ctypes.c_uint64 * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _ThreadEntry(ctypes.Structure):
        """THREADENTRY32."""

        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    def _declare(library: ctypes.WinDLL, name: str, restype: object, *argtypes: object):
        """Return a Win32 function with its prototype set; no function is called untyped."""
        function = getattr(library, name)
        function.argtypes = list(argtypes)
        function.restype = restype
        return function

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _pointer = ctypes.c_void_p
    _dword = wintypes.DWORD

    _create_job_object = _declare(
        _kernel32, "CreateJobObjectW", _pointer, _pointer, wintypes.LPCWSTR
    )
    _set_job_information = _declare(
        _kernel32,
        "SetInformationJobObject",
        wintypes.BOOL,
        _pointer,
        ctypes.c_int,
        _pointer,
        _dword,
    )
    _assign_process = _declare(
        _kernel32, "AssignProcessToJobObject", wintypes.BOOL, _pointer, _pointer
    )
    _terminate_job_object = _declare(
        _kernel32, "TerminateJobObject", wintypes.BOOL, _pointer, wintypes.UINT
    )
    _terminate_process = _declare(
        _kernel32, "TerminateProcess", wintypes.BOOL, _pointer, wintypes.UINT
    )
    _open_process = _declare(
        _kernel32, "OpenProcess", _pointer, _dword, wintypes.BOOL, _dword
    )
    _open_thread = _declare(
        _kernel32, "OpenThread", _pointer, _dword, wintypes.BOOL, _dword
    )
    _get_process_id_of_thread = _declare(
        _kernel32, "GetProcessIdOfThread", _dword, _pointer
    )
    _resume_thread = _declare(_kernel32, "ResumeThread", _dword, _pointer)
    _create_snapshot = _declare(
        _kernel32, "CreateToolhelp32Snapshot", _pointer, _dword, _dword
    )
    _thread_first = _declare(
        _kernel32, "Thread32First", wintypes.BOOL, _pointer, _pointer
    )
    _thread_next = _declare(
        _kernel32, "Thread32Next", wintypes.BOOL, _pointer, _pointer
    )
    _close_handle = _declare(_kernel32, "CloseHandle", wintypes.BOOL, _pointer)

    def _ok(result: int | None) -> int:
        """Return a Win32 result, raising the last error when it is zero."""
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    def _valid_handle(handle: int | None) -> int:
        """Return a handle, raising the last error when the call returned none."""
        if handle is None or handle == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def _new_job() -> int:
        """Create a job that kills its members on close and allows no breakaway."""
        # NULL security attributes make the handle non-inheritable.
        job = _valid_handle(_create_job_object(None, None))
        try:
            limits = _ExtendedLimitInformation()
            limits.BasicLimitInformation.LimitFlags = (
                _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            _ok(
                _set_job_information(
                    job,
                    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                    ctypes.byref(limits),
                    ctypes.sizeof(limits),
                )
            )
        except BaseException:
            _close_handle(job)
            raise
        return job

    def _only_thread_of(pid: int) -> int:
        """Return the id of the one thread that process ``pid`` owns, or raise."""
        snapshot = _valid_handle(_create_snapshot(_TH32CS_SNAPTHREAD, 0))
        try:
            entry = _ThreadEntry()
            entry.dwSize = ctypes.sizeof(entry)
            threads: list[int] = []
            found = _thread_first(snapshot, ctypes.byref(entry))
            while found:
                if entry.th32OwnerProcessID == pid:
                    threads.append(entry.th32ThreadID)
                found = _thread_next(snapshot, ctypes.byref(entry))
            if ctypes.get_last_error() != _ERROR_NO_MORE_FILES:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _close_handle(snapshot)
        if len(threads) != 1:
            raise OSError("the suspended child does not have exactly one thread")
        return threads[0]

    def _resume_only_thread(pid: int) -> None:
        thread = _valid_handle(
            _open_thread(
                _THREAD_SUSPEND_RESUME | _THREAD_QUERY_LIMITED_INFORMATION,
                False,
                _only_thread_of(pid),
            )
        )
        try:
            if _get_process_id_of_thread(thread) != pid:
                raise OSError("the child thread belongs to another process")
            # A fresh CREATE_SUSPENDED thread has a suspend count of exactly 1.
            if _resume_thread(thread) != 1:
                raise OSError("the child thread was not suspended exactly once")
        finally:
            _close_handle(thread)

    def _attach_to_new_job(pid: int) -> int:
        """Put the suspended child ``pid`` in a new job, then resume it."""
        job = _new_job()
        process: int | None = None
        try:
            process = _valid_handle(
                _open_process(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
            )
            _ok(_assign_process(job, process))
            _resume_only_thread(pid)
        except BaseException as error:
            if process is not None:
                _terminate_process(process, 1)
            _close_handle(job)
            if isinstance(error, Exception) and not isinstance(error, OSError):
                raise OSError("could not contain the child in a job object") from error
            raise
        finally:
            if process is not None:
                _close_handle(process)
        return job
