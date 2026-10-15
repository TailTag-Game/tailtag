"""Offline acceptance contract for the guarded #207 restore drill entry point."""

# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import hashlib
import importlib
import json
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, NoReturn, Self, cast

import pytest

from tests import windows_acl_support as acl

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_restore_drill.py"
DOCKER_ENDPOINT = (
    "npipe:////./pipe/docker_engine"
    if sys.platform == "win32"
    else "unix:///private/docker.sock"
)
SENSITIVE = "postgresql://private-user:private-password@private-host/private-db"
REVIEWED_SCHEMA_SHA = "f16ff7527059e32d2cca15038e55ba406aa35381"
REPLACEMENT_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
)

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing fake must never make this acceptance suite contact Staging."""

    def forbidden_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("restore-drill acceptance tests must remain offline")

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden_network)


@pytest.fixture
def drill() -> ModuleType:
    """Load the only approved #207 operator entry point once it exists."""
    assert SCRIPT.is_file(), "scripts/api_staging_restore_drill.py must exist"
    return cast(Any, importlib.import_module("scripts.api_staging_restore_drill"))


def prevent_subprocesses(
    monkeypatch: pytest.MonkeyPatch, drill: ModuleType
) -> list[object]:
    """Make accidental command execution observable while parsing is rejected."""
    calls: list[object] = []

    def forbidden_command(*args: object, **kwargs: object) -> NoReturn:
        calls.append((args, kwargs))
        raise AssertionError("a rejected restore command must not open a subprocess")

    # The frozen Test Surface Contract permits faking command execution.  The
    # production entry point may use either common subprocess primitive.
    monkeypatch.setattr(drill.subprocess, "run", forbidden_command)
    monkeypatch.setattr(drill.subprocess, "Popen", forbidden_command)
    return calls


def assert_denied(action: object) -> None:
    """Accept any sanitized operational denial while rejecting accidental acceptance."""
    try:
        cast(Any, action)()
    except Exception:  # noqa: BLE001 - the frozen contract does not name a denial type.
        return
    pytest.fail("unsafe restore input was accepted")


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--confirm", "wrong"),
        ("--confirm", "restore-tailtag-staging-backup", "--database-url", SENSITIVE),
        ("--confirm", "restore-tailtag-staging-backup", "--target", "staging"),
        ("--confirm", "restore-tailtag-staging-backup", "--environment", "production"),
        ("--confirm", "restore-tailtag-staging-backup", "--host", "private-host"),
    ),
)
def test_only_the_fixed_confirmation_can_reach_any_operational_phase(
    drill: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: tuple[str, ...],
) -> None:
    """AC-1/4: no caller-supplied source or restore destination is accepted."""
    calls = prevent_subprocesses(monkeypatch, drill)
    monkeypatch.setattr(sys, "argv", ["api_staging_restore_drill.py", *arguments])

    assert drill.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert SENSITIVE not in captured.err
    assert calls == []


def test_untrusted_option_text_is_never_reflected_in_the_sanitized_failure(
    drill: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-2/9: parser failures cannot leak a URL, password, or private hostname."""
    calls = prevent_subprocesses(monkeypatch, drill)
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_restore_drill.py", f"--unsafe={SENSITIVE}"],
    )

    assert drill.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert SENSITIVE not in captured.err
    assert calls == []


def test_tunnel_details_require_one_complete_loopback_tunnel_without_untrusted_extras(
    drill: ModuleType,
) -> None:
    """AC-1/2: only Railway's complete local tunnel shape can reach pg_dump."""
    details = drill.parse_tunnel_details(
        "Host: 127.0.0.1\n"
        "Port: 54321\n"
        "User: postgres\n"
        "Password: private-password\n"
        "Database: railway\n"
        "URL: postgresql://postgres:private-password@127.0.0.1:54321/railway"
    )

    assert details.host == "127.0.0.1"
    assert details.port == 54321
    assert details.user == "postgres"
    assert details.database == "railway"

    for unsafe_output in (
        "Host: 10.0.0.9\nPort: 54321\nUser: postgres\nPassword: x\nDatabase: railway\nURL: x",
        "Host: localhost\nPort: 54321\nUser: postgres\nPassword: x\nDatabase: railway\nURL: x",
        "Host: 127.0.0.1\nPort: not-a-port\nUser: postgres\nPassword: x\nDatabase: railway\nURL: x",
        "Host: 127.0.0.1\nPort: 54321\nUser: postgres\nDatabase: railway\nURL: x",
        "Host: 127.0.0.1\nPort: 54321\nUser: postgres\nPassword: x\nDatabase: railway\nURL: x\nURL: other",
    ):
        assert_denied(
            lambda unsafe_output=unsafe_output: drill.parse_tunnel_details(
                unsafe_output
            )
        )


@pytest.mark.parametrize("operation", ("tunnel", "fingerprint"))
def test_unavailable_replacement_binding_refuses_before_provider_actions(
    drill: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """Issue 208 OR-8: unavailable pins cannot open a tunnel or inspect a DB."""

    def load_binding() -> tuple[str, str, str, str]:
        raise ValueError("missing pins")

    monkeypatch.setattr(drill, "_target_ids", load_binding)
    monkeypatch.setattr(
        drill,
        "verify_railway_identity",
        lambda: pytest.fail("invalid pins reached Railway identity lookup"),
    )
    monkeypatch.setattr(
        drill.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("invalid pins opened a tunnel"),
    )
    monkeypatch.setattr(
        drill,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("invalid pins queried Railway"),
    )

    with pytest.raises(drill.DrillDenied):
        if operation == "tunnel":
            drill.open_railway_tunnel()
        else:
            drill._staging_database_fingerprint()


@pytest.mark.parametrize("operation", ("tunnel", "fingerprint"))
def test_supplied_target_cannot_override_replacement_binding(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """Issue 208 OR-8: a caller cannot redirect either source helper."""
    import scripts.api_staging_reset_ssh as reset

    other_ids = (
        "66666666-6666-4666-8666-666666666666",
        *REPLACEMENT_IDS[1:],
    )
    monkeypatch.setattr(drill, "_target_ids", lambda: REPLACEMENT_IDS)
    monkeypatch.setattr(
        drill,
        "verify_railway_identity",
        lambda: pytest.fail("alternate target reached Railway identity lookup"),
    )
    monkeypatch.setattr(
        drill.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("alternate target opened a tunnel"),
    )
    monkeypatch.setattr(
        drill,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("alternate target queried Railway"),
    )
    monkeypatch.setattr(
        reset,
        "_variables",
        lambda _service_id: pytest.fail("alternate target queried variables"),
    )

    with pytest.raises(drill.DrillDenied):
        if operation == "tunnel":
            drill.open_railway_tunnel(other_ids)
        else:
            drill._staging_database_fingerprint(other_ids)


def test_replacement_binding_selects_tunnel_and_database_relationship(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue 208 OR-8: one approved pin tuple selects the source for both guards."""
    import scripts.api_staging_reset_ssh as reset

    project_id, environment_id, api_id, postgres_id = REPLACEMENT_IDS
    database_url = "postgresql://synthetic:secret@synthetic.invalid/railway"
    volume_id = "55555555-5555-4555-8555-555555555555"
    requests: list[str] = []
    commands: list[tuple[str, ...]] = []
    monkeypatch.setattr(drill, "_target_ids", lambda: REPLACEMENT_IDS)
    monkeypatch.setattr(drill, "verify_railway_identity", lambda: None)

    def tunnel_command(command: tuple[str, ...], **_kwargs: object) -> NoReturn:
        commands.append(command)
        raise RuntimeError("tunnel command observed")

    monkeypatch.setattr(drill.subprocess, "Popen", tunnel_command)
    with pytest.raises(RuntimeError, match="tunnel command observed"):
        drill.open_railway_tunnel()
    assert commands == [
        (
            "railway",
            "connect",
            "Postgres",
            "--tunnel-only",
            "--project",
            project_id,
            "--environment",
            environment_id,
        )
    ]

    def variables(service_id: str) -> dict[str, str]:
        requests.append(service_id)
        assert service_id in {api_id, postgres_id}
        return {
            "RAILWAY_PROJECT_ID": project_id,
            "RAILWAY_ENVIRONMENT_ID": environment_id,
            "RAILWAY_ENVIRONMENT_NAME": "staging",
            "RAILWAY_SERVICE_ID": service_id,
            "DATABASE_URL": database_url,
        }

    status = {
        "id": project_id,
        "name": "TailTag",
        "environments": {
            "edges": [
                {
                    "node": {
                        "id": environment_id,
                        "name": "staging",
                        "deletedAt": None,
                        "volumeInstances": {
                            "edges": [
                                {
                                    "node": {
                                        "id": volume_id,
                                        "serviceId": postgres_id,
                                        "environmentId": environment_id,
                                        "state": "READY",
                                        "isPendingDeletion": False,
                                        "deletedAt": None,
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        },
        "services": {
            "edges": [
                {"node": {"name": "api", "id": api_id}},
                {"node": {"name": "Postgres", "id": postgres_id}},
            ]
        },
    }
    monkeypatch.setattr(reset, "_variables", variables)

    def status_command(*args: str) -> SimpleNamespace:
        commands.append(args)
        return SimpleNamespace(stdout=json.dumps(status))

    monkeypatch.setattr(drill, "_run", status_command)
    expected_fingerprint = hashlib.sha256(
        (database_url + "\n" + volume_id + "\n" + postgres_id).encode("utf-8")
    ).hexdigest()
    assert drill._staging_database_fingerprint() == expected_fingerprint
    assert requests == [api_id, postgres_id]
    assert commands[-1] == (
        "railway",
        "status",
        "--project",
        project_id,
        "--environment",
        environment_id,
        "--json",
    )


def test_reviewed_schema_revision_requires_matching_sha_and_clean_schema_dirs(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue 208 OR-8: an unreviewed deployed or local schema cannot claim integrity."""
    commands: list[tuple[str, ...]] = []
    returncode = 0

    def git_diff(command: tuple[str, ...], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(drill.subprocess, "run", git_diff)
    drill._verify_manifest_revision(REVIEWED_SCHEMA_SHA)
    assert len(commands) == 1
    assert commands[0][:4] == (
        "git",
        "diff",
        "--quiet",
        REVIEWED_SCHEMA_SHA,
    )
    assert set(commands[0][5:]) == {
        f"services/api/{app}"
        for app in (
            "accounts",
            "profiles",
            "fursuits",
            "conventions",
            "catches",
            "operator_audit",
            "rehearsal",
        )
    }

    with pytest.raises(drill.DrillDenied):
        drill._verify_manifest_revision("856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a")
    assert len(commands) == 1

    returncode = 1
    with pytest.raises(drill.DrillDenied):
        drill._verify_manifest_revision(REVIEWED_SCHEMA_SHA)
    assert len(commands) == 2


def recovery_inspect(expected_id: str, image_id: str) -> dict[str, object]:
    """The exact disposable target shape required before pg_restore."""
    return {
        "Id": expected_id,
        "Image": image_id,
        "Config": {
            "Image": "postgres:18",
            "Labels": {"tailtag.issue": "207"},
        },
        "HostConfig": {"NetworkMode": "none", "PortBindings": {}},
        "Mounts": [
            {"Type": "tmpfs", "Destination": "/var/lib/postgresql"},
            {"Type": "tmpfs", "Destination": "/backup"},
        ],
    }


@pytest.mark.parametrize(
    "mutate",
    (
        lambda inspect: inspect.update({"Id": "different-container"}),
        lambda inspect: inspect["Config"].update({"Image": "postgres:17"}),  # type: ignore[union-attr]
        lambda inspect: inspect["Config"].update({"Labels": {"tailtag.issue": "206"}}),  # type: ignore[union-attr]
        lambda inspect: inspect["HostConfig"].update({"NetworkMode": "bridge"}),  # type: ignore[union-attr]
        lambda inspect: inspect["HostConfig"].update(
            {"PortBindings": {"5432/tcp": [{}]}}
        ),  # type: ignore[union-attr]
        lambda inspect: inspect.update({"Mounts": []}),
        lambda inspect: inspect["Mounts"].append(
            {"Type": "bind", "Destination": "/persistent"}
        ),  # type: ignore[union-attr]
    ),
)
def test_target_guard_rejects_every_non_disposable_or_non_isolated_shape(
    drill: ModuleType, mutate: Any
) -> None:
    """AC-4: pg_restore must not be routable to Staging or persistent storage."""
    expected_id = "a" * 64
    image_id = "sha256:" + "b" * 64
    inspect = recovery_inspect(expected_id, image_id)
    mutate(inspect)

    assert_denied(
        lambda: drill.validate_recovery_target(inspect, expected_id, image_id)
    )


def test_target_guard_accepts_only_the_exact_full_id_and_isolated_tmpfs_target(
    drill: ModuleType,
) -> None:
    """AC-4: the returned Docker ID and immutable image identity bind the guard."""
    expected_id = "a" * 64
    image_id = "sha256:" + "b" * 64

    assert (
        drill.validate_recovery_target(
            recovery_inspect(expected_id, image_id), expected_id, image_id
        )
        is None
    )


def test_failed_recovery_container_start_removes_the_exact_created_container(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-8: Docker may create a target and fail before returning its ID."""
    recovery_id = "c" * 64
    name = "tailtag-207-recovery-" + "a" * 32
    present = {recovery_id}
    monkeypatch.setattr(drill.uuid, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    monkeypatch.setattr(drill, "_run", lambda *_args: (_ for _ in ()).throw(OSError()))

    def command(args: tuple[str, ...], **_: object) -> SimpleNamespace:
        if args[:2] == ("docker", "ps"):
            return SimpleNamespace(returncode=0, stdout="")
        if args == ("docker", "container", "inspect", name):
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "Id": recovery_id,
                            "Name": f"/{name}",
                            "Config": {
                                "Image": "postgres:18",
                                "Labels": {"tailtag.issue": "207"},
                            },
                        }
                    ]
                ),
            )
        if args == ("docker", "rm", "--force", recovery_id):
            present.remove(recovery_id)
            return SimpleNamespace(returncode=0)
        if args == ("docker", "container", "inspect", recovery_id):
            return SimpleNamespace(returncode=1)
        pytest.fail(f"unexpected Docker call: {args!r}")

    monkeypatch.setattr(drill.subprocess, "run", command)
    with pytest.raises(OSError):
        drill._start_recovery_target(1024, 1024)
    assert not present


def test_ambiguous_failed_container_start_reports_cleanup_handle(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-8: a Docker inspection outage cannot be called verified cleanup."""
    monkeypatch.setattr(drill.uuid, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    monkeypatch.setattr(drill, "_run", lambda *_args: (_ for _ in ()).throw(OSError()))
    calls = 0

    def command(args: tuple[str, ...], **_: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 1:
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(drill.subprocess, "run", command)
    with pytest.raises(drill.CleanupUnverified) as raised:
        drill._start_recovery_target(1024, 1024)
    assert raised.value.handle == "tailtag-207-recovery-" + "a" * 32


@dataclass
class Process:
    """Small controllable process group used only at the approved cleanup seam."""

    complete: bool = False
    events: list[str] = field(default_factory=list)

    def poll(self) -> int | None:
        self.events.append("poll")
        return 0 if self.complete else None

    def terminate(self) -> None:
        self.events.append("terminate")
        self.complete = True

    def wait(self, timeout: object = None) -> int:
        self.events.append("wait")
        if not self.complete:
            raise TimeoutError
        return 0

    def kill(self) -> None:
        self.events.append("kill")
        self.complete = True


def test_failure_cleanup_terminates_every_process_then_removes_only_captured_ids(
    drill: ModuleType,
) -> None:
    """AC-8: failed streams cannot retain a dump or remove unrelated containers."""
    processes = [Process(), Process()]
    captured_ids = ["c" * 64, "d" * 64]
    commands: list[tuple[object, ...]] = []

    def command_runner(*args: object, **_: object) -> object:
        commands.append(args)
        return object()

    result = drill.cleanup_task_resources(processes, captured_ids, command_runner)

    assert all(process.complete for process in processes)
    assert all(
        "terminate" in process.events and "wait" in process.events
        for process in processes
    )
    command_text = "\n".join(" ".join(map(str, command)) for command in commands)
    assert captured_ids[0] in command_text and captured_ids[1] in command_text
    assert "tailtag-207-recovery" not in command_text
    assert result is True


def test_cleanup_uses_subprocess_run_args_shape_and_proves_the_target_is_gone(
    drill: ModuleType,
) -> None:
    """AC-8: task cleanup must work with the real subprocess.run call signature."""
    container_id = "9" * 64
    live_containers = {container_id}
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def subprocess_run_compatible(
        args: tuple[str, ...], **kwargs: object
    ) -> SimpleNamespace:
        calls.append((args, kwargs))
        if args == ("docker", "rm", "--force", container_id):
            live_containers.remove(container_id)
            return SimpleNamespace(returncode=0)
        if args == ("docker", "container", "inspect", container_id):
            return SimpleNamespace(
                returncode=1 if container_id not in live_containers else 0
            )
        pytest.fail(f"unexpected cleanup command: {args!r}")

    assert drill.cleanup_task_resources((), (container_id,), subprocess_run_compatible)
    assert not live_containers
    assert calls == [
        (
            ("docker", "rm", "--force", container_id),
            {"check": True, "capture_output": True, "text": True, "encoding": "utf-8"},
        ),
        (
            ("docker", "container", "inspect", container_id),
            {"check": False, "capture_output": True, "text": True, "encoding": "utf-8"},
        ),
    ]


@dataclass
class SnapshotCursor:
    """A read-only source cursor that exposes only the exported snapshot value."""

    statements: list[str] = field(default_factory=list)
    rows: list[tuple[str, ...]] = field(
        default_factory=lambda: [("private-snapshot-token",)]
    )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def fetchone(self) -> tuple[str]:
        return cast(tuple[str], self.rows.pop(0))


@dataclass
class SnapshotConnection:
    """Connection spy that has no database transport behind it."""

    cursor_value: SnapshotCursor
    events: list[str] = field(default_factory=list)

    def cursor(self) -> SnapshotCursor:
        self.events.append("cursor")
        return self.cursor_value

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


def tunnel_details(drill: ModuleType) -> Any:
    return drill.TunnelDetails(
        host="127.0.0.1",
        port=54321,
        user="postgres",
        password="private-password",
        database="railway",
        url=SENSITIVE,
    )


def test_source_snapshot_is_repeatable_read_only_and_remains_open_until_explicit_cleanup(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2/3: facts and pg_dump can share one exported read-only snapshot."""
    cursor = SnapshotCursor(rows=[("repeatable read",), ("private-snapshot-token",)])
    connection = SnapshotConnection(cursor)
    connect_calls: list[dict[str, object]] = []

    def connect(**kwargs: object) -> SnapshotConnection:
        connect_calls.append(kwargs)
        return connection

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))

    snapshot = drill.open_source_snapshot(tunnel_details(drill))

    assert connect_calls == [
        {
            "host": "127.0.0.1",
            "port": 54321,
            "user": "postgres",
            "password": "private-password",
            "dbname": "railway",
            "options": "-c default_transaction_read_only=on",
            "autocommit": False,
        }
    ]
    assert cursor.statements == [
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY",
        "SHOW transaction_isolation",
        "SELECT pg_export_snapshot()",
    ]
    assert connection.events == ["cursor"]
    assert snapshot.snapshot == "private-snapshot-token"

    snapshot.close()

    assert connection.events == ["cursor", "rollback", "close"]


def test_source_snapshot_refuses_to_export_when_postgresql_reports_weaker_isolation(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2/3: a snapshot must never be exported unless its active transaction is repeatable read."""
    cursor = SnapshotCursor(rows=[("read committed",)])
    connection = SnapshotConnection(cursor)
    monkeypatch.setitem(
        sys.modules, "psycopg", SimpleNamespace(connect=lambda **_kwargs: connection)
    )

    with pytest.raises(
        drill.DrillDenied, match="source snapshot isolation unavailable"
    ):
        drill.open_source_snapshot(tunnel_details(drill))

    assert cursor.statements == [
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY",
        "SHOW transaction_isolation",
    ]
    assert connection.events == ["cursor", "close"]


def test_recovery_readiness_uses_tcp_loopback_not_the_entrypoint_unix_socket(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4: readiness waits for the networked server that will serve pg_restore."""
    readiness_commands: list[tuple[str, ...]] = []

    def command(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        readiness_commands.append(command)
        assert kwargs["check"] is False
        assert isinstance(kwargs["timeout"], int)
        assert kwargs["timeout"] <= 60
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(drill.subprocess, "run", command)
    monkeypatch.setattr(
        drill,
        "_run",
        lambda *_command, **_kwargs: (
            SimpleNamespace(stdout="180000\n")
            if _command[-1] == "SHOW server_version_num"
            else SimpleNamespace(stdout="0\n")
        ),
    )

    drill._wait_for_empty_postgres("a" * 64)

    assert readiness_commands == [
        (
            "docker",
            "exec",
            "a" * 64,
            "pg_isready",
            "--host",
            "127.0.0.1",
            "--username",
            "postgres",
            "--dbname",
            drill.TARGET_DATABASE,
        )
    ]


def test_recovery_readiness_retries_a_slow_probe_within_the_deadline(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4: one timed-out Docker probe cannot reject a target that becomes ready."""
    calls = 0

    def command(command: tuple[str, ...], **kwargs: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        assert 0 < cast(float, kwargs["timeout"]) <= 5
        if calls == 1:
            raise drill.subprocess.TimeoutExpired(command, kwargs["timeout"])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(drill.subprocess, "run", command)
    monkeypatch.setattr(
        drill,
        "_run",
        lambda *_command, **_kwargs: (
            SimpleNamespace(stdout="180000\n")
            if _command[-1] == "SHOW server_version_num"
            else SimpleNamespace(stdout="0\n")
        ),
    )

    drill._wait_for_empty_postgres("a" * 64)

    assert calls == 2


def test_recovery_readiness_probe_cannot_outlast_its_remaining_budget(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4: repeated slow probes fail only when the overall readiness budget expires."""
    clock = [0.0]
    timeouts: list[float] = []

    def command(command: tuple[str, ...], **kwargs: object) -> NoReturn:
        timeout = cast(float, kwargs["timeout"])
        timeouts.append(timeout)
        clock[0] = 58.75 if len(timeouts) == 1 else 60.0
        raise drill.subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(drill.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(drill.subprocess, "run", command)

    with pytest.raises(
        drill.DrillDenied, match="recovery database did not become ready"
    ):
        drill._wait_for_empty_postgres("a" * 64)

    assert timeouts == [5.0, 1.25]


REAL_POPEN = subprocess.Popen
ARCHIVE = b"custom-format-archive"
SLEEP = "import time; time.sleep(600)"
DUMP_ARCHIVE = (
    f"import sys; sys.stdout.buffer.write({ARCHIVE!r}); sys.stdout.buffer.flush()"
)
# Crashes after a partial archive, as pg_dump would when its connection drops.
DUMP_CRASH = (
    "import sys; sys.stdout.buffer.write(b'x' * 100000); "
    "sys.stdout.buffer.flush(); sys.exit(1)"
)
# Exits successfully after reading a little, as a receiver that failed silently.
RECEIVER_QUITS = "import sys; sys.stdin.buffer.read(1024)"
TUNNEL_PARTIAL = (
    "import sys, time\n"
    "sys.stdout.write('Host: 127.0.0.1\\nPort: 54321\\nUser: pos')\n"
    "sys.stdout.flush()\n"
    "time.sleep(0.3)\n"
    "sys.stdout.write('tgres\\nPassword: private-password\\nDatabase: railway\\n"
    "URL: postgresql://synthetic\\n')\n"
    "sys.stdout.flush()\n"
    "time.sleep(600)\n"
)


def receiver_records_to(path: Path) -> str:
    return (
        "import sys\n"
        f"with open({str(path)!r}, 'wb') as output:\n"
        "    output.write(sys.stdin.buffer.read())\n"
    )


def dump_floods_and_logs_progress(path: Path) -> str:
    return (
        "import sys\n"
        "block = b'x' * 65536\n"
        "written = 0\n"
        "for _ in range(1024):\n"
        "    sys.stdout.buffer.write(block)\n"
        "    sys.stdout.buffer.flush()\n"
        "    written += len(block)\n"
        f"    open({str(path)!r}, 'w').write(str(written))\n"
    )


@pytest.fixture
def children() -> Iterator[list[Any]]:
    """Real child processes started through the drill; none may outlive a test."""
    started: list[Any] = []
    yield started
    for process in started:
        if process.poll() is None:
            process.kill()
        process.wait(10)
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


def run_real_children(
    monkeypatch: pytest.MonkeyPatch,
    drill: ModuleType,
    started: list[Any],
    scripts: dict[str, str],
) -> list[tuple[tuple[str, ...], object]]:
    """Run a tiny Python child in place of pg_dump, docker, or railway.

    Only the external executables are substituted; pipes, process groups or
    job objects, and every kwarg the drill passes are real.
    """
    calls: list[tuple[tuple[str, ...], object]] = []

    def popen(command: tuple[str, ...], **kwargs: Any) -> Any:
        calls.append((command, kwargs.get("env")))
        process = REAL_POPEN([sys.executable, "-c", scripts[command[0]]], **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(drill.subprocess, "Popen", popen)
    return calls


def fast_clock(
    monkeypatch: pytest.MonkeyPatch, drill: ModuleType, factor: int = 2000
) -> None:
    """Make the drill's deadlines elapse quickly without touching real waits."""
    real_time = time
    start = real_time.monotonic()
    monkeypatch.setattr(
        drill,
        "time",
        SimpleNamespace(
            **{
                **vars(real_time),
                "monotonic": lambda: start + (real_time.monotonic() - start) * factor,
            }
        ),
    )


def with_watchdog(operation: Callable[[], Any], timeout: float = 60) -> Any:
    """Fail, instead of hanging the suite, if the operation never returns."""
    outcome: dict[str, Any] = {}

    def target() -> None:
        try:
            outcome["value"] = operation()
        except BaseException as error:  # noqa: BLE001 - re-raised below
            outcome["error"] = error

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        pytest.fail("operation hung instead of returning or being denied")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def test_pg_dump_uses_the_exported_snapshot_and_streams_only_to_the_fixed_target(
    drill: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    children: list[Any],
    tmp_path: Path,
) -> None:
    """AC-3/4, S3-5: no host archive or alternate destination; every byte arrives."""
    received = tmp_path / "received.bin"
    calls = run_real_children(
        monkeypatch,
        drill,
        children,
        {"pg_dump": DUMP_ARCHIVE, "docker": receiver_records_to(received)},
    )
    container_id = "e" * 64

    transferred = with_watchdog(
        lambda: drill.dump_snapshot_to_target(
            tunnel_details(drill),
            SimpleNamespace(snapshot="private-snapshot-token"),
            container_id,
        )
    )

    dump_command = calls[0][0]
    receiver_command = calls[1][0]
    assert "--format=custom" in dump_command
    assert "--no-owner" in dump_command and "--no-acl" in dump_command
    assert ("--snapshot", "private-snapshot-token") == tuple(
        dump_command[dump_command.index("--snapshot") :][:2]
    )
    assert SENSITIVE not in " ".join(map(str, dump_command))
    assert receiver_command[:4] == ("docker", "exec", "-i", container_id)
    assert receiver_command[-1] == "cat > /backup/recovery.dump"
    assert received.read_bytes() == ARCHIVE
    assert transferred == len(ARCHIVE)


@pytest.mark.parametrize(
    ("dump_script", "receiver_script"),
    (
        pytest.param(DUMP_CRASH, "receiver", id="dump-crashes-partway"),
        pytest.param("flood", RECEIVER_QUITS, id="receiver-exits-zero-partway"),
    ),
)
def test_a_failure_partway_through_the_stream_is_a_denial_never_success(
    drill: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    children: list[Any],
    tmp_path: Path,
    dump_script: str,
    receiver_script: str,
) -> None:
    """AC-3/8, S3-5: a truncated archive cannot be reported as a completed dump.

    The writer failing silently is the dangerous case: the receiver's stdin
    closes, the receiver exits 0 with a truncated file, and the reader still
    reached its end. Catches: a writer-thread failure that is not re-raised,
    and success judged only from exit codes.
    """
    received = tmp_path / "received.bin"
    scripts = {
        "pg_dump": (
            dump_floods_and_logs_progress(tmp_path / "progress")
            if dump_script == "flood"
            else dump_script
        ),
        "docker": (
            receiver_records_to(received)
            if receiver_script == "receiver"
            else receiver_script
        ),
    }
    run_real_children(monkeypatch, drill, children, scripts)

    with pytest.raises(drill.DrillDenied):
        with_watchdog(
            lambda: drill.dump_snapshot_to_target(
                tunnel_details(drill), SimpleNamespace(snapshot="snapshot"), "f" * 64
            )
        )

    assert all(process.wait(20) is not None for process in children)


@pytest.mark.parametrize(
    "blocked_receiver", (False, True), ids=("silent-dump", "blocked-receiver")
)
def test_a_stalled_stream_observes_the_total_deadline_and_stops_both_children(
    drill: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    children: list[Any],
    tmp_path: Path,
    blocked_receiver: bool,
) -> None:
    """AC-3/8 RELIABILITY, S3-5: open but silent pipes time out; the buffer stays bounded.

    A producer that never writes, or a receiver that never reads, must end in
    the existing denial with both children stopped. With a blocked receiver
    the host may hold roughly one chunk, so the flooding dump is stopped far
    short of its 64 MiB. Catches: a missing main-thread deadline, children left
    running, and an unbounded queue between the reader and writer.
    """
    progress = tmp_path / "progress"
    run_real_children(
        monkeypatch,
        drill,
        children,
        {
            "pg_dump": (
                dump_floods_and_logs_progress(progress) if blocked_receiver else SLEEP
            ),
            "docker": SLEEP,
        },
    )
    fast_clock(monkeypatch, drill)

    with pytest.raises(drill.DrillDenied, match="custom dump timed out"):
        with_watchdog(
            lambda: drill.dump_snapshot_to_target(
                tunnel_details(drill), SimpleNamespace(snapshot="snapshot"), "f" * 64
            )
        )

    assert all(process.wait(20) is not None for process in children)
    if blocked_receiver:
        assert int(progress.read_text() or "0") < 8 * 1024 * 1024


def drill_tunnel_environment(
    monkeypatch: pytest.MonkeyPatch, drill: ModuleType
) -> None:
    monkeypatch.setattr(drill, "_target_ids", lambda: REPLACEMENT_IDS)
    monkeypatch.setattr(drill, "verify_railway_identity", lambda: None)


def test_tunnel_details_arrive_in_pieces_and_the_tunnel_stays_open_afterwards(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch, children: list[Any]
) -> None:
    """AC-1/2, S3-5: details split across writes parse, and the tunnel outlives the read.

    Catches: a tunnel reader that needs select or blocks for a full buffer, a
    reader that closes or drains the tunnel's stdout after parsing, and one
    that cannot assemble a partial line.
    """
    drill_tunnel_environment(monkeypatch, drill)
    run_real_children(monkeypatch, drill, children, {"railway": TUNNEL_PARTIAL})

    tunnel, details = with_watchdog(drill.open_railway_tunnel)

    assert (details.host, details.port, details.user) == (
        "127.0.0.1",
        54321,
        "postgres",
    )
    assert tunnel.poll() is None
    assert tunnel.stdout is not None and not tunnel.stdout.closed
    assert drill.cleanup_task_resources((tunnel,), ()) is True
    assert tunnel.wait(20) is not None


@pytest.mark.parametrize(
    "script",
    ("print('not a tunnel')", SLEEP),
    ids=("garbage-then-exit", "silent-until-deadline"),
)
def test_a_tunnel_that_never_yields_details_is_denied_and_reaped(
    drill: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    children: list[Any],
    script: str,
) -> None:
    """AC-1/8, S3-5: no details means a denial within the deadline and no leftover tunnel."""
    drill_tunnel_environment(monkeypatch, drill)
    run_real_children(monkeypatch, drill, children, {"railway": script})
    fast_clock(monkeypatch, drill)

    with pytest.raises(drill.DrillDenied, match="Railway tunnel unavailable"):
        with_watchdog(drill.open_railway_tunnel)

    assert all(process.wait(20) is not None for process in children)


@pytest.mark.parametrize(
    ("endpoint", "accepted_on_posix", "accepted_on_windows"),
    (
        ("unix:///private/docker.sock", True, False),
        ("npipe:////./pipe/docker_engine", False, True),
        ("npipe:////./pipe/docker.desktop-linux", False, True),
        ("npipe:////host/pipe/docker_engine", False, False),
        ("npipe:///./pipe/docker_engine", False, False),
        ("npipe://./pipe/docker_engine", False, False),
        ("npipe:////./pipe/", False, False),
        ("npipe:////./pipe/docker/engine", False, False),
        ("npipe:////./pipe/docker engine", False, False),
        ("npipe:////./pipe/docker_engine/", False, False),
        ("tcp://127.0.0.1:2375", False, False),
        ("", False, False),
    ),
)
def test_docker_endpoint_must_be_a_local_socket_or_pipe_for_this_platform(
    drill: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
    accepted_on_posix: bool,
    accepted_on_windows: bool,
) -> None:
    """D4, S3-7: the Staging dump can only reach a local Docker daemon.

    The endpoint check precedes everything else in preflight, so acceptance is
    observed as the next step (the tool-version probe) being reached.
    Catches: accepting a remote npipe host, accepting malformed npipe variants
    through a prefix match, accepting unix:// on Windows, and breaking POSIX.
    """
    reached: list[str] = []
    monkeypatch.setattr(drill, "_target_ids", lambda: REPLACEMENT_IDS)
    monkeypatch.setattr(
        drill, "_run", lambda *_args, **_kwargs: SimpleNamespace(stdout=endpoint + "\n")
    )

    def tool_versions() -> NoReturn:
        reached.append("tool versions")
        raise drill.DrillDenied("unavailable")

    monkeypatch.setattr(drill, "_tool_versions", tool_versions)
    monkeypatch.setattr(drill, "write_sanitized_evidence", lambda *_args: None)

    with pytest.raises(drill.DrillDenied, match="restore drill failed at PREFLIGHT"):
        drill.run_drill()

    accepted = accepted_on_windows if sys.platform == "win32" else accepted_on_posix
    assert (reached == ["tool versions"]) is accepted


def test_command_runner_sets_a_bounded_default_subprocess_deadline(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-8 RELIABILITY: a command invoked without an explicit budget cannot run forever."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        drill.subprocess,
        "run",
        lambda _command, **kwargs: (
            calls.append(kwargs) or SimpleNamespace(stdout="", returncode=0)
        ),
    )

    drill._run("fixed", "command")

    assert len(calls) == 1
    assert isinstance(calls[0].get("timeout"), int)
    assert 0 < cast(int, calls[0]["timeout"]) <= 1_800


def test_recovery_queries_use_a_bounded_read_only_subprocess_deadline(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-5/8 RELIABILITY: catalog validation cannot wait forever on a restored target."""
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def command(*args: str, **kwargs: object) -> SimpleNamespace:
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="count\n0\n")

    monkeypatch.setattr(drill, "_run", command)

    assert drill.recovery_query_executor("e" * 64)("SELECT 0 AS count") == [
        {"count": 0}
    ]
    assert calls[0][1]["timeout"] == 60
    assert calls[0][1]["input"] == "BEGIN READ ONLY; SELECT 0 AS count; ROLLBACK;"


def sanitized_evidence() -> dict[str, object]:
    """One complete public-safe #207 outcome record with no row-level data."""
    return {
        "schema_version": 1,
        "outcome": "GO",
        "mechanism": "logical_custom_pg_dump",
        "selection_reason": "LOGICAL_DUMP_FOR_ISOLATED_RESTORE_PROOF",
        "recovery_point_time": "2026-09-22T12:00:00Z",
        "source_sha": "a" * 40,
        "source_deployment_fingerprint": "b" * 64,
        "source_database_fingerprint": "c" * 64,
        "source_postgres_major": 18,
        "source_migration_leaves": ["accounts.0001_initial"],
        "source_table_counts": {
            "accounts_user": 1,
            "profiles_playerprofile": 1,
            "fursuits_fursuit": 1,
            "conventions_convention": 1,
            "conventions_conventionenrollment": 1,
            "conventions_fursuitactivation": 1,
            "conventions_fursuitcatchsession": 1,
            "conventions_fursuitcatchcredential": 1,
            "catches_catch": 1,
        },
        "source_constraint_catalog_digest": "d" * 64,
        "tool_versions": {"pg_dump": "18.6", "pg_restore": "18.6"},
        "target_class": "local_disposable_docker_tmpfs",
        "dump_started_at": "2026-09-22T12:00:01Z",
        "dump_completed_at": "2026-09-22T12:00:13Z",
        "restore_started_at": "2026-09-22T12:00:14Z",
        "restore_completed_at": "2026-09-22T12:00:48Z",
        "dump_duration_seconds": 12,
        "restore_duration_seconds": 34,
        "checks": {
            "dump_archive": "PASS",
            "profile_user_one_to_one": "PASS",
            "catch_representative_read": "NOT_EXERCISED",
        },
        "backend_usability": "PASS",
        "staging_nonimpact": "PASS",
        "cleanup_verified": True,
        "failure_stage": None,
        "limitations": [],
        "follow_up": [],
    }


def test_evidence_writer_persists_only_the_fixed_sanitized_allowlist(
    drill: ModuleType, tmp_path: Path
) -> None:
    """AC-9: durable proof has bounded fields, no process output, and no secrets."""
    destination = tmp_path / "2026-09-22-issue-207-restore.json"
    evidence = sanitized_evidence()

    drill.write_sanitized_evidence(destination, evidence)

    assert json.loads(destination.read_text()) == evidence
    # S3-6: durable evidence is private on every platform.
    if sys.platform == "win32":
        access = acl.read_access(destination)
        assert access.protected
        assert len(access.entries) == 3
    else:
        assert (destination.stat().st_mode & 0o777) == 0o600


def test_evidence_writer_refuses_to_overwrite_an_existing_durable_record(
    drill: ModuleType, tmp_path: Path
) -> None:
    """AC-9: a second attempt cannot replace evidence captured for an earlier drill."""
    destination = tmp_path / "2026-09-22-issue-207-restore.json"
    original = sanitized_evidence()
    drill.write_sanitized_evidence(destination, original)

    with pytest.raises(drill.DrillDenied, match="sanitized evidence write failed"):
        drill.write_sanitized_evidence(destination, sanitized_evidence())

    assert json.loads(destination.read_text()) == original


def test_runner_uses_a_distinct_timestamped_evidence_path_for_each_attempt(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-9: independent attempts retain separate durable outcomes rather than replacing one file."""
    paths: list[Path] = []
    evidence_records: list[dict[str, object]] = []
    monkeypatch.setattr(drill, "_target_ids", lambda: REPLACEMENT_IDS)
    monkeypatch.setattr(
        drill,
        "_run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=DOCKER_ENDPOINT),
    )
    monkeypatch.setattr(
        drill,
        "_tool_versions",
        lambda: (_ for _ in ()).throw(drill.DrillDenied("unavailable")),
    )

    def capture_evidence(path: Path, evidence: dict[str, object]) -> None:
        paths.append(path)
        evidence_records.append(dict(evidence))

    monkeypatch.setattr(drill, "write_sanitized_evidence", capture_evidence)

    for _ in range(2):
        with pytest.raises(
            drill.DrillDenied, match="restore drill failed at PREFLIGHT"
        ):
            drill.run_drill()

    assert len(paths) == 2
    assert paths[0].parent == paths[1].parent
    assert paths[0] != paths[1]
    assert all(
        evidence["selection_reason"] == "LOGICAL_DUMP_FOR_ISOLATED_RESTORE_PROOF"
        for evidence in evidence_records
    )
    assert all(
        re.fullmatch(
            r"[0-9]{8}T[0-9]{6}Z-issue-207-restore-[0-9a-f]{32}\.json",
            path.name,
        )
        for path in paths
    )


def test_failure_evidence_preserves_boundary_after_verified_cleanup(
    drill: ModuleType, tmp_path: Path
) -> None:
    """AC-8/9: an early refusal has a durable, bounded failure result."""
    evidence = sanitized_evidence()
    evidence.update(
        outcome="FAIL",
        recovery_point_time=None,
        source_sha=None,
        source_deployment_fingerprint=None,
        source_database_fingerprint=None,
        source_postgres_major=None,
        source_migration_leaves=None,
        source_table_counts=None,
        source_constraint_catalog_digest=None,
        tool_versions=None,
        dump_started_at=None,
        dump_completed_at=None,
        restore_started_at=None,
        restore_completed_at=None,
        checks={},
        backend_usability="NOT_EXERCISED",
        staging_nonimpact="NOT_EXERCISED",
        failure_stage="PREFLIGHT",
        local_recovery_handle=None,
    )
    destination = tmp_path / "failure.json"

    drill.write_sanitized_evidence(destination, evidence)

    assert json.loads(destination.read_text()) == evidence


def test_failure_evidence_keeps_only_opaque_task_handle_when_cleanup_is_unverified(
    drill: ModuleType, tmp_path: Path
) -> None:
    """AC-8/9: a cleanup failure cannot be marked as GO or lose its local handle."""
    evidence = sanitized_evidence()
    evidence.update(
        outcome="FAIL",
        cleanup_verified=False,
        failure_stage="CLEANUP",
        local_recovery_handle="d" * 64,
        follow_up=["CLEANUP_UNVERIFIED"],
    )
    destination = tmp_path / "cleanup-failure.json"

    drill.write_sanitized_evidence(destination, evidence)

    assert json.loads(destination.read_text()) == evidence


@pytest.mark.parametrize(
    "mutate",
    (
        lambda evidence: evidence.update({"private_url": SENSITIVE}),
        lambda evidence: evidence.update({"source_sha": SENSITIVE}),
        lambda evidence: evidence.update({"checks": {"raw_error": SENSITIVE}}),
        lambda evidence: evidence.update(
            {"checks": {"operator_supplied_name": "PASS"}}
        ),
        lambda evidence: evidence.update({"recovery_point_time": "not-a-utc-time"}),
        lambda evidence: evidence.update({"limitations": ["UNAPPROVED_CODE"]}),
        lambda evidence: evidence.update({"cleanup_verified": False}),
        lambda evidence: evidence.update(
            {"selection_reason": "PITR_DISABLED_NO_VOLUME_BACKUPS_LOGICAL_DUMP"}
        ),
    ),
)
def test_evidence_writer_rejects_unsafe_or_incomplete_records_without_writing(
    drill: ModuleType, tmp_path: Path, mutate: Any
) -> None:
    """AC-8/9: incomplete cleanup and sensitive or free-form evidence are absent."""
    destination = tmp_path / "restore.json"
    evidence = sanitized_evidence()
    mutate(evidence)

    with pytest.raises(drill.DrillDenied):
        drill.write_sanitized_evidence(destination, evidence)

    assert not destination.exists()


def install_runner_preflight(
    monkeypatch: pytest.MonkeyPatch,
    drill: ModuleType,
    identities: list[dict[str, object]],
) -> None:
    """Replace only external command/source seams for an offline runner observation."""
    monkeypatch.setattr(drill, "_target_ids", lambda: REPLACEMENT_IDS)
    monkeypatch.setattr(
        drill,
        "_run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=DOCKER_ENDPOINT),
    )
    monkeypatch.setattr(drill, "verify_railway_identity", lambda: None)
    monkeypatch.setattr(drill, "_verify_exact_deployment", lambda _identity: None)
    monkeypatch.setattr(
        drill, "_staging_database_fingerprint", lambda _target_ids: "a" * 64
    )
    monkeypatch.setattr(
        drill, "_tool_versions", lambda: {"pg_dump": "18.6", "pg_restore": "18.6"}
    )
    monkeypatch.setattr(drill, "write_sanitized_evidence", lambda *_args: None)
    monkeypatch.setattr(drill, "_docker_image_id", lambda: "sha256:" + "a" * 64)
    monkeypatch.setattr(drill, "_active_staging_identity", lambda: identities.pop(0))
    monkeypatch.setattr(
        drill,
        "_create_exact_source_worktree",
        lambda _source_sha: Path("/tmp/tailtag-207-source"),
    )
    monkeypatch.setattr(
        drill, "_remove_exact_source_worktree", lambda _source_root: True
    )
    monkeypatch.setattr(drill, "_migration_leaves", lambda: frozenset())
    monkeypatch.setattr(drill, "_verify_manifest_revision", lambda _sha: None)


def test_runner_refuses_target_identity_mismatch_before_dump_or_restore(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1/4: an inspected target mismatch cannot receive a source archive."""
    import scripts.staging_restore_integrity as integrity

    identity: dict[str, object] = {
        "source_sha": "b" * 40,
        "deployment_id": "deployment",
        "environment": "staging",
    }
    install_runner_preflight(monkeypatch, drill, [identity])
    tunnel = Process()
    closed: list[str] = []
    cleanup_calls: list[tuple[tuple[object, ...], tuple[object, ...]]] = []
    evidence_records: list[dict[str, object]] = []
    created_id = "c" * 64

    monkeypatch.setattr(
        drill,
        "open_railway_tunnel",
        lambda _target_ids: (tunnel, tunnel_details(drill)),
    )
    monkeypatch.setattr(
        drill,
        "open_source_snapshot",
        lambda _details: SimpleNamespace(
            query=lambda _sql: [], close=lambda: closed.append("snapshot")
        ),
    )
    monkeypatch.setattr(
        drill, "_capacity_bytes", lambda _snapshot: (2 * 1024**3, 1024**3)
    )
    monkeypatch.setattr(
        integrity,
        "collect_integrity",
        lambda *_args: SimpleNamespace(
            table_counts={},
            constraint_fingerprints={},
            representative_records={},
        ),
    )
    monkeypatch.setattr(drill, "_start_recovery_target", lambda *_args: created_id)
    monkeypatch.setattr(
        drill,
        "_docker_inspect",
        lambda _container_id: recovery_inspect("d" * 64, "sha256:" + "a" * 64),
    )
    monkeypatch.setattr(
        drill,
        "cleanup_task_resources",
        lambda processes, container_ids: (
            cleanup_calls.append((tuple(processes), tuple(container_ids))) or True
        ),
    )
    monkeypatch.setattr(
        drill,
        "write_sanitized_evidence",
        lambda _path, value: evidence_records.append(dict(value)),
    )
    monkeypatch.setattr(
        drill,
        "dump_snapshot_to_target",
        lambda *_args: pytest.fail("target mismatch reached pg_dump"),
    )
    monkeypatch.setattr(
        drill,
        "restore_archive",
        lambda *_args: pytest.fail("target mismatch reached pg_restore"),
    )

    with pytest.raises(drill.DrillDenied) as raised:
        drill.run_drill()

    assert str(raised.value) == "restore drill failed at TARGET"
    assert closed == ["snapshot"]
    assert any(container_ids == (created_id,) for _, container_ids in cleanup_calls)
    assert len(evidence_records) == 1
    assert evidence_records[0]["outcome"] == "FAIL"
    assert evidence_records[0]["failure_stage"] == "TARGET"
    assert evidence_records[0]["cleanup_verified"] is True


def test_runner_marks_changed_staging_identity_as_a_failed_nonimpact_proof_and_cleans_up(
    drill: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-7/8: a restore cannot pass if canonical Staging changes during the drill."""
    import scripts.staging_restore_integrity as integrity

    before: dict[str, object] = {
        "source_sha": "b" * 40,
        "deployment_id": "before",
        "environment": "staging",
    }
    after: dict[str, object] = {
        "source_sha": "d" * 40,
        "deployment_id": "after",
        "environment": "staging",
    }
    install_runner_preflight(monkeypatch, drill, [before, after])
    recovery_id = "e" * 64
    cleanup_calls: list[tuple[tuple[object, ...], tuple[object, ...]]] = []
    backend_calls: list[str] = []

    monkeypatch.setattr(
        drill,
        "open_railway_tunnel",
        lambda _target_ids: (Process(), tunnel_details(drill)),
    )
    monkeypatch.setattr(
        drill,
        "open_source_snapshot",
        lambda _details: SimpleNamespace(query=lambda _sql: [], close=lambda: None),
    )
    monkeypatch.setattr(
        drill, "_capacity_bytes", lambda _snapshot: (2 * 1024**3, 1024**3)
    )
    monkeypatch.setattr(
        integrity,
        "collect_integrity",
        lambda *_args: SimpleNamespace(
            table_counts={},
            constraint_fingerprints={},
            representative_records={
                table: False for table in drill._REPRESENTATIVE_CHECKS
            },
        ),
    )
    monkeypatch.setattr(
        integrity,
        "compare_integrity",
        lambda *_args: SimpleNamespace(
            overall_outcome="PASS",
            checks={
                name: "PASS"
                for name in drill._EVIDENCE_CHECK_NAMES
                - {"dump_archive", "restore", "target_guard"}
            },
        ),
    )
    monkeypatch.setattr(drill, "_start_recovery_target", lambda *_args: recovery_id)
    monkeypatch.setattr(
        drill,
        "_docker_inspect",
        lambda _container_id: recovery_inspect(recovery_id, "sha256:" + "a" * 64),
    )
    monkeypatch.setattr(drill, "_wait_for_empty_postgres", lambda _container_id: None)
    monkeypatch.setattr(drill, "dump_snapshot_to_target", lambda *_args: 1)
    monkeypatch.setattr(drill, "restore_archive", lambda _container_id: None)
    monkeypatch.setattr(
        drill, "recovery_query_executor", lambda _container_id: lambda _sql: []
    )
    monkeypatch.setattr(
        drill,
        "_build_exact_backend_image",
        lambda _source_sha: "sha256:" + "f" * 64,
    )
    monkeypatch.setattr(
        drill,
        "backend_read_only_proof",
        lambda _image, _container_id: backend_calls.append("read-only") or "backend-id",
    )
    monkeypatch.setattr(
        drill,
        "cleanup_task_resources",
        lambda processes, container_ids: (
            cleanup_calls.append((tuple(processes), tuple(container_ids))) or True
        ),
    )

    with pytest.raises(drill.DrillDenied) as raised:
        drill.run_drill()

    assert str(raised.value) == "restore drill failed at NONIMPACT"
    assert backend_calls == ["read-only"]
    assert any(container_ids == (recovery_id,) for _, container_ids in cleanup_calls)
