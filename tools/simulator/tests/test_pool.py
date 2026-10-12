"""Tests for pool provisioning, the launcher channel, naming and the CLI (#219 P-1, P-7, P-8a).

The launcher channel is exercised against a REAL subprocess (a tiny python script
standing in for scripts/api_sim_pool_ssh.py); Clerk and the lease table are the
in-memory boundaries from pool_support.
"""

import asyncio
import getpass
import json
import logging
import socket
import subprocess
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pool_support
import pytest
from pool_support import (
    POOL,
    RUN_ID,
    SECRET,
    FakeChannel,
    World,
    user_json,
)

from tailtag_simulator import clerk
from tailtag_simulator.__main__ import main
from tailtag_simulator.clerk import ClerkFailed, open_admin
from tailtag_simulator.pool import (
    LauncherChannel,
    LeaseFailed,
    pool_display_name,
    pool_handle,
    provision,
    validate_pool_name,
)

world = pool_support.world  # the shared fixture

# -- names ------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["p1", "a", "abc123", "a" * 12])
def test_valid_pool_names_are_returned_unchanged(name: str) -> None:
    assert validate_pool_name(name) == name


@pytest.mark.parametrize(
    "name", ["", "a" * 13, "P1", "p_1", "p-1", "p 1", "p1\n", "é", "../x"]
)
def test_other_pool_names_are_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        validate_pool_name(name)


def test_pool_handle_and_display_name_follow_the_documented_forms() -> None:
    assert pool_handle("p1", 7) == "sp_p1_7"
    assert pool_display_name("p1", 7) == "Sim p1 7"


# -- provision (P-1, P-8a) ---------------------------------------------------------


def run_provision(world: World, channel: FakeChannel, size: int) -> int:
    async def attempt() -> int:
        async with open_admin(SECRET, transport=world.clerk_transport) as admin:
            return await provision(POOL, size, admin=admin, channel=channel)

    return asyncio.run(attempt())


def test_provision_is_idempotent_creates_only_missing_users_and_registers_last(
    world: World,
) -> None:
    world.users.clear()
    channel = FakeChannel(world, slots=0)

    first = run_provision(world, channel, 3)

    # Instance verified first; every Clerk call precedes the single register call.
    assert world.log[:2] == [
        ("backend", "GET /v1/instance"),
        ("backend", "GET /v1/domains"),
    ]
    assert [kind for kind, _ in world.log[:-1]] == ["backend"] * (len(world.log) - 1)
    assert world.log[-1][0] == "channel"
    # Re-running creates nothing; expanding creates only the new index.
    created = [
        first,
        run_provision(world, channel, 3),
        run_provision(world, channel, 4),
    ]
    assert created == [3, 0, 1]
    assert world.created_users == [0, 1, 2, 3]
    assert channel.calls_to("register") == [{"size": 3}, {"size": 3}, {"size": 4}]
    assert set(channel.slots) == {0, 1, 2, 3}


def _unmarked_existing_user(world: World, _: pytest.MonkeyPatch) -> None:
    world.users[1] = user_json(1, public_metadata={"tailtag_synthetic": False})


def _wrong_instance(_: World, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clerk, "INSTANCE_FINGERPRINT", "0" * 16)


@pytest.mark.parametrize(
    "break_world",
    [_unmarked_existing_user, _wrong_instance],
    ids=["unmarked-existing-user", "wrong-instance"],
)
def test_provision_aborts_before_registering_when_any_identity_or_the_instance_is_bad(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    break_world: Callable[[World, pytest.MonkeyPatch], None],
) -> None:
    world.users = {1: world.users[1]}
    break_world(world, monkeypatch)
    channel = FakeChannel(world, slots=0)

    with pytest.raises(ClerkFailed):
        run_provision(world, channel, 3)

    assert channel.calls == []
    assert 1 not in world.created_users
    assert world.tickets == []


# -- LauncherChannel against a real subprocess (P-7, P-12 protocol) ------------------

REQUEST = ("allocate", POOL, {"run_id": RUN_ID, "count": 2, "ttl_seconds": 1800})


def launcher(
    tmp_path: Path,
    stdout: str,
    *,
    code: int = 0,
    hang: bool = False,
    timeout: float = 3,
) -> tuple[LauncherChannel, Path]:
    record = tmp_path / "record.json"
    script = (
        "import json, sys, time\n"
        "stdin = sys.stdin.read()\n"
        f"open({str(record)!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], 'stdin': stdin}}))\n"
        f"time.sleep(30) if {hang} else None\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.exit({code})\n"
    )
    return LauncherChannel(
        [sys.executable, "-c", script], timeout_seconds=timeout
    ), record


def test_request_goes_on_stdin_never_argv_and_pass_returns_the_data(
    tmp_path: Path,
) -> None:
    channel, record = launcher(
        tmp_path, '{"data": {"indexes": [0, 1]}, "result": "PASS"}\n'
    )

    data = asyncio.run(channel.call(*REQUEST))

    assert data == {"indexes": [0, 1]}
    seen = json.loads(record.read_text())
    assert seen["argv"] == []
    assert json.loads(seen["stdin"]) == {
        "operation": "allocate",
        "pool": POOL,
        "arguments": {"run_id": RUN_ID, "count": 2, "ttl_seconds": 1800},
    }


def _pass(data: str = "{}") -> str:
    return f'{{"data": {data}, "result": "PASS"}}'


# stdout, exit code, hang, expected (result, available); None result = anything but PASS
LAUNCHER_FAILURES: dict[str, tuple[str, int, bool, tuple[str | None, int | None]]] = {
    "insufficient": (
        '{"data": {"available": 2}, "result": "FAIL_INSUFFICIENT"}\n',
        1,
        False,
        ("FAIL_INSUFFICIENT", 2),
    ),
    "slot": ('{"data": {}, "result": "FAIL_SLOT"}\n', 1, False, ("FAIL_SLOT", None)),
    "pass-with-nonzero-exit": (_pass(), 1, False, (None, None)),
    "failure-result-with-zero-exit": (
        '{"data": {}, "result": "FAIL_TARGET"}\n',
        0,
        False,
        (None, None),
    ),
    "not-json": ("SENTINEL-OUTPUT not json\n", 0, False, ("FAIL_LAUNCHER", None)),
    "empty": ("", 0, False, ("FAIL_LAUNCHER", None)),
    "json-array": ("[]\n", 0, False, ("FAIL_LAUNCHER", None)),
    "two-objects": (
        _pass() + "\n" + _pass() + "\n",
        0,
        False,
        ("FAIL_LAUNCHER", None),
    ),
    "trailing-text": (
        _pass() + "\nSENTINEL-OUTPUT\n",
        0,
        False,
        ("FAIL_LAUNCHER", None),
    ),
    "timeout": (_pass(), 0, True, ("FAIL_LAUNCHER", None)),
}


@pytest.mark.parametrize("case", LAUNCHER_FAILURES)
def test_launcher_failures_become_a_detail_free_lease_failure(
    tmp_path: Path, case: str
) -> None:
    stdout, code, hang, (result, available) = LAUNCHER_FAILURES[case]
    channel, _ = launcher(tmp_path, stdout, code=code, hang=hang, timeout=0.5)

    with pytest.raises(LeaseFailed) as exc:
        asyncio.run(channel.call(*REQUEST))

    if result is None:
        assert exc.value.result != "PASS"
    else:
        assert (exc.value.result, exc.value.available) == (result, available)
    assert "SENTINEL" not in f"{exc.value}{exc.value!r}"


def test_a_launcher_that_cannot_be_started_is_a_lease_failure() -> None:
    channel = LauncherChannel(["/nonexistent/sim-pool-launcher"])

    with pytest.raises(LeaseFailed) as exc:
        asyncio.run(channel.call(*REQUEST))

    assert exc.value.result == "FAIL_LAUNCHER"


# -- CLI wiring (P-6 recovery commands, staging-only smoke) ---------------------------


@pytest.fixture
def nothing_reached(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    reached: list[str] = []

    def trip(*_args: object, **_kwargs: object) -> None:
        reached.append("touched")
        raise RuntimeError

    monkeypatch.setattr(getpass, "getpass", trip)  # the secret prompt
    monkeypatch.setattr(subprocess, "Popen", trip)  # any launcher child
    monkeypatch.setattr(socket.socket, "connect", trip)  # any network call
    return reached


COMMANDS = {
    "provision": ["pool", "provision", "--size", "3"],
    "status": ["pool", "status"],
    "readmit": ["pool", "readmit", "--index", "1"],
    "pool-smoke": ["pool-smoke", "--count", "2"],
}


@pytest.mark.parametrize("command", COMMANDS)
def test_an_invalid_pool_name_is_rejected_before_any_prompt_launcher_or_network(
    nothing_reached: list[str], monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    # Positive control: the same arguments with a valid pool are accepted. The run
    # itself is stubbed out, so this proves only that parsing and validation pass.
    def accept(coroutine: Coroutine[Any, Any, int]) -> int:
        coroutine.close()
        return 0

    with monkeypatch.context() as control:
        control.setattr(asyncio, "run", accept)
        assert main([*COMMANDS[command], "--pool", POOL]) == 0

    for bad in ["Bad_Pool", "a" * 13, "p1\n"]:
        try:
            code = main([*COMMANDS[command], "--pool", bad])
        except SystemExit as exit_:
            code = exit_.code
        except ValueError:
            code = 1
        assert code not in (0, None)

    assert nothing_reached == []


@pytest.mark.parametrize("command", COMMANDS)
def test_provider_http_loggers_are_silenced_before_any_pool_command_runs(
    nothing_reached: list[str], monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    # httpx logs full URLs (with Clerk user and session IDs) at INFO (P-7, D5).
    # Seam: main() must configure logging itself, before it starts the run.
    loggers = [logging.getLogger(name) for name in ("httpx", "httpcore")]
    for logger in loggers:
        monkeypatch.setattr(logger, "level", logging.NOTSET)
        monkeypatch.setattr(logger, "propagate", True)

    def run_stub(coroutine: Coroutine[Any, Any, int]) -> int:
        coroutine.close()
        return 0

    monkeypatch.setattr(asyncio, "run", run_stub)
    main([*COMMANDS[command], "--pool", POOL])

    for logger in loggers:
        assert logger.level == logging.WARNING
        assert logger.propagate is False


@pytest.mark.parametrize(
    "extra",
    [["--target", "staging"], ["--target", "local"], ["--base-url", "http://x"]],
)
def test_pool_smoke_offers_no_way_to_name_a_target(
    nothing_reached: list[str], extra: list[str]
) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["pool-smoke", "--pool", POOL, "--count", "2", *extra])

    assert exit_.value.code == 2
    assert nothing_reached == []
