"""Offline acceptance coverage for guarded emergency Staging SSH provisioning."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import runpy
import subprocess
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType
from typing import NoReturn, Self, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
MODULE = "scripts.api_staging_emergency_operator_ssh"
IDENTITY = {
    "environment": "staging",
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
}
INSTANCE = "22222222-2222-4222-8222-222222222222"
PROJECT = "a1111111-1111-4111-8111-111111111111"
ENVIRONMENT = "c3333333-3333-4333-8333-333333333333"
SERVICE = "d4444444-4444-4444-8444-444444444444"
POSTGRES = "e5555555-5555-4555-8555-555555555555"
WINDOW = ["2026-09-25T00:00:00Z", "2026-09-25T00:00:01Z"]
PRIVATE = "private-emergency-identifier-password-sentinel"
DATABASE_URL = "postgresql://private-user:private-password@private-host:5432/tailtag"
DATABASE_HOST = "private-host"
DATABASE_NAME = "tailtag"
DATABASE_CLUSTER = "742391"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Terminal(StringIO):
    def __init__(self, *, attached: bool = True) -> None:
        super().__init__()
        self.attached = attached

    def isatty(self) -> bool:
        return self.attached


@pytest.fixture
def runner() -> ModuleType:
    assert (ROOT / "scripts/api_staging_emergency_operator_ssh.py").is_file()
    return importlib.import_module(MODULE)


def _inspector_result(status: str = "PASS") -> dict[str, object]:
    return {
        "result": status,
        "phase": "exact_instance_inspector",
        "identity": dict(IDENTITY),
        "target_verified": True,
        "window_utc": WINDOW,
    }


def _registry_result(*, mismatch: str | None = None) -> dict[str, object]:
    from scripts import api_staging_registry_reconcile as registry

    structural = {"registry_singleton", "registry_structure", "root_completeness"}
    checks = {
        key: "PASS" if key in structural else "MATCH"
        for key in registry._CHECKS  # pyright: ignore[reportPrivateUsage]
    }
    if mismatch is not None:
        checks[mismatch] = "MISMATCH"
    return {"result": "MISMATCH" if mismatch else "PASS", "checks": checks}


def _green_guards(runner: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub only provider/read-only boundaries, never the launcher decisions."""
    events: list[str] = []

    def github_identity() -> None:
        events.append("github")

    def railway_identity() -> None:
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

    def registry(_path: Path) -> dict[str, object]:
        events.append("registry")
        return _registry_result()

    def inspector() -> dict[str, object]:
        events.append("inspector")
        return _inspector_result()

    def precondition(identity: dict[str, str], instance_id: str) -> str:
        assert identity == IDENTITY and instance_id == INSTANCE
        events.append("precondition")
        return "ABSENT"

    def postcondition(identity: dict[str, str], instance_id: str) -> str:
        assert identity == IDENTITY and instance_id == INSTANCE
        events.append("postcondition")
        return "READY"

    monkeypatch.setattr(runner.sys, "stdin", Terminal())
    monkeypatch.setattr(runner.sys, "stdout", Terminal())
    monkeypatch.setattr(runner, "_github_identity", github_identity)
    monkeypatch.setattr(runner, "_railway_identity", railway_identity)
    monkeypatch.setattr(runner, "_preflight", preflight)
    monkeypatch.setattr(runner, "_approved_receipt", receipt)
    monkeypatch.setattr(runner, "_active_instance", instance)
    monkeypatch.setattr(
        runner, "_target_ids", lambda: (PROJECT, ENVIRONMENT, SERVICE, POSTGRES)
    )

    def binding_request(identity: dict[str, str]) -> dict[str, object]:
        assert identity == IDENTITY
        return _binding_request()

    monkeypatch.setattr(
        runner,
        "_binding_request",
        binding_request,
    )
    monkeypatch.setattr(runner._registry_reconcile, "run", registry)
    monkeypatch.setattr(runner._inspector, "run", inspector)
    monkeypatch.setattr(runner, "_emergency_precondition", precondition)
    monkeypatch.setattr(runner, "_emergency_postcondition", postcondition)
    return events


def _result(result: object) -> dict[str, object]:
    assert isinstance(result, dict)
    value = cast(dict[str, object], result)
    assert set(value) == {"result", "phase", "identity", "window_utc"}
    assert value["identity"] in (None, IDENTITY)
    assert isinstance(value["phase"], str)
    assert isinstance(value["window_utc"], list)
    assert PRIVATE not in json.dumps(value)
    assert INSTANCE not in json.dumps(value)
    return value


def _unexpected_ssh(*_args: object, **_kwargs: object) -> NoReturn:
    pytest.fail("SSH began before every pre-mutation guard passed")


def test_one_exact_instance_interactive_ssh_requires_independent_postcondition(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = _green_guards(runner, monkeypatch)
    executions: list[list[str]] = []

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("ssh")
        executions.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner, "_run", execute)

    result = _result(runner.run())

    assert result["result"] == "PASS_EMERGENCY_OPERATOR_READY"
    assert len(executions) == 1
    assert events.index("github") < events.index("ssh")
    assert events.index("railway") < events.index("ssh")
    assert events.index("preflight") < events.index("receipt") < events.index("ssh")
    assert events.index("receipt") < events.index("instance") < events.index("ssh")
    assert events.index("registry") < events.index("ssh")
    assert events.index("inspector") < events.index("ssh")
    assert (
        events.index("precondition")
        < events.index("ssh")
        < events.index("postcondition")
    )
    assert events.count("preflight") >= 2  # fresh repeat before mutation
    arguments = executions[0]
    assert arguments[:2] == ["railway", "ssh"]
    for flag, expected in (
        ("--project", PROJECT),
        ("--service", SERVICE),
        ("--environment", ENVIRONMENT),
        ("--deployment-instance", INSTANCE),
    ):
        assert arguments[arguments.index(flag) + 1] == expected
    rendered = " ".join(arguments)
    assert PRIVATE not in rendered
    assert DATABASE_URL not in rendered
    assert DATABASE_HOST not in rendered
    assert DATABASE_CLUSTER not in rendered
    assert "--password" not in arguments
    assert "--identifier" not in arguments
    request = json.loads(arguments[-1])
    assert set(request) == {
        "identity",
        "database_url_fingerprint",
        "database_facts_fingerprint",
    }
    assert request == _binding_request()


@pytest.mark.parametrize("detached", ("stdin", "stdout"))
def test_real_terminal_is_required_before_provider_access(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, detached: str
) -> None:
    events = _green_guards(runner, monkeypatch)
    monkeypatch.setattr(runner.sys, detached, Terminal(attached=False))
    monkeypatch.setattr(runner, "_run", _unexpected_ssh)

    result = _result(runner.run())

    assert cast(str, result["result"]).startswith("FAIL_")
    assert events == []


@pytest.mark.parametrize("status", ("READY", "MISMATCH", "INDETERMINATE"))
def test_existing_or_unknown_superuser_blocks_mutation(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    events = _green_guards(runner, monkeypatch)

    def precondition(*_args: object) -> str:
        events.append("precondition")
        return status

    monkeypatch.setattr(runner, "_emergency_precondition", precondition)
    monkeypatch.setattr(runner, "_run", _unexpected_ssh)

    result = _result(runner.run())

    assert cast(str, result["result"]).startswith("FAIL_")
    assert "precondition" in events
    assert "postcondition" not in events


@pytest.mark.parametrize(
    "status", ("FAIL_MANAGED_OPERATOR_PERMISSION", "FAIL_LIMITED_OPERATOR_MISSING")
)
def test_operator_state_must_pass_before_mutation(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    events = _green_guards(runner, monkeypatch)
    monkeypatch.setattr(runner._inspector, "run", lambda: _inspector_result(status))
    monkeypatch.setattr(runner, "_run", _unexpected_ssh)

    result = _result(runner.run())

    assert cast(str, result["result"]).startswith("FAIL_")
    assert "postcondition" not in events


@pytest.mark.parametrize(
    "mismatch",
    ("database_name_actual_registry", "cluster_identifier_actual_registry"),
)
def test_live_database_binding_mismatch_blocks_mutation(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, mismatch: str
) -> None:
    events = _green_guards(runner, monkeypatch)

    def registry(_path: Path) -> dict[str, object]:
        events.append("registry")
        return _registry_result(mismatch=mismatch)

    monkeypatch.setattr(runner._registry_reconcile, "run", registry)
    monkeypatch.setattr(runner, "_run", _unexpected_ssh)

    result = _result(runner.run())

    assert cast(str, result["result"]).startswith("FAIL_")
    assert "registry" in events
    assert "postcondition" not in events


@pytest.mark.parametrize(
    "guard", ("github", "railway", "preflight", "receipt", "instance")
)
def test_identity_or_target_failure_stops_before_ssh(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, guard: str
) -> None:
    _green_guards(runner, monkeypatch)
    if guard == "github":
        monkeypatch.setattr(
            runner,
            "_github_identity",
            lambda: (_ for _ in ()).throw(ValueError(PRIVATE)),
        )
    elif guard == "railway":
        monkeypatch.setattr(
            runner,
            "_railway_identity",
            lambda: (_ for _ in ()).throw(ValueError(PRIVATE)),
        )
    elif guard == "preflight":
        monkeypatch.setattr(
            runner, "_preflight", lambda: {**IDENTITY, "source_sha": "b" * 40}
        )
    elif guard == "receipt":

        def failed_receipt(_identity: dict[str, str]) -> NoReturn:
            raise ValueError(PRIVATE)

        monkeypatch.setattr(
            runner,
            "_approved_receipt",
            failed_receipt,
        )
    else:

        def invalid_instance(_identity: dict[str, str]) -> str:
            return "not-a-uuid"

        monkeypatch.setattr(runner, "_active_instance", invalid_instance)
    monkeypatch.setattr(runner, "_run", _unexpected_ssh)

    result = _result(runner.run())

    assert cast(str, result["result"]).startswith("FAIL_")


@pytest.mark.parametrize("transport", ("nonzero", "stderr", "timeout"))
def test_transport_uncertainty_is_never_promoted_to_ready_or_retried(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, transport: str
) -> None:
    events = _green_guards(runner, monkeypatch)
    attempts = 0

    def execute(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        events.append("ssh")
        if transport == "timeout":
            raise subprocess.TimeoutExpired(arguments, 30)
        if transport == "stderr":
            return subprocess.CompletedProcess(arguments, 0, None, PRIVATE)
        return subprocess.CompletedProcess(arguments, 1, None, "")

    monkeypatch.setattr(runner, "_run", execute)

    result = _result(runner.run())

    assert result["result"] == "FAIL_TRANSPORT_UNCERTAIN"
    assert attempts == 1
    assert "postcondition" not in events


@pytest.mark.parametrize("status", ("MISMATCH", "ABSENT", "INDETERMINATE", "PASS"))
def test_zero_exit_is_not_ready_without_exact_read_only_postcondition(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    events = _green_guards(runner, monkeypatch)

    def execute(args: list[str]) -> subprocess.CompletedProcess[str]:
        events.append("ssh")
        return subprocess.CompletedProcess(args, 0, None, "")

    def postcondition(*_args: object) -> str:
        events.append("postcondition")
        return status

    monkeypatch.setattr(runner, "_run", execute)
    monkeypatch.setattr(runner, "_emergency_postcondition", postcondition)

    result = _result(runner.run())

    assert cast(str, result["result"]).startswith("FAIL_")
    assert events.index("ssh") < events.index("postcondition")


def test_subprocess_transport_inherits_real_terminal_and_never_captures_secrets(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, object] = {}

    def subprocess_run(
        arguments: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        observed.update(kwargs)
        return subprocess.CompletedProcess(arguments, 0, None, "")

    monkeypatch.setattr(runner.subprocess, "run", subprocess_run)
    runner._run(["railway", "ssh"])

    assert observed.get("shell") is False
    assert observed.get("stdin") is None
    assert observed.get("stdout") is None
    assert observed.get("capture_output") is not True
    assert observed.get("input") is None
    assert observed.get("stderr") == subprocess.PIPE


def _binding_request(
    *,
    url: str = DATABASE_URL,
    host: str = DATABASE_HOST,
    port: str = "5432",
    name: str = DATABASE_NAME,
    cluster: str = DATABASE_CLUSTER,
) -> dict[str, object]:
    """Use the frozen value-free request schema, never its private inputs."""
    facts = [
        "tailtag-staging-emergency-db-v1",
        host.lower(),
        str(int(port)),
        name,
        cluster,
    ]
    return {
        "identity": dict(IDENTITY),
        "database_url_fingerprint": hashlib.sha256(url.encode()).hexdigest(),
        "database_facts_fingerprint": hashlib.sha256(
            json.dumps(facts, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def test_binding_request_uses_private_config_and_joined_api_postgres_url_only_as_digests(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed_paths: list[Path] = []

    def configuration(path: Path) -> dict[str, str]:
        observed_paths.append(path)
        return {
            "TAILTAG_STAGING_DATABASE_HOST": DATABASE_HOST,
            "TAILTAG_STAGING_DATABASE_PORT": "5432",
            "TAILTAG_STAGING_DATABASE_NAME": DATABASE_NAME,
            "TAILTAG_STAGING_DATABASE_SYSTEM_ID": DATABASE_CLUSTER,
        }

    monkeypatch.setattr(runner, "_read_configuration", configuration)
    monkeypatch.setattr(
        runner,
        "_runtime_database_fingerprint",
        lambda: hashlib.sha256(DATABASE_URL.encode()).hexdigest(),
    )

    request = cast(dict[str, object], runner._binding_request(dict(IDENTITY)))

    assert observed_paths == [
        Path.home() / ".config/tailtag/staging-reset-replacement.env"
    ]
    assert request == _binding_request()
    rendered = json.dumps(request, sort_keys=True)
    assert DATABASE_HOST not in rendered
    assert DATABASE_NAME not in rendered
    assert DATABASE_CLUSTER not in rendered
    assert DATABASE_URL not in rendered


def test_read_only_state_transport_sends_only_opaque_binding_request(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runner, "_target_ids", lambda: (PROJECT, ENVIRONMENT, SERVICE, POSTGRES)
    )
    monkeypatch.setattr(runner, "_railway_identity", lambda: None)

    def binding_request(identity: dict[str, str]) -> dict[str, object]:
        assert identity == IDENTITY
        return _binding_request()

    monkeypatch.setattr(runner, "_binding_request", binding_request)
    seen: list[list[str]] = []

    def subprocess_run(
        arguments: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, "ABSENT\n", "")

    monkeypatch.setattr(runner.subprocess, "run", subprocess_run)

    assert runner._state(dict(IDENTITY), INSTANCE) == "ABSENT"
    assert len(seen) == 1
    arguments = seen[0]
    assert arguments[arguments.index("--deployment-instance") + 1] == INSTANCE
    assert json.loads(arguments[-1]) == _binding_request()
    rendered = " ".join(arguments)
    assert DATABASE_URL not in rendered
    assert DATABASE_HOST not in rendered
    assert DATABASE_CLUSTER not in rendered


class _FakeCursor:
    def __init__(
        self,
        events: list[str],
        *,
        query_failure: bool = False,
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        self.events = events
        self.query_failure = query_failure
        self.on_exit = on_exit

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        if self.on_exit is not None:
            self.on_exit()

    def execute(self, query: str, _params: object = None) -> None:
        if self.query_failure:
            raise ValueError("private-database-query-sentinel")
        if "READ ONLY" in query.upper():
            self.events.append("read_only")
        elif "current_database" in query or "pg_control_system" in query:
            self.events.append("database_facts")
        else:
            raise AssertionError("Unexpected remote database query")

    def fetchone(self) -> tuple[str, int]:
        return DATABASE_NAME, int(DATABASE_CLUSTER)


class _FakeConnection:
    def __init__(
        self,
        events: list[str],
        *,
        query_failure: bool = False,
        replace_after_cursor: bool = False,
    ) -> None:
        self.events = events
        self.query_failure = query_failure
        self.replace_after_cursor = replace_after_cursor
        self.connection: object = _FakePhysical()
        self.in_atomic_block = False
        self.settings_dict = {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": DATABASE_HOST,
            "PORT": "5432",
            "NAME": DATABASE_NAME,
        }

    def cursor(self) -> _FakeCursor:
        on_exit = None
        if self.replace_after_cursor:
            self.replace_after_cursor = False

            def replace() -> None:
                self.connection = _FakePhysical()
                self.events.append("connection_replaced")

            on_exit = replace
        return _FakeCursor(
            self.events, query_failure=self.query_failure, on_exit=on_exit
        )


class _FakePhysical:
    closed = False


def _exercise_remote_bootstrap(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    kind: str,
    request: dict[str, object],
    query_failure: bool = False,
    replace_connection: bool = False,
    replace_before_command: bool = False,
    commit_failure: bool = False,
    wrong_build: bool = False,
    wrong_runtime: bool = False,
) -> tuple[int, str, str, list[str]]:
    """Execute the actual shipped remote program with controlled local modules."""
    import django
    from django import db
    from django.db import transaction

    from accounts.management.commands import (
        bootstrap_staging_emergency_operator as command,
    )
    from config import replacement_target_binding

    events: list[str] = []
    fake_connection = _FakeConnection(
        events,
        query_failure=query_failure,
        replace_after_cursor=replace_before_command,
    )
    original_read_text = Path.read_text
    original_path = list(sys.path)
    original_environment = dict(os.environ)
    output, errors = StringIO(), StringIO()
    code = cast(
        str, runner._STATE_BOOTSTRAP if kind == "state" else runner._CREATE_BOOTSTRAP
    )
    bootstrap_path = tmp_path / "reviewed_emergency_bootstrap.py"
    bootstrap_path.write_text(code, encoding="utf-8")

    def read_text(path: Path, *args: object, **kwargs: object) -> str:
        if str(path) == "/opt/tailtag/build-identity.json":
            return json.dumps(
                {"source_sha": "b" * 40 if wrong_build else IDENTITY["source_sha"]}
            )
        return original_read_text(path, *args, **kwargs)  # pyright: ignore[reportArgumentType]

    def runtime_target(_actual: object) -> None:
        events.append("runtime_target")
        if wrong_runtime:
            raise ValueError("private-runtime-target-sentinel")

    @contextmanager
    def atomic(*_args: object, **_kwargs: object) -> Generator[None]:
        events.append("transaction_begin")
        fake_connection.in_atomic_block = True
        try:
            yield
        finally:
            fake_connection.in_atomic_block = False
            events.append("transaction_end")
            if commit_failure:
                raise ValueError("private-commit-failure-sentinel")

    def execute_command(self: object, **_kwargs: object) -> None:
        events.append("command_entered")
        assert "database_facts" in events
        assert "transaction_begin" in events
        assert "read_only" not in events
        events.append("command")
        if replace_connection:
            fake_connection.connection = object()

    def inspect_state() -> str:
        assert "database_facts" in events
        assert "transaction_begin" in events
        assert "read_only" in events
        events.append("state")
        return "ABSENT"

    with monkeypatch.context() as patch:
        # Remote code may set DJANGO_SETTINGS_MODULE; isolate its process view.
        patch.setattr(os, "environ", dict(os.environ))
        patch.setattr(Path, "read_text", read_text)
        patch.setattr(django, "setup", lambda: events.append("django_setup"))
        patch.setattr(
            replacement_target_binding, "validate_runtime_target", runtime_target
        )
        patch.setattr(db, "connection", fake_connection)
        patch.setattr(transaction, "atomic", atomic)
        patch.setattr(command.Command, "execute", execute_command)
        patch.setattr(command, "inspect_emergency_state", inspect_state)
        patch.setattr(
            sys,
            "argv",
            ["remote-bootstrap", json.dumps(request, separators=(",", ":"))],
        )
        patch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
        patch.setenv("RAILWAY_SERVICE_NAME", "api")
        patch.setenv("RAILWAY_DEPLOYMENT_ID", IDENTITY["deployment_id"])
        patch.setenv("DATABASE_URL", DATABASE_URL)
        with redirect_stdout(output), redirect_stderr(errors):
            try:
                runpy.run_path(str(bootstrap_path), run_name="__main__")
                status = 0
            except SystemExit as error:
                status = cast(int, error.code)
    sys.path[:] = original_path
    assert os.environ == original_environment
    return status, output.getvalue(), errors.getvalue(), events


@pytest.mark.parametrize("kind", ("state", "create"))
def test_remote_bootstraps_bind_actual_database_before_read_or_mutation(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    request = _binding_request()

    status, output, errors, events = _exercise_remote_bootstrap(
        runner, monkeypatch, tmp_path, kind=kind, request=request
    )

    assert status == 0
    assert events.index("runtime_target") < events.index("transaction_begin")
    assert events.index("transaction_begin") < events.index("database_facts")
    if kind == "state":
        assert events.index("read_only") < events.index("database_facts")
        assert events.index("read_only") < events.index("state")
        assert output.strip() == "ABSENT"
        assert errors == ""
    else:
        assert events.index("transaction_begin") < events.index("command")
        assert "TAILTAG_EMERGENCY_COMMAND_COMPLETED" in output
    assert DATABASE_URL not in output + errors
    assert DATABASE_HOST not in output + errors
    assert DATABASE_CLUSTER not in output + errors


@pytest.mark.parametrize("kind", ("state", "create"))
@pytest.mark.parametrize(
    "mismatch", ("url", "host", "port", "name", "cluster", "query", "build", "runtime")
)
def test_remote_binding_mismatch_or_query_error_blocks_before_mutation(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    mismatch: str,
) -> None:
    request = _binding_request(
        url="postgresql://wrong-url" if mismatch == "url" else DATABASE_URL,
        host="wrong-host" if mismatch == "host" else DATABASE_HOST,
        port="5433" if mismatch == "port" else "5432",
        name="wrong-database" if mismatch == "name" else DATABASE_NAME,
        cluster="999999" if mismatch == "cluster" else DATABASE_CLUSTER,
    )
    status, output, errors, events = _exercise_remote_bootstrap(
        runner,
        monkeypatch,
        tmp_path,
        kind=kind,
        request=request,
        query_failure=mismatch == "query",
        wrong_build=mismatch == "build",
        wrong_runtime=mismatch == "runtime",
    )

    assert status != 0
    assert "command" not in events
    assert "state" not in events
    if kind == "state":
        assert output.strip() == "INDETERMINATE"
    else:
        assert errors.strip() == "FAIL_EMERGENCY_COMMAND"
        assert "TAILTAG_EMERGENCY_COMMAND_COMPLETED" not in output
    assert DATABASE_URL not in output + errors
    assert DATABASE_HOST not in output + errors


def test_create_refuses_connection_replacement_after_command(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    status, output, errors, events = _exercise_remote_bootstrap(
        runner,
        monkeypatch,
        tmp_path,
        kind="create",
        request=_binding_request(),
        replace_connection=True,
    )
    assert "command" in events
    assert status != 0
    assert errors.strip() == "FAIL_EMERGENCY_COMMAND"
    assert "TAILTAG_EMERGENCY_COMMAND_COMPLETED" not in output


def test_create_refuses_replaced_handle_before_command_can_enter(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    status, output, errors, events = _exercise_remote_bootstrap(
        runner,
        monkeypatch,
        tmp_path,
        kind="create",
        request=_binding_request(),
        replace_before_command=True,
    )
    assert "connection_replaced" in events
    assert "command_entered" not in events
    assert status != 0
    assert errors.strip() == "FAIL_EMERGENCY_COMMAND"
    assert "TAILTAG_EMERGENCY_COMMAND_COMPLETED" not in output


def test_create_commit_failure_has_fixed_result_and_no_completion_marker(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A completed command body is not evidence that its outer commit succeeded."""
    status, output, errors, events = _exercise_remote_bootstrap(
        runner,
        monkeypatch,
        tmp_path,
        kind="create",
        request=_binding_request(),
        commit_failure=True,
    )

    assert events.index("command") < events.index("transaction_end")
    assert status != 0
    assert errors.strip() == "FAIL_EMERGENCY_COMMAND"
    assert "TAILTAG_EMERGENCY_COMMAND_COMPLETED" not in output
    assert "private-commit-failure-sentinel" not in output + errors
