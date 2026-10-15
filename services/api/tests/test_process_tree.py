"""Behavioral contract for launcher process trees (issue #315, slice 3).

Replaces ``start_new_session`` plus ``os.killpg``. Spec references are to
docs/specs/2026-10-15-windows-owner-only-files-and-process-trees.md, "Process trees".
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import subprocess
import sys
import threading
import time
from typing import IO, Any, Final, cast

import pytest

from config.process_tree import ProcessTree, spawn_options

WIN: Final = sys.platform == "win32"
windows_only = pytest.mark.skipif(not WIN, reason="Windows job objects")

# A child that starts a grandchild sharing its stdout pipe, then reports the
# grandchild's pid. A pipe that reaches EOF proves no descendant survived.
CHILD: Final = (
    "import subprocess, sys, time\n"
    "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
    "print(grandchild.pid, flush=True)\n"
    "time.sleep(600)\n"
)

# The child first moves itself into an inner job that permits silent
# breakaway, so its grandchild is created outside that inner job.
INNER_JOB_CHILD: Final = (
    "import ctypes, subprocess, sys, time\n"
    "from ctypes import wintypes\n"
    "k = ctypes.WinDLL('kernel32', use_last_error=True)\n"
    "class Basic(ctypes.Structure):\n"
    "    _fields_ = [('a', ctypes.c_int64), ('b', ctypes.c_int64),\n"
    "                ('LimitFlags', wintypes.DWORD), ('c', ctypes.c_size_t),\n"
    "                ('d', ctypes.c_size_t), ('e', wintypes.DWORD),\n"
    "                ('f', ctypes.c_size_t), ('g', wintypes.DWORD),\n"
    "                ('h', wintypes.DWORD)]\n"
    "k.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]\n"
    "k.CreateJobObjectW.restype = wintypes.HANDLE\n"
    "k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,\n"
    "                                      ctypes.c_void_p, wintypes.DWORD]\n"
    "k.SetInformationJobObject.restype = wintypes.BOOL\n"
    "k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]\n"
    "k.AssignProcessToJobObject.restype = wintypes.BOOL\n"
    "k.GetCurrentProcess.restype = wintypes.HANDLE\n"
    "job = k.CreateJobObjectW(None, None)\n"
    "info = Basic()\n"
    "info.LimitFlags = 0x1000  # JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK\n"
    "ok = k.SetInformationJobObject(job, 2, ctypes.byref(info), ctypes.sizeof(info))\n"
    "ok = ok and k.AssignProcessToJobObject(job, k.GetCurrentProcess())\n"
    "if not ok:\n"
    "    print('ERR', ctypes.get_last_error(), flush=True)\n"
    "    sys.exit(3)\n"
    "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])\n"
    "print(grandchild.pid, flush=True)\n"
    "time.sleep(600)\n"
)


def _options() -> dict[str, Any]:
    return dict(spawn_options())


class Watch:
    """Observe one process by identity: a handle on Windows, the pid on POSIX."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.handle: Any = None
        if sys.platform == "win32":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [
                ctypes.c_uint32,
                ctypes.c_int,
                ctypes.c_uint32,
            ]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel32.WaitForSingleObject.restype = ctypes.c_uint32
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            self.kernel32 = kernel32
            self.handle = kernel32.OpenProcess(0x00100000 | 0x1000, 0, pid)

    def gone(self) -> bool:
        if sys.platform == "win32":
            if not self.handle:
                return True
            return self.kernel32.WaitForSingleObject(self.handle, 0) == 0
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return True
        return False

    def wait_gone(self, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while not self.gone():
            assert time.monotonic() < deadline, f"process {self.pid} survived"
            time.sleep(0.05)

    def close(self) -> None:
        if sys.platform == "win32" and self.handle:
            self.kernel32.CloseHandle(self.handle)
            self.handle = None


def _read_pid(stream: IO[bytes]) -> int:
    box: list[bytes] = []
    reader = threading.Thread(target=lambda: box.append(stream.readline()), daemon=True)
    reader.start()
    reader.join(20)
    if not box:
        pytest.fail("child never reported its grandchild (not resumed, or crashed)")
    text = box[0].decode().strip()
    assert text.isdigit(), f"child failed to set up its grandchild: {text!r}"
    return int(text)


def _spawn(script: str) -> subprocess.Popen[bytes]:
    return cast(
        subprocess.Popen[bytes],
        subprocess.Popen(
            [sys.executable, "-c", script], stdout=subprocess.PIPE, **_options()
        ),
    )


def test_spawn_options_keep_children_in_their_own_group() -> None:
    """Process trees: POSIX starts a new session; Windows starts suspended in a new group.

    Catches: dropping CREATE_NEW_PROCESS_GROUP (the terminal's Ctrl+C then
    reaches children), dropping CREATE_SUSPENDED (the child runs before it is
    in the job), or dropping start_new_session (killpg could not target the tree).
    """
    expected: dict[str, object] = (
        {"creationflags": 0x00000004 | 0x00000200}
        if WIN
        else {"start_new_session": True}
    )
    assert spawn_options() == expected


@pytest.mark.parametrize("method", ("terminate", "kill"))
def test_stopping_the_tree_ends_child_and_grandchild(method: str) -> None:
    """S3-4: the launcher chain dies as a tree, on every OS.

    Catches: killing only the direct child (the grandchild survives and keeps
    the stdout pipe open, so communicate() would time out), attach not
    resuming the child, and terminate/kill wired to the wrong operation.
    """
    process = _spawn(CHILD)
    tree = ProcessTree()
    tree.attach(process.pid)
    grandchild: Watch | None = None
    try:
        assert process.stdout is not None
        grandchild = Watch(_read_pid(process.stdout))
        getattr(tree, method)()
        process.communicate(timeout=20)
        grandchild.wait_gone()
        assert process.returncode is not None
    finally:
        tree.kill()
        tree.close()
        if grandchild is not None:
            grandchild.close()
        if process.poll() is None:
            process.kill()


def test_stopping_the_tree_works_for_asyncio_subprocesses() -> None:
    """S3-4: ``asyncio.create_subprocess_exec(**spawn_options())`` is supported.

    Catches: options that only Popen accepts (asyncio must forward
    creationflags or start_new_session), and a Windows child that never
    resumes under the asyncio event loop.
    """

    async def scenario() -> Watch:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-c", CHILD, stdout=subprocess.PIPE, **_options()
        )
        tree = ProcessTree()
        tree.attach(process.pid)
        grandchild: Watch | None = None
        try:
            assert process.stdout is not None
            line = await asyncio.wait_for(process.stdout.readline(), 20)
            grandchild = Watch(int(line))
            tree.kill()
            await asyncio.wait_for(process.communicate(), 20)
            return grandchild
        finally:
            tree.kill()
            tree.close()

    grandchild = asyncio.run(scenario())
    try:
        grandchild.wait_gone()
    finally:
        grandchild.close()


def test_stopping_an_already_finished_tree_is_quiet() -> None:
    """S3-4: cleanup runs ``kill`` after normal exits; it must not raise.

    Catches: ProcessLookupError escaping killpg on POSIX, or a failed
    TerminateJobObject on an empty job escaping on Windows.
    """
    process = _spawn("pass")
    tree = ProcessTree()
    tree.attach(process.pid)
    try:
        process.communicate(timeout=20)
        tree.terminate()
        tree.kill()
    finally:
        tree.close()


@windows_only
def test_closing_the_job_kills_a_surviving_descendant() -> None:
    """Process trees (close): KILL_ON_JOB_CLOSE covers descendants after cleanup.

    Catches: a job created without JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, or a
    close() that leaves the handle (and so the tree) alive.
    """
    process = _spawn(CHILD)
    tree = ProcessTree()
    tree.attach(process.pid)
    grandchild: Watch | None = None
    try:
        assert process.stdout is not None
        grandchild = Watch(_read_pid(process.stdout))
        tree.close()
        process.communicate(timeout=20)
        grandchild.wait_gone()
    finally:
        if grandchild is not None:
            grandchild.close()
        if process.poll() is None:
            process.kill()


@windows_only
def test_a_grandchild_that_breaks_away_from_an_inner_job_is_still_killed() -> None:
    """Process trees (job): the job must not permit breakaway of its own.

    Catches: JOB_OBJECT_LIMIT_BREAKAWAY_OK or SILENT_BREAKAWAY_OK on
    TailTag's job, which would let descendants of an inner job escape the kill.
    """
    process = _spawn(INNER_JOB_CHILD)
    tree = ProcessTree()
    tree.attach(process.pid)
    grandchild: Watch | None = None
    try:
        assert process.stdout is not None
        grandchild = Watch(_read_pid(process.stdout))
        tree.kill()
        process.communicate(timeout=20)
        grandchild.wait_gone()
    finally:
        tree.kill()
        tree.close()
        if grandchild is not None:
            grandchild.close()
        if process.poll() is None:
            process.kill()


@windows_only
def test_attach_to_an_exited_process_fails_closed() -> None:
    """Process trees (attach): if the child cannot be put in the job, attach raises.

    Catches: attach swallowing an AssignProcessToJobObject or ResumeThread
    failure, which would leave a caller believing the tree is contained.
    """
    process = subprocess.Popen([sys.executable, "-c", "pass"], **_options())
    process.kill()
    process.wait(20)
    tree = ProcessTree()
    try:
        with pytest.raises(Exception):  # noqa: B017 - the spec names no attach error type
            tree.attach(process.pid)
    finally:
        tree.close()
