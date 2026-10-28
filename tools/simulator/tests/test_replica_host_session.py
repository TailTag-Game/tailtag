"""#359 U3b: the replica host session (prepare, run-local, bridge, container bind)."""

import asyncio
import getpass
import importlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from journey_support import JourneyWorld
from platform_support import skip_on_windows
from pool_support import SECRET
from test_host_cli import (
    JourneysRig,
    RoleKeyedInspection,
    bridge,
    host_manifest,
    install_http,
    journeys_host_manifest,
    packaged_source,
    section,
)
from test_journeys import make_rig as make_journeys_rig
from test_task_commands import CHECKOUT, write_adapter

from tailtag_simulator import host_operator, targets
from tailtag_simulator.__main__ import main
from tailtag_simulator.host_bridge import relay_dispatch
from tailtag_simulator.host_operator import main as operator_main
from tailtag_simulator.owner_only import create_private_file
from tailtag_simulator.targets import replica_host_digest, resolve_target

HOST = "tailtag-api-replica-123456789012.us-east4.run.app"
ORIGIN = f"https://{HOST}"
REVISION = "tailtag-api-replica-00016-fh9"
SOURCE_SHA = "a" * 40
IDENTITY: dict[str, object] = {
    "source_sha": SOURCE_SHA,
    "deployment_id": REVISION,
    "environment": "replica",
}


@pytest.fixture(autouse=True)
def pinned(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(targets, "REPLICA_HOST_DIGEST", replica_host_digest(HOST))
    yield


def private(path: Path, content: str) -> Path:
    """Write an owner-only file the way an operator does, on every platform."""
    os.close(create_private_file(path))
    path.write_text(content)
    return path


def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    return root


def receipt(
    folder: Path,
    name: str,
    finished: str,
    *,
    outcome: str = "PROMOTED",
    revision: str = REVISION,
) -> Path:
    path = folder / name
    path.write_text(
        json.dumps(
            {
                "schema": "tailtag-replica-release-v1",
                "outcome": outcome,
                "serving_revision": revision,
                "source_sha": SOURCE_SHA,
                "finished_at": finished,
            }
        )
    )
    return path


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "older-receipt",
        "wrong-folder",
        "serving-changed",
        "no-receipt-flag",
        "unpinned-host",
        "session-shared",
        "replica-profile-without-flags",
    ],
)
def test_prepare_pins_the_replica_to_the_newest_promoted_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    """H1: the manifest names the replica only with the revision of the newest release."""
    if fault == "session-shared" and os.name == "nt":
        pytest.skip("POSIX mode bits; Windows owner-only is ACL-based")
    value = host_manifest()
    profile = {
        key: value[key]
        for key in ("scenario_id", "scenario_version", "seed", "configuration")
    }
    # Committed host profiles name no target. Prepare sets it from the session.
    profile["configuration"] = {
        key: item
        for key, item in cast(dict[str, object], profile["configuration"]).items()
        if key != "target"
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
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    session_host = (
        "tailtag-api-replica-999.us-east4.run.app" if fault == "unpinned-host" else HOST
    )
    session = private(
        private_root(tmp_path) / "session.json",
        json.dumps({"project": "synthetic-project", "host": session_host}),
    )
    if fault == "session-shared":
        session.chmod(0o644)
    if fault == "replica-profile-without-flags":
        profile["configuration"] = {**profile["configuration"], "target": "replica"}
        (tmp_path / "profile.json").write_text(json.dumps(profile))
    folder = tmp_path / "replica-deployments"
    folder.mkdir()
    older = receipt(
        folder,
        "1-1.json",
        "2026-10-26T10:00:00Z",
        revision="tailtag-api-replica-00014-wtd",
    )
    latest = receipt(folder, "2-1.json", "2026-10-27T17:46:36Z")
    receipt(folder, "3-1.json", "2026-10-28T09:00:00Z", outcome="FAIL_GATE")
    chosen = older if fault == "older-receipt" else latest
    if fault == "wrong-folder":
        other = tmp_path / "elsewhere"
        other.mkdir()
        chosen = other / "2-1.json"
        shutil.copy(latest, chosen)
    hosts: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ok"})
        served = dict(IDENTITY)
        if fault == "serving-changed":
            served["deployment_id"] = "tailtag-api-replica-00017-abc"
        elif fault == "older-receipt":
            # A rollback: the service serves the older receipt's revision, so only
            # the newest-receipt rule can refuse it.
            served["deployment_id"] = "tailtag-api-replica-00014-wtd"
        return httpx.Response(200, json=served)

    install_http(monkeypatch, respond)
    output = tmp_path / "manifest.json"
    arguments = [
        "prepare",
        "--profile",
        str(tmp_path / "profile.json"),
        "--safety-config",
        str(tmp_path / "safety.json"),
        "--release",
        str(tmp_path / "release.json"),
        "--output",
        str(output),
        "--replica-session",
        str(session),
    ]
    if fault == "replica-profile-without-flags":
        arguments = arguments[:-2]
    elif fault != "no-receipt-flag":
        arguments += ["--receipt", str(chosen)]

    code = operator_main(arguments)

    if fault is None:
        assert code == 0
        manifest = cast(dict[str, Any], json.loads(output.read_text()))
        assert manifest["target"] == {"name": "replica", "origin": ORIGIN}
        assert manifest["backend_identity"] == IDENTITY
        assert manifest["configuration"]["target"] == "replica"
        assert set(hosts) == {HOST}
    else:
        assert code != 0
        assert not output.exists()
        assert "staging.tailtag.app" not in hosts


def local_tree(tmp_path: Path) -> tuple[Path, Path]:
    workspace, tools = tmp_path / "workspace", tmp_path / "tools"
    (workspace / "services/api").mkdir(parents=True)
    (workspace / "Taskfile.yml").write_text("version: '3'\n")
    (tools / "bin").mkdir(parents=True)
    for name in ("uv", "bin/task"):
        (tools / name).write_text("#!/bin/sh\n")
        (tools / name).chmod(0o755)
    return workspace, tools


@pytest.mark.parametrize(
    "fault", [None, "no-variables", "unpinned-session", "token-shared"]
)
def test_replica_run_local_needs_only_its_owner_only_relay_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str | None
) -> None:
    """H2: no Railway binary or update pin. Both relay files must be owner-only."""
    if fault == "token-shared" and os.name == "nt":
        pytest.skip("POSIX mode bits; Windows owner-only is ACL-based")
    workspace, tools = local_tree(tmp_path)
    root = private_root(tmp_path)
    host = (
        "tailtag-api-replica-999.us-east4.run.app"
        if fault == "unpinned-session"
        else HOST
    )
    session = private(
        root / "session.json", json.dumps({"project": "p-1", "host": host})
    )
    token = private(root / "token", "synthetic-token\n")
    if fault == "token-shared":
        token.chmod(0o644)
    monkeypatch.delenv("RAILWAY_NO_AUTO_UPDATE", raising=False)
    if fault != "no-variables":
        monkeypatch.setenv("TAILTAG_REPLICA_SESSION_FILE", str(session))
        monkeypatch.setenv("TAILTAG_REPLICA_TOKEN_FILE", str(token))

    def terminal(_fd: int) -> bool:
        return True

    monkeypatch.setattr(os, "isatty", terminal)
    target = resolve_target("replica", ORIGIN)

    uv = host_operator._refuse_local(workspace, tools, target)  # pyright: ignore[reportPrivateUsage]

    if fault is not None:
        assert uv is None
        return
    assert uv is not None and uv == tools / "uv"
    env = host_operator._relay_env(tools, uv, target)  # pyright: ignore[reportPrivateUsage]
    assert set(env) == {
        "PATH",
        "UV",
        "HOME",
        "TAILTAG_REPLICA_SESSION_FILE",
        "TAILTAG_REPLICA_TOKEN_FILE",
    }
    staging = host_operator._relay_env(tools, uv, resolve_target("staging", None))  # pyright: ignore[reportPrivateUsage]
    assert set(staging) == {"PATH", "UV", "HOME", "RAILWAY_NO_AUTO_UPDATE"}


@skip_on_windows("the adapter is a POSIX script, as in test_task_commands")
@pytest.mark.parametrize(
    ("channel", "relay"),
    [("pool", "pool"), ("fixture", "fixture"), ("inspection", "inspect")],
)
def test_replica_bridge_dispatch_runs_the_replica_relay_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, channel: str, relay: str
) -> None:
    """H3: a replica session relays through the replica tasks, never Railway SSH."""
    adapter = write_adapter(
        tmp_path / "uv-adapter",
        "import json, sys\n"
        "print(json.dumps({'result': 'PASS', 'data': {'argv': sys.argv[1:]}}))\n",
    )
    monkeypatch.setenv("UV", adapter)
    task = shutil.which("task")
    assert task is not None
    dispatch = relay_dispatch(CHECKOUT, Path(task), dict(os.environ), "replica")
    envelope: dict[str, object] = {"channel": channel, "request": {"operation": "x"}}

    result, data = asyncio.run(dispatch(channel, envelope))

    assert result == "PASS"
    assert cast(list[str], data["argv"])[-4:] == [
        "-m",
        "scripts.api_sim_replica_relay",
        "--channel",
        relay,
    ]


def test_in_container_replica_run_reaches_only_replica_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """H5: the container binds the manifest target before any call.

    The replica host passes its target checks. The Clerk instance check then
    refuses the synthetic Staging-shaped Clerk instance, so the run stops before
    any gameplay. Every API call must reach the replica host.
    """
    value = journeys_host_manifest()
    value.update(
        target={"name": "replica", "origin": ORIGIN}, backend_identity=dict(IDENTITY)
    )
    source = packaged_source(tmp_path / "source")
    section(value, "release")["dependency_lock_sha256"] = source[
        "dependency_lock_sha256"
    ]
    module = importlib.import_module("tailtag_simulator.__main__")
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path / "source")
    parts = make_journeys_rig(JourneyWorld())
    run = JourneysRig(
        parts.leases, parts.fixtures, RoleKeyedInspection(parts.inspection)
    )
    hosts: list[str] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        if request.url.host == HOST:
            if request.url.path == "/health/ready":
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(200, json=IDENTITY)
        return await parts.world.clerk_transport.handle_async_request(request)

    install_http(monkeypatch, respond)
    prompts: list[str] = []

    def secret(prompt: str = "", *_args: object, **_kwargs: object) -> str:
        prompts.append(prompt)
        return SECRET

    monkeypatch.setattr(getpass, "getpass", secret)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    root = tmp_path / "cli"
    root.mkdir()
    (root / "manifest.json").write_text(json.dumps(value))
    with tempfile.TemporaryDirectory(prefix="t359-", dir="/tmp") as path:
        directory = Path(path).resolve() / "s"
        with bridge(value, run, directory):
            code = main(
                [
                    "journeys",
                    "--pool",
                    str(section(value, "configuration")["pool"]),
                    "--scenario-version",
                    "1",
                    "--seed",
                    "0",
                    "--host-manifest",
                    str(root / "manifest.json"),
                    "--host-socket-dir",
                    str(directory),
                    "--report-dir",
                    str(root / "reports"),
                ]
            )

    assert code != 0
    assert HOST in hosts, "the replica target was checked"
    assert "api.clerk.com" in hosts, "the run reached Clerk after the target bind"
    # The run stops at the Clerk instance check, so every call reached the replica
    # host or the Clerk Backend API. Frontend API use is proven in the live run.
    assert set(hosts) <= {HOST, "api.clerk.com"}
    assert prompts and "Replica" in prompts[0]
    text = "".join(p.read_text() for p in (root / "reports").rglob("*.json"))
    assert HOST not in text
