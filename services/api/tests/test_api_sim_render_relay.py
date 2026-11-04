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
    monkeypatch.setattr(relay, "active", lambda: True)
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


@pytest.mark.parametrize("phase", ["candidate", "canonical"])
def test_relays_reach_render_staging_in_both_phases(
    relay: ModuleType, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    """#452 AC11: the pools move to Virginia before the cutover, so the relays
    must not fall back to the frozen Railway path in the candidate phase."""
    monkeypatch.setattr(relay._staging_preflight, "_RENDER_STAGING_PHASE", phase)
    assert relay.active() is True
