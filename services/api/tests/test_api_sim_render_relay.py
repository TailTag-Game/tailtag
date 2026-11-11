"""#411 AC3/AC5: the simulation relays reach Render Staging over pinned plain ssh."""

from __future__ import annotations

import importlib
import io
import json
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

SERVICE = "srv-d0staging000000000000"
INSTANCE = f"{SERVICE}-874b544b8-k7qws"
OTHER_INSTANCE = f"{SERVICE}-54fcd9cd8d-wthkj"
IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": None,
    "environment": "staging",
}
GATEWAY_KEY = (
    "ssh.virginia.render.com ssh-ed25519 "
    "AAAAC3NzaC1lZDI1NTE5AAAAIJ6uO0jKQX9IjefnLz+pxTgfPhsPBhNuvxmvCFrxqxAM\n"
)
CALLER_REQUEST: dict[str, object] = {
    "operation": "status",
    "pool": "privatepool",
    "arguments": {},
}
PASS = {"result": "PASS", "data": {"total": 2}}
FAILURE: dict[str, object] = {"result": "FAIL_LAUNCHER", "data": {}}


@pytest.fixture
def relay() -> ModuleType:
    return importlib.import_module("scripts.api_sim_render_relay")


@pytest.fixture
def launcher() -> ModuleType:
    return importlib.import_module("scripts.api_sim_pool_ssh")


Run = Callable[..., subprocess.CompletedProcess[str]]


def install(
    relay: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    reply: object,
    *,
    returncode: int = 0,
) -> list[dict[str, Any]]:
    """Replace the public identity, the manifest pin and ssh; record each ssh call."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(relay._staging_preflight, "_RENDER_STAGING_PHASE", "canonical")
    monkeypatch.setattr(relay, "_identity", lambda: dict(IDENTITY))
    monkeypatch.setattr(relay, "_service_id", lambda: SERVICE)

    def run(
        arguments: list[str], *, input: str | None = None, timeout: int
    ) -> subprocess.CompletedProcess[str]:
        known_hosts = next(
            option.split("=", 1)[1].strip('"')
            for option in arguments
            if option.startswith("UserKnownHostsFile=")
        )
        calls.append(
            {
                "arguments": arguments,
                "input": json.loads(input or "null"),
                "known_hosts": Path(known_hosts).read_text(encoding="utf-8"),
                "timeout": timeout,
            }
        )
        return subprocess.CompletedProcess(arguments, returncode, json.dumps(reply), "")

    monkeypatch.setattr(relay, "_run", run)
    return calls


def invoke(launcher: ModuleType, request: dict[str, object]) -> tuple[int, object]:
    stdout = io.StringIO()
    code = launcher.main([], stdin=io.StringIO(json.dumps(request)), stdout=stdout)
    return code, json.loads(stdout.getvalue())


def test_first_call_uses_the_service_user_and_relays_the_instance(
    relay: ModuleType, launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = install(relay, monkeypatch, {**PASS, "instance": INSTANCE})

    code, response = invoke(
        launcher, {**CALLER_REQUEST, "expected_identity": dict(IDENTITY)}
    )

    assert (code, response) == (0, {**PASS, "instance": INSTANCE})
    [call] = calls
    arguments = call["arguments"]
    assert arguments[:2] == ["ssh", "-T"]
    options = {arguments[i + 1] for i, part in enumerate(arguments) if part == "-o"}
    assert {
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        "GlobalKnownHostsFile=/dev/null",
        "IdentitiesOnly=yes",
        "ForwardAgent=no",
        "UpdateHostKeys=no",
        "ControlMaster=no",
        "ControlPath=none",
        "KnownHostsCommand=none",
        "PermitLocalCommand=no",
        "ProxyCommand=none",
    } <= options
    assert call["known_hosts"] == GATEWAY_KEY
    assert arguments[-2] == f"{SERVICE}@ssh.virginia.render.com"
    assert shlex.split(arguments[-1])[:3] == ["/app/.venv/bin/python", "-I", "-c"]
    assert call["input"] == {**CALLER_REQUEST, "identity": IDENTITY}
    assert "privatepool" not in " ".join(arguments)


def test_a_pinned_call_uses_the_exact_instance_user(
    relay: ModuleType, launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = install(relay, monkeypatch, {**PASS, "instance": INSTANCE})

    code, response = invoke(launcher, {**CALLER_REQUEST, "expected_instance": INSTANCE})

    assert (code, response) == (0, {**PASS, "instance": INSTANCE})
    [call] = calls
    assert call["arguments"][-2] == f"{SERVICE}-k7qws@ssh.virginia.render.com"
    assert call["input"]["expected_instance"] == INSTANCE


def test_a_replaced_instance_is_relayed_as_a_target_failure(
    relay: ModuleType, launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(relay, monkeypatch, {"result": "FAIL_TARGET", "data": {}})

    code, response = invoke(launcher, {**CALLER_REQUEST, "expected_instance": INSTANCE})

    assert (code, response) == (1, {"result": "FAIL_TARGET", "data": {}})


def test_a_changed_public_identity_fails_before_any_ssh(
    relay: ModuleType, launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = install(relay, monkeypatch, {**PASS, "instance": INSTANCE})
    expected = {**IDENTITY, "source_sha": "b" * 40}

    code, response = invoke(launcher, {**CALLER_REQUEST, "expected_identity": expected})

    assert (code, response) == (1, {"result": "FAIL_TARGET", "data": {}})
    assert calls == []


@pytest.mark.parametrize(
    ("request_overrides", "reply", "returncode"),
    [
        # A pin for another service or a malformed pin never reaches ssh.
        ({"expected_instance": "srv-d0other0000000000000-874b544b8-k7qws"}, PASS, 0),
        ({"expected_instance": f"{SERVICE}-k7qws"}, PASS, 0),
        # A Railway identity is not a Render Staging identity.
        (
            {
                "expected_identity": {
                    **IDENTITY,
                    "deployment_id": "11111111-1111-4111-8111-111111111111",
                }
            },
            PASS,
            0,
        ),
        # The reply must name the pinned instance of the pinned service.
        ({}, PASS, 0),
        ({}, {**PASS, "instance": "srv-d0other0000000000000-874b544b8-k7qws"}, 0),
        ({"expected_instance": INSTANCE}, {**PASS, "instance": OTHER_INSTANCE}, 0),
        ({}, {**PASS, "instance": INSTANCE, "extra": 1}, 0),
        ({}, {**PASS, "instance": INSTANCE}, 255),
    ],
    ids=[
        "pin-other-service",
        "pin-without-hex",
        "railway-expected-identity",
        "pass-without-instance",
        "instance-other-service",
        "instance-differs-from-pin",
        "extra-reply-key",
        "ssh-failed",
    ],
)
def test_every_deviation_fails_closed_as_a_launcher_failure(
    relay: ModuleType,
    launcher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    request_overrides: dict[str, object],
    reply: object,
    returncode: int,
) -> None:
    install(relay, monkeypatch, reply, returncode=returncode)

    code, response = invoke(launcher, {**CALLER_REQUEST, **request_overrides})

    assert (code, response) == (1, FAILURE)


@pytest.mark.parametrize(
    ("name", "caller_request", "reply"),
    [
        ("scripts.api_sim_pool_ssh", CALLER_REQUEST, PASS),
        (
            "scripts.api_sim_fixture_ssh",
            {"operation": "retained", "arguments": {}},
            {"result": "PASS", "data": {"retained": 0}},
        ),
        (
            "scripts.api_sim_inspect_ssh",
            {
                "operation": "inspect",
                "arguments": {
                    "pool": "privatepool",
                    "run_id": "55555555-5555-4555-8555-555555555555",
                    "identities": {"owner0": 1},
                },
            },
            {"result": "FAIL_RUN_UNKNOWN", "data": {}},
        ),
    ],
)
def test_each_launcher_sends_its_own_bootstrap_through_the_render_relay(
    relay: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    caller_request: dict[str, object],
    reply: dict[str, object],
) -> None:
    module = importlib.import_module(name)
    calls = install(relay, monkeypatch, {**reply, "instance": INSTANCE})

    code, response = invoke(module, caller_request)

    assert response == {**reply, "instance": INSTANCE}
    assert code == (0 if reply["result"] == "PASS" else 1)
    [call] = calls
    assert shlex.split(call["arguments"][-1])[3] == module._BOOTSTRAP


_Case = tuple[str, dict[str, object], dict[str, object]]
_POOL_CASE: _Case = (
    "scripts.api_sim_pool_ssh",
    CALLER_REQUEST,
    {"result": "PASS", "data": {"indexes": [0, 1]}},
)
_FIXTURE_CASE: _Case = (
    "scripts.api_sim_fixture_ssh",
    {"operation": "retained", "arguments": {}},
    {"result": "PASS", "data": {"status": "provisioned", "counts": {"fursuit": 2}}},
)
_INSPECT_CASE: _Case = (
    "scripts.api_sim_inspect_ssh",
    {
        "operation": "inspect",
        "arguments": {
            "pool": "privatepool",
            "run_id": "55555555-5555-4555-8555-555555555555",
            "identities": {"owner0": 1},
        },
    },
    {
        "result": "PASS",
        "data": {
            "catches": [],
            "fursuits": [{"id": 35, "owner": 5}],
            "fixture_photos_unchanged": True,
            "avatars": [3, 5],
        },
    },
)


@pytest.mark.parametrize("pin", ["matching", "changed-sha", "malformed"])
@pytest.mark.parametrize(
    ("name", "caller_request", "reply"),
    [_POOL_CASE, _FIXTURE_CASE, _INSPECT_CASE],
    ids=["pool", "fixture", "inspect"],
)
def test_expected_run_identity_is_checked_before_ssh_and_stripped_from_remote_wire(
    relay: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    caller_request: dict[str, object],
    reply: dict[str, object],
    pin: str,
) -> None:
    """#227 AC11: a new Staging deployment cannot silently replace the run target.

    The matching case also relays one exact valid payload through each launcher's
    own output validator.
    """
    module = importlib.import_module(name)
    calls = install(relay, monkeypatch, {**reply, "instance": INSTANCE})
    expected: dict[str, object] = dict(IDENTITY)
    if pin == "changed-sha":
        expected["source_sha"] = "b" * 40
    elif pin == "malformed":
        expected["SENTINEL-secret"] = "private"

    code, response = invoke(module, {**caller_request, "expected_identity": expected})

    if pin == "matching":
        assert (code, response) == (0, {**reply, "instance": INSTANCE})
        [call] = calls
        assert call["input"] == {**caller_request, "identity": IDENTITY}
    else:
        assert code == 1
        assert response == (
            FAILURE if pin == "malformed" else {"result": "FAIL_TARGET", "data": {}}
        )
        assert calls == []
    assert "SENTINEL" not in json.dumps(response)


_LISTED_RUN = {
    "run_id": "55555555-5555-4555-8555-555555555555",
    "pool": "alpha",
    "reason": "journeys",
    "age_days": 3,
}
_FIXTURE_COUNTS = {"convention": 1, "enrollment": 3, "fursuit": 2, "activation": 2}
_CATCH: dict[str, object] = {
    "id": 11,
    "catcher": 8,
    "fursuit": 34,
    "fursuit_owner": 5,
    "run_convention": True,
    "provenance": True,
    "in_window": True,
    "caught_at": "2026-10-03T19:41:53.769123Z",
}
_FOREIGN_CATCH: dict[str, object] = {
    **_CATCH,
    "id": 12,
    "catcher": None,
    "fursuit_owner": None,
    "run_convention": False,
    "provenance": False,
    "in_window": False,
    "caught_at": "2026-10-03T19:41:53Z",
}
_FIXTURE_PASSES: list[dict[str, object]] = [
    {"result": "PASS", "data": _FIXTURE_COUNTS},
    {"result": "PASS", "data": {"status": "provisioned", "counts": _FIXTURE_COUNTS}},
    {
        "result": "PASS",
        "data": {
            **_FIXTURE_COUNTS,
            "catch": 1,
            "session": 1,
            "credential": 2,
            "image": 4,
            "readmitted": 5,
        },
    },
    {"result": "PASS", "data": {"quarantined": 4}},
    {
        "result": "PASS",
        "data": {
            "runs": [_LISTED_RUN, {**_LISTED_RUN, "reason": "unfinished"}],
            "retained": 1,
            "unfinished": 1,
        },
    },
    {"result": "PASS", "data": {"runs": [], "retained": 0, "unfinished": 0}},
]
_FIXTURE_FAILURES = (
    "FAIL_REQUEST",
    "FAIL_TARGET",
    "FAIL_RUN_EXISTS",
    "FAIL_LEASE",
    "FAIL_INVARIANT",
    "FAIL_ERROR",
    "FAIL_RUN_UNKNOWN",
    "FAIL_BOOTSTRAP",
    "FAIL_ATTRIBUTION",
    "FAIL_STORAGE",
    "FAIL_VERIFY",
    "FAIL_LIMIT",
)
_INSPECT_REPLIES: list[dict[str, object]] = [
    {
        "result": "PASS",
        "data": {
            "catches": [_CATCH, _FOREIGN_CATCH],
            "fursuits": [{"id": 35, "owner": 5}],
            "fixture_photos_unchanged": True,
            "avatars": [3, 5],
        },
    },
    *(
        {"result": code, "data": {}}
        for code in (
            "FAIL_REQUEST",
            "FAIL_TARGET",
            "FAIL_LEASE",
            "FAIL_RUN_UNKNOWN",
            "FAIL_LIMIT",
            "FAIL_BOOTSTRAP",
        )
    ),
]
# Each launcher: the relay timeout it must pass, and every valid result shape.
_VALID_RESULTS: list[tuple[str, int, dict[str, object]]] = [
    ("scripts.api_sim_pool_ssh", 30, {"result": "PASS", "data": {"indexes": [0, 1]}}),
    (
        "scripts.api_sim_pool_ssh",
        30,
        {"result": "FAIL_INSUFFICIENT", "data": {"available": 1}},
    ),
    ("scripts.api_sim_pool_ssh", 30, {"result": "FAIL_TARGET", "data": {}}),
    *(("scripts.api_sim_fixture_ssh", 150, reply) for reply in _FIXTURE_PASSES),
    (
        "scripts.api_sim_fixture_ssh",
        150,
        {"result": "FAIL_DIRTY", "data": {"quarantined": 2}},
    ),
    *(
        ("scripts.api_sim_fixture_ssh", 150, {"result": code, "data": {}})
        for code in _FIXTURE_FAILURES
    ),
    *(("scripts.api_sim_inspect_ssh", 30, reply) for reply in _INSPECT_REPLIES),
]
_REQUESTS = {case[0]: case[1] for case in (_POOL_CASE, _FIXTURE_CASE, _INSPECT_CASE)}


@pytest.mark.parametrize(("name", "timeout", "remote"), _VALID_RESULTS)
def test_each_launcher_relays_every_valid_result_shape_with_its_timeout(
    relay: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    timeout: int,
    remote: dict[str, object],
) -> None:
    """The output validator accepts each shape a remote sends, within the timeout."""
    module = importlib.import_module(name)
    calls = install(relay, monkeypatch, {**remote, "instance": INSTANCE})

    code, response = invoke(module, _REQUESTS[name])

    assert code == (0 if remote["result"] == "PASS" else 1)
    assert response == {**remote, "instance": INSTANCE}
    assert [call["timeout"] for call in calls] == [timeout]


_STUB_REMOTE = (
    "def execute(request, *, runtime_identity, environ):\n"
    f"    return {{'result': 'PASS', 'data': {{}}, 'instance': {INSTANCE!r}}}\n"
)
_STUBS = {
    "django/__init__.py": "def setup():\n    pass\n",
    "config/__init__.py": "",
    "config/build_identity.py": "def get_identity():\n    return {}\n",
    "simulation_pool/__init__.py": "",
    "simulation_pool/remote.py": _STUB_REMOTE,
    "simulation_fixtures/__init__.py": "",
    "simulation_fixtures/remote.py": _STUB_REMOTE,
    "simulation_fixtures/inspection_remote.py": _STUB_REMOTE,
}


@pytest.mark.parametrize(
    "name",
    [
        "scripts.api_sim_pool_ssh",
        "scripts.api_sim_fixture_ssh",
        "scripts.api_sim_inspect_ssh",
    ],
)
def test_each_in_image_bootstrap_prints_the_instance_it_ran_on(
    tmp_path: Path, name: str
) -> None:
    """The bootstrap is the seam between the remote reply and the launcher check."""
    for relative, text in _STUBS.items():
        path = tmp_path / "app" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    bootstrap: str = importlib.import_module(name)._BOOTSTRAP  # pyright: ignore[reportPrivateUsage]

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            bootstrap.replace('"/app"', repr(str(tmp_path / "app"))),
        ],
        input="{}",
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert json.loads(completed.stdout) == {
        "result": "PASS",
        "data": {},
        "instance": INSTANCE,
    }


def test_candidate_phase_refuses_before_any_identity_read_or_ssh(
    relay: ModuleType, launcher: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#452 AC11: the simulator targets staging.tailtag.app, which serves Oregon
    until the cutover, so a Virginia relay would split one run across two
    databases."""
    calls = install(relay, monkeypatch, PASS)
    monkeypatch.setattr(relay._staging_preflight, "_RENDER_STAGING_PHASE", "candidate")

    def no_identity() -> dict[str, object]:
        raise AssertionError("identity read")

    monkeypatch.setattr(relay, "_identity", no_identity)
    code, response = invoke(
        launcher, {**CALLER_REQUEST, "expected_identity": dict(IDENTITY)}
    )

    assert (code, response) == (1, {"result": "FAIL_TARGET", "data": {}})
    assert calls == []
