"""#225 AC12-17: real population orchestration, offline input and renewal loss."""

import asyncio
import getpass
import importlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import pool_support
import pytest
from convention_support import CONFIG, BlockedHttp, Rig, rig
from pool_support import RUN_ID, SECRET
from report_support import read_report

from tailtag_simulator.__main__ import main

world = pool_support.world


def assert_finalized(run: Rig) -> None:
    assert run.leases.calls_to("release") == [{"run_id": RUN_ID}]
    assert not {i for i, slot in run.leases.slots.items() if slot.run_id == RUN_ID}
    assert set(run.world.ended_sessions) == set(run.world.opened_sessions)
    evidence = run.report.path.read_text() + "\n".join(run.lines)
    for secret in (SECRET, "SENTINEL", "user_SECRET", "tailtag:catch", "media.example"):
        assert secret not in evidence


def test_population_orchestration_records_variable_actors_and_cleans_before_release(
    tmp_path: Path,
    world: pool_support.World,
) -> None:
    del world
    run = rig(tmp_path)

    async def exercise() -> int:
        before = asyncio.all_tasks()
        code = await run.run()
        assert asyncio.all_tasks() - before == set()
        return code

    assert asyncio.run(exercise()) == 0
    value = read_report(run.report.path)
    assert value["schema_version"] == 4
    assert value["outcome"] == value["correctness"] == "passed"
    assert value["results"]["behavior"]["items"]["casual"]["actors"] == 2
    assert value["results"]["behavior"]["items"]["retry_prone"]["retries"] == 12
    assert run.inspection.calls == [
        {"owner0": 0, "owner1": 1, **{f"attendee{n}": n + 2 for n in range(6)}}
    ]
    assert run.fixtures.operations == ["retained_counts", "provision", "cleanup"]
    assert_finalized(run)


@pytest.mark.parametrize(
    "fault", ["ambiguous-positive", "inspection", "actor-and-inspection", "storage"]
)
def test_failed_population_reconciles_when_usable_retains_and_releases(
    tmp_path: Path,
    world: pool_support.World,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    del world
    run = rig(tmp_path)
    if fault in {"inspection", "actor-and-inspection"}:
        run.inspection.corrupt = True
    if fault in {"ambiguous-positive", "actor-and-inspection"}:
        run.population.fault = "ambiguous-positive"
    if fault == "storage":
        # Failure at a real filesystem boundary after allocation/provision.
        original = os.replace

        def replace(source: Any, destination: Any) -> None:
            if "provision" in run.fixtures.operations:
                raise OSError("SENTINEL-storage-private")
            original(source, destination)

        monkeypatch.setattr(os, "replace", replace)
    assert asyncio.run(run.run()) != 0
    assert run.fixtures.operations[-1] == "retain"
    assert "cleanup" not in run.fixtures.operations
    if fault == "storage":
        assert not run.inspection.calls
        assert "FAIL safety reason=report_failure" in run.lines
        assert not any(line.startswith("PASS reconciliation") for line in run.lines)
    else:
        assert run.inspection.calls
    assert_finalized(run)
    if fault != "storage":
        value = read_report(run.report.path)
        assert value["outcome"] == (
            "aborted" if fault in {"inspection", "actor-and-inspection"} else "failed"
        )
        if fault in {"inspection", "actor-and-inspection"}:
            assert value["safety"]["abort"]["reason"] == "correctness"
        assert value["correctness"] == "failed"
        if fault in {"ambiguous-positive", "actor-and-inspection"}:
            assert value["results"]["behavior"]["failure"] == "FAIL_SIMULATION"
            assert len(run.population.gameplay.catches) == 1


@pytest.mark.parametrize(
    ("stage", "failure"),
    [
        ("setup", "heartbeat"),
        ("simulation", "heartbeat"),
        ("simulation", "count"),
        ("simulation", "interrupt"),
    ],
)
def test_renewal_loss_or_interruption_awaits_worker_before_finalization(
    tmp_path: Path,
    world: pool_support.World,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    failure: str,
) -> None:
    del world
    run = rig(tmp_path)
    if failure == "heartbeat":
        run.leases.fail.add("heartbeat")
    elif failure == "count":
        run.leases.reclaim_before_heartbeat = 1
    path = "/v1/sign_in_tokens" if stage == "setup" else "/api/catches/confirm/"
    blocked = BlockedHttp(
        run.world.clerk_transport if stage == "setup" else run.world.api_transport, path
    )
    fixtures_module = importlib.import_module("tailtag_simulator.fixtures")

    async def timer(seconds: float) -> None:
        assert seconds == 60
        await blocked.entered.wait()
        if failure == "interrupt":
            await asyncio.Event().wait()

    monkeypatch.setattr(fixtures_module.asyncio, "sleep", timer)

    async def exercise() -> int | None:
        before = asyncio.all_tasks()
        task = asyncio.create_task(
            run.run(
                clerk_transport=blocked.boundary if stage == "setup" else None,
                api_transport=blocked.boundary if stage == "simulation" else None,
            )
        )
        try:
            await asyncio.wait_for(blocked.entered.wait(), 3)
            if failure == "interrupt":
                task.cancel()
            try:
                result = await asyncio.wait_for(task, 3)
            except asyncio.CancelledError:
                assert failure == "interrupt"
                result = None
            assert blocked.cancelled.is_set()
            assert asyncio.all_tasks() - before == set()
            return result
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    result = asyncio.run(exercise())
    assert not [
        path
        for path in blocked.after_cancel
        if not path.endswith("/end")
        and path not in {"/health/identity", "/health/ready"}
    ]
    assert "cleanup" not in run.fixtures.operations
    if stage == "setup":
        assert run.fixtures.operations == ["retained_counts"]
    else:
        assert run.fixtures.operations[-1] == "retain"
    assert_finalized(run)
    value = read_report(run.report.path)
    if failure == "interrupt":
        assert result is None  # Operator cancellation must propagate.
        status, code = "interrupted", "FAIL_INTERRUPTED"
    else:
        assert result == 1
        status, code = "failed", "FAIL_LEASE"
        assert "FAIL lease result=FAIL_LEASE" in run.lines
    assert value["outcome"] == status
    assert value["failure"] == {"stage": stage, "code": code}
    assert value["phases"][stage]["status"] == status
    assert value["phases"][stage]["code"] == code


BAD_CONFIGS = [
    '{"casual":1,"casual":2}',
    '{"token":"SENTINEL-private"}',
    '{"pool":"other"}',
    '{"target":"production"}',
    '{"base_url":"https://SENTINEL.example"}',
    '{"family":"soak"}',
    '{"casual":true}',
    '{"casual":26,"casual_budget":8,"active":0,"heavy":0,"retry_prone":0}',
    "[1,2]",
    '{"casual":NaN}',
    '{"SENTINEL":',
    "{}" + " " * 2_000_000,
]


@pytest.mark.parametrize(
    "body",
    BAD_CONFIGS,
    ids=[
        "duplicate",
        "private",
        "pool-override",
        "target-override",
        "url-override",
        "family-override",
        "boolean",
        "overcap",
        "non-object",
        "non-finite",
        "malformed",
        "oversize",
    ],
)
def test_invalid_cli_configuration_is_offline_and_detail_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    body: str,
) -> None:
    path = tmp_path / "SENTINEL-private-config.json"
    path.write_text(body)
    reached: list[str] = []

    def trip(*_args: object, **_kwargs: object) -> Any:
        reached.append("external")
        raise AssertionError("invalid config reached external work")

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
                "--config",
                str(path),
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
        != 0
    )
    output = capsys.readouterr()
    assert "SENTINEL" not in output.out + output.err
    assert reached == []


def test_default_orchestration_clock_refreshes_near_expiry_unix_tokens_before_public_reads(
    tmp_path: Path,
    world: pool_support.World,
) -> None:
    # A normal provider token inside Clerk's existing refresh margin must be
    # refreshed on the next API read. A monotonic clock treats its Unix expiry
    # as far in the future and incorrectly sends the cached token again.
    del world
    from tailtag_simulator.convention import run_convention

    run = rig(tmp_path)
    run.world.clock.now = time.time()
    provider = run.world.clerk_transport

    async def clerk_reply(request: httpx.Request) -> httpx.Response:
        response = await provider.handle_async_request(request)
        if request.url.path.endswith("/tokens"):
            body = json.loads(response.content)
            claims = pool_support.jwt_claims(body["jwt"])
            claims["exp"] = int(time.time()) + 10
            body["jwt"] = pool_support.make_jwt(claims)
            return httpx.Response(response.status_code, json=body)
        return response

    code = asyncio.run(
        run_convention(
            pool_support.POOL,
            config=CONFIG,
            seed=-42,
            prompt_secret=lambda: SECRET,
            lease_channel=run.leases,
            fixture_channel=run.fixtures,
            inspection_channel=run.inspection,
            emit=run.lines.append,
            clerk_transport=httpx.MockTransport(clerk_reply),
            api_transport=run.world.api_transport,
            run_id=RUN_ID,
            report=run.report,
        )
    )
    assert code == 0
    # Compare only harmless mint ordinals, never expose bearer token values.
    claims = [
        pool_support.jwt_claims(
            request.headers["authorization"].removeprefix("Bearer ")
        )
        for request in run.world.api_requests
        if request.headers.get("authorization")
    ]
    mints = [int(str(value["n"])) for value in claims if value["sub"] == "user_SECRET0"]
    assert len(set(mints)) >= 2
    assert_finalized(run)


def test_successful_independent_renewal_repeats_while_public_response_is_pending(
    tmp_path: Path,
    world: pool_support.World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del world
    run = rig(tmp_path)
    blocked = BlockedHttp(run.world.api_transport, "/api/catches/confirm/")
    fixtures_module = importlib.import_module("tailtag_simulator.fixtures")
    ticks = 0

    async def timer(seconds: float) -> None:
        nonlocal ticks
        assert seconds == 60
        await blocked.entered.wait()
        ticks += 1
        if ticks == 3:
            # Two renewals have completed while all allocated identities remain
            # leased. Resume the real API/engine only after that protection.
            assert len(run.leases.indexes("leased")) == 8
            blocked.released.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(fixtures_module.asyncio, "sleep", timer)

    async def exercise() -> int:
        before = asyncio.all_tasks()
        task = asyncio.create_task(run.run(api_transport=blocked.boundary))
        try:
            code = await asyncio.wait_for(task, 3)
            assert asyncio.all_tasks() - before == set()
            return code
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    assert asyncio.run(exercise()) == 0
    assert len(run.leases.calls_to("heartbeat")) >= 2
    assert blocked.released.is_set()
    assert not blocked.cancelled.is_set()
    assert run.fixtures.operations == ["retained_counts", "provision", "cleanup"]
    value = read_report(run.report.path)
    assert value["outcome"] == value["correctness"] == "passed"
    assert_finalized(run)
