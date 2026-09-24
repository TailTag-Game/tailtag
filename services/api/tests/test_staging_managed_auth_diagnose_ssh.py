"""Acceptance tests for the one-shot, read-only #243 managed credential diagnosis."""

from __future__ import annotations

import getpass
import hashlib
import importlib
import json
import os
import pty
import select
import signal
import subprocess
import sys
import termios
import time
import warnings
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

import pytest
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext, override_settings
from pytest_django.fixtures import SettingsWrapper

from accounts.models import User
from tests.test_staging_operator_inspector import (
    DEPLOYMENT_ID,
    RUNTIME_SELECTORS,
    SOURCE_SHA,
    UserWithRoles,
    create_limited_operator,
    create_managed_operator,
    create_owned_baseline,
    permission_map,
)

ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = ROOT / "scripts" / "api_staging_managed_auth_diagnose_ssh.py"
REMOTE_PATH = ROOT / "scripts" / "api_staging_managed_auth_diagnose.py"
IDENTITY = {
    "source_sha": SOURCE_SHA,
    "deployment_id": DEPLOYMENT_ID,
    "environment": "staging",
}
INSTANCE = "22222222-2222-4222-8222-222222222222"
WINDOW = ["2026-09-23T00:00:00Z", "2026-09-23T00:00:01Z"]
IDENTIFIER = "managed-operator"
PASSWORD = "local-inspector-test-password"
PRIVATE = "private-identifier-password-and-provider-diagnostic"


class Terminal(StringIO):
    def __init__(self, *, attached: bool = True) -> None:
        super().__init__()
        self.attached = attached

    def isatty(self) -> bool:
        return self.attached


@pytest.fixture
def runner() -> ModuleType:
    assert RUNNER_PATH.is_file(), "the approved managed-auth launcher must exist"
    return importlib.import_module("scripts.api_staging_managed_auth_diagnose_ssh")


@pytest.fixture
def remote() -> ModuleType:
    assert REMOTE_PATH.is_file(), "the approved managed-auth remote source must exist"
    return importlib.import_module("scripts.api_staging_managed_auth_diagnose")


def inspector_pass(*, identity: object = IDENTITY) -> dict[str, object]:
    return {
        "result": "PASS",
        "phase": "exact_instance_inspector",
        "identity": identity,
        "target_verified": True,
        "window_utc": WINDOW,
    }


def install_launcher_guards(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    """Replace provider boundaries, keeping public launcher behavior under test."""
    events: list[str] = []

    def inspect() -> dict[str, object]:
        events.append("inspector")
        return inspector_pass()

    def railway() -> None:
        events.append("railway")

    def preflight() -> dict[str, str]:
        events.append("preflight")
        return dict(IDENTITY)

    def receipt(identity: dict[str, str]) -> None:
        assert identity == IDENTITY
        events.append("receipt")

    def instance(identity: dict[str, str]) -> str:
        assert identity == IDENTITY
        events.append("instance")
        return INSTANCE

    monkeypatch.setattr(runner._inspector, "run", inspect)
    monkeypatch.setattr(runner, "_railway_identity", railway)
    monkeypatch.setattr(runner, "_preflight", preflight)
    monkeypatch.setattr(runner, "_approved_receipt", receipt)
    monkeypatch.setattr(runner, "_active_instance", instance)
    monkeypatch.setattr(runner.sys, "stdin", Terminal())
    monkeypatch.setattr(runner.sys, "stdout", Terminal())
    return events


def assert_public_launcher_result(
    result: dict[str, object], *, code: str, target_verified: bool
) -> None:
    assert set(result) == {
        "result",
        "phase",
        "identity",
        "target_verified",
        "window_utc",
    }
    assert result["result"] == code
    assert result["target_verified"] is target_verified
    assert result["identity"] in (None, IDENTITY)
    assert isinstance(result["phase"], str)
    assert isinstance(result["window_utc"], list)
    assert len(cast(list[object], result["window_utc"])) == 2
    rendered = json.dumps(result)
    assert PRIVATE not in rendered
    assert IDENTIFIER not in rendered
    assert PASSWORD not in rendered
    assert INSTANCE not in rendered


def unexpected_ssh(_arguments: list[str]) -> NoReturn:
    pytest.fail("SSH must not start")


def stored_password(user: User) -> str:
    return cast(str, user.password)  # pyright: ignore[reportUnknownMemberType]


def test_launcher_uses_fresh_exact_instance_guards_and_one_interactive_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 1/2/4: pin one instance; public argv cannot carry credentials."""
    events = install_launcher_guards(runner, monkeypatch)
    invocations: list[list[str]] = []

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("ssh")
        invocations.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run())

    assert_public_launcher_result(
        result, code="TRANSPORT_EXITED_ZERO_UNVERIFIED", target_verified=False
    )
    assert result["phase"] == "exact_instance_auth_diagnosis"
    assert events == [
        "inspector",
        "railway",
        "preflight",
        "receipt",
        "instance",
        "preflight",
        "railway",
        "ssh",
    ]
    assert len(invocations) == 1
    arguments = invocations[0]
    assert arguments[:2] == ["railway", "ssh"]
    assert arguments[arguments.index("--deployment-instance") + 1] == INSTANCE
    assert arguments[arguments.index("--project") + 1] == runner._PROJECT_ID
    assert arguments[arguments.index("--service") + 1] == runner._SERVICE_ID
    assert arguments[arguments.index("--environment") + 1] == runner._ENVIRONMENT_ID
    assert arguments[arguments.index("-c") - 1] == "-I"
    assert "DJANGO_SETTINGS_MODULE=config.settings.production" in arguments
    request = json.loads(arguments[-1])
    assert request["identity"] == IDENTITY
    assert request["source"] == REMOTE_PATH.read_text(encoding="utf-8")
    assert PRIVATE not in json.dumps(request)
    assert PASSWORD not in json.dumps(request)
    assert IDENTIFIER not in json.dumps(request)


def test_interactive_ssh_allows_the_full_human_prompt_window(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 2: two hidden human inputs retain the 30-minute SSH window."""
    observed: list[dict[str, object]] = []

    def execute(
        arguments: list[str], **options: object
    ) -> subprocess.CompletedProcess[str]:
        observed.append(options)
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner.subprocess, "run", execute)

    runner._run(["railway", "ssh"])

    assert len(observed) == 1
    assert observed[0]["timeout"] == 1800
    assert observed[0].get("stdin") is None
    assert observed[0]["stdout"] is None
    assert observed[0]["stderr"] is subprocess.PIPE


@pytest.mark.parametrize("detached", ["stdin", "stdout"])
def test_launcher_refuses_missing_terminal_before_inspection(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, detached: str
) -> None:
    """Contract 2: no credentials or provider calls over a detached terminal."""
    events: list[str] = []
    monkeypatch.setattr(runner.sys, "stdin", Terminal(attached=detached != "stdin"))
    monkeypatch.setattr(runner.sys, "stdout", Terminal(attached=detached != "stdout"))
    monkeypatch.setattr(runner._inspector, "run", lambda: events.append("inspector"))
    monkeypatch.setattr(runner, "_railway_identity", lambda: events.append("railway"))

    result = cast(dict[str, object], runner.run())

    assert result["result"] == "FAIL_INTERACTIVE_INPUT"
    assert events == []


@pytest.mark.parametrize(
    "bad_evidence",
    [
        {**inspector_pass(), "result": "FAIL_MANAGED_OPERATOR_PERMISSION"},
        {**inspector_pass(), "target_verified": False},
        {**inspector_pass(), "phase": "public_preflight"},
        {**inspector_pass(), "identity": {**IDENTITY, "source_sha": "b" * 40}},
    ],
)
def test_launcher_requires_canonical_pass_for_both_roles(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    bad_evidence: dict[str, object],
) -> None:
    """Contract 1: a status string or wrong target cannot unlock a password prompt."""
    events = install_launcher_guards(runner, monkeypatch)
    monkeypatch.setattr(runner._inspector, "run", lambda: bad_evidence)
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run())

    if bad_evidence["identity"] != IDENTITY:
        assert result["result"] == "FAIL_TARGET_CHANGED"
        assert events == ["railway", "preflight"]
    else:
        assert result["result"] == "FAIL_INSPECTOR"
        assert events == []


def test_launcher_preserves_fatal_inspector_identity_failure(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 1: an identity failure remains fatal before SSH or secret input."""
    events = install_launcher_guards(runner, monkeypatch)
    monkeypatch.setattr(
        runner._inspector,
        "run",
        lambda: {
            "result": "FAIL_IDENTITY",
            "phase": "railway_identity",
            "identity": None,
            "target_verified": False,
            "window_utc": WINDOW,
        },
    )
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run())

    assert_public_launcher_result(result, code="FAIL_IDENTITY", target_verified=False)
    assert events == []


def test_launcher_maps_inspector_unusable_hash_without_starting_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 1/4: the mandatory inspector names missing local auth safely."""
    install_launcher_guards(runner, monkeypatch)
    monkeypatch.setattr(
        runner._inspector,
        "run",
        lambda: {
            **inspector_pass(),
            "result": "FAIL_MANAGED_OPERATOR_PASSWORD_UNUSABLE",
        },
    )
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run())

    assert_public_launcher_result(
        result, code="PASSWORD_UNUSABLE", target_verified=False
    )


@pytest.mark.parametrize(
    "fault", ["phase", "target_verified", "invalid_identity", "missing_identity"]
)
def test_launcher_rejects_noncanonical_inspector_unusable_hash_evidence(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    """Contract 1/4: an unusable-hash code alone does not bypass target proof."""
    events = install_launcher_guards(runner, monkeypatch)
    evidence = {
        **inspector_pass(),
        "result": "FAIL_MANAGED_OPERATOR_PASSWORD_UNUSABLE",
    }
    if fault == "phase":
        evidence["phase"] = "public_preflight"
    elif fault == "target_verified":
        evidence["target_verified"] = False
    elif fault == "invalid_identity":
        evidence["identity"] = {**IDENTITY, "source_sha": "invalid"}
    else:
        evidence["identity"] = None
    monkeypatch.setattr(runner._inspector, "run", lambda: evidence)
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run())

    assert_public_launcher_result(result, code="FAIL_INSPECTOR", target_verified=False)
    assert events == []


@pytest.mark.parametrize("failed_check", [1, 2])
def test_launcher_preserves_fatal_fresh_railway_identity_failure(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    failed_check: int,
) -> None:
    """Contract 1: either fresh acting-account check fails closed before SSH."""
    events = install_launcher_guards(runner, monkeypatch)
    attempts = 0

    def railway_identity() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == failed_check:
            raise ValueError(PRIVATE)
        events.append("railway")

    monkeypatch.setattr(runner, "_railway_identity", railway_identity)
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run())

    assert_public_launcher_result(result, code="FAIL_IDENTITY", target_verified=False)
    assert attempts == failed_check
    assert PRIVATE not in json.dumps(result)


@pytest.mark.parametrize(
    ("guard", "completed_guards"),
    [
        ("railway", []),
        ("preflight", ["railway"]),
        ("receipt", ["railway", "preflight"]),
        ("instance", ["railway", "preflight", "receipt"]),
    ],
)
def test_launcher_stops_before_ssh_on_each_fresh_guard_failure(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    guard: str,
    completed_guards: list[str],
) -> None:
    """Contract 1: approved receipt and exact instance are fresh prerequisites."""
    events = install_launcher_guards(runner, monkeypatch)
    seam = {
        "railway": "_railway_identity",
        "preflight": "_preflight",
        "receipt": "_approved_receipt",
        "instance": "_active_instance",
    }[guard]

    def unavailable(*_args: object) -> None:
        raise ValueError(PRIVATE)

    monkeypatch.setattr(runner, seam, unavailable)
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run())

    assert str(result["result"]).startswith("FAIL_")
    assert PRIVATE not in json.dumps(result)
    assert events == ["inspector", *completed_guards]


def test_launcher_refuses_preflight_drift_after_instance_selection(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 1: a deployment change invalidates the selected SSH target."""
    events = install_launcher_guards(runner, monkeypatch)
    observations = iter(
        [
            IDENTITY,
            {**IDENTITY, "deployment_id": "33333333-3333-4333-8333-333333333333"},
        ]
    )
    monkeypatch.setattr(runner, "_preflight", lambda: next(observations))
    monkeypatch.setattr(runner, "_run", unexpected_ssh)

    result = cast(dict[str, object], runner.run())

    assert result["result"] == "FAIL_TARGET_CHANGED"
    assert events == ["inspector", "railway", "receipt", "instance"]


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (
            subprocess.CompletedProcess(["railway"], 1, None, PRIVATE),
            "FAIL_TRANSPORT_EXIT_STATUS",
        ),
        (
            subprocess.CompletedProcess(["railway"], 0, None, PRIVATE),
            "FAIL_TRANSPORT_STDERR",
        ),
        (
            subprocess.TimeoutExpired("railway ssh", 120, output=PRIVATE),
            "FAIL_TRANSPORT_TIMEOUT",
        ),
        (KeyboardInterrupt(), "FAIL_TRANSPORT_EXECUTION"),
    ],
)
def test_launcher_transport_uncertainty_is_sanitized_and_never_retried(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    outcome: object,
    expected: str,
) -> None:
    """Contract 4: no exit code, stderr, or interrupted SSH implies acceptance."""
    install_launcher_guards(runner, monkeypatch)
    attempts = 0

    def execute(_arguments: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return cast(subprocess.CompletedProcess[str], outcome)

    monkeypatch.setattr(runner, "_run", execute)

    result = cast(dict[str, object], runner.run())

    assert_public_launcher_result(result, code=expected, target_verified=False)
    assert attempts == 1


def test_remote_bootstrap_rejects_malformed_public_request_without_echoing_it(
    runner: ModuleType,
) -> None:
    """Contract 2/4: even protocol errors have no raw request/output channel."""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", runner._BOOTSTRAP, PRIVATE],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert completed.returncode != 0
    assert PRIVATE not in completed.stdout + completed.stderr
    assert "CREDENTIAL_ACCEPTED" not in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    ("reported_identity", "reported_window"),
    [
        (None, WINDOW),
        (IDENTITY, ["invalid-time", "invalid-time"]),
    ],
)
def test_bootstrap_never_marks_malformed_remote_acceptance_complete(
    runner: ModuleType,
    reported_identity: object,
    reported_window: list[str],
) -> None:
    """Contract 4: the completion marker needs exact public remote evidence."""
    source = (
        "def run(expected_identity):\n"
        "    return {'classification': 'CREDENTIAL_ACCEPTED', "
        f"'identity': {reported_identity!r}, 'window_utc': {reported_window!r}}}\n"
    )
    inspector_source = "def _bootstrap():\n    pass\n"
    request = {
        "source": source,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "inspector_source": inspector_source,
        "inspector_sha256": hashlib.sha256(inspector_source.encode()).hexdigest(),
        "identity": IDENTITY,
    }
    completed = subprocess.run(
        [sys.executable, "-I", "-c", runner._BOOTSTRAP, json.dumps(request)],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert completed.returncode != 0
    assert "DIAGNOSIS_COMPLETED" not in completed.stdout + completed.stderr
    assert PRIVATE not in completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["classification"] == "EXECUTION_FAILURE"


def prepare_exact_roles() -> User:
    create_owned_baseline()
    managed = create_managed_operator()
    create_limited_operator()
    return managed


def configure_remote_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fake only the established build-identity provider used by the inspector."""
    for name, value in RUNTIME_SELECTORS.items():
        monkeypatch.setenv(name, value)
    inspector = importlib.import_module("scripts.api_staging_operator_inspect")
    monkeypatch.setattr(inspector, "get_identity", lambda: IDENTITY)


def attach_synthetic_terminal(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> Terminal:
    """Attach a terminal-shaped stream for pre-prompt control-path tests."""
    output = Terminal()
    monkeypatch.setattr(remote.sys, "stdin", Terminal())
    monkeypatch.setattr(remote.sys, "stdout", output)
    return output


def read_only_diagnosis(remote: ModuleType, identifier: str, password: str) -> str:
    """Exercise the real PostgreSQL transaction and the approved local seam."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SHOW transaction_read_only")
            assert cursor.fetchone() == ("on",)
        with CaptureQueriesContext(connection) as queries:
            classification = cast(str, remote.diagnose_local(identifier, password))
        assert not any(
            entry["sql"]
            .lstrip()
            .upper()
            .startswith(("INSERT", "UPDATE", "DELETE", "TRUNCATE"))
            for entry in queries.captured_queries
        )
    return classification


@pytest.mark.django_db(transaction=True)
def test_local_password_match_and_mismatch_are_distinct_and_read_only(
    remote: ModuleType,
) -> None:
    """Contract 3/4: exact actor plus matching hash is only a local credential fact."""
    managed = prepare_exact_roles()
    original_hash = stored_password(managed)

    assert read_only_diagnosis(remote, IDENTIFIER, PASSWORD) == "CREDENTIAL_ACCEPTED"
    assert (
        read_only_diagnosis(remote, IDENTIFIER, "wrong-password")
        == "CREDENTIAL_REJECTED"
    )
    managed.refresh_from_db()
    assert stored_password(managed) == original_hash


@pytest.mark.django_db(transaction=True)
def test_wrong_identifier_cannot_use_another_actors_password(
    remote: ModuleType,
) -> None:
    """Contract 3/4: valid password for the sole actor is insufficient by itself."""
    prepare_exact_roles()

    assert (
        read_only_diagnosis(remote, "limited-operator", PASSWORD) == "IDENTITY_MISMATCH"
    )
    assert (
        read_only_diagnosis(remote, "missing-operator", PASSWORD) == "IDENTITY_MISMATCH"
    )


@pytest.mark.django_db(transaction=True)
def test_extra_managed_member_is_ambiguous_even_when_one_password_matches(
    remote: ModuleType,
) -> None:
    """Contract 3/4: an extra group member cannot be silently ignored."""
    managed = prepare_exact_roles()
    extra = User(clerk_user_id="another-managed-operator", is_staff=True)
    extra.set_password("another-password")
    extra.save()
    cast(UserWithRoles, extra).groups.add(cast(UserWithRoles, managed).groups.get())

    assert read_only_diagnosis(remote, IDENTIFIER, PASSWORD) == "IDENTITY_AMBIGUOUS"


@pytest.mark.django_db(transaction=True)
def test_unusable_password_is_not_a_credential_rejection(remote: ModuleType) -> None:
    """Contract 4: exact actor with no usable local hash has its own outcome."""
    managed = prepare_exact_roles()
    managed.set_unusable_password()
    managed.save(update_fields={"password"})

    assert read_only_diagnosis(remote, IDENTIFIER, PASSWORD) == "PASSWORD_UNUSABLE"


@pytest.mark.django_db(transaction=True)
def test_password_check_never_upgrades_a_stale_hash(remote: ModuleType) -> None:
    """Contract 3: Django's hash-upgrade setter must never write on a match."""
    managed = prepare_exact_roles()
    weak_hasher = PBKDF2PasswordHasher()
    weak_hasher.iterations = 1
    old_hash = weak_hasher.encode(PASSWORD, "fixed-test-salt")
    managed.password = old_hash
    managed.save(update_fields={"password"})

    assert read_only_diagnosis(remote, IDENTIFIER, PASSWORD) == "CREDENTIAL_ACCEPTED"
    managed.refresh_from_db()
    assert stored_password(managed) == old_hash


@pytest.mark.django_db(transaction=True)
def test_permission_drift_stops_before_a_password_result(remote: ModuleType) -> None:
    """Contract 3/4: a different effective role invalidates diagnosis."""
    managed = prepare_exact_roles()
    cast(UserWithRoles, managed).user_permissions.add(
        permission_map()["profiles.view_playerprofile"]
    )

    assert read_only_diagnosis(remote, IDENTIFIER, PASSWORD) == "TARGET_OR_ROLE_FAILURE"


@pytest.mark.django_db(transaction=True)
def test_real_database_query_failure_is_not_relabelled_password_failure(
    remote: ModuleType,
) -> None:
    """Contract 4: a broken PostgreSQL transaction is execution uncertainty."""
    prepare_exact_roles()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            with pytest.raises(DatabaseError):
                cursor.execute("SELECT 1 / 0")
        assert remote.diagnose_local(IDENTIFIER, PASSWORD) == "EXECUTION_FAILURE"


def _read_pty(master: int, until: bytes, *, deadline: float) -> bytes:
    output = bytearray()
    while until not in output and time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.05)
        if not ready:
            continue
        try:
            chunk = os.read(master, 4096)
        except OSError:
            break
        if not chunk:
            break
        output.extend(chunk)
    return bytes(output)


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
def test_remote_run_uses_hidden_real_tty_and_returns_only_fixed_classification(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 1–4: a real PTY proves non-echo and the public result shape."""
    managed = prepare_exact_roles()
    original_hash = stored_password(managed)
    configure_remote_target(monkeypatch)
    assert connection.force_debug_cursor is False
    connection.close()  # Fork only after the parent releases its PostgreSQL socket.

    child, master = pty.fork()
    if child == 0:
        try:
            sys.stdin = os.fdopen(os.dup(0), "r")
            sys.stdout = os.fdopen(os.dup(1), "w")
            sys.stderr = os.fdopen(os.dup(2), "w")
            result = remote.run(IDENTITY)
            os.write(1, (json.dumps(result, sort_keys=True) + "\n").encode())
        except Exception:  # noqa: BLE001
            os.write(1, b"CHILD_EXECUTION_FAILURE\n")
        finally:
            os._exit(0)

    reaped = False
    try:
        deadline = time.monotonic() + 8
        transcript = bytearray()
        while (
            time.monotonic() < deadline and termios.tcgetattr(master)[3] & termios.ECHO
        ):
            transcript.extend(
                _read_pty(master, b"\n", deadline=time.monotonic() + 0.05)
            )
        assert not termios.tcgetattr(master)[3] & termios.ECHO
        os.write(master, (IDENTIFIER + "\n").encode())
        transcript.extend(_read_pty(master, b"Password:", deadline=deadline))
        assert b"Password:" in transcript
        assert not termios.tcgetattr(master)[3] & termios.ECHO
        os.write(master, (PASSWORD + "\n").encode())
        transcript.extend(_read_pty(master, b'"classification"', deadline=deadline))
        transcript.extend(_read_pty(master, b"\n", deadline=deadline))
        status = 0
        while time.monotonic() < deadline:
            finished, status = os.waitpid(child, os.WNOHANG)
            if finished == child:
                reaped = True
                break
            time.sleep(0.01)
        assert reaped, "remote diagnosis did not complete after two hidden inputs"
        assert os.WIFEXITED(status)
        assert b"CHILD_EXECUTION_FAILURE" not in transcript
        assert IDENTIFIER.encode() not in transcript
        assert PASSWORD.encode() not in transcript
        lines = [line.strip() for line in transcript.decode().splitlines()]
        records = [json.loads(line[line.index("{") :]) for line in lines if "{" in line]
        assert len(records) == 1
        assert set(records[0]) == {"classification", "identity", "window_utc"}
        assert records[0]["classification"] == "CREDENTIAL_ACCEPTED"
        assert records[0]["identity"] == IDENTITY
        managed.refresh_from_db()
        assert stored_password(managed) == original_hash
    finally:
        if not reaped:
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)
        os.close(master)


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
def test_remote_run_rejects_detached_terminal_without_prompt(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 2/4: hidden input requires real stdin and stdout terminals."""
    prepare_exact_roles()
    configure_remote_target(monkeypatch)
    monkeypatch.setattr(remote.sys, "stdin", Terminal(attached=False))
    monkeypatch.setattr(remote.sys, "stdout", Terminal(attached=False))

    result = cast(dict[str, object], remote.run(IDENTITY))

    assert set(result) == {"classification", "identity", "window_utc"}
    assert result["classification"] == "AUTH_PROTOCOL_FAILURE"
    assert PRIVATE not in json.dumps(result)


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
def test_remote_never_holds_a_database_transaction_during_secret_input(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 2/3: human input occurs between the two read-only DB checks."""
    prepare_exact_roles()
    configure_remote_target(monkeypatch)
    attach_synthetic_terminal(remote, monkeypatch)
    prompts: list[str] = []

    def hidden_input(prompt: str) -> str:
        assert connection.in_atomic_block is False
        prompts.append(prompt)
        return IDENTIFIER if len(prompts) == 1 else PASSWORD

    monkeypatch.setattr(remote.getpass, "getpass", hidden_input)

    result = cast(dict[str, object], remote.run(IDENTITY))

    assert result["classification"] == "CREDENTIAL_ACCEPTED"
    assert len(prompts) == 2


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
def test_getpass_warning_blocks_echo_fallback_and_classifies_protocol_failure(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 2/4: getpass cannot fall back to visible input."""
    prepare_exact_roles()
    configure_remote_target(monkeypatch)
    output = attach_synthetic_terminal(remote, monkeypatch)
    prompts = 0

    def unsafe_fallback(_prompt: str) -> str:
        nonlocal prompts
        prompts += 1
        warnings.warn(PRIVATE, getpass.GetPassWarning, stacklevel=1)
        output.write(PRIVATE)  # Reached only if warning was not made fatal.
        return PASSWORD

    monkeypatch.setattr(remote.getpass, "getpass", unsafe_fallback)

    result = cast(dict[str, object], remote.run(IDENTITY))

    assert result["classification"] == "AUTH_PROTOCOL_FAILURE"
    assert prompts == 1
    assert PRIVATE not in output.getvalue() + json.dumps(result)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("debug_mode", ["settings", "cursor"])
def test_debug_query_logging_stops_before_any_secret_prompt(
    remote: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsWrapper,
    debug_mode: str,
) -> None:
    """Contract 2/3: unsafe SQL logging precludes any credential collection."""
    prepare_exact_roles()
    configure_remote_target(monkeypatch)
    attach_synthetic_terminal(remote, monkeypatch)
    settings.DEBUG = debug_mode == "settings"
    if debug_mode == "cursor":
        monkeypatch.setattr(connection, "force_debug_cursor", True)

    def unexpected_prompt(_prompt: str) -> NoReturn:
        pytest.fail("secret prompt started while query logging was enabled")

    monkeypatch.setattr(remote.getpass, "getpass", unexpected_prompt)

    result = cast(dict[str, object], remote.run(IDENTITY))

    assert result["classification"] == "AUTH_PROTOCOL_FAILURE"


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
def test_limited_role_drift_stops_before_hidden_credential_prompts(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 1/3: both exact roles are prerequisites for diagnosis."""
    create_owned_baseline()
    create_managed_operator()
    limited = create_limited_operator()
    cast(UserWithRoles, limited).user_permissions.add(
        permission_map()["profiles.view_playerprofile"]
    )
    configure_remote_target(monkeypatch)
    attach_synthetic_terminal(remote, monkeypatch)

    def unexpected_prompt(_prompt: str) -> NoReturn:
        pytest.fail("credential prompt started despite limited-role drift")

    monkeypatch.setattr(remote.getpass, "getpass", unexpected_prompt)

    result = cast(dict[str, object], remote.run(IDENTITY))

    assert result["classification"] == "TARGET_OR_ROLE_FAILURE"


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
def test_unusable_managed_hash_stops_before_hidden_credential_prompts(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 3/4: post-inspector hash drift has a fixed pre-prompt result."""
    managed = prepare_exact_roles()
    managed.set_unusable_password()
    managed.save(update_fields={"password"})
    configure_remote_target(monkeypatch)
    attach_synthetic_terminal(remote, monkeypatch)

    def unexpected_prompt(_prompt: str) -> NoReturn:
        pytest.fail("credential prompt started despite an unusable managed hash")

    monkeypatch.setattr(remote.getpass, "getpass", unexpected_prompt)

    result = cast(dict[str, object], remote.run(IDENTITY))

    assert result["classification"] == "PASSWORD_UNUSABLE"


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
def test_fixture_drift_stops_before_hidden_credential_prompts(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 1/3: the exact #204 fixture is checked before secrets."""
    baseline = create_owned_baseline()
    create_managed_operator()
    create_limited_operator()
    owner = baseline.owner
    owner.is_staff = True
    owner.save(update_fields={"is_staff"})
    configure_remote_target(monkeypatch)
    attach_synthetic_terminal(remote, monkeypatch)

    def unexpected_prompt(_prompt: str) -> NoReturn:
        pytest.fail("credential prompt started despite fixture drift")

    monkeypatch.setattr(remote.getpass, "getpass", unexpected_prompt)

    result = cast(dict[str, object], remote.run(IDENTITY))

    assert result["classification"] == "TARGET_OR_ROLE_FAILURE"


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
def test_custom_sql_execute_wrapper_stops_before_secret_prompt(
    remote: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract 2/3: a wrapper could record the bound identifier parameter."""
    prepare_exact_roles()
    configure_remote_target(monkeypatch)
    attach_synthetic_terminal(remote, monkeypatch)

    def unexpected_prompt(_prompt: str) -> NoReturn:
        pytest.fail("secret prompt started with an installed SQL execute wrapper")

    def observe_sql(
        execute: Callable[..., object],
        sql: str,
        params: object,
        many: bool,
        context: object,
    ) -> object:
        return execute(sql, params, many, context)

    monkeypatch.setattr(remote.getpass, "getpass", unexpected_prompt)
    with connection.execute_wrapper(observe_sql):
        result = cast(dict[str, object], remote.run(IDENTITY))

    assert result["classification"] == "AUTH_PROTOCOL_FAILURE"


@override_settings(DEBUG=False)
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("bad_target", [False, True])
def test_remote_target_or_role_failure_finishes_without_password_input(
    remote: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    bad_target: bool,
) -> None:
    """Contract 1/3: exact runtime and #205 shape precede any terminal secret."""
    managed = prepare_exact_roles()
    configure_remote_target(monkeypatch)
    if bad_target:
        requested = {**IDENTITY, "source_sha": "b" * 40}
    else:
        requested = IDENTITY
        cast(UserWithRoles, managed).user_permissions.add(
            permission_map()["profiles.view_playerprofile"]
        )
    connection.close()  # Prevent the child from closing the parent's live socket.

    child, master = pty.fork()
    if child == 0:
        try:
            sys.stdin = os.fdopen(os.dup(0), "r")
            sys.stdout = os.fdopen(os.dup(1), "w")
            sys.stderr = os.fdopen(os.dup(2), "w")
            result = remote.run(requested)
            os.write(1, (json.dumps(result, sort_keys=True) + "\n").encode())
        except Exception:  # noqa: BLE001
            os.write(1, b"CHILD_EXECUTION_FAILURE\n")
        finally:
            os._exit(0)

    reaped = False
    try:
        deadline = time.monotonic() + 5
        transcript = _read_pty(master, b'"classification"', deadline=deadline)
        transcript += _read_pty(master, b"\n", deadline=deadline)
        while time.monotonic() < deadline:
            finished, _ = os.waitpid(child, os.WNOHANG)
            if finished == child:
                reaped = True
                break
            time.sleep(0.01)
        assert reaped, (
            "remote prompted for a secret before passing target and role guards"
        )
        assert b"CHILD_EXECUTION_FAILURE" not in transcript
        assert b"password" not in transcript.lower()
        assert b"identifier" not in transcript.lower()
        lines = [line.strip() for line in transcript.decode().splitlines()]
        records = [json.loads(line[line.index("{") :]) for line in lines if "{" in line]
        assert len(records) == 1
        assert records[0]["classification"] == "TARGET_OR_ROLE_FAILURE"
    finally:
        if not reaped:
            os.kill(child, signal.SIGKILL)
            os.waitpid(child, 0)
        os.close(master)
