"""Replica reset safety (#355 U2b, B1 and B3-B7).

Two levels. The SQL rules (maintainer privilege, replica quiescence) run on the real
local PostgreSQL with real roles and sessions. The `replica_reset` command runs end
to end with only two substitutions: the public identity endpoint is faked at the
urllib network seam, and the destructive domain steps (`DatabaseMaintenance`,
`reset_baseline`, `provision_identity`) are faked as attributes of their home modules,
`rehearsal.safety` and `rehearsal.reset`. The command must reach them by attribute
lookup at call time, as the Railway script's lazy wrappers do. The command cannot use
a real database here because the runner pins the database host to a synthetic value.
"""

from __future__ import annotations

import importlib
import json
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Generator, Mapping
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Final, Self, cast

import psycopg
import pytest
from django.db import connection, connections
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from pytest import CaptureFixture, MonkeyPatch

from tests import replica_contract, test_replica_operations
from tests import replica_job_support as support
from tests.test_replica_operations import Invoke, passing
from tests.test_staging_reset_maintenance import control_url, validated_identity

pytestmark = pytest.mark.django_db

# Reuse the U2a command fixture (faked metadata, one-line output rules) unchanged.
invoke = test_replica_operations.invoke

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
RESET_JOB: Final = "tailtag-replica-reset"
RESET_CONFIRM: Final = "reset-tailtag-replica"
PROVISION_CONFIRM: Final = "provision-tailtag-replica-reset"
SENSITIVE: Final = "untrusted-replica-diagnostic-secret"
DATABASE: Final = "tailtag_355_replica_reset_test"
ROLE_PASSWORD: Final = "replica-reset-test-password"
ROLES: Final = ("maintainer", "other_owner", "foreign_client", "cloud_admin")
COUNTS: Final = {"profiles": 2, "fursuits": 2, "catches": 0}
IDENTITY: Final = {
    "source_sha": support.SOURCE_SHA,
    "deployment_id": "tailtag-api-replica-00007-abc",
    "environment": "replica",
}
RAILWAY_IDENTITY: Final = {
    "source_sha": support.SOURCE_SHA,
    "deployment_id": support.RAILWAY_DEPLOYMENT_ID,
    "environment": "staging",
}
CONFIGURATION: Final = {
    "TAILTAG_STAGING_RESET_ENABLED": "true",
    "TAILTAG_STAGING_RESET_ID": "11111111-2222-4333-8444-555555555555",
    "TAILTAG_STAGING_DATABASE_SYSTEM_ID": "7654321098765432109",
    "TAILTAG_STAGING_DATABASE_HOST": "db.replica-private.example.test",
    "TAILTAG_STAGING_DATABASE_PORT": "5432",
    "TAILTAG_STAGING_DATABASE_NAME": "tailtag_private_marker",
    "TAILTAG_STAGING_RESET_OWNER_CLERK_ID": "user_private_owner_marker",
    "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID": "user_private_catcher_marker",
    "TAILTAG_STAGING_RESET_MEDIA_KEY": "images/0123456789abcdef0123456789abcdef.png",
}
PRIVATE_VALUES: Final = tuple(
    value for value in CONFIGURATION.values() if value not in {"true", "5432"}
)
EXPECTED_ORDER: Final = [
    "preflight",
    "maintenance-enter",
    "quiesce",
    "reset",
    "resume",
    "preflight",
    "maintenance-exit",
]


# ---------------------------------------------------------------------------
# Real PostgreSQL: B3 privilege rule and B4 quiescence rule
# ---------------------------------------------------------------------------


@pytest.fixture
def safety() -> ModuleType:
    return importlib.import_module("rehearsal.safety")


@pytest.fixture
def replica_roles() -> Generator[None]:
    """Create the cluster roles Neon provides, and remove only those afterwards."""
    with psycopg.connect(control_url(), autocommit=True) as database:
        existing = database.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(ROLES),)
        ).fetchall()
        assert existing == [], "refusing to touch pre-existing cluster roles"
        for role in ROLES:
            database.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(ROLE_PASSWORD)
                )
            )
        database.execute("GRANT pg_signal_backend TO maintainer")
    try:
        yield
    finally:
        with psycopg.connect(control_url(), autocommit=True) as database:
            for role in ROLES:
                database.execute(
                    sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role))
                )


@dataclass
class Opened:
    """One disposable database whose Django connection runs as one chosen role."""

    values: dict[str, str]
    host: str
    port: str
    sessions: ExitStack = field(default_factory=ExitStack)

    def session_as(self, role: str) -> psycopg.Connection[Any]:
        """Open a live foreign client session on the target database."""
        client = psycopg.connect(
            host=self.host,
            port=self.port,
            user=role,
            password=ROLE_PASSWORD,
            dbname=DATABASE,
            autocommit=True,
        )
        self.sessions.callback(client.close)
        return client


OpenTarget = Callable[[str, str], Opened]


@pytest.fixture
def open_target(replica_roles: None) -> Generator[OpenTarget]:
    """Create the database owned by `owner` and run Django as `executor`."""
    database_settings = connections.databases["default"]
    original = deepcopy(database_settings)
    opened: list[Opened] = []

    def drop() -> None:
        with psycopg.connect(control_url(), autocommit=True) as database:
            database.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(DATABASE)
                )
            )

    def create(owner: str, executor: str) -> Opened:
        connections.close_all()
        drop()
        with psycopg.connect(control_url(), autocommit=True) as database:
            database.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(DATABASE), sql.Identifier(owner)
                )
            )
        database_settings["NAME"] = DATABASE
        if executor != original["USER"]:
            database_settings["USER"] = executor
            database_settings["PASSWORD"] = ROLE_PASSWORD
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT (pg_control_system()).system_identifier")
            cluster = str(cursor.fetchone()[0])
        values = {
            **CONFIGURATION,
            "TAILTAG_STAGING_DATABASE_SYSTEM_ID": cluster,
            "TAILTAG_STAGING_DATABASE_HOST": str(database_settings["HOST"]),
            "TAILTAG_STAGING_DATABASE_PORT": str(database_settings["PORT"]),
            "TAILTAG_STAGING_DATABASE_NAME": DATABASE,
        }
        target = Opened(
            values, str(database_settings["HOST"]), str(database_settings["PORT"])
        )
        opened.append(target)
        return target

    try:
        yield create
    finally:
        for target in opened:
            target.sessions.close()
        connections.close_all()
        drop()
        database_settings.clear()
        database_settings.update(original)
        connection.ensure_connection()


def configuration_for(safety: ModuleType, platform: str, values: dict[str, str]) -> Any:
    if platform == "replica":
        return safety.load_replica_configuration(values)
    return safety.ResetConfiguration(
        environment_id=uuid.UUID(values["TAILTAG_STAGING_RESET_ID"]),
        cluster_identifier=values["TAILTAG_STAGING_DATABASE_SYSTEM_ID"],
        database_host=values["TAILTAG_STAGING_DATABASE_HOST"],
        database_port=values["TAILTAG_STAGING_DATABASE_PORT"],
        database_name=values["TAILTAG_STAGING_DATABASE_NAME"],
        owner_clerk_id=values["TAILTAG_STAGING_RESET_OWNER_CLERK_ID"],
        catcher_clerk_id=values["TAILTAG_STAGING_RESET_CATCHER_CLERK_ID"],
        media_key=values["TAILTAG_STAGING_RESET_MEDIA_KEY"],
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("platform", "owner", "executor", "superuser", "admitted"),
    (
        pytest.param(
            "replica", "maintainer", "maintainer", False, True, id="maintainer-owner"
        ),
        pytest.param(
            "replica", "tailtag", "maintainer", False, False, id="not-the-owner"
        ),
        pytest.param(
            "replica",
            "maintainer",
            "maintainer",
            True,
            False,
            id="superuser-maintainer",
        ),
        pytest.param(
            "replica", "other_owner", "other_owner", False, False, id="other-role"
        ),
        pytest.param(
            "railway",
            "maintainer",
            "maintainer",
            False,
            False,
            id="railway-needs-super",
        ),
    ),
)
def test_database_privilege_rule_is_per_platform(
    safety: ModuleType,
    open_target: OpenTarget,
    platform: str,
    owner: str,
    executor: str,
    superuser: bool,
    admitted: bool,
) -> None:
    """B3/failure modes 1-2: only the non-superuser maintainer that owns the database
    is a replica executor, and the Railway rule still demands `rolsuper`."""
    if superuser:
        with psycopg.connect(control_url(), autocommit=True) as database:
            database.execute("ALTER ROLE maintainer SUPERUSER")
    target = open_target(owner, executor)
    configuration = configuration_for(safety, platform, target.values)

    if admitted:
        safety.validate_database(configuration)
    else:
        with pytest.raises(safety.ResetSafetyError):
            safety.validate_database(configuration)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("platform", ("replica", "railway"))
def test_control_connection_keeps_verify_full_tls_only_on_the_replica(
    safety: ModuleType, monkeypatch: MonkeyPatch, platform: str
) -> None:
    """AC13: the raw maintenance connection reuses the replica's verify-full options.

    Railway connections stay exactly as they were.
    """
    from django.conf import settings

    tls = {
        "sslmode": "verify-full",
        "sslrootcert": "/etc/ssl/certs/ca.pem",
        "channel_binding": "require",
    }
    monkeypatch.setitem(
        settings.DATABASES["default"], "OPTIONS", {"connect_timeout": 5, **tls}
    )
    monkeypatch.setattr(safety, "validate_database", lambda _: None)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    monkeypatch.setattr(safety, "validate_identity", lambda _: None)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    seen: list[dict[str, object]] = []

    def refuse(conninfo: str = "", **arguments: object) -> None:
        seen.append({**conninfo_to_dict(conninfo), **arguments})
        raise psycopg.OperationalError

    monkeypatch.setattr(safety.psycopg, "connect", refuse)
    configuration = configuration_for(safety, platform, CONFIGURATION)

    with pytest.raises(safety.ResetSafetyError):
        safety.DatabaseMaintenance(configuration).__enter__()

    assert len(seen) == 1
    passed = {name: seen[0].get(name) for name in tls}
    assert passed == (tls if platform == "replica" else dict.fromkeys(tls))


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("platform", "owner", "executor", "session_role", "quiescent"),
    (
        pytest.param(
            "replica", "maintainer", "maintainer", "foreign_client", False, id="foreign"
        ),
        pytest.param(
            "replica", "maintainer", "maintainer", "cloud_admin", True, id="cloud-admin"
        ),
        pytest.param(
            "railway",
            "tailtag",
            "tailtag",
            "cloud_admin",
            False,
            id="railway-counts-all",
        ),
    ),
)
def test_assert_quiescent_counts_foreign_client_sessions_except_cloud_admin(
    safety: ModuleType,
    open_target: OpenTarget,
    platform: str,
    owner: str,
    executor: str,
    session_role: str,
    quiescent: bool,
) -> None:
    """B4/failure mode 3: a live session of any other role blocks the replica proof,
    the `cloud_admin` platform session does not, and Railway still counts everyone."""
    target = open_target(owner, executor)
    target.session_as(session_role)
    with psycopg.connect(control_url(), autocommit=True) as database:
        database.execute(
            sql.SQL("ALTER DATABASE {} WITH ALLOW_CONNECTIONS false").format(
                sql.Identifier(DATABASE)
            )
        )
    configuration = configuration_for(safety, platform, target.values)

    if quiescent:
        safety.assert_quiescent(configuration)
    else:
        with pytest.raises(safety.ResetSafetyError):
            safety.assert_quiescent(configuration)


@pytest.mark.django_db(transaction=True)
def test_replica_maintenance_terminates_foreign_clients_and_spares_cloud_admin(
    safety: ModuleType, open_target: OpenTarget, monkeypatch: MonkeyPatch
) -> None:
    """B3/B4: the whole replica maintenance cycle runs as the non-superuser maintainer,
    drains foreign clients, leaves the `cloud_admin` session alive and reopens."""
    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    target = open_target("maintainer", "maintainer")
    foreign = target.session_as("foreign_client")
    platform_session = target.session_as("cloud_admin")
    configuration = configuration_for(safety, "replica", target.values)

    with safety.DatabaseMaintenance(configuration) as maintenance:
        maintenance.quiesce()

        with pytest.raises(psycopg.OperationalError):
            foreign.execute("SELECT 1")
        assert platform_session.execute("SELECT 1").fetchone() == (1,)
        maintenance.resume()

    with psycopg.connect(control_url(), autocommit=True) as database:
        row = database.execute(
            "SELECT datallowconn FROM pg_database WHERE datname = %s", (DATABASE,)
        ).fetchone()
    assert row == (True,)


@pytest.mark.django_db(transaction=True)
def test_replica_maintenance_keeps_its_executor_when_the_client_pid_is_wrong(
    safety: ModuleType, open_target: OpenTarget, monkeypatch: MonkeyPatch
) -> None:
    """Live finding: behind Neon's proxy the client-reported backend pid is not the
    server pid, so the executor must be excluded by the pid the server reports."""
    monkeypatch.setattr(safety, "validate_identity", validated_identity)
    target = open_target("maintainer", "maintainer")
    foreign = target.session_as("foreign_client")
    configuration = configuration_for(safety, "replica", target.values)
    # No session has pid 0, so excluding it would end the executor and every client.
    monkeypatch.setattr(
        psycopg.ConnectionInfo, "backend_pid", property(lambda _self: 0)
    )

    with safety.DatabaseMaintenance(configuration) as maintenance:
        maintenance.quiesce()

        with pytest.raises(psycopg.OperationalError):
            foreign.execute("SELECT 1")
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)


# ---------------------------------------------------------------------------
# Command level: B1, B5, B6, B7
# ---------------------------------------------------------------------------


class Response:
    def __init__(self, url: str, body: bytes) -> None:
        self._url = url
        self._body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def getcode(self) -> int:
        return 200

    def geturl(self) -> str:
        return self._url

    def read(self, limit: int = -1) -> bytes:
        return self._body if limit < 0 else self._body[:limit]


class Seams:
    """Scripted public endpoint and recorded domain steps shared by every command test."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.urls: list[str] = []
        self.bodies: list[object] = [IDENTITY, IDENTITY]
        self.quiesce_error = False
        self.reset_error = False
        self.provision_error = False


@pytest.fixture
def seams(monkeypatch: MonkeyPatch, settings: Any) -> Seams:
    settings.ALLOWED_HOSTS = [replica_contract.RUN_APP_HOST]
    state = Seams()

    def fake_open(_: object, request: urllib.request.Request, **__: object) -> Response:
        state.urls.append(request.full_url)
        state.events.append("preflight")
        if not state.bodies:
            raise urllib.error.URLError("no scripted response")
        body = state.bodies.pop(0)
        return Response(
            request.full_url,
            body if isinstance(body, bytes) else json.dumps(body).encode(),
        )

    class Maintenance:
        def __init__(self, _configuration: object) -> None:
            return None

        def __enter__(self) -> Self:
            state.events.append("maintenance-enter")
            return self

        def quiesce(self) -> None:
            state.events.append("quiesce")
            if state.quiesce_error and state.events.count("quiesce") == 1:
                raise RuntimeError(SENSITIVE)

        def resume(self) -> None:
            state.events.append("resume")

        def __exit__(self, *_: object) -> None:
            state.events.append("maintenance-exit")

    def reset_baseline(_: object) -> dict[str, int]:
        state.events.append("reset")
        if state.reset_error:
            raise RuntimeError(SENSITIVE)
        return COUNTS

    def provision_identity(_: object) -> None:
        state.events.append("provision")
        if state.provision_error:
            raise RuntimeError(SENSITIVE)

    from rehearsal import reset, safety

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", fake_open)
    monkeypatch.setattr(safety, "DatabaseMaintenance", Maintenance)
    monkeypatch.setattr(reset, "reset_baseline", reset_baseline)
    monkeypatch.setattr(reset, "provision_identity", provision_identity)
    return state


def request_for(
    operation: str,
    confirm: object = None,
    configuration: Mapping[str, object] | None = None,
) -> dict[str, object]:
    request: dict[str, object] = {
        "operation": operation,
        "configuration": dict(
            CONFIGURATION if configuration is None else configuration
        ),
    }
    if confirm is not None:
        request["confirm"] = confirm
    return request


def run_replica(invoke: Invoke, request: Mapping[str, object]) -> dict[str, Any]:
    output = invoke("replica_reset", request, job=RESET_JOB, uses_media=True)
    text = json.dumps(output)
    assert SENSITIVE not in text
    assert not any(value in text for value in PRIVATE_VALUES)
    return output


@pytest.mark.parametrize(
    ("operation", "confirm"),
    (
        pytest.param("reset", PROVISION_CONFIRM, id="reset-with-provision-confirm"),
        pytest.param("provision", RESET_CONFIRM, id="provision-with-reset-confirm"),
        pytest.param("reset", None, id="missing"),
    ),
)
def test_wrong_confirmation_is_refused_before_network_or_database(
    invoke: Invoke,
    seams: Seams,
    django_assert_num_queries: Any,
    operation: str,
    confirm: str | None,
) -> None:
    """B1/failure mode 4: each operation has its own confirm string, checked first."""
    with django_assert_num_queries(0):
        output = run_replica(invoke, request_for(operation, confirm))

    assert output["result"] == "FAIL_CONFIRMATION"
    assert output["data"] == {}
    assert seams.events == []


def test_reset_runs_the_guarded_procedure_and_reports_the_baseline(
    invoke: Invoke, seams: Seams
) -> None:
    """B5/B6/B7: preflight, one maintenance cycle, preflight again, fixed PASS data
    from the public identity URL built from the pinned ALLOWED_HOSTS entry."""
    output = run_replica(invoke, request_for("reset", RESET_CONFIRM))

    assert output == passing(RESET_JOB, {"baseline_version": 1, "counts": COUNTS})
    assert seams.events == EXPECTED_ORDER
    assert (
        seams.urls == [f"https://{replica_contract.RUN_APP_HOST}/health/identity"] * 2
    )


def test_provision_runs_without_maintenance_and_reports_provisioned(
    invoke: Invoke, seams: Seams
) -> None:
    """B7: provision reaches only the provision step, with the Railway ordering."""
    output = run_replica(invoke, request_for("provision", PROVISION_CONFIRM))

    assert output == passing(RESET_JOB, {"provisioned": 1})
    assert seams.events == ["preflight", "provision"]


@pytest.mark.parametrize(
    "body",
    (
        pytest.param(RAILWAY_IDENTITY, id="railway-identity"),
        pytest.param({**IDENTITY, "source_sha": "a" * 40}, id="other-source-sha"),
        pytest.param(
            {**IDENTITY, "deployment_id": "tailtag-api-replicx-00007-abc"},
            id="wrong-deployment-prefix",
        ),
        pytest.param({**IDENTITY, "extra": "field"}, id="extra-field"),
    ),
)
def test_preflight_refuses_anything_but_the_replica_identity_of_this_build(
    invoke: Invoke, seams: Seams, body: object
) -> None:
    """B6/failure mode 5: a non-replica, other-build or malformed identity stops the
    job before configuration or maintenance."""
    seams.bodies = [body]

    output = run_replica(invoke, request_for("reset", RESET_CONFIRM))

    assert output["result"] == "FAIL_PREFLIGHT"
    assert seams.events == ["preflight"]


def test_preflight_refuses_an_unpinned_public_host_without_any_request(
    invoke: Invoke, seams: Seams, settings: Any
) -> None:
    """B6: ALLOWED_HOSTS[0] must pass the run.app pin before it is ever contacted."""
    settings.ALLOWED_HOSTS = [replica_contract.OTHER_RUN_APP_HOST]

    output = run_replica(invoke, request_for("reset", RESET_CONFIRM))

    assert output["result"] == "FAIL_PREFLIGHT"
    assert seams.events == []


def test_invalid_configuration_never_reaches_a_domain_step(
    invoke: Invoke, seams: Seams
) -> None:
    """B1/B7: a configuration with an extra key is FAIL_CONFIGURATION, no mutation."""
    configuration = {**CONFIGURATION, "RAILWAY_SERVICE_ID": SENSITIVE}

    output = run_replica(invoke, request_for("reset", RESET_CONFIRM, configuration))

    assert output["result"] == "FAIL_CONFIGURATION"
    assert seams.events == ["preflight"]


def test_provision_failure_maps_to_its_fixed_result(
    invoke: Invoke, seams: Seams
) -> None:
    """B7: a failing provision step is FAIL_PROVISION without diagnostics."""
    seams.provision_error = True

    output = run_replica(invoke, request_for("provision", PROVISION_CONFIRM))

    assert output["result"] == "FAIL_PROVISION"
    assert output["data"] == {}


# B5: the Railway script and the replica command must be one state machine.

RAILWAY_PHASE_RESULT: Final = {
    "maintenance unknown": "FAIL_MAINTENANCE_UNKNOWN",
    "maintenance retained": "FAIL_MAINTENANCE_RETAINED",
    "committed maintenance retained": "FAIL_COMMITTED_MAINTENANCE_RETAINED",
}


@pytest.mark.parametrize(
    ("scenario", "phase"),
    (
        pytest.param("quiesce", "maintenance unknown", id="quiesce-fails"),
        pytest.param("reset", "maintenance retained", id="reset-fails"),
        pytest.param(
            "identity", "committed maintenance retained", id="final-identity-changed"
        ),
    ),
)
def test_replica_and_railway_run_the_same_state_machine(
    invoke: Invoke,
    seams: Seams,
    monkeypatch: MonkeyPatch,
    capfd: CaptureFixture[str],
    scenario: str,
    phase: str,
) -> None:
    """B5/failure mode 6: for the same faults, both entry points perform the same
    ordered steps (including the re-gate after a changed final identity) and report
    the same phase, so the sequence cannot have been copied and drifted."""
    if scenario == "quiesce":
        seams.quiesce_error = True
    if scenario == "reset":
        seams.reset_error = True
    if scenario == "identity":
        seams.bodies = [
            IDENTITY,
            {**IDENTITY, "deployment_id": "tailtag-api-replica-2"},
        ]

    replica = run_replica(invoke, request_for("reset", RESET_CONFIRM))
    replica_events = seams.events[:]
    assert replica["result"] == RAILWAY_PHASE_RESULT[phase]

    # Same faults through the Railway script, using its module-level seams.
    seams.events.clear()
    seams.bodies = []
    railway_events = seams.events
    if str(REPOSITORY_ROOT) not in sys.path:
        sys.path.insert(0, str(REPOSITORY_ROOT))
    script = cast(Any, importlib.import_module("scripts.api_staging_reset"))
    from rehearsal import reset, safety

    calls = 0

    def configuration_object(_: object) -> object:
        return object()

    def validate_target(_: str) -> dict[str, str]:
        nonlocal calls
        calls += 1
        railway_events.append("preflight")
        if scenario == "identity" and calls == 2:
            return {**RAILWAY_IDENTITY, "deployment_id": "other"}
        return RAILWAY_IDENTITY

    monkeypatch.setattr(
        sys, "argv", ["api_staging_reset.py", "--confirm", "reset-tailtag-staging"]
    )
    monkeypatch.setattr(script, "validate_target", validate_target)
    monkeypatch.setattr(script, "load_configuration", configuration_object)
    monkeypatch.setattr(script, "_bootstrap", lambda: None)
    monkeypatch.setattr(script, "DatabaseMaintenance", safety.DatabaseMaintenance)
    monkeypatch.setattr(script, "reset_baseline", reset.reset_baseline)
    capfd.readouterr()

    assert script.main() == 1
    assert capfd.readouterr().err == f"FAIL staging reset {phase}\n"
    assert railway_events == replica_events
