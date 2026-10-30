"""PostgreSQL integration contract for #204 maintenance connection gating."""

from __future__ import annotations

import importlib
import os
import sys
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest
from django.db import connection, connections
from psycopg import sql

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
DEDICATED_DATABASE = "tailtag_204_maintenance_test"
RENDER_OWNER = "tailtag_204_render_owner"
OTHER_ROLE = "tailtag_204_other_role"
ROLE_PASSWORD = "local-test-only"
MEDIA_KEY = "images/0123456789abcdef0123456789abcdef.png"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


@dataclass(frozen=True)
class MaintenanceTarget:
    configuration: Any
    target_url: str
    control_url: str


class _ControlResult:
    """Forward a real control query while replacing only its identity facts."""

    def __init__(
        self, delegate: psycopg.Cursor[Any], replacement: tuple[object, object, object]
    ) -> None:
        self._delegate = delegate
        self._replacement = replacement

    def fetchone(self) -> tuple[object, object, object]:
        self._delegate.fetchone()
        return self._replacement

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)


class _ControlConnection:
    """Forward normal psycopg operations and expose their observable ordering."""

    def __init__(
        self,
        delegate: psycopg.Connection[Any],
        events: list[str],
        replacement: tuple[object, object, object] | None = None,
        before_terminate: Callable[[], None] | None = None,
    ) -> None:
        self._delegate = delegate
        self._events = events
        self._replacement = replacement
        self._before_terminate = before_terminate

    def execute(self, query: Any, *args: Any, **kwargs: Any) -> Any:
        text = str(query)
        self._events.append(text)
        if "pg_terminate_backend" in text and self._before_terminate is not None:
            self._before_terminate()
        result = self._delegate.execute(query, *args, **kwargs)
        if "pg_control_system" in text and self._replacement is not None:
            return _ControlResult(result, self._replacement)
        return result

    def __getattr__(self, name: str) -> object:
        return getattr(self._delegate, name)


def validated_identity(_: object) -> object:
    """Keep maintenance integration focused on database mechanics."""
    return object()


@pytest.fixture
def safety() -> Any:
    """Delay the new production import so RED remains a normal missing-feature failure."""
    assert (API_ROOT / "rehearsal" / "safety.py").is_file()
    return cast(Any, importlib.import_module("rehearsal.safety"))


def control_url() -> str:
    """Use the task-owned local PostgreSQL control database, never a live endpoint."""
    parsed = urlparse(os.environ["DATABASE_URL"])
    return urlunparse(parsed._replace(path="/postgres"))


@pytest.fixture
def maintenance_target(safety: ModuleType) -> Generator[MaintenanceTarget]:
    """Point Django at one disposable DB and always restore/drop only that DB."""
    with _dedicated_target(safety) as target:
        yield target


@pytest.fixture
def local_roles() -> Generator[None]:
    """Create task-owned login roles that are never superusers, then drop them."""
    with psycopg.connect(control_url(), autocommit=True) as database:
        for role in (RENDER_OWNER, OTHER_ROLE):
            database.execute(f"DROP ROLE IF EXISTS {role}")
            database.execute(
                f"CREATE ROLE {role} LOGIN NOSUPERUSER PASSWORD '{ROLE_PASSWORD}'"
            )
    yield
    with psycopg.connect(control_url(), autocommit=True) as database:
        for role in (RENDER_OWNER, OTHER_ROLE):
            database.execute(f"DROP ROLE IF EXISTS {role}")


@pytest.fixture
def render_owner_target(
    safety: ModuleType, local_roles: None
) -> Generator[MaintenanceTarget]:
    """Run the executor as the non-superuser owner, like Render Postgres."""
    with _dedicated_target(
        safety, owner=RENDER_OWNER, executor=RENDER_OWNER, platform="render"
    ) as target:
        yield target


def _role_url(url: str, role: str) -> str:
    parsed = urlparse(url)
    netloc = f"{role}:{ROLE_PASSWORD}@{parsed.hostname}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


@contextmanager
def _dedicated_target(
    safety: ModuleType,
    *,
    owner: str | None = None,
    executor: str | None = None,
    platform: str = "railway",
) -> Generator[MaintenanceTarget]:
    control = control_url()
    target = urlunparse(urlparse(control)._replace(path=f"/{DEDICATED_DATABASE}"))
    with psycopg.connect(control, autocommit=True) as database:
        database.execute(f"DROP DATABASE IF EXISTS {DEDICATED_DATABASE}")
        create = sql.SQL("CREATE DATABASE {}").format(
            sql.Identifier(DEDICATED_DATABASE)
        )
        if owner:
            create = sql.SQL("{} OWNER {}").format(create, sql.Identifier(owner))
        database.execute(create)

    database_settings = connections.databases["default"]
    original = deepcopy(database_settings)
    connections.close_all()
    database_settings["NAME"] = DEDICATED_DATABASE
    if executor is not None:
        database_settings["USER"] = executor
        database_settings["PASSWORD"] = ROLE_PASSWORD
        target = _role_url(target, executor)
    connection.ensure_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT (pg_control_system()).system_identifier")
            system_identifier = str(cursor.fetchone()[0])
        yield MaintenanceTarget(
            configuration=safety.ResetConfiguration(
                environment_id=uuid.uuid4(),
                cluster_identifier=system_identifier,
                database_host=str(database_settings["HOST"]),
                database_port=str(database_settings["PORT"]),
                database_name=DEDICATED_DATABASE,
                owner_clerk_id="user_rehearsal_owner",
                catcher_clerk_id="user_rehearsal_catcher",
                media_key=MEDIA_KEY,
                platform=platform,
            ),
            target_url=target,
            control_url=control,
        )
    finally:
        connections.close_all()
        with psycopg.connect(control, autocommit=True) as database:
            database.execute(
                f"ALTER DATABASE {DEDICATED_DATABASE} WITH ALLOW_CONNECTIONS true"
            )
            database.execute(f"DROP DATABASE IF EXISTS {DEDICATED_DATABASE}")
        database_settings.clear()
        database_settings.update(original)
        connection.ensure_connection()


def target_allows_connections(control: str) -> bool:
    with psycopg.connect(control, autocommit=True) as database:
        row = database.execute(
            "SELECT datallowconn FROM pg_database WHERE datname = %s",
            (DEDICATED_DATABASE,),
        ).fetchone()
    assert row is not None
    return bool(row[0])


@pytest.mark.django_db(transaction=True)
def test_maintenance_quiesces_a_dedicated_database_and_reopens_only_after_success(
    safety: ModuleType,
    maintenance_target: MaintenanceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5/6: committed gate plus sole retained executor, not a lock, proves quiescence."""
    assert target_allows_connections(maintenance_target.control_url) is True
    monkeypatch.setattr(safety, "validate_identity", validated_identity)

    with safety.DatabaseMaintenance(maintenance_target.configuration) as maintenance:
        maintenance.quiesce()

        assert target_allows_connections(maintenance_target.control_url) is False
        with pytest.raises(psycopg.OperationalError):
            psycopg.connect(maintenance_target.target_url, connect_timeout=1)
        safety.assert_quiescent(maintenance_target.configuration)
        maintenance.resume()

    assert target_allows_connections(maintenance_target.control_url) is True


@pytest.mark.django_db(transaction=True)
def test_reset_failure_retains_the_committed_maintenance_gate_for_recovery(
    safety: ModuleType,
    maintenance_target: MaintenanceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6/7/RELIABILITY: exception paths cannot resume writers before safe proof."""
    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    with (
        pytest.raises(RuntimeError, match="forced reset failure"),
        safety.DatabaseMaintenance(maintenance_target.configuration) as maintenance,
    ):
        maintenance.quiesce()
        raise RuntimeError("forced reset failure")

    assert target_allows_connections(maintenance_target.control_url) is False


@pytest.mark.django_db(transaction=True)
def test_maintenance_refuses_postgres_as_the_mutation_target(
    safety: ModuleType,
    maintenance_target: MaintenanceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5/6: control database is never an eligible destructive target."""
    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    configuration = replace(maintenance_target.configuration, database_name="postgres")

    with (
        pytest.raises(safety.ResetSafetyError),
        safety.DatabaseMaintenance(configuration),
    ):
        raise AssertionError("unsafe control target opened maintenance")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "wrong_control_facts",
    (("wrong-control-database", None, True), ("postgres", "999999999", True)),
)
def test_maintenance_denies_wrong_actual_control_identity_before_mutating_target(
    safety: ModuleType,
    maintenance_target: MaintenanceTarget,
    monkeypatch: pytest.MonkeyPatch,
    wrong_control_facts: tuple[object, object, object],
) -> None:
    """AC-5/6: a control socket's actual DB and cluster are guards, not config claims."""
    events: list[str] = []
    real_connect = psycopg.connect

    def connect_with_wrong_control_facts(
        *args: Any, **kwargs: Any
    ) -> psycopg.Connection[Any] | _ControlConnection:
        delegate = real_connect(*args, **kwargs)
        if kwargs.get("dbname") != "postgres":
            return delegate
        with delegate.cursor() as cursor:
            cursor.execute(
                "SELECT current_database(), (pg_control_system()).system_identifier, "
                "rolsuper FROM pg_roles WHERE rolname = current_user"
            )
            row = cursor.fetchone()
        assert row is not None
        database = row[0] if wrong_control_facts[0] is None else wrong_control_facts[0]
        cluster = row[1] if wrong_control_facts[1] is None else wrong_control_facts[1]
        return _ControlConnection(
            delegate, events, (database, cluster, wrong_control_facts[2])
        )

    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    monkeypatch.setattr(safety.psycopg, "connect", connect_with_wrong_control_facts)

    with (
        pytest.raises(safety.ResetSafetyError),
        safety.DatabaseMaintenance(maintenance_target.configuration),
    ):
        raise AssertionError("unsafe control connection entered maintenance")

    assert target_allows_connections(maintenance_target.control_url) is True
    assert not any(
        "ALTER DATABASE" in query or "pg_terminate_backend" in query for query in events
    )


@pytest.mark.django_db(transaction=True)
def test_maintenance_commits_the_connection_gate_before_draining_writers(
    safety: ModuleType,
    maintenance_target: MaintenanceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5/6: control commits a visible gate before any writer termination request."""
    events: list[str] = []
    real_connect = psycopg.connect

    def observe_committed_gate() -> None:
        with real_connect(maintenance_target.control_url, autocommit=True) as control:
            row = control.execute(
                "SELECT datallowconn FROM pg_database WHERE datname = %s",
                (DEDICATED_DATABASE,),
            ).fetchone()
        assert row is not None
        assert bool(row[0]) is False

    def connect_observing_drain(
        *args: Any, **kwargs: Any
    ) -> psycopg.Connection[Any] | _ControlConnection:
        delegate = real_connect(*args, **kwargs)
        if kwargs.get("dbname") != "postgres":
            return delegate
        return _ControlConnection(
            delegate, events, before_terminate=observe_committed_gate
        )

    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    monkeypatch.setattr(safety.psycopg, "connect", connect_observing_drain)

    writer = real_connect(maintenance_target.target_url)
    try:
        with safety.DatabaseMaintenance(
            maintenance_target.configuration
        ) as maintenance:
            maintenance.quiesce()

        with pytest.raises(psycopg.OperationalError):
            writer.execute("SELECT 1")
    finally:
        writer.close()

    assert any("pg_terminate_backend" in query for query in events)


def _observe_control(events: list[str]) -> Callable[..., Any]:
    real_connect = psycopg.connect

    def connect(
        *args: Any, **kwargs: Any
    ) -> psycopg.Connection[Any] | _ControlConnection:
        delegate = real_connect(*args, **kwargs)
        if kwargs.get("dbname") != "postgres":
            return delegate
        return _ControlConnection(delegate, events)

    return connect


@pytest.mark.django_db(transaction=True)
def test_render_maintenance_gates_drains_and_reopens_as_the_non_superuser_owner(
    safety: ModuleType,
    render_owner_target: MaintenanceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#410 AC4: Render Postgres has no superuser, so the exact owner runs the gate."""
    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    configuration = render_owner_target.configuration
    writer = psycopg.connect(render_owner_target.target_url)
    try:
        with safety.DatabaseMaintenance(configuration) as maintenance:
            maintenance.quiesce()

            assert target_allows_connections(render_owner_target.control_url) is False
            safety.assert_quiescent(configuration)
            maintenance.resume()

        with pytest.raises(psycopg.OperationalError):
            writer.execute("SELECT 1")
    finally:
        writer.close()

    assert target_allows_connections(render_owner_target.control_url) is True


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("platform", "owner", "executor"),
    (
        pytest.param("render", None, None, id="render-superuser-executor"),
        pytest.param("render", None, RENDER_OWNER, id="render-executor-not-owner"),
        pytest.param(
            "railway", RENDER_OWNER, RENDER_OWNER, id="railway-needs-superuser"
        ),
    ),
)
def test_maintenance_refuses_an_executor_its_platform_does_not_permit(
    safety: ModuleType,
    local_roles: None,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    owner: str | None,
    executor: str | None,
) -> None:
    """#410 AC4: Render needs the owner without superuser; Railway still needs superuser."""
    events: list[str] = []
    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    monkeypatch.setattr(safety.psycopg, "connect", _observe_control(events))

    with _dedicated_target(
        safety, owner=owner, executor=executor, platform=platform
    ) as target:
        with pytest.raises(safety.ResetSafetyError):
            safety.validate_database(target.configuration)
        with (
            pytest.raises(safety.ResetSafetyError),
            safety.DatabaseMaintenance(target.configuration),
        ):
            raise AssertionError("an unpermitted executor entered maintenance")

        assert target_allows_connections(target.control_url) is True
    assert not any(
        "ALTER DATABASE" in query or "pg_terminate_backend" in query for query in events
    )


@pytest.mark.django_db(transaction=True)
def test_render_maintenance_fails_closed_on_another_roles_session(
    safety: ModuleType,
    render_owner_target: MaintenanceTarget,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#410 AC3/AC4: the owner cannot end another role's client, so the gate stays."""
    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    stranger = psycopg.connect(_role_url(render_owner_target.target_url, OTHER_ROLE))
    try:
        with (
            pytest.raises(safety.ResetSafetyError),
            safety.DatabaseMaintenance(
                render_owner_target.configuration
            ) as maintenance,
        ):
            maintenance.quiesce()

        assert target_allows_connections(render_owner_target.control_url) is False
        assert stranger.execute("SELECT 1").fetchone() == (1,)
    finally:
        stranger.close()
