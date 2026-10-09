"""#228 U2: owned SSH liveness and monotonic named-child supervision.

SSH/Docker executables are external-boundary substitutes. Unix sockets, clocks'
consumers, subprocess ownership and the signal-receiving Python child are real.
"""

import asyncio
import json
import os
import shlex
import signal
import socket
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, cast

import pytest
from report_support import read_report
from test_host_cli import IMAGE, RUN, SENTINEL, host_manifest, packaged_source, section
from traffic_support import ManualClock

from tailtag_simulator.host_operator import run_session
from tailtag_simulator.host_runner import supervise_run


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


def ssh_boundary(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    binary = root / "bin"
    binary.mkdir(mode=0o700)
    record = root / "ssh.jsonl"
    executable(binary / "scp", "import sys\nraise SystemExit(0)\n")
    executable(
        binary / "ssh",
        f"""
import json, os, sys, time
from pathlib import Path
root = Path({str(root)!r})
argv = sys.argv[1:]
with (root / "ssh.jsonl").open("a") as out:
    out.write(json.dumps({{"argv": argv, "pid": os.getpid(),
                          "stdio_devices":[os.fstat(fd).st_rdev for fd in range(3)]}}) + "\\n")
if "-R" in argv:
    while not (root / "ssh-exit").exists():
        time.sleep(0.01)
    raise SystemExit(1)
print(json.dumps({{"image_id": {IMAGE!r}, "platform": "linux/amd64"}}))
""",
    )
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    return record


async def health(path: Path) -> dict[str, object]:
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(path), 2)
    try:
        writer.write(
            json.dumps(
                {"schema_version": 1, "channel": "health", "run_id": RUN}
            ).encode()
            + b"\n"
        )
        await writer.drain()
        return cast(
            dict[str, object], json.loads(await asyncio.wait_for(reader.readline(), 2))
        )
    finally:
        writer.close()
        await writer.wait_closed()


def attached_ssh(record: Path) -> dict[str, Any] | None:
    return next((item for item in records(record) if "-R" in item["argv"]), None)


@pytest.mark.parametrize("stop", ["ssh-exit", "SIGINT", "SIGHUP"])
def test_operator_owned_ssh_or_terminal_loss_revokes_health_before_teardown(
    monkeypatch: pytest.MonkeyPatch, stop: str
) -> None:
    async def execute(root: Path) -> None:
        record = ssh_boundary(root, monkeypatch)
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps(host_manifest()))
        manifest.chmod(0o600)
        state = root / "state"
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "tailtag_simulator.host_operator",
            "run",
            "--manifest",
            str(manifest),
            "--host",
            "tailtag-test",
            "--host-root",
            "/srv/tailtag root",
            "--state-dir",
            str(state),
            # The operator inherits these caller streams. Nothing reads a secret.
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        ssh_pid: int | None = None
        try:
            await eventually(
                lambda: attached_ssh(record) is not None, "owned SSH never attached"
            )
            attached = attached_ssh(record)
            assert attached is not None
            ssh_pid = int(attached["pid"])
            assert attached["stdio_devices"] == [os.stat(os.devnull).st_rdev] * 3
            argv = cast(list[str], attached["argv"])
            forwards = [
                argv[index + 1] for index, arg in enumerate(argv) if arg == "-R"
            ]
            assert len(forwards) == 2
            local_health = next(
                Path(item.split(":", 1)[1])
                for item in forwards
                if "health.sock" in item
            )
            assert await health(local_health) == {"run_id": RUN, "live": True}
            joined = " ".join(argv)
            assert "ForwardAgent=no" in joined or "-a" in argv
            for setting in (
                "StrictHostKeyChecking=yes",
                "ExitOnForwardFailure=yes",
                "StreamLocalBindUnlink=no",
            ):
                assert setting in joined
            assert "/srv/tailtag root" in shlex.split(argv[-1])
            if stop == "ssh-exit":
                (root / "ssh-exit").touch()
            else:
                process.send_signal(getattr(signal, stop))

            # A removed listener is closed authority too. A reachable listener
            # must never answer live after loss and cannot reopen on a reread.
            for _ in range(2):
                await asyncio.sleep(0.05)
                try:
                    assert await health(local_health) == {"run_id": RUN, "live": False}
                except (OSError, asyncio.IncompleteReadError, json.JSONDecodeError):
                    pass
            assert await asyncio.wait_for(process.wait(), 5) != 0
            assert state.stat().st_mode & 0o777 == 0o700
            assert RUN in "".join(
                path.name + path.read_text()
                for path in state.rglob("*")
                if path.is_file()
            )
            assert not local_health.exists()
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            if ssh_pid is not None:
                with suppress(ProcessLookupError):
                    os.kill(ssh_pid, signal.SIGKILL)

    with owned_root() as root:
        asyncio.run(execute(root))


def test_operator_deadline_is_nonrenewable_and_manifest_cannot_reopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def execute(root: Path) -> None:
        record = ssh_boundary(root, monkeypatch)
        value = host_manifest()
        section(value, "safety")["seconds"] = 1
        section(value, "safety")["final_seconds"] = 1
        timer = ManualClock()
        state = root / "state"
        task = asyncio.create_task(
            run_session(
                value,
                "tailtag-test",
                Path("/srv/tailtag"),
                state_dir=state,
                clock=lambda: timer.now,
                sleep=timer.sleep,
            )
        )
        ssh_pid: int | None = None
        try:
            await eventually(
                lambda: attached_ssh(record) is not None, "owned SSH never attached"
            )
            attached = attached_ssh(record)
            assert attached is not None
            ssh_pid = int(attached["pid"])
            argv = cast(list[str], attached["argv"])
            local_health = next(
                Path(argv[i + 1].split(":", 1)[1])
                for i, arg in enumerate(argv)
                if arg == "-R" and "health.sock" in argv[i + 1]
            )
            assert (await health(local_health))["live"] is True
            await timer.advance(0.9)
            assert (await health(local_health))["live"] is True
            await timer.advance(0.1)
            assert (await health(local_health))["live"] is False
            await timer.advance(2)
            assert await asyncio.wait_for(task, 5) != 0
            count = len(records(record))
            assert (
                await run_session(
                    value, "tailtag-test", Path("/srv/tailtag"), state_dir=state
                )
                != 0
            )
            assert len(records(record)) == count
            assert state.stat().st_mode & 0o777 == 0o700
            assert all(path.stat().st_mode & 0o077 == 0 for path in state.rglob("*"))
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if ssh_pid is not None:
                with suppress(ProcessLookupError):
                    os.kill(ssh_pid, signal.SIGKILL)

    with owned_root() as root:
        asyncio.run(execute(root))


@pytest.mark.parametrize(
    ("host", "host_root"),
    [
        ("-oProxyCommand=bad", "/srv/tailtag"),
        ("tailtag;echo SENTINEL", "/srv/tailtag"),
        ("tailtag-test", "relative"),
        ("tailtag-test", "/srv/tailtag\nSENTINEL"),
    ],
)
def test_operator_rejects_unsafe_ssh_inputs_before_any_external_process(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    host_root: str,
) -> None:
    async def execute(root: Path) -> None:
        record = ssh_boundary(root, monkeypatch)
        assert (
            await run_session(
                host_manifest(), host, Path(host_root), state_dir=root / "state"
            )
            != 0
        )
        assert not records(record)

    with owned_root() as root:
        asyncio.run(execute(root))


def test_remote_commands_import_uninstalled_release_from_unrelated_cwd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def execute(root: Path) -> None:
        value = host_manifest()
        host_root = root / "host's release root"
        release_root = (
            host_root / "releases" / str(section(value, "release")["simulator_sha"])
        )
        packaged_source(release_root)
        python = release_root / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        # Keep the actual dependency-bearing interpreter prefix; a bare venv
        # symlink without pyvenv.cfg would accidentally lose installed httpx.
        executable(
            python,
            f"import os, sys\nos.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n",
        )
        unrelated = root / "ssh-home"
        unrelated.mkdir()
        binary = root / "bin"
        binary.mkdir()
        executable(
            binary / "ssh",
            f"""
import json, os, shlex, subprocess, sys
from pathlib import Path
root = Path({str(root)!r})
command = sys.argv[-1]
words = shlex.split(command)
operation = words[words.index("tailtag_simulator.host_runner") + 1]
payload = json.loads(sys.stdin.read()) if operation != "run" else None
environment = dict(os.environ)
environment.pop("PYTHONPATH", None)
environment.pop("PYTHONHOME", None)
# Actual remote shell syntax/cwd and actual uninstalled package imports. Help
# stops before Linux policy/workload; this is not a simulated host execution.
result = subprocess.run(["/bin/sh", "-c", command + " --help"],
                        cwd=root / "ssh-home", env=environment,
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, timeout=5)
with (root / "ssh.jsonl").open("a") as out:
    out.write(json.dumps({{"operation":operation, "returncode":result.returncode,
                          "help": "usage:" in result.stdout.decode(),
                          "payload":payload}}) + "\\n")
raise SystemExit(result.returncode)
""",
        )
        monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
        assert (
            await asyncio.wait_for(
                run_session(value, "tailtag-test", host_root, state_dir=root / "state"),
                10,
            )
            == 0
        )
        commands = records(root / "ssh.jsonl")
        assert [item["operation"] for item in commands] == [
            "prepare",
            "run",
            "recovery-resolve",
        ]
        assert all(item["returncode"] == 0 and item["help"] for item in commands)
        assert commands[0]["payload"] == value
        assert commands[-1]["payload"] == {
            "schema_version": 1,
            "run_id": RUN,
            "backend_identity": value["backend_identity"],
            "disposition": "no_mutation",
        }

    with owned_root() as root:
        asyncio.run(execute(root))


@pytest.mark.parametrize(
    "outcome", ["no_mutation", "released", "resolve_failure", "held"]
)
def test_operator_runner_zero_requires_acknowledged_exact_recovery_receipt(
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    async def execute(root: Path) -> None:
        value = host_manifest()
        binary = root / "bin"
        binary.mkdir()
        executable(
            binary / "make",
            f"""
import json, sys
from pathlib import Path
root = Path({str(root)!r})
request = json.loads(sys.stdin.read())
with (root / "relay.jsonl").open("a") as out:
    out.write(json.dumps({{"argv":sys.argv[1:],"request":request}}) + "\\n")
operation = request["operation"]
assert operation in {{"allocate", "release"}}
data = {{"indexes":[17,23,31,37,41,43,47,53]}} if operation == "allocate" else {{"released":8}}
print(json.dumps({{"result":"PASS","data":data}}))
""",
        )
        executable(
            binary / "ssh",
            f"""
import json, shlex, socket, sys
from pathlib import Path
root = Path({str(root)!r})
argv = sys.argv[1:]
words = shlex.split(argv[-1])
operation = words[words.index("tailtag_simulator.host_runner") + 1]
payload = json.loads(sys.stdin.read()) if operation != "run" else None
with (root / "ssh.jsonl").open("a") as out:
    out.write(json.dumps({{"operation":operation,"argv":argv,"payload":payload}}) + "\\n")
if operation == "run" and {outcome!r} in ("released", "held"):
    path = next(argv[i+1].split(":",1)[1] for i,arg in enumerate(argv)
                if arg == "-R" and "rpc.sock" in argv[i+1])
    manifest = json.loads((root / "launch.json").read_text())
    for op in (["allocate", "release"] if {outcome!r} == "released" else ["allocate"]):
        arguments = {{"run_id":manifest["run_id"]}}
        if op == "allocate": arguments.update(count=8, ttl_seconds=1800)
        request = {{"operation":op,"pool":"p1","arguments":arguments,
                   "expected_identity":manifest["backend_identity"]}}
        with socket.socket(socket.AF_UNIX) as connection:
            connection.connect(path)
            connection.sendall((json.dumps({{"schema_version":1,"channel":"pool","request":request}})+"\\n").encode())
            with connection.makefile("rb") as stream:
                reply = json.loads(stream.readline())
        assert reply["result"] == "PASS", reply
raise SystemExit(1 if operation == "recovery-resolve" and {outcome!r} == "resolve_failure" else 0)
""",
        )
        (root / "launch.json").write_text(json.dumps(value))
        monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
        result = await asyncio.wait_for(
            run_session(
                value, "tailtag-test", root / "remote", state_dir=root / "state"
            ),
            5,
        )
        assert result == (0 if outcome in {"no_mutation", "released"} else 1)
        ssh = records(root / "ssh.jsonl")
        expected_operations = ["prepare", "run"] + (
            [] if outcome == "held" else ["recovery-resolve"]
        )
        assert [item["operation"] for item in ssh] == expected_operations
        disposition = (
            "released"
            if outcome == "released"
            else "held"
            if outcome == "held"
            else "no_mutation"
        )
        receipt = {
            "schema_version": 1,
            "run_id": RUN,
            "backend_identity": value["backend_identity"],
            "disposition": disposition,
        }
        if outcome != "held":
            assert ssh[-1]["payload"] == receipt
            words = shlex.split(ssh[-1]["argv"][-1])
            assert words[-6:] == [
                "--root",
                str(root / "remote"),
                "--run-id",
                RUN,
                "--receipt",
                "-",
            ]
        relays = records(root / "relay.jsonl")
        operations = (
            ["allocate", "release"]
            if outcome == "released"
            else ["allocate"]
            if outcome == "held"
            else []
        )
        expected_requests: list[dict[str, object]] = []
        for operation in operations:
            arguments: dict[str, object] = {"run_id": RUN}
            if operation == "allocate":
                arguments.update(count=8, ttl_seconds=1800)
            expected_requests.append(
                {
                    "operation": operation,
                    "pool": "p1",
                    "arguments": arguments,
                    "expected_identity": value["backend_identity"],
                }
            )
        assert [item["request"] for item in relays] == expected_requests
        assert all(
            item["argv"] == ["-s", "--no-print-directory", "api-sim-pool-ssh"]
            for item in relays
        )
        snapshots = [
            json.loads(path.read_text()) for path in (root / "state").glob("*.json")
        ]
        evidence = next(item for item in snapshots if "disposition" in item)
        assert {key: evidence[key] for key in receipt} == receipt
        assert SENTINEL not in json.dumps(evidence)

    with owned_root() as root:
        asyncio.run(execute(root))


def docker_boundary(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    stuck: bool,
    client_exit: bool = False,
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
def stop(signum, frame):
    (root / "child-signal").write_text(str(signum))
    if {stuck!r}:
        return
    report.end("simulation", "interrupted", "FAIL_INTERRUPTED")
    code = report.finish(130)
    (root / "child-finalized").write_text(str(code))
    raise SystemExit(code)
signal.signal(signal.SIGINT, stop)
(root / "child-ready").write_text(str(os.getpid()))
print({SENTINEL!r}, flush=True)
print({SENTINEL!r}, file=sys.stderr, flush=True)
while True: time.sleep(0.01)
""")
    executable(
        binary / "docker",
        f"""
import json, os, shutil, signal, subprocess, sys, time, uuid
from pathlib import Path
root = Path({str(root)!r})
args = sys.argv[1:]
with (root / "docker.jsonl").open("a") as out:
    out.write(json.dumps({{"argv":args}}) + "\\n")
op = args[0]
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
    proc = subprocess.Popen([{sys.executable!r}, str(root / "python-child.py")],
                            env={{**os.environ, "PYTHONPATH":str(root / "source")}})
    (root / "container.json").write_text(json.dumps({{"name":name,"pid":proc.pid}}))
    if {client_exit!r}:
        while not (root / "child-ready").exists() and proc.poll() is None:
            time.sleep(0.01)
        # Losing the attached client does not stop the named container.
        raise SystemExit(1)
    code = proc.wait()
    (root / "container-exit").write_text(str(code))
    raise SystemExit(code if code >= 0 else 128-code)
elif op == "kill":
    state = json.loads((root / "container.json").read_text())
    assert args[-1] == state["name"], args
    value = "KILL"
    for i, item in enumerate(args):
        if item in ("--signal", "-s"): value = args[i+1]
        if item.startswith("--signal="): value = item.split("=",1)[1]
    value = value.removeprefix("SIG")
    os.kill(state["pid"], getattr(signal, "SIG" + value))
    print(state["name"])
elif op in ("inspect", "image"):
    ended = (root/"container-exit").exists() or (root/"child-finalized").exists()
    data = {{"Id":{IMAGE!r},"Architecture":"amd64","Os":"linux",
            "Config":{{"User":"1000:1000","Entrypoint":["python","-m","tailtag_simulator"],"Env":[]}},
            "State":{{"Running":not ended,"ExitCode":130 if ended else 0}}}}
    print(json.dumps([data]))
elif op == "create": print("tailtag-228-extract")
elif op == "cp":
    destination = Path(args[-1])
    if args[-2].endswith("/source.json"):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root/"image-source.json", destination)
    else: shutil.copytree(root/"source", destination, dirs_exist_ok=True)
elif op == "stats": print(json.dumps({{"CPUPerc":"0.00%","MemUsage":"1MiB / 1GiB","MemPerc":"0.10%"}}))
elif op == "wait":
    while not (root/"container-exit").exists() and not (root/"child-finalized").exists(): time.sleep(0.01)
    print((root/"container-exit").read_text() if (root/"container-exit").exists() else "130")
elif op == "rm": pass
elif op == "info": print(json.dumps({{"OSType":"linux","Architecture":"x86_64"}}))
else: raise SystemExit("unexpected Docker boundary operation")
""",
    )
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    return root / "docker.jsonl"


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
    ],
)
def test_supervisor_latches_health_loss_or_deadline_and_signals_named_real_child(
    monkeypatch: pytest.MonkeyPatch,
    stuck: bool,
    stop: str,
) -> None:
    async def execute(root: Path) -> None:
        record = docker_boundary(
            root, monkeypatch, stuck=stuck, client_exit=stop == "client-exit"
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
            await eventually(lambda: bool(requests), "supervisor never checked health")
            assert requests[0] == {
                "schema_version": 1,
                "channel": "health",
                "run_id": RUN,
            }
            live = stop not in {"supervision", "late-live"}
            # Wall-clock changes are deliberately irrelevant to monotonic loss.
            monkeypatch.setattr(time, "time", lambda: 1.0)
            requests_before_deadline = len(requests)
            samples_before_deadline = 0
            if stop != "client-exit":
                stop_at = 10 if stop in {"deadline", "deadline-before-health"} else 30
                for _ in range(stop_at // 5 - 1):
                    await timer.advance(5)
                    await asyncio.sleep(0.02)
                if stop == "deadline-before-health":
                    # Finish the predeadline poll/sample before moving time;
                    # otherwise slow process startup can shift its next poll.
                    await eventually(
                        lambda: len(requests) == 2 and 10.0 in timer.waiters.values(),
                        "predeadline health/sample did not settle",
                    )
                await timer.advance(4.999)
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
                seconds=0.5 if stop in {"late-live", "deadline-before-health"} else 5,
            )
            if stop == "deadline-before-health":
                assert len(requests) == requests_before_deadline
                assert not delayed_health.is_set()
                assert (
                    len(
                        [item for item in records(record) if item["argv"][0] == "stats"]
                    )
                    == samples_before_deadline
                )
            assert (root / "child-signal").read_text() == str(signal.SIGINT)
            assert unrelated.returncode is None
            live = True
            await timer.advance(5)
            if stuck:
                await timer.advance(9.999)
                assert not (root / "container-exit").exists()
                await timer.advance(0.001)
            assert await asyncio.wait_for(task, 5) != 0
            commands = [item["argv"] for item in records(record)]
            if stop == "client-exit":
                assert any(
                    args[0] in ("inspect", "wait") and args[-1] == "tailtag-sim-" + RUN
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
            assert len(kills) == (2 if stuck else 1)
            assert all(args[-1] == "tailtag-sim-" + RUN for args in kills)
            evidence_path = run_root / "host.json"
            evidence = evidence_path.read_text()
            assert len(evidence.encode()) < 65536
            assert SENTINEL not in evidence
            if stop in {"supervision", "late-live"}:
                assert "supervision_lost" in evidence
            assert isinstance(json.loads(evidence), dict)
            if stuck:
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
        )
        child_pid: int | None = None
        try:
            await eventually(
                lambda: (root / "child-ready").exists(),
                "host CLI never launched Python",
            )
            child_pid = int((root / "child-ready").read_text())
            process.send_signal(signal.SIGHUP)
            await eventually(
                lambda: (root / "child-finalized").exists(),
                "SIGHUP orphaned the Python run",
            )
            assert (root / "child-signal").read_text() == str(signal.SIGINT)
            assert await asyncio.wait_for(process.wait(), 5) != 0
            commands = [item["argv"] for item in records(record)]
            assert (
                len(
                    [
                        args
                        for args in commands
                        if args[0] == "run"
                        and "tailtag_simulator.provenance" not in args
                    ]
                )
                == 1
            )
            kills = [args for args in commands if args[0] == "kill"]
            assert len(kills) == 1
            assert kills[0][-1] == "tailtag-sim-" + RUN
            report_path = next((run_root / "reports").rglob("*.json"))
            assert read_report(report_path)["outcome"] == "interrupted"
            assert (run_root / "host.json").is_file()
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
            stop_owned_container_child(root, child_pid)
            server.close()
            await server.wait_closed()

    with owned_root() as root:
        asyncio.run(execute(root))
