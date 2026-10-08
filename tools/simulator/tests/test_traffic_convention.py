"""#226 AC15–16/19: real v2 orchestration over external HTTP/launcher seams."""

import asyncio
import getpass
import hashlib
import importlib
import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pool_support
import pytest
from convention_support import CONFIG, BlockedHttp, Inspection, Rig, rig
from pool_support import POOL, RUN_ID, SECRET
from report_support import literal_report, read_report

from tailtag_simulator.__main__ import main
from tailtag_simulator.convention import run_convention
from tailtag_simulator.reports import RunReport

world = pool_support.world


def configuration(*, attempts: int = 5000) -> dict[str, object]:
    return {
        **CONFIG,
        "traffic": {
            "segments": [{"duration_seconds": 0.2, "start": 0, "end": 0}],
            "bursts": [{"at_seconds": 0.01, "count": 6}],
            "think_seconds": 0,
        },
        "limits": {"attempts": attempts},
    }


def traffic_rig(root: Path, config: dict[str, object]) -> Rig:
    value = rig(root / "legacy")
    value.report = RunReport(
        root / "traffic",
        "convention-baseline",
        scenario_version=2,
        config=config,
        seed=-42,
        run_id=RUN_ID,
    )
    value.report.record_source(literal_report()["source"])
    value.report.begin("provenance")
    value.report.end("provenance", "passed")
    return value


async def execute(
    run: Rig,
    config: dict[str, object],
    *,
    api_transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    from tailtag_simulator.traffic import Clock

    return await run_convention(
        POOL,
        config=config,
        scenario_version=2,
        traffic_clock=Clock(),
        seed=-42,
        prompt_secret=lambda: SECRET,
        lease_channel=run.leases,
        fixture_channel=run.fixtures,
        inspection_channel=run.inspection,
        emit=run.lines.append,
        clerk_transport=run.world.clerk_transport,
        api_transport=api_transport or run.world.api_transport,
        clock=run.world.clock,
        run_id=RUN_ID,
        report=run.report,
    )


def finalized(run: Rig) -> None:
    assert run.leases.calls_to("release") == [{"run_id": RUN_ID}]
    assert not {
        index for index, slot in run.leases.slots.items() if slot.run_id == RUN_ID
    }
    assert set(run.world.ended_sessions) == set(run.world.opened_sessions)
    evidence = run.report.path.read_text() + "\n".join(run.lines)
    for secret in (SECRET, "SENTINEL", "user_SECRET", "tailtag:catch", "media.example"):
        assert secret not in evidence


@pytest.mark.parametrize(
    "fault", [None, "inspection", "attempts", "unexpected-success"]
)
def test_v2_workload_evidence_drives_cleanup_or_retention_and_always_releases(
    tmp_path: Path,
    world: pool_support.World,
    fault: str | None,
) -> None:
    del world
    # Enough for discovery and owner preparation; finite admission must then
    # stop the multi-persona gameplay workload while comparison remains usable.
    config = configuration(attempts=64 if fault == "attempts" else 5000)
    if fault == "unexpected-success":
        # Observe the first response before another actor is offered. Requests
        # already in flight before an invalid response need no retroactive denial.
        config["traffic"] = {
            "segments": [{"duration_seconds": 0.2, "start": 0, "end": 0}],
            "bursts": [
                {"at_seconds": 0.01, "count": 1},
                {"at_seconds": 0.1, "count": 1},
            ],
            "think_seconds": 0,
        }
    run = traffic_rig(tmp_path, config)
    run.inspection.corrupt = fault == "inspection"

    async def respond(request: httpx.Request) -> httpx.Response:
        response = await run.world.api_transport.handle_async_request(request)
        if (
            fault == "unexpected-success"
            and request.url.path == "/api/catches/confirm/"
        ):
            return httpx.Response(204)
        return response

    async def exercise() -> int:
        before = asyncio.all_tasks()
        code = await asyncio.wait_for(
            execute(run, config, api_transport=httpx.MockTransport(respond)), 3
        )
        assert asyncio.all_tasks() - before == set()
        return code

    code = asyncio.run(exercise())
    value = read_report(run.report.path)
    assert value["schema_version"] == 4
    assert value["scenario"]["version"] == 2
    traffic = value["results"]["traffic"]
    assert traffic["reason"] is None
    assert traffic["value"]["plan_digest"]
    assert run.inspection.calls
    if fault is None:
        assert code == 0
        assert value["outcome"] == value["correctness"] == "passed"
        assert traffic["value"]["offered"] == 6
        assert traffic["value"]["completed"] == traffic["value"]["admitted"] > 0
        assert traffic["value"]["stop_reason"] is None
        assert run.fixtures.operations == ["retained_counts", "provision", "cleanup"]
    else:
        assert code == 1
        assert value["outcome"] == (
            "aborted" if fault in {"inspection", "unexpected-success"} else "failed"
        )
        if fault in {"inspection", "unexpected-success"}:
            assert value["safety"]["abort"]["reason"] == "correctness"
        if fault == "unexpected-success":
            assert (
                len(
                    [
                        request
                        for request in run.population.requests
                        if request[2] == "/api/catches/confirm/"
                    ]
                )
                == 1
            )
        assert run.fixtures.operations[-1] == "retain"
        assert "cleanup" not in run.fixtures.operations
        if fault == "attempts":
            assert traffic["value"]["stop_reason"] == "attempts"
            assert traffic["value"]["attempts"] == 64
            # A clean persisted/public comparison alone cannot promote a stopped
            # workload to passed. These are distinct pieces of evidence.
            assert value["results"]["checks"]["reason"] is None
            assert value["results"]["checks"]["items"] == []
    finalized(run)


def test_v2_cancelled_pending_real_confirmation_is_joined_before_retention_and_release(
    tmp_path: Path,
    world: pool_support.World,
) -> None:
    del world
    config = configuration()
    run = traffic_rig(tmp_path, config)
    blocked = BlockedHttp(run.world.api_transport, "/api/catches/confirm/")
    original_inspect = run.inspection.inspect

    async def inspect(*args: Any, **kwargs: Any) -> Any:
        assert blocked.cancelled.is_set()
        return await original_inspect(*args, **kwargs)

    # Inspection is a real privileged external boundary. Its assertion proves
    # the cancelled HTTP worker was awaited before authoritative comparison.
    run.inspection.inspect = inspect

    async def exercise() -> None:
        before = asyncio.all_tasks()
        task = asyncio.create_task(execute(run, config, api_transport=blocked.boundary))
        try:
            await asyncio.wait_for(blocked.entered.wait(), 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)
            assert blocked.cancelled.is_set()
            assert asyncio.all_tasks() - before == set()
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    asyncio.run(exercise())
    assert not [
        path
        for path in blocked.after_cancel
        if not path.endswith("/end")
        and path not in {"/health/identity", "/health/ready"}
    ]
    assert "cleanup" not in run.fixtures.operations
    assert run.fixtures.operations[-1] == "retain"
    value = read_report(run.report.path)
    assert value["outcome"] == "interrupted"
    assert value["failure"] == {"stage": "simulation", "code": "FAIL_INTERRUPTED"}
    assert value["results"]["traffic"]["reason"] is None
    assert value["results"]["traffic"]["value"]["stop_reason"] is not None
    finalized(run)


@pytest.mark.parametrize(
    "body",
    [
        '{"traffic":{"mode":"arrivals","mode":"active"}}',
        '{"traffic":{"token":"SENTINEL-private"}}',
        '{"failure":{"lost_response_rate":NaN}}',
        '{"retry":{"attempts":true}}',
        '{"limits":{"attempts":0}}',
    ],
)
def test_v2_cli_rejects_invalid_nested_configuration_before_external_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    body: str,
) -> None:
    path = tmp_path / "SENTINEL-config.json"
    path.write_text(body)
    reached: list[str] = []

    def trip(*_args: object, **_kwargs: object) -> Any:
        reached.append("external")
        raise AssertionError("invalid nested configuration reached external work")

    monkeypatch.setattr(socket.socket, "connect", trip)
    monkeypatch.setattr(subprocess, "Popen", trip)
    monkeypatch.setattr(getpass, "getpass", trip)
    assert (
        main(
            [
                "convention",
                "--pool",
                "p1",
                "--family",
                "baseline",
                "--scenario-version",
                "2",
                "--config",
                str(path),
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert "SENTINEL" not in output.out + output.err
    assert "FAIL configuration" in output.out
    assert reached == []
    assert not (tmp_path / "reports").exists()


def test_cli_explicit_v2_creates_schema3_before_source_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Source verification is a filesystem boundary; an empty root must reject
    # provenance after the real CLI has resolved v2 and durably created evidence.
    module = importlib.import_module("tailtag_simulator.__main__")
    monkeypatch.setattr(module, "REPOSITORY_ROOT", tmp_path / "absent-source")
    root = tmp_path / "reports"
    assert (
        main(
            [
                "convention",
                "--pool",
                "p1",
                "--family",
                "baseline",
                "--scenario-version",
                "2",
                "--report-dir",
                str(root),
            ]
        )
        == 1
    )
    output = capsys.readouterr()
    assert "FAIL provenance" in output.out
    paths = list(root.rglob("*.json"))
    assert len(paths) == 1
    value = read_report(paths[0])
    assert value["schema_version"] == 4
    assert value["scenario"]["version"] == 2
    assert value["failure"] == {"stage": "provenance", "code": "FAIL_PROVENANCE"}


def test_successful_cli_v2_forwards_version_to_real_runner(
    tmp_path: Path,
    world: pool_support.World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del world
    config = configuration()
    run = rig(tmp_path / "support")
    module = importlib.import_module("tailtag_simulator.__main__")
    source = tmp_path / "packaged-source"
    simulator = Path(__file__).parents[1]
    checkout = simulator.parents[1]
    files: dict[str, bytes] = {
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
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    manifest = {
        name: hashlib.sha256(content).hexdigest() for name, content in files.items()
    }
    (source / "source.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "simulator_sha": "f" * 40,
                "dependency_lock_sha256": manifest["uv.lock"],
                "manifest": manifest,
            }
        )
    )
    monkeypatch.setattr(module, "REPOSITORY_ROOT", source)
    monkeypatch.setattr(module, "_launcher", lambda: run.leases)
    monkeypatch.setattr(module, "_fixture_launcher", lambda: run.fixtures)

    def inspection_launcher(*_args: object, **_kwargs: object) -> Inspection:
        return run.inspection

    monkeypatch.setattr(
        module, "PopulationInspectionLauncherChannel", inspection_launcher
    )
    monkeypatch.setattr(module, "_prompt_secret", lambda: SECRET)

    # The CLI has no public transport option. Supply only HTTPX's external
    # transport default, leaving real clients, runner and reconciliation intact.
    async def serve(request: httpx.Request) -> httpx.Response:
        boundary = (
            run.world.api_transport
            if request.url.host == "staging.tailtag.app"
            else run.world.clerk_transport
        )
        return await boundary.handle_async_request(request)

    original_init = httpx.AsyncClient.__init__

    def client_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("transport") is None:
            kwargs["transport"] = httpx.MockTransport(serve)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", client_init)
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                key: value
                for key, value in config.items()
                if key not in {"pool", "family"}
            }
        )
    )
    root = tmp_path / "reports"
    assert (
        main(
            [
                "convention",
                "--pool",
                POOL,
                "--family",
                "baseline",
                "--scenario-version",
                "2",
                "--config",
                str(path),
                "--report-dir",
                str(root),
            ]
        )
        == 0
    )
    paths = list(root.rglob("*.json"))
    assert len(paths) == 1
    value = read_report(paths[0])
    assert value["schema_version"] == 4
    assert value["scenario"]["version"] == 2
    assert value["outcome"] == value["correctness"] == "passed"
    assert value["results"]["traffic"]["value"]["offered"] == 6
    assert run.fixtures.operations == ["retained_counts", "provision", "cleanup"]
    assert run.leases.calls_to("release") == [{"run_id": value["run_id"]}]
    assert set(run.world.ended_sessions) == set(run.world.opened_sessions)
