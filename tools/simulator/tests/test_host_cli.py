"""#228 U2: manifest binding through actual convention and prepare entrypoints."""

import asyncio
import getpass
import hashlib
import importlib
import json
import os
import tempfile
import threading
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from convention_support import CONFIG, Rig, rig
from pool_support import DEPLOYMENT_ID, INSTANCE_ID, POOL, SECRET, SHA
from report_support import read_report

from tailtag_simulator import clerk
from tailtag_simulator.__main__ import main
from tailtag_simulator.host_bridge import BridgeServer, BridgeSession
from tailtag_simulator.host_operator import main as operator_main
from tailtag_simulator.safety import resolve_safety_policy
from tailtag_simulator.traffic_config import resolve_traffic_config

RUN = "55555555-5555-4555-8555-555555555555"
IDENTITY: dict[str, object] = {
    "source_sha": SHA,
    "deployment_id": DEPLOYMENT_ID,
    "environment": "staging",
}
IMAGE = "sha256:" + "d" * 64
SENTINEL = "SENTINEL-private-secret"


def host_manifest() -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": RUN,
        "scenario_id": "convention-baseline",
        "scenario_version": 2,
        "seed": -7,
        "configuration": resolve_traffic_config(
            {
                **CONFIG,
                "traffic": {
                    "segments": [{"duration_seconds": 0.05, "start": 0, "end": 0}],
                    "bursts": [],
                    "think_seconds": 0,
                },
            }
        ),
        "safety": resolve_safety_policy({"population": 50, "final_seconds": 5}),
        "backend_identity": dict(IDENTITY),
        "release": {
            "simulator_sha": "b" * 40,
            "dependency_lock_sha256": "c" * 64,
            "image_id": IMAGE,
            "platform": "linux/amd64",
        },
    }


def section(value: dict[str, object], key: str) -> dict[str, object]:
    return cast(dict[str, object], value[key])


def packaged_source(root: Path) -> dict[str, object]:
    """Real packaged provenance, following the existing CLI test's filesystem seam."""
    simulator = Path(__file__).parents[1]
    checkout = simulator.parents[1]
    files = {
        "pyproject.toml": (simulator / "pyproject.toml").read_bytes(),
        "uv.lock": (simulator / "uv.lock").read_bytes(),
    }
    for directory, destination in (
        (simulator / "tailtag_simulator", "tailtag_simulator"),
        (
            checkout / "services/api/simulation_fixtures/images",
            "services/api/simulation_fixtures/images",
        ),
    ):
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".json", ".jpg"}:
                files[f"{destination}/{path.relative_to(directory)}"] = (
                    path.read_bytes()
                )
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    hashes = {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    }
    source: dict[str, object] = {
        "schema_version": 1,
        "simulator_sha": "b" * 40,
        "dependency_lock_sha256": hashes["uv.lock"],
        "manifest": hashes,
    }
    (root / "source.json").write_text(json.dumps(source))
    return source


def cli_files(root: Path, value: dict[str, object]) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    config = section(value, "configuration")
    paths = {
        "manifest": value,
        "config": {
            key: item for key, item in config.items() if key not in {"pool", "family"}
        },
        "safety": value["safety"],
    }
    for name, content in paths.items():
        (root / f"{name}.json").write_text(json.dumps(content, indent=2))
    return [
        "convention",
        "--pool",
        POOL,
        "--family",
        "baseline",
        "--scenario-version",
        "2",
        "--seed",
        "-7",
        "--config",
        str(root / "config.json"),
        "--safety-config",
        str(root / "safety.json"),
        "--host-manifest",
        str(root / "manifest.json"),
        "--report-dir",
        str(root / "reports"),
    ]


def install_http(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], Any]
) -> None:
    original = httpx.AsyncClient.__init__

    def initialize(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("transport") is None:
            kwargs["transport"] = httpx.MockTransport(handler)
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", initialize)


@contextmanager
def bridge(
    value: dict[str, object], run: Rig, directory: Path
) -> Generator[list[tuple[str, dict[str, object]]]]:
    """Actual bridge on a separate loop; only its external relay boundary is fake."""
    seen: list[tuple[str, dict[str, object]]] = []

    async def dispatch(
        channel: str, request: dict[str, object]
    ) -> tuple[str, dict[str, object]]:
        seen.append((channel, deepcopy(request)))
        arguments = section(request, "arguments")
        if channel == "pool":
            data = await run.leases.call(
                str(request["operation"]), str(request["pool"]), arguments
            )
        elif channel == "fixture":
            data = await run.fixtures.call(str(request["operation"]), arguments)
        else:
            data = dict(
                await run.inspection.inspect(
                    str(arguments["pool"]),
                    str(arguments["run_id"]),
                    cast(dict[str, int], arguments["identities"]),
                )
            )
        return "PASS", dict(data)

    loop = asyncio.new_event_loop()
    session = BridgeSession(value, dispatch)
    server = BridgeServer(session, directory)
    ready = threading.Event()
    errors: list[Exception] = []

    def serve() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.start())
            ready.set()
            loop.run_forever()
        except Exception as error:  # noqa: BLE001 - report owned loop startup to caller
            errors.append(error)
            ready.set()

    thread = threading.Thread(target=serve, name="tailtag-228-cli-bridge")
    thread.start()
    try:
        assert ready.wait(5), "owned bridge did not start"
        if errors:
            raise errors[0]
        yield seen
    finally:
        try:
            if not errors and loop.is_running():

                async def shutdown() -> None:
                    try:
                        await asyncio.wait_for(server.close(), 3)
                    finally:
                        pending = asyncio.all_tasks() - {asyncio.current_task()}
                        for task in pending:
                            task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)

                asyncio.run_coroutine_threadsafe(shutdown(), loop).result(timeout=5)
        finally:
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)
            assert not thread.is_alive(), "owned bridge thread failed to stop"
            loop.close()


@pytest.mark.parametrize("stage_fault", [None, "limit", "symlink"])
def test_host_cli_binds_manifest_uuid_socket_channels_and_stage_only_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage_fault: str | None,
) -> None:
    value = host_manifest()
    source = packaged_source(tmp_path / "source")
    section(value, "release")["dependency_lock_sha256"] = source[
        "dependency_lock_sha256"
    ]
    module = importlib.import_module("tailtag_simulator.__main__")
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path / "source")
    # Match the synthetic /v1/instance identity from the existing HTTP rig;
    # leave real ClerkAdmin fingerprint/domain verification intact.
    monkeypatch.setattr(
        clerk,
        "INSTANCE_FINGERPRINT",
        hashlib.sha256(INSTANCE_ID.encode()).hexdigest()[:16],
    )
    run = rig(tmp_path / "boundary")

    async def respond(request: httpx.Request) -> httpx.Response:
        transport = (
            run.world.api_transport
            if request.url.host == "staging.tailtag.app"
            else run.world.clerk_transport
        )
        return await transport.handle_async_request(request)

    install_http(monkeypatch, respond)
    stage_log = tmp_path / "cli" / "stages.log"

    def prompt(*_args: object, **_kwargs: object) -> str:
        # Raw diagnostic output remains on the inherited terminal, never in the
        # stage artifact. The secret itself still enters through the prompt seam.
        print(SENTINEL)
        if stage_fault == "limit":
            emit = cast(Callable[[str], None], module._emit)  # pyright: ignore[reportPrivateUsage]
            emit("PASS simulation " + "x" * (1024 * 1024))
        return SECRET

    monkeypatch.setattr(getpass, "getpass", prompt)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    args = cli_files(tmp_path / "cli", value)
    if stage_fault == "symlink":
        foreign = tmp_path / "foreign.log"
        foreign.write_text("foreign-owner-evidence")
        stage_log.symlink_to(foreign)
    with tempfile.TemporaryDirectory(prefix="t228-", dir="/tmp") as path:
        # BridgeServer must create the absent owner-only directory itself.
        directory = Path(path).resolve() / "s"
        with bridge(value, run, directory) as seen:
            code = main(
                [
                    *args,
                    "--host-socket-dir",
                    str(directory),
                    "--stage-log",
                    str(stage_log),
                ]
            )
    if stage_fault:
        assert code != 0
        if stage_fault == "symlink":
            assert (tmp_path / "foreign.log").read_text() == "foreign-owner-evidence"
        else:
            assert stage_log.stat().st_size <= 1024 * 1024
        return
    assert code == 0
    assert (
        "PASS provenance" in stage_log.read_text()
        or "PASS target" in stage_log.read_text()
    )
    assert SENTINEL not in stage_log.read_text()
    assert SECRET not in stage_log.read_text()
    assert stage_log.stat().st_mode & 0o777 == 0o600
    reports = list((tmp_path / "cli/reports").rglob("*.json"))
    assert len(reports) == 1
    report = read_report(reports[0])
    assert report["run_id"] == RUN
    assert report["schema_version"] == 4
    assert report["scenario"]["version"] == 2
    assert report["outcome"] == "passed"
    assert {channel for channel, _ in seen} == {"pool", "fixture", "inspection"}
    assert [
        request["operation"]
        for _, request in seen
        if request["operation"] != "heartbeat"
    ] == [
        "retained_counts",
        "allocate",
        "provision",
        "inspect-population-v1",
        "cleanup",
        "release",
    ]
    for _, request in seen:
        assert request["expected_identity"] == IDENTITY
        arguments = section(request, "arguments")
        if request["operation"] != "retained_counts":
            assert arguments["run_id"] == RUN
    assert set(run.world.ended_sessions) == set(run.world.opened_sessions)


@pytest.mark.parametrize(
    "fault",
    [
        "missing-directory",
        "missing-manifest",
        "version",
        "family",
        "pool",
        "seed",
        "configuration",
        "safety",
        "source",
    ],
)
def test_incompatible_host_cli_fails_before_credentials_network_or_launcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    value = host_manifest()
    source = packaged_source(tmp_path / "source")
    section(value, "release")["dependency_lock_sha256"] = source[
        "dependency_lock_sha256"
    ]
    module = importlib.import_module("tailtag_simulator.__main__")
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path / "source")
    args = cli_files(tmp_path / "cli", value) + [
        "--host-socket-dir",
        str(tmp_path / "unused"),
    ]
    if fault == "missing-directory":
        del args[-2:]
    elif fault == "missing-manifest":
        at = args.index("--host-manifest")
        del args[at : at + 2]
    elif fault in {"version", "family", "pool", "seed"}:
        flag = "--scenario-version" if fault == "version" else f"--{fault}"
        args[args.index(flag) + 1] = {
            "version": "1",
            "family": "retry",
            "pool": "other",
            "seed": "8",
        }[fault]
    else:
        if fault == "source":
            section(value, "release")["simulator_sha"] = "e" * 40
        elif fault == "safety":
            section(value, "safety")["requests"] = 9999
        else:
            section(value, "configuration")["casual"] = 3
        (tmp_path / "cli/manifest.json").write_text(json.dumps(value, indent=2))

    def forbidden(*_args: object, **_kwargs: object) -> Any:
        pytest.fail("incompatible host configuration crossed an external boundary")

    monkeypatch.setattr(getpass, "getpass", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    try:
        assert main(args) != 0
    except SystemExit as failure:
        assert failure.code != 0


@pytest.mark.parametrize("fault", [None, "changed-identity"])
def test_prepare_verifies_staging_without_mutation_and_writes_fresh_private_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str | None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    value = host_manifest()
    profile = {
        key: value[key]
        for key in ("scenario_id", "scenario_version", "seed", "configuration")
    }
    release = {
        "schema_version": 1,
        **section(value, "release"),
        "archive_sha256": "e" * 64,
    }
    for name, data in (
        ("profile", profile),
        ("safety", value["safety"]),
        ("release", release),
    ):
        (tmp_path / f"{name}.json").write_text(json.dumps(data, indent=2))
    seen: list[tuple[str, str]] = []
    identity_reads = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal identity_reads
        seen.append((request.method, str(request.url)))
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ok"})
        assert request.url.path == "/health/identity"
        identity_reads += 1
        identity = dict(IDENTITY)
        if fault and identity_reads == 2:
            identity["source_sha"] = "f" * 40
            identity["deployment_id"] = SENTINEL
        return httpx.Response(200, json=identity)

    install_http(monkeypatch, respond)
    uuids: list[str] = []
    for index in range(1 if fault else 2):
        output = tmp_path / f"manifest-{index}.json"
        code = operator_main(
            [
                "prepare",
                "--profile",
                str(tmp_path / "profile.json"),
                "--safety-config",
                str(tmp_path / "safety.json"),
                "--release",
                str(tmp_path / "release.json"),
                "--output",
                str(output),
            ]
        )
        if fault:
            assert code != 0
            assert not output.exists()
        else:
            assert code == 0
            actual = cast(dict[str, object], json.loads(output.read_text()))
            run_id = str(actual["run_id"])
            assert str(uuid.UUID(run_id)) == run_id
            uuids.append(run_id)
            assert actual == {**value, "run_id": run_id}
            assert os.stat(output).st_mode & 0o777 == 0o600
    assert all(
        method == "GET" and url.startswith("https://staging.tailtag.app/health/")
        for method, url in seen
    )
    assert len(set(uuids)) == len(uuids)
    assert SENTINEL not in "".join(capsys.readouterr())
