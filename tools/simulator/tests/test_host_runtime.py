"""#228 U2: owned SSH liveness and monotonic named-child supervision.

SSH/Docker executables are external-boundary substitutes. Unix sockets, clocks'
consumers, subprocess ownership and the signal-receiving Python child are real.
"""

import asyncio
import json
import os
import pty
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, cast

import pytest
from pool_support import POOL
from report_support import read_report
from test_host_artifacts import report_file
from test_host_cli import (
    IMAGE,
    RUN,
    SENTINEL,
    host_manifest,
    journeys_host_manifest,
    packaged_source,
    section,
)
from traffic_support import ManualClock

from tailtag_simulator.host_runner import supervise_run

CID = "1" * 64
FOREIGN_CID = "2" * 64


def executable(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o700)


async def eventually(predicate: Any, message: str, *, seconds: float = 5) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        assert time.monotonic() < deadline, message
        await asyncio.sleep(0.01)


def records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def stop_owned_container_child(root: Path, pid: int | None) -> None:
    """Cleanup still finds this fixture's child if startup failed before ready."""
    registry = root / "container.json"
    if pid is None and registry.exists():
        pid = int(json.loads(registry.read_text())["pid"])
    if pid is not None:
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


@contextmanager
def owned_root() -> Generator[Path]:
    with tempfile.TemporaryDirectory(prefix="t228-", dir="/tmp") as path:
        root = Path(path).resolve()
        root.chmod(0o700)
        yield root


def prepared_skeleton(root: Path, value: dict[str, object]) -> tuple[Path, Path]:
    """Match the private operator preparation/forwarding layout before admission."""
    run_root = root / "runs" / RUN
    rpc, control = run_root / "rpc", run_root / "control"
    for directory in (root / "runs", run_root, rpc, control):
        directory.mkdir(mode=0o700)
    manifest_path = control / "manifest.json"
    manifest_path.write_text(json.dumps(value))
    manifest_path.chmod(0o600)
    # The supervisor reads only health; RPC's real owned filesystem socket
    # represents the separately forwarded listener without simulating gameplay.
    rpc_path = rpc / "rpc.sock"
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(rpc_path))
    rpc_path.chmod(0o600)
    return run_root, control


def first_revocation(state: Path, cause: str) -> float:
    """The operator's bridge evidence records only the first cause of revocation."""
    bridge = json.loads((state / (RUN + ".bridge.json")).read_text())
    revocation = bridge["revocation"]
    assert set(revocation) == {"cause", "offset_seconds"}
    assert revocation["cause"] == cause  # later operator_exit revokes never replace it
    offset = revocation["offset_seconds"]
    assert offset >= 0 and round(offset, 1) == offset
    return cast(float, offset)


def docker_boundary(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stuck: bool,
    client_exit: bool = False,
    report_outcome: str | None = None,
    collision: str | None = None,
    inspect_failure: bool = False,
    startup_gate: bool = False,
    cancel_cleanup_gate: bool = False,
) -> Path:
    """Docker's boundary operates a single real child and a fake immutable image."""
    binary = root / "bin"
    binary.mkdir(mode=0o700)
    source = root / "source"
    provenance = packaged_source(source)
    (root / "image-source.json").write_text(json.dumps(provenance))
    child = root / "python-child.py"
    child.write_text(f"""
import asyncio, json, os, signal, sys, time
from pathlib import Path
from tailtag_simulator.reports import RunReport
from tailtag_simulator.provenance import load_source
from tailtag_simulator.safety import SafetyRuntime
root = Path({str(root)!r})
manifest = json.loads((root / "run-manifest.json").read_text())
report = RunReport(root / "runs" / {RUN!r} / "reports", "convention-baseline",
                   scenario_version=2, seed=-7, config=manifest["configuration"],
                   safety_policy=manifest["safety"], run_id={RUN!r})
report.record_source(load_source(root / "source"))
identity = manifest["backend_identity"]
report.record_target("staging", "https://staging.tailtag.app", identity)
safety = SafetyRuntime(manifest["safety"])
async def verified_target():
    return dict(identity)
safety.bind_probe(verified_target)
asyncio.run(safety.check_target())
report.record_safety(safety.snapshot())
report.begin("provenance"); report.end("provenance", "passed")
report.begin("simulation")
def mark(name, text):
    # Publish markers atomically: the test polls for existence, then reads.
    (root / (name + ".tmp")).write_text(text)
    os.replace(root / (name + ".tmp"), root / name)
def stop(signum, frame):
    mark("child-signal", str(signum))
    if {stuck!r}:
        return
    if {client_exit!r}:
        while not (root / "finalize-child").exists(): time.sleep(0.01)
    report.end("simulation", "interrupted", "FAIL_INTERRUPTED")
    code = report.finish(130)
    (root / "child-finalized").write_text(str(code))
    raise SystemExit(code)
signal.signal(signal.SIGINT, stop)
mark("child-ready", str(os.getpid()))
print({SENTINEL!r}, flush=True)
print({SENTINEL!r}, file=sys.stderr, flush=True)
report_outcome = {report_outcome!r}
if report_outcome is not None:
    if {report_outcome!r} == "missing": report.path.unlink()
    elif {report_outcome!r} == "failed":
        report.end("simulation", "failed", "FAIL_SIMULATION")
        report.finish(1)
    elif {report_outcome!r} == "passed":
        report.path.write_bytes((root / "passed" / {RUN!r} / "snapshot.json").read_bytes())
    (root / "child-finalized").write_text("0")
    raise SystemExit(0)
while True: time.sleep(0.01)
""")
    executable(
        binary / "docker",
        f"""
import json, os, shutil, signal, subprocess, sys, time, uuid
from pathlib import Path
root = Path({str(root)!r})
args = sys.argv[1:]
def publish(name, text):
    # Inspect checks existence, then reads: never expose a partial file.
    (root / (name + ".tmp")).write_text(text)
    os.replace(root / (name + ".tmp"), root / name)
with (root / "docker.jsonl").open("a") as out:
    out.write(json.dumps({{"argv":args,"pid":os.getpid(),"sid":os.getsid(0),"pgid":os.getpgrp()}}) + "\\n")
op = args[0]
collision = {collision!r}
if op == "run" and "tailtag_simulator.provenance" in args:
    assert args[:2] == ["run", "--name"], args
    name = args[2]
    probe_uuid = name.removeprefix("tailtag-sim-source-")
    assert name == "tailtag-sim-source-" + str(uuid.UUID(probe_uuid)), name
    assert args == ["run", "--name", name, "--rm", "--network=none", "--read-only",
                    "--cap-drop=ALL", "--security-opt=no-new-privileges",
                    "--log-driver=none", "--entrypoint", "python", {IMAGE!r},
                    "-m", "tailtag_simulator.provenance", "inspect"], args
    # The verifier executes no workload child. Keep packaged-source validation
    # real and return the existing provenance inspector's complete JSON reply.
    sys.path.insert(0, str(root / "source"))
    from tailtag_simulator.provenance import load_source
    print(json.dumps(load_source(root / "source")))
elif op == "run":
    name = args[args.index("--name") + 1]
    if collision is not None:
        raise SystemExit(125)  # Docker name collision produces no created CID.
    if "--cidfile" in args:
        destination = args[args.index("--cidfile") + 1]
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        with os.fdopen(fd, "w") as out:
            while {startup_gate!r} and not (root / "publish-cid").exists(): time.sleep(0.01)
            out.write({CID!r} + "\\n")
    labels = dict(item.split("=", 1) for i,item in enumerate(args)
                  if i and args[i-1] == "--label")
    proc = subprocess.Popen([{sys.executable!r}, str(root / "python-child.py")],
                            env={{**os.environ, "PYTHONPATH":str(root / "source")}},
                            start_new_session=True)
    publish("container.json", json.dumps({{"name":name,"pid":proc.pid,"labels":labels}}))
    # The container child is outside the host's terminal process group. Docker
    # CLI's real default sigProxy nevertheless forwards received HUP into it.
    def forward_hup(signum, frame):
        if "--sig-proxy=false" not in args:
            (root / "docker-forwarded-hup").touch()
            with suppress(ProcessLookupError): os.kill(proc.pid, signal.SIGHUP)
    from contextlib import suppress
    signal.signal(signal.SIGHUP, forward_hup)
    if {client_exit!r}:
        while not (root / "child-ready").exists() and proc.poll() is None:
            time.sleep(0.01)
        # Losing the attached client does not stop the named container.
        raise SystemExit(1)
    code = proc.wait()
    publish("container-exit", str(code))
    raise SystemExit(code if code >= 0 else 128-code)
elif op == "kill":
    state = json.loads((root / ("foreign.json" if {collision!r} else "container.json")).read_text())
    assert args[-1] in (state["name"], {FOREIGN_CID!r} if {collision!r} else {CID!r}), args
    value = "KILL"
    for i, item in enumerate(args):
        if item in ("--signal", "-s"): value = args[i+1]
        if item.startswith("--signal="): value = item.split("=",1)[1]
    value = value.removeprefix("SIG")
    if {cancel_cleanup_gate!r} and value == "INT" and args[-1] == {CID!r}:
        while not (root / "release-kill").exists(): time.sleep(0.01)
    os.kill(state["pid"], getattr(signal, "SIG" + value))
    print(state["name"])
elif op in ("inspect", "image"):
    ended = (root/"container-exit").exists() or (root/"child-finalized").exists()
    data = {{"Id":{IMAGE!r},"Architecture":"amd64","Os":"linux",
            "Config":{{"User":"1000:1000","Entrypoint":["python","-m","tailtag_simulator"],"Env":[]}},
            "State":{{"Running":not ended,"ExitCode":130 if ended else 0}}}}
    if op == "inspect":
        if {inspect_failure!r}:
            while not (root / "child-ready").exists(): time.sleep(0.01)
            raise SystemExit(1)
        state_path = root / ("foreign.json" if {collision!r} else "container.json")
        if not state_path.exists(): raise SystemExit(1)
        state = json.loads(state_path.read_text())
        data.update(Id={FOREIGN_CID!r} if {collision!r} else {CID!r},
                    Name="/"+state["name"], Image={IMAGE!r})
        data["Config"]["Labels"] = state["labels"]
        data["State"]["ExitCode"] = int((root/"container-exit").read_text()) if (root/"container-exit").exists() else (0 if {report_outcome!r} else (130 if ended else 0))
        if {client_exit!r} and not ended and (root / "child-signal").exists():
            (root / "stopping-inspected").touch()
    print(json.dumps([data]))
elif op == "ps":
    assert args == ["ps", "--all", "--no-trunc", "--quiet", "--filter", "name=^/tailtag-sim-"+{RUN!r}+"$"], args
    print({FOREIGN_CID!r} if {collision!r} == "preexisting" else "")
elif op == "create": print("tailtag-228-extract")
elif op == "cp":
    destination = Path(args[-1])
    if args[-2].endswith("/source.json"):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root/"image-source.json", destination)
    else: shutil.copytree(root/"source", destination, dirs_exist_ok=True)
elif op == "stats": print(json.dumps({{"CPUPerc":"0.00%","MemUsage":"1MiB / 1GiB","MemPerc":"0.10%"}}))
elif op == "wait":
    if {collision!r}: raise SystemExit(1)
    while not (root/"container-exit").exists() and not (root/"child-finalized").exists(): time.sleep(0.01)
    print((root/"container-exit").read_text() if (root/"container-exit").exists() else "130")
elif op == "rm":
    if collision and args[-1] in ({FOREIGN_CID!r}, "tailtag-sim-"+{RUN!r}):
        (root / "foreign-removed").touch()
elif op == "info": print(json.dumps({{"OSType":"linux","Architecture":"x86_64"}}))
else: raise SystemExit("unexpected Docker boundary operation")
""",
    )
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    return root / "docker.jsonl"


@pytest.mark.parametrize(
    "collision",
    [
        "preexisting",
        "race",
        "inspect-failure",
        "startup-signal",
        "startup-cancel",
        "cid-file-fsync-failure",
        "cid-dir-fsync-failure",
    ],
)
def test_container_collision_and_unbound_stop_preserve_foreign_work_and_hold(
    monkeypatch: pytest.MonkeyPatch, collision: str
) -> None:
    async def execute(root: Path) -> None:
        startup = collision in {"startup-signal", "startup-cancel"}
        storage_failure = collision in {
            "cid-file-fsync-failure",
            "cid-dir-fsync-failure",
        }
        record = docker_boundary(
            root,
            monkeypatch,
            stuck=False,
            collision=None
            if collision == "inspect-failure" or startup or storage_failure
            else collision,
            inspect_failure=collision == "inspect-failure",
            startup_gate=startup,
            cancel_cleanup_gate=collision == "startup-cancel",
        )
        value = host_manifest()
        section(value, "release")["dependency_lock_sha256"] = json.loads(
            (root / "image-source.json").read_text()
        )["dependency_lock_sha256"]
        (root / "run-manifest.json").write_text(json.dumps(value))
        release = {
            "schema_version": 1,
            **section(value, "release"),
            "archive_sha256": "e" * 64,
        }
        run_root, control = prepared_skeleton(root, value)
        acquisition = asyncio.Event()
        release_poll = asyncio.Event()

        async def poll_sleep(seconds: float) -> None:
            cidfile = control / "container.cid"
            if startup and cidfile.exists() and cidfile.stat().st_size == 0:
                acquisition.set()
                await release_poll.wait()
            else:
                await asyncio.sleep(seconds)

        async def serve(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                await reader.readline()
                writer.write(json.dumps({"run_id": RUN, "live": True}).encode() + b"\n")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(serve, path=control / "health.sock")
        (control / "health.sock").chmod(0o600)
        foreign = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import signal,sys,time\nfrom pathlib import Path\n"
            "signal.signal(signal.SIGINT, lambda *_: Path(sys.argv[1]).write_text('SIGINT'))\n"
            "Path(sys.argv[2]).touch()\nwhile True: time.sleep(0.01)\n",
            str(root / "foreign-signal"),
            str(root / "foreign-ready"),
        )
        (root / "foreign.json").write_text(
            json.dumps(
                {
                    "name": "tailtag-sim-" + RUN,
                    "pid": foreign.pid,
                    "labels": {
                        "tailtag.run_id": "66666666-6666-4666-8666-666666666666"
                    },
                }
            )
        )
        task: asyncio.Task[int] | None = None
        cleanup_interrupt: asyncio.Task[None] | None = None
        failed_fsync = False
        real_fsync = os.fsync

        def storage_fsync(fd: int) -> None:
            nonlocal failed_fsync
            cidfile = control / "container.cid"
            if cidfile.exists() and cidfile.stat().st_size >= 64:
                target = cidfile if collision == "cid-file-fsync-failure" else control
                expected, actual = target.stat(), os.fstat(fd)
                if (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino):
                    # Only this storage boundary waits for the real external
                    # child. Report/admission/companion fsync calls stay real.
                    until = time.monotonic() + 2
                    while (
                        not (root / "child-ready").exists() and time.monotonic() < until
                    ):
                        time.sleep(0.001)
                    assert (root / "child-ready").exists(), (
                        "storage fault preceded real child creation"
                    )
                    failed_fsync = True
                    raise OSError("injected CID durability failure")
            real_fsync(fd)

        try:
            await eventually(
                lambda: (root / "foreign-ready").exists(), "foreign fixture not ready"
            )
            if storage_failure:
                monkeypatch.setattr(os, "fsync", storage_fsync)
            task = asyncio.create_task(
                supervise_run(value, release, root, sleep=poll_sleep)
            )
            if startup:
                await eventually(
                    acquisition.is_set,
                    "ownership polling bypassed the public sleep boundary",
                    seconds=0.5,
                )
                (root / "publish-cid").touch()
                await eventually(
                    lambda: (root / "child-ready").exists(),
                    "gated Docker child did not start",
                )
                assert (control / "container.cid").read_text().strip() == CID
                assert not [
                    item for item in records(record) if item["argv"][0] == "inspect"
                ]
                if collision == "startup-signal":
                    os.kill(os.getpid(), signal.SIGINT)
                else:
                    task.cancel()

                    async def cancel_during_cleanup() -> None:
                        assert task is not None
                        try:
                            await eventually(
                                lambda: any(
                                    item["argv"][0] == "kill"
                                    and item["argv"][-1] == CID
                                    for item in records(record)
                                ),
                                "CID cleanup never started",
                            )
                            task.cancel()
                            await asyncio.sleep(0.05)
                            assert not task.done(), (
                                "caller returned before CID cleanup joined"
                            )
                        finally:
                            (root / "release-kill").touch()

                    cleanup_interrupt = asyncio.create_task(cancel_during_cleanup())
            result = 1
            with suppress(ValueError, TimeoutError, asyncio.CancelledError):
                result = await asyncio.wait_for(task, 2)
            if cleanup_interrupt is not None:
                await cleanup_interrupt
            assert result != 0
            commands = [item["argv"] for item in records(record)]
            foreign_actions = [
                args
                for args in commands
                if args[0] in {"kill", "wait", "rm"}
                and args[-1] in {FOREIGN_CID, "tailtag-sim-" + RUN}
            ]
            assert not foreign_actions
            assert foreign.returncode is None
            assert not (root / "foreign-signal").exists()
            assert not (root / "foreign-removed").exists()
            assert json.loads((run_root / "recovery-hold.json").read_text()) == {
                "schema_version": 1,
                "run_id": RUN,
            }
            assert [args for args in commands if args[0] == "ps"] == [
                [
                    "ps",
                    "--all",
                    "--no-trunc",
                    "--quiet",
                    "--filter",
                    "name=^/tailtag-sim-" + RUN + "$",
                ]
            ]
            launches = [
                args
                for args in commands
                if args[0] == "run" and "tailtag_simulator.provenance" not in args
            ]
            assert len(launches) == (0 if collision == "preexisting" else 1)
            cidfile = control / "container.cid"
            if collision == "inspect-failure" or startup or storage_failure:
                if storage_failure:
                    assert failed_fsync
                assert cidfile.read_text().strip() == CID
                await eventually(
                    lambda: (root / "child-finalized").exists(),
                    "fresh owned CID was orphaned during startup",
                    seconds=0.5,
                )
                assert (root / "child-signal").read_text() == str(signal.SIGINT)
                assert (root / "child-finalized").read_text() == "130"
                cleanup = [
                    args
                    for args in commands
                    if args[0] in {"kill", "wait", "rm"} and args[-1] == CID
                ]
                assert cleanup and any(args[0] == "kill" for args in cleanup)
                return
            assert not cidfile.exists()
            # The real stop CLI has no Linux admission bypass. Neither absent
            # ownership evidence nor a foreign CID with mismatching run label
            # permits a name fallback or signal to the foreign child.
            for cid in (None, FOREIGN_CID):
                if cid is not None:
                    cidfile.write_text(cid + "\n")
                    cidfile.chmod(0o600)
                before = len(records(record))
                stop = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "tailtag_simulator.host_runner",
                    "stop",
                    "--root",
                    str(root),
                    "--run-id",
                    RUN,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(stop.communicate(), 5)
                finally:
                    if stop.returncode is None:
                        stop.kill()
                        await stop.wait()
                assert stop.returncode != 0
                assert stdout == b"FAIL host_runner\n" and not stderr
                new = records(record)[before:]
                assert not [
                    item for item in new if item["argv"][0] in {"kill", "wait", "rm"}
                ]
                assert foreign.returncode is None
                assert not (root / "foreign-signal").exists()
                assert (run_root / "recovery-hold.json").exists()
        finally:
            (root / "release-kill").touch()
            if cleanup_interrupt is not None and not cleanup_interrupt.done():
                cleanup_interrupt.cancel()
                with suppress(asyncio.CancelledError):
                    await cleanup_interrupt
            release_poll.set()
            if task is not None and not task.done():
                task.cancel()
                with suppress(ValueError, asyncio.CancelledError):
                    await task
            stop_owned_container_child(root, None)
            if foreign.returncode is None:
                foreign.terminate()
            await asyncio.wait_for(foreign.wait(), 5)
            server.close()
            await server.wait_closed()

    with owned_root() as root:
        asyncio.run(execute(root))


HEALTH_CATEGORIES = {
    "live",
    "not_live",
    "refused",
    "timeout",
    "connect_error",
    "invalid",
}


def health_diagnostics(control: Path) -> dict[str, Any]:
    """Closed, private, non-authoritative supervision-health summary (#230)."""
    path = control / "health.json"
    assert path.stat().st_mode & 0o777 == 0o600
    data = json.loads(path.read_text())
    assert set(data) == {
        "schema_version",
        "run_id",
        "checks",
        "counts",
        "longest_gap_seconds",
        "failures",
    }
    assert data["schema_version"] == 1 and data["run_id"] == RUN
    assert set(data["counts"]) == HEALTH_CATEGORIES
    assert all(type(v) is int and v >= 0 for v in data["counts"].values())
    assert data["checks"] == sum(data["counts"].values()) >= 1
    gap = data["longest_gap_seconds"]
    assert gap >= 0 and round(gap, 1) == gap
    failures = data["failures"]
    assert all(set(f) == {"offset_seconds", "result"} for f in failures)
    assert {f["result"] for f in failures} <= HEALTH_CATEGORIES - {"live"}
    offsets = [f["offset_seconds"] for f in failures]
    assert offsets == sorted(offsets)  # oldest first
    assert len(failures) == min(64, data["checks"] - data["counts"]["live"])
    return cast(dict[str, Any], data)


@pytest.mark.parametrize(
    ("stop", "stuck"),
    [
        ("supervision", False),
        ("supervision", True),
        ("deadline", False),
        ("deadline", True),
        ("client-exit", False),
        ("late-live", False),
        ("deadline-before-health", False),
        ("missing-report", False),
        ("failed-report", False),
        ("running-report", False),
        ("passed-report", False),
        ("unwritable-health", False),
    ],
)
def test_supervisor_latches_health_loss_or_deadline_and_signals_named_real_child(
    monkeypatch: pytest.MonkeyPatch,
    stuck: bool,
    stop: str,
) -> None:
    async def execute(root: Path) -> None:
        report_outcome = (
            stop.removesuffix("-report") if stop.endswith("-report") else None
        )
        record = docker_boundary(
            root,
            monkeypatch,
            stuck=stuck,
            client_exit=stop == "client-exit",
            report_outcome=report_outcome,
        )
        value = host_manifest()
        if stop in {"deadline", "deadline-before-health"}:
            section(value, "safety")["seconds"] = 10
        section(value, "release")["dependency_lock_sha256"] = json.loads(
            (root / "image-source.json").read_text()
        )["dependency_lock_sha256"]
        (root / "run-manifest.json").write_text(json.dumps(value))
        release = {
            "schema_version": 1,
            **section(value, "release"),
            "archive_sha256": "e" * 64,
        }
        run_root, control = prepared_skeleton(root, value)
        if report_outcome == "passed":
            destination = root / "passed" / RUN
            destination.mkdir(parents=True)
            snapshot = report_file(destination, value, root / "scratch")
            snapshot.rename(destination / "snapshot.json")
        live = True
        requests: list[object] = []
        delayed_health = asyncio.Event()
        finish_health = asyncio.Event()
        timer = ManualClock()

        async def serve(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                requests.append(json.loads(await reader.readline()))
                if (
                    stop == "late-live"
                    and timer.now >= 25
                    or stop == "deadline-before-health"
                    and timer.now >= 10
                ):
                    delayed_health.set()
                    await finish_health.wait()
                writer.write(json.dumps({"run_id": RUN, "live": live}).encode() + b"\n")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(serve, path=control / "health.sock")
        (control / "health.sock").chmod(0o600)
        task = asyncio.create_task(
            supervise_run(
                value,
                release,
                root,
                clock=lambda: timer.now,
                sleep=timer.sleep,
            )
        )
        unrelated = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(30)"
        )
        child_pid: int | None = None
        try:
            await eventually(
                lambda: (root / "child-ready").exists(),
                "supervisor never launched Python",
            )
            child_pid = int((root / "child-ready").read_text())
            # Advance only a pending public ownership poll before normal work;
            # its elapsed time still counts toward the original execution end.
            await eventually(
                lambda: (
                    task.done()
                    or bool(timer.waiters)
                    or any(item["argv"][0] == "inspect" for item in records(record))
                ),
                "startup did not reach a public poll or inspection",
            )
            if timer.waiters and not any(
                item["argv"][0] == "inspect" for item in records(record)
            ):
                await timer.advance(min(timer.waiters.values()) - timer.now)
            if report_outcome is not None:
                result = await asyncio.wait_for(task, 5)
                assert result == (0 if report_outcome == "passed" else 1)
                assert not (root / "child-signal").exists()
                assert (root / "child-finalized").read_text() == "0"
                assert json.loads((run_root / "recovery-hold.json").read_text()) == {
                    "schema_version": 1,
                    "run_id": RUN,
                }
            else:
                await eventually(
                    lambda: bool(requests), "supervisor never checked health"
                )
                assert requests[0] == {
                    "schema_version": 1,
                    "channel": "health",
                    "run_id": RUN,
                }
                if stop != "client-exit":
                    await eventually(
                        lambda: (
                            bool(timer.waiters)
                            and any(
                                item["argv"][0] == "stats" for item in records(record)
                            )
                        ),
                        "initial health/sample did not settle",
                    )
                if stop == "unwritable-health":
                    # Admitted and running: now the diagnostic write cannot succeed.
                    (control / "health.json").mkdir(mode=0o700)
                live = stop not in {"supervision", "late-live", "unwritable-health"}
                # Wall-clock changes are deliberately irrelevant to monotonic loss.
                monkeypatch.setattr(time, "time", lambda: 1.0)
                requests_before_deadline = len(requests)
                samples_before_deadline = 0
                if stop != "client-exit":
                    deadline_case = stop in {"deadline", "deadline-before-health"}
                    stop_at = 10.0 if deadline_case else timer.now + 30
                    for _ in range(1 if deadline_case else 5):
                        await timer.advance(5)
                        await asyncio.sleep(0.02)
                    if stop == "deadline-before-health":
                        # Finish the predeadline poll/sample before moving time;
                        # otherwise slow process startup can shift its next poll.
                        await eventually(
                            lambda: (
                                len(requests) == 2 and 10.0 in timer.waiters.values()
                            ),
                            "predeadline health/sample did not settle",
                        )
                    await timer.advance(stop_at - timer.now - 0.001)
                    assert not (root / "child-signal").exists()
                    if stop == "late-live":
                        await asyncio.wait_for(delayed_health.wait(), 1)
                    requests_before_deadline = len(requests)
                    samples_before_deadline = len(
                        [item for item in records(record) if item["argv"][0] == "stats"]
                    )
                    await timer.advance(float(stop_at) - timer.now)
                    if stop == "late-live":
                        # A reply from a request begun before expiry cannot erase
                        # the elapsed loss window when it arrives after >=30 s.
                        live = True
                        await timer.advance(0.5)
                        finish_health.set()
                await eventually(
                    lambda: (root / "child-signal").exists(),
                    "bounded stop did not reach Python",
                    seconds=0.5
                    if stop in {"late-live", "deadline-before-health"}
                    else 5,
                )
                if stop == "deadline-before-health":
                    assert len(requests) == requests_before_deadline
                    assert not delayed_health.is_set()
                    assert (
                        len(
                            [
                                item
                                for item in records(record)
                                if item["argv"][0] == "stats"
                            ]
                        )
                        == samples_before_deadline
                    )
                assert (root / "child-signal").read_text() == str(signal.SIGINT)
                assert unrelated.returncode is None
                live = True
                if stop == "client-exit":
                    # Exercise an inspection that still sees the signalled child
                    # running, then let that real child finish its report.
                    await eventually(
                        lambda: (root / "stopping-inspected").exists(),
                        "supervisor never inspected the stopping container",
                    )
                    (root / "finalize-child").touch()
                if not stuck:
                    await eventually(
                        lambda: (root / "child-finalized").exists(),
                        "signalled child never finalized",
                    )
                # SIGINT receipt does not mean Docker inspection has settled.
                # Arm the next poll before advancing its injected clock.
                await eventually(
                    lambda: task.done() or bool(timer.waiters),
                    "supervisor neither completed nor armed its stop poll",
                )
                await timer.advance(5)
                if stuck:
                    await timer.advance(9.999)
                    assert not (root / "container-exit").exists()
                    await timer.advance(0.001)
                assert await asyncio.wait_for(task, 5) != 0
            commands = [item["argv"] for item in records(record)]
            if stop == "client-exit":
                assert any(
                    args[0] in ("inspect", "wait") and args[-1] == CID
                    for args in commands
                )
            launches = [
                args
                for args in commands
                if args[0] == "run" and "tailtag_simulator.provenance" not in args
            ]
            assert len(launches) == 1  # Late live health never restarts this run.
            launch = launches[0]
            assert launch[launch.index("--name") + 1] == "tailtag-sim-" + RUN
            assert launch[launch.index("--cidfile") + 1] == str(
                control / "container.cid"
            )
            assert launch[launch.index("--label") + 1] == "tailtag.run_id=" + RUN
            cidfile = control / "container.cid"
            assert cidfile.read_text().strip() == CID
            assert cidfile.stat().st_mode & 0o777 == 0o600
            assert cidfile.stat().st_uid == os.getuid()
            workload_actions = [
                args
                for args in commands
                if args[0] in {"inspect", "stats", "kill", "wait", "rm"}
                and not (args[0] == "rm" and args[-1].startswith("tailtag-sim-source-"))
            ]
            assert workload_actions and all(
                args[-1] == CID for args in workload_actions
            )
            assert "--init" in launch
            assert (
                "--log-driver=none" in launch
                or ["--log-driver", "none"]
                == launch[
                    launch.index("--log-driver") : launch.index("--log-driver") + 2
                ]
            )
            assert not any(arg.startswith("--restart") for arg in launch)
            assert "core=0" in " ".join(launch)
            assert "--user" in launch
            assert launch[launch.index("--user") + 1].split(":")[0] != "0"
            assert IMAGE in launch
            assert "docker.sock" not in " ".join(launch)
            assert "SSH_AUTH_SOCK" not in " ".join(launch)
            mounts = [
                launch[i + 1]
                for i, arg in enumerate(launch)
                if arg in ("--mount", "-v", "--volume")
            ]
            assert not any(
                "/control" in mount and "manifest.json" not in mount for mount in mounts
            )
            assert any(
                "/rpc" in mount and ("readonly" in mount or mount.endswith(":ro"))
                for mount in mounts
            )
            kills = [args for args in commands if args[0] == "kill"]
            assert len(kills) == (0 if report_outcome else 2 if stuck else 1)
            assert all(args[-1] == CID for args in kills)
            evidence_path = run_root / "host.json"
            evidence = evidence_path.read_text()
            assert len(evidence.encode()) < 65536
            assert SENTINEL not in evidence
            if stop in {"supervision", "late-live", "unwritable-health"}:
                assert "supervision_lost" in evidence
            assert isinstance(json.loads(evidence), dict)
            if stop == "unwritable-health":
                assert (control / "health.json").is_dir()
                assert not (control / "health.json.tmp").exists()
                # Same fail-closed outcome as the plain supervision-loss case.
                assert json.loads(evidence)["evidence"]["stop_reason"] == (
                    "supervision_lost"
                )
            else:
                diagnostics = health_diagnostics(control)
                assert "health" not in evidence  # host.json's shape is closed
                if stop == "supervision":
                    # Fail-closed loss: only the first reply was live, and the
                    # open interval to the 30 s stop is the longest gap.
                    assert diagnostics["counts"]["live"] >= 1
                    assert diagnostics["counts"]["not_live"] >= 1
                    assert diagnostics["longest_gap_seconds"] == 30.0
                    assert {f["result"] for f in diagnostics["failures"]} == {
                        "not_live"
                    }
                elif stop == "passed-report":
                    assert diagnostics["counts"]["live"] == diagnostics["checks"]
                    assert diagnostics["failures"] == []
            if report_outcome is not None:
                assert json.loads(evidence)["evidence"]["recovery"] == "uncertain"
                reports = list((run_root / "reports").glob("*.json"))
                if report_outcome == "missing":
                    assert not reports
                else:
                    assert len(reports) == 1
                    report = read_report(reports[0])
                    assert report["outcome"] == report_outcome
                    assert (
                        report["target"]["starting"]["value"]
                        == value["backend_identity"]
                    )
            elif stuck:
                assert "uncertain" in evidence or "hard_stop" in evidence
                assert not (root / "child-finalized").exists()
            else:
                assert (root / "child-finalized").read_text() == "130"
                reports = [path for path in (run_root / "reports").rglob("*.json")]
                assert len(reports) == 1
                report = read_report(reports[0])
                assert report["run_id"] == RUN
                assert report["outcome"] == "interrupted"
                assert report["safety"]["abort"] is None
        finally:
            finish_health.set()
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            stop_owned_container_child(root, child_pid)
            unrelated.terminate()
            await asyncio.wait_for(unrelated.wait(), 5)
            server.close()
            await server.wait_closed()

    with owned_root() as root:
        asyncio.run(execute(root))


def test_supervision_health_diagnostics_classify_every_check_and_cap_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One live reply at least every 25 s keeps supervision alive for 86 checks.
    block = ["live", "refused", "refused", "refused", "refused"]
    script = (
        ["live", "not_live", "refused", "invalid", "timeout"]
        + block * 15
        + ["live", "refused", "refused", "refused", "refused", "connect_error"]
    )

    async def execute(root: Path) -> None:
        record = docker_boundary(root, monkeypatch, stuck=False)
        value = host_manifest()
        section(value, "release")["dependency_lock_sha256"] = json.loads(
            (root / "image-source.json").read_text()
        )["dependency_lock_sha256"]
        (root / "run-manifest.json").write_text(json.dumps(value))
        release = {
            "schema_version": 1,
            **section(value, "release"),
            "archive_sha256": "e" * 64,
        }
        run_root, control = prepared_skeleton(root, value)
        timer = ManualClock()
        asked = 0
        hang = asyncio.Event()

        async def serve(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            nonlocal asked
            try:
                await reader.readline()
                mode = script[asked]
                asked += 1
                if mode == "timeout":
                    await hang.wait()
                elif mode != "refused":  # refused: EOF without a reply
                    reply = {
                        "run_id": "x" if mode == "invalid" else RUN,
                        "live": mode == "live",
                    }
                    writer.write(json.dumps(reply).encode() + b"\n")
                    await writer.drain()
            finally:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()

        def sampled() -> int:
            return sum(1 for item in records(record) if item["argv"][0] == "stats")

        server = await asyncio.start_unix_server(serve, path=control / "health.sock")
        (control / "health.sock").chmod(0o600)
        task = asyncio.create_task(
            supervise_run(
                value, release, root, clock=lambda: timer.now, sleep=timer.sleep
            )
        )
        child_pid: int | None = None
        try:
            await eventually(lambda: (root / "child-ready").exists(), "no child")
            child_pid = int((root / "child-ready").read_text())
            await eventually(
                lambda: (
                    task.done()
                    or bool(timer.waiters)
                    or any(item["argv"][0] == "inspect" for item in records(record))
                ),
                "startup did not reach a public poll or inspection",
            )
            if timer.waiters and not any(
                item["argv"][0] == "inspect" for item in records(record)
            ):
                await timer.advance(min(timer.waiters.values()) - timer.now)
            for check in range(len(script)):
                # Each check, with its sample, settles before time moves again.
                await eventually(
                    lambda check=check: sampled() == check + 1 and bool(timer.waiters),
                    f"check {check} did not settle",
                    seconds=8,
                )
                if check == len(script) - 2:
                    (control / "health.sock").unlink()  # the last is connect_error
                await timer.advance(5)
            await eventually(lambda: (root / "child-signal").exists(), "no stop")
            await eventually(lambda: (root / "child-finalized").exists(), "no final")
            await eventually(lambda: task.done() or bool(timer.waiters), "no poll")
            await timer.advance(5)
            assert await asyncio.wait_for(task, 5) != 0
            assert "supervision_lost" in (run_root / "host.json").read_text()
            diagnostics = health_diagnostics(control)
            assert asked == len(script) - 1  # the last check never connected
            assert diagnostics["checks"] == len(script)
            assert diagnostics["counts"] == {
                category: script.count(category) for category in HEALTH_CATEGORIES
            }
            assert diagnostics["longest_gap_seconds"] == 30.0
            # The 64 newest failures, oldest first; counts keep the older ones.
            failing = [
                {"offset_seconds": 5.0 * index, "result": result}
                for index, result in enumerate(script)
                if result != "live"
            ]
            assert len(failing) > 64
            assert diagnostics["failures"] == failing[-64:]
        finally:
            hang.set()
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            stop_owned_container_child(root, child_pid)
            server.close()
            await server.wait_closed()

    with owned_root() as root:
        asyncio.run(execute(root))


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="host_runner CLI prerequisite/signal proof requires supported Linux; portable named-child seam is tested above",
)
def test_host_cli_survives_sighup_until_named_python_finalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Newly discovered risk: losing a foreground TTY must not orphan Docker work."""

    async def execute(root: Path) -> None:
        record = docker_boundary(root, monkeypatch, stuck=False)
        value = host_manifest()
        section(value, "release")["dependency_lock_sha256"] = json.loads(
            (root / "image-source.json").read_text()
        )["dependency_lock_sha256"]
        (root / "run-manifest.json").write_text(json.dumps(value))
        release = {
            "schema_version": 1,
            **section(value, "release"),
            "archive_sha256": "e" * 64,
        }
        run_root, control = prepared_skeleton(root, value)
        manifest_path = control / "manifest.json"
        release_path = root / "release.json"
        release_path.write_text(json.dumps(release))
        release_path.chmod(0o600)

        async def serve(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                assert json.loads(await reader.readline()) == {
                    "schema_version": 1,
                    "channel": "health",
                    "run_id": RUN,
                }
                writer.write(json.dumps({"run_id": RUN, "live": True}).encode() + b"\n")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(serve, path=control / "health.sock")
        (control / "health.sock").chmod(0o600)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tailtag_simulator.host_runner",
            "run",
            "--manifest",
            str(manifest_path),
            "--release",
            str(release_path),
            "--root",
            str(root),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        unrelated = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(30)", start_new_session=True
        )
        child_pid: int | None = None
        try:
            await eventually(
                lambda: (root / "child-ready").exists(),
                "host CLI never launched Python",
            )
            child_pid = int((root / "child-ready").read_text())
            assert os.getsid(process.pid) == process.pid
            assert os.getpgid(process.pid) == process.pid
            os.killpg(process.pid, signal.SIGHUP)
            await eventually(
                lambda: (root / "child-finalized").exists(),
                "SIGHUP orphaned the Python run",
            )
            assert (root / "child-signal").read_text() == str(signal.SIGINT)
            assert await asyncio.wait_for(process.wait(), 5) != 0
            assert unrelated.returncode is None
            assert not (root / "docker-forwarded-hup").exists()
            commands = [item["argv"] for item in records(record)]
            workload = [
                item
                for item in records(record)
                if item["argv"][0] == "run"
                and "tailtag_simulator.provenance" not in item["argv"]
            ]
            assert len(workload) == 1
            assert workload[0]["sid"] != process.pid
            assert workload[0]["pgid"] != process.pid
            assert "--sig-proxy=false" in workload[0]["argv"]
            kills = [args for args in commands if args[0] == "kill"]
            assert len(kills) == 1
            assert kills[0][-1] == CID
            report_path = next((run_root / "reports").rglob("*.json"))
            assert read_report(report_path)["outcome"] == "interrupted"
            assert (run_root / "host.json").is_file()
            assert json.loads((run_root / "recovery-hold.json").read_text()) == {
                "schema_version": 1,
                "run_id": RUN,
            }
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            stop_owned_container_child(root, child_pid)
            unrelated.terminate()
            await asyncio.wait_for(unrelated.wait(), 5)
            server.close()
            await server.wait_closed()

    with owned_root() as root:
        asyncio.run(execute(root))


# #230 U2: the container command is derived from the manifest's scenario.
@pytest.mark.parametrize("scenario", ["convention", "journeys"])
def test_container_command_is_built_from_the_admitted_scenario(
    monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    async def execute(root: Path) -> None:
        record = docker_boundary(
            root, monkeypatch, stuck=False, report_outcome="failed"
        )
        value = (
            host_manifest() if scenario == "convention" else journeys_host_manifest()
        )
        section(value, "release")["dependency_lock_sha256"] = json.loads(
            (root / "image-source.json").read_text()
        )["dependency_lock_sha256"]
        (root / "run-manifest.json").write_text(json.dumps(value))
        release = {
            "schema_version": 1,
            **section(value, "release"),
            "archive_sha256": "e" * 64,
        }
        _, control = prepared_skeleton(root, value)

        async def serve(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                await reader.readline()
                writer.write(json.dumps({"run_id": RUN, "live": True}).encode() + b"\n")
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(serve, path=control / "health.sock")
        (control / "health.sock").chmod(0o600)
        task = asyncio.create_task(supervise_run(value, release, root))
        try:
            with suppress(ValueError, TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(task, 10)
            launches = [
                item["argv"]
                for item in records(record)
                if item["argv"][0] == "run"
                and "tailtag_simulator.provenance" not in item["argv"]
            ]
            assert len(launches) == 1
            argv = launches[0]
            command = argv[argv.index("tailtag_simulator") + 1 :]
            assert command[0] == scenario
            flags = dict(zip(command[1::2], command[2::2], strict=True))
            expected = {
                "--pool": POOL,
                "--scenario-version": "2" if scenario == "convention" else "1",
                "--seed": "-7" if scenario == "convention" else "0",
                "--host-manifest": "/manifest.json",
                "--host-socket-dir": "/bridge",
                "--report-dir": "/reports",
                "--stage-log": "/reports/stages.log",
            }
            if scenario == "convention":
                expected["--family"] = "baseline"
            assert flags == expected
        finally:
            if not task.done():
                task.cancel()
                with suppress(ValueError, asyncio.CancelledError):
                    await task
            stop_owned_container_child(root, None)
            server.close()
            await server.wait_closed()

    with owned_root() as root:
        asyncio.run(execute(root))


# --- #316 U2: `host_operator run-local` (bridge and host_runner on one machine) ---

RUNNER = """
import json, os, signal, socket, sys, time
from pathlib import Path
root = Path({root!r})
argv = sys.argv[1:]
assert argv[:2] == ["-m", "tailtag_simulator.host_runner"], argv
op = argv[2]
host_root = Path(argv[argv.index("--root") + 1])
base = host_root / "runs" / {run!r}
state = root / "state"
scenario = (root / "scenario").read_text()
record = {{"op": op, "argv": argv, "cwd": os.getcwd(), "pid": os.getpid(),
          "used": (state / "{run}.used.json").exists(),
          "bridge": (state / "{run}.bridge.json").exists()}}

def ask(path, frame):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(3)
        connection.connect(str(path))
        connection.sendall((json.dumps(frame) + "\\n").encode())
        with connection.makefile("rb") as stream:
            return json.loads(stream.readline())

def health():
    try:
        return ask(base / "control/health.sock",
                   {{"schema_version": 1, "channel": "health", "run_id": {run!r}}})
    except OSError:
        return None

def log(entry):
    with (root / "runner.jsonl").open("a") as out:
        out.write(json.dumps(entry) + "\\n")

if op in ("prepare", "recovery-resolve"):
    record["payload"] = json.loads(sys.stdin.read())
if op == "prepare":
    for directory in (host_root / "runs", base, base / "rpc", base / "control"):
        directory.mkdir(mode=0o700, exist_ok=True)
if op == "run":
    record["tty"] = [os.isatty(0), os.isatty(1)]
    record["sockets"] = {{
        name: [(base / name).is_socket(), (base / name).stat().st_mode & 0o777]
        for name in ("rpc/rpc.sock", "control/health.sock")
        if (base / name).exists()
    }}
    record["health"] = health()
log(record)
if op == "run" and scenario == "wait":
    def stopped(number, _frame):
        log({{"op": "signal", "name": signal.Signals(number).name, "health": health()}})
        raise SystemExit(1)
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, stopped)
    (root / "ready").touch()
    time.sleep(60)
if op == "recovery-resolve" and scenario == "resolve_failure":
    raise SystemExit(1)
if op == "run" and scenario in ("released", "runner_failure", "held", "resolve_failure"):
    for name in (["allocate"] if scenario == "held" else ["allocate", "release"]):
        arguments = {{"run_id": {run!r}}}
        if name == "allocate":
            arguments.update(count=8, ttl_seconds=1800)
        manifest = json.loads((root / "manifest.json").read_text())
        reply = ask(base / "rpc/rpc.sock", {{"schema_version": 1, "channel": "pool", "request": {{
            "operation": name, "pool": "p1", "arguments": arguments,
            "expected_identity": manifest["backend_identity"]}}}})
        assert reply["result"] == "PASS", reply
    raise SystemExit(1 if scenario == "runner_failure" else 0)
"""

TASK = """
import json, os, sys
from pathlib import Path
request = json.loads(sys.stdin.read())
with Path({root!r}, "task.jsonl").open("a") as out:
    out.write(json.dumps({{"argv": sys.argv, "cwd": os.getcwd(), "env": dict(os.environ),
                          "operation": request["operation"]}}) + "\\n")
data = ({{"indexes": [17, 23, 31, 37, 41, 43, 47, 53]}}
        if request["operation"] == "allocate" else {{"released": 8}})
print(json.dumps({{"result": "PASS", "data": data}}))
"""

LOCAL_FAULTS = [
    "auto-update-unset",
    "auto-update-0",
    "stdin-not-tty",
    "stdout-not-tty",
    "no-taskfile",
    "no-services-api",
    "no-task",
    "railway-not-executable",
    "no-uv",
    "relative-tools",
    "symlinked-host-root",
    "relative-state-dir",
]


class LocalRig:
    def __init__(self, root: Path, scenario: str, final_seconds: float = 5) -> None:
        self.root = root
        self.host_root = root / "host"
        self.workspace = root / "workspace"
        self.tools = root / "tools"
        self.state = root / "state"
        value = host_manifest()
        section(value, "safety")["final_seconds"] = final_seconds
        self.value = value
        (root / "manifest.json").write_text(json.dumps(value))
        (root / "scenario").write_text(scenario)
        sha = str(section(value, "release")["simulator_sha"])
        self.release = self.host_root / "releases" / sha
        python = self.release / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        executable(python, RUNNER.format(root=str(root), run=RUN))
        self.workspace.mkdir()
        (self.workspace / "Taskfile.yml").write_text("version: '3'\n")
        (self.workspace / "services/api").mkdir(parents=True)
        (self.tools / "bin").mkdir(parents=True)
        executable(self.tools / "bin/task", TASK.format(root=str(root)))
        for tool in (self.tools / "bin/railway", self.tools / "uv"):
            executable(tool, "")
        self.home = root / "home"
        self.home.mkdir()

    def environment(self, **changes: str | None) -> dict[str, str]:
        env = {
            **os.environ,
            "RAILWAY_NO_AUTO_UPDATE": "1",
            "HOME": str(self.home),
            "PATH": "/tt316-sentinel-bin" + os.pathsep + os.environ["PATH"],
        }
        for key, replacement in changes.items():
            if replacement is None:
                env.pop(key, None)
            else:
                env[key] = replacement
        return env

    def command(self, paths: dict[str, str] | None = None) -> list[str]:
        values = {
            "manifest": str(self.root / "manifest.json"),
            "host-root": str(self.host_root),
            "workspace": str(self.workspace),
            "tools": str(self.tools),
            "state-dir": str(self.state),
            **(paths or {}),
        }
        return [
            sys.executable,
            "-m",
            "tailtag_simulator.host_operator",
            "run-local",
            *(item for key, value in values.items() for item in (f"--{key}", value)),
        ]

    @contextmanager
    def start(
        self,
        *,
        stdin_tty: bool = True,
        stdout_tty: bool = True,
        paths: dict[str, str] | None = None,
        cwd: Path | None = None,
        **changes: str | None,
    ) -> Generator[subprocess.Popen[bytes]]:
        """Run the operator on a real pseudo-terminal; plain files stand in for a non-tty."""
        master, slave = pty.openpty()
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                self.command(paths),
                cwd=cwd,
                env=self.environment(**changes),
                stdin=slave if stdin_tty else subprocess.DEVNULL,
                stdout=slave if stdout_tty else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            os.close(slave)
            yield process
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            for entry in records(self.root / "runner.jsonl"):
                if entry["op"] == "run":
                    with suppress(ProcessLookupError):
                        os.kill(int(entry["pid"]), signal.SIGKILL)
            os.close(master)

    def ops(self) -> list[str]:
        return [entry["op"] for entry in records(self.root / "runner.jsonl")]


@pytest.mark.parametrize("fault", LOCAL_FAULTS)
def test_run_local_refuses_unsafe_start_before_prepare(fault: str) -> None:
    """#316 C1 and AC8: every refusal exits 1 before any host_runner process starts."""
    with owned_root() as root:
        rig = LocalRig(root, "released")
        changes: dict[str, str | None] = {}
        if fault == "auto-update-unset":
            changes["RAILWAY_NO_AUTO_UPDATE"] = None
        elif fault == "auto-update-0":
            changes["RAILWAY_NO_AUTO_UPDATE"] = "0"
        elif fault == "no-taskfile":
            (rig.workspace / "Taskfile.yml").unlink()
        elif fault == "no-services-api":
            (rig.workspace / "services/api").rmdir()
            (rig.workspace / "services").rmdir()
        elif fault == "no-task":
            (rig.tools / "bin/task").unlink()
        elif fault == "railway-not-executable":
            (rig.tools / "bin/railway").chmod(0o600)
        elif fault == "no-uv":
            # The plan does not say whether uv sits at tools/uv or tools/bin/uv.
            (rig.tools / "uv").unlink()
            (rig.tools / "bin/uv").unlink(missing_ok=True)
        # Path faults: each good path exists and is resolved, so only the form is wrong.
        paths: dict[str, str] = {}
        cwd: Path | None = None
        if fault in {"relative-tools", "relative-state-dir"}:
            # Relative to this cwd the path resolves to a real tools/state directory.
            cwd = root
            changes["PYTHONPATH"] = str(Path(__file__).parents[1])
            paths = (
                {"tools": "tools"}
                if fault == "relative-tools"
                else {"state-dir": "state"}
            )
        elif fault == "symlinked-host-root":
            (root / "hostlink").symlink_to(rig.host_root, target_is_directory=True)
            paths = {"host-root": str(root / "hostlink")}
        with rig.start(
            stdin_tty=fault != "stdin-not-tty",
            stdout_tty=fault != "stdout-not-tty",
            paths=paths,
            cwd=cwd,
            **changes,
        ) as process:
            assert process.wait(timeout=20) == 1
        assert rig.ops() == []
        assert not (rig.host_root / "runs").exists()
        assert list(root.rglob("*.used.json")) == []


@pytest.mark.parametrize("outcome", ["released", "runner_failure"])
def test_run_local_prepares_then_binds_then_runs_and_resolves_the_receipt_locally(
    outcome: str,
) -> None:
    """#316 AC8/C2/C3: order, sockets before run, workspace relays, local resolve."""
    with owned_root() as root:
        rig = LocalRig(root, outcome)
        with rig.start() as process:
            assert process.wait(timeout=30) == (0 if outcome == "released" else 1)
        entries = records(root / "runner.jsonl")
        prepare, run = entries[0], entries[1]
        # recovery-resolve runs only after a clean runner exit with a released receipt.
        assert [e["op"] for e in entries] == (
            ["prepare", "run", "recovery-resolve"]
            if outcome == "released"
            else ["prepare", "run"]
        )
        assert all(e["cwd"] == str(rig.release) for e in entries)
        assert prepare["payload"] == rig.value
        assert prepare["used"] is True  # <UUID>.used.json exists before prepare
        # prepare created the 0700 parents; the bridge bound both sockets before run.
        assert run["sockets"] == {
            "rpc/rpc.sock": [True, 0o600],
            "control/health.sock": [True, 0o600],
        }
        assert run["health"] == {"run_id": RUN, "live": True}
        assert run["tty"] == [True, True]  # the Clerk prompt needs the terminal
        assert run["bridge"] is False
        words = run["argv"]
        assert words[words.index("--root") + 1] == str(rig.host_root)
        assert words[words.index("--manifest") + 1] == str(
            rig.host_root / "runs" / RUN / "control/manifest.json"
        )
        assert words[words.index("--release") + 1] == str(rig.release / "release.json")
        evidence = json.loads((rig.state / (RUN + ".bridge.json")).read_text())
        assert evidence["disposition"] == "released"
        assert json.loads((rig.state / (RUN + ".used.json")).read_text()) == {
            "schema_version": 1,
            "run_id": RUN,
        }
        # The relays run `task` by absolute path in the workspace, with an explicit env.
        relays = records(root / "task.jsonl")
        assert [r["operation"] for r in relays] == ["allocate", "release"]
        for relay in relays:
            assert relay["argv"] == [
                str(rig.tools / "bin/task"),
                "-s",
                "api-sim-pool-ssh",
            ]
            assert Path(relay["cwd"]).resolve() == rig.workspace.resolve()
            env = relay["env"]
            assert env["RAILWAY_NO_AUTO_UPDATE"] == "1"
            assert env["HOME"] == str(rig.home)
            assert Path(env["UV"]).name == "uv"
            assert Path(env["UV"]).is_relative_to(rig.tools)
            assert str(rig.tools / "bin") in env["PATH"].split(os.pathsep)
            assert "/tt316-sentinel-bin" not in env["PATH"]
        if outcome == "released":
            resolve = entries[2]
            assert resolve["bridge"] is True  # evidence is written after settle
            assert resolve["payload"] == {
                "schema_version": 1,
                "run_id": RUN,
                "backend_identity": rig.value["backend_identity"],
                "disposition": "released",
            }
            assert resolve["argv"][-6:] == [
                "--root",
                str(rig.host_root),
                "--run-id",
                RUN,
                "--receipt",
                "-",
            ]
            # The used file is create-once: the same manifest never starts again.
            with rig.start() as again:
                assert again.wait(timeout=20) == 1
            assert rig.ops() == ["prepare", "run", "recovery-resolve"]


@pytest.mark.parametrize("sent", ["SIGINT", "SIGTERM", "SIGHUP"])
def test_run_local_revokes_on_a_signal_and_stops_the_runner_child(sent: str) -> None:
    """#316 C3: a signal to the operator alone revokes health and reaches the child."""
    with owned_root() as root:
        rig = LocalRig(root, "wait", final_seconds=20)
        with rig.start() as process:
            deadline = time.monotonic() + 15
            while not (root / "ready").exists():
                assert time.monotonic() < deadline, "runner never started"
                assert process.poll() is None
                time.sleep(0.02)
            process.send_signal(getattr(signal, sent))
            # final_seconds is 20: only an explicit stop ends the child within 8 s.
            assert process.wait(timeout=8) != 0
        received = next(
            e for e in records(root / "runner.jsonl") if e["op"] == "signal"
        )
        assert received["name"] in (
            {sent} if sent != "SIGINT" else {"SIGINT", "SIGTERM"}
        )
        assert received["health"] == {"run_id": RUN, "live": False}
        assert first_revocation(rig.state, "signal_" + sent) >= 0


def test_run_local_revokes_at_the_execution_deadline_and_stops_the_runner() -> None:
    """Shared core: the deadline never renews and ends a runner that would not stop."""
    with owned_root() as root:
        rig = LocalRig(root, "wait", final_seconds=1)
        section(rig.value, "safety")["seconds"] = 1
        (root / "manifest.json").write_text(json.dumps(rig.value))
        with rig.start() as process:
            deadline = time.monotonic() + 15
            while not (root / "ready").exists():
                assert time.monotonic() < deadline, "runner never started"
                assert process.poll() is None
                time.sleep(0.02)
            # The runner sleeps 60 s: only the operator's deadline can end it.
            assert process.wait(timeout=15) != 0
        received = next(
            e for e in records(root / "runner.jsonl") if e["op"] == "signal"
        )
        assert received["health"] == {"run_id": RUN, "live": False}
        assert first_revocation(rig.state, "execution_deadline") >= 1.0


def test_run_local_withholds_recovery_resolve_when_the_receipt_is_held() -> None:
    """Shared core: a clean runner exit that leaves the pool held must not resolve."""
    with owned_root() as root:
        rig = LocalRig(root, "held")
        with rig.start() as process:
            assert process.wait(timeout=30) == 1
        assert rig.ops() == ["prepare", "run"]
        evidence = json.loads((rig.state / (RUN + ".bridge.json")).read_text())
        assert evidence["disposition"] == "held"


def test_run_local_fails_but_keeps_evidence_when_the_recovery_resolve_fails() -> None:
    """Shared core: a failed local resolve is a failed session, never a pass."""
    with owned_root() as root:
        rig = LocalRig(root, "resolve_failure")
        with rig.start() as process:
            assert process.wait(timeout=30) == 1
        assert rig.ops() == ["prepare", "run", "recovery-resolve"]
        evidence = json.loads((rig.state / (RUN + ".bridge.json")).read_text())
        assert evidence["disposition"] == "released"


def test_run_local_resolves_a_no_mutation_receipt_and_exits_clean() -> None:
    """Shared core: a runner that never allocated still resolves and passes."""
    with owned_root() as root:
        rig = LocalRig(root, "no_mutation")
        with rig.start() as process:
            assert process.wait(timeout=30) == 0
        entries = records(root / "runner.jsonl")
        assert [e["op"] for e in entries] == ["prepare", "run", "recovery-resolve"]
        assert entries[2]["payload"]["disposition"] == "no_mutation"
        evidence = json.loads((rig.state / (RUN + ".bridge.json")).read_text())
        assert evidence["disposition"] == "no_mutation"
