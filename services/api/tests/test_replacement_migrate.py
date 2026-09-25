"""Acceptance tests for the replacement API's guarded first migration.

Provider identities are synthetic. The only schema writes made by this file are
to a disposable local PostgreSQL database created and dropped by a fixture.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from tests.test_production_settings import VALID_ENVIRONMENT

PROJECT = "a1111111-1111-4111-8111-111111111111"
DEVELOPMENT = "22222222-2222-4222-8222-222222222222"
STAGING = "33333333-3333-4333-8333-333333333333"
API = "d4444444-4444-4444-8444-444444444444"
POSTGRES = "55555555-5555-4555-8555-555555555555"
OTHER = "66666666-6666-4666-8666-666666666666"
DEPLOYMENT = "77777777-7777-4777-8777-777777777777"
SOURCE_SHA = "a" * 40
PRIVATE_SENTINEL = "private-migration-sentinel-must-not-escape"
API_ROOT = Path(__file__).resolve().parents[1]


def _tuple_digest(role: str, environment: str, service: str) -> str:
    return hashlib.sha256(
        _frame("tailtag-rebuild-v1", role, PROJECT, environment, service)
    ).hexdigest()


def _frame(*fields: str) -> bytes:
    """Use the frozen NUL framing instead of an ambiguous text concatenation."""
    return "\0".join(fields).encode()


def _target_pins() -> dict[str, str]:
    return {
        "development-api": _tuple_digest("development-api", DEVELOPMENT, API),
        "development-postgres": _tuple_digest(
            "development-postgres", DEVELOPMENT, POSTGRES
        ),
        "staging-api": _tuple_digest("staging-api", STAGING, API),
        "staging-postgres": _tuple_digest("staging-postgres", STAGING, POSTGRES),
    }


def _database_digest(
    environment: str, name: str, cluster: str, service: str = POSTGRES
) -> str:
    environment_id = DEVELOPMENT if environment == "development" else STAGING
    return hashlib.sha256(
        _frame(
            "tailtag-postgres-first-boot-v1",
            environment,
            PROJECT,
            environment_id,
            service,
            name,
            cluster,
        )
    ).hexdigest()


def _runtime(environment: str = "development") -> dict[str, str]:
    return {
        "RAILWAY_PROJECT_ID": PROJECT,
        "RAILWAY_ENVIRONMENT_ID": (
            DEVELOPMENT if environment == "development" else STAGING
        ),
        "RAILWAY_ENVIRONMENT_NAME": environment,
        "RAILWAY_SERVICE_ID": API,
        "RAILWAY_SERVICE_NAME": "api",
        "RAILWAY_DEPLOYMENT_ID": DEPLOYMENT,
        "TAILTAG_REPLACEMENT_POSTGRES_SERVICE_ID": POSTGRES,
        "TAILTAG_STAGING_TARGET_PHASE": "candidate",
        # Runtime source/expectation fields must not replace the baked artifact
        # or the code-owned database digest.
        "RAILWAY_GIT_COMMIT_SHA": "b" * 40,
        "TAILTAG_EXPECTED_DATABASE_DIGEST": PRIVATE_SENTINEL,
    }


def _environment(
    database_url: str, overrides: Mapping[str, str] | None = None
) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(API_ROOT),
        "DJANGO_SETTINGS_MODULE": "config.settings.production",
        **VALID_ENVIRONMENT,
        "DATABASE_URL": database_url,
        "DJANGO_SECRET_KEY": PRIVATE_SENTINEL,
        **_runtime(),
        **(overrides or {}),
    }


def _run_wrapper(
    tmp_path: Path,
    *,
    environment: Mapping[str, str],
    database_digests: Mapping[str, str] | None = None,
    source_sha: object = SOURCE_SHA,
    before_import: str = "",
    before_main: str = "",
    observe_setup: bool = False,
    observe_migration: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Invoke the production main in a fresh process with synthetic code pins."""
    metadata = tmp_path / "build-identity.json"
    if source_sha is not None:
        metadata.write_text(json.dumps({"source_sha": source_sha}))
    setup_marker = tmp_path / "django-setup-called"
    migration_marker = tmp_path / "migration-called"
    setup_spy = (
        "import django\n"
        "_real_setup = django.setup\n"
        "def _observed_setup(*args, **kwargs):\n"
        f"    Path({str(setup_marker)!r}).write_text('called')\n"
        "    return _real_setup(*args, **kwargs)\n"
        "django.setup = _observed_setup\n"
        if observe_setup
        else ""
    )
    migration_spy = (
        "import django.core.management as management\n"
        "_real_call_command = management.call_command\n"
        "def _observed_call_command(*args, **kwargs):\n"
        f"    _marker = Path({str(migration_marker)!r})\n"
        "    _marker.write_text(_marker.read_text() + 'x' if _marker.exists() else 'x')\n"
        "    return _real_call_command(*args, **kwargs)\n"
        "management.call_command = _observed_call_command\n"
        if observe_migration
        else ""
    )
    program = (
        "from pathlib import Path\n"
        f"{before_import}\n"
        f"{setup_spy}"
        f"{migration_spy}"
        "import config.replacement_target_binding as binding\n"
        f"binding._EXPECTED_DIGESTS = {_target_pins()!r}\n"
        "import config.replacement_migrate as wrapper\n"
        f"wrapper._BUILD_METADATA_PATH = Path({str(metadata)!r})\n"
        f"wrapper._EXPECTED_BINDING_DIGESTS = {dict(database_digests or {})!r}\n"
        f"{before_main}\n"
        "raise SystemExit(wrapper.main())\n"
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=API_ROOT,
            env=dict(environment),
            capture_output=True,
            text=True,
            check=False,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("replacement migration test subprocess timed out", pytrace=False)
    return completed, setup_marker, migration_marker


def _assert_classification(
    completed: subprocess.CompletedProcess[str], classification: str
) -> None:
    # Fixed test failures must not echo captured process output or exception
    # values, including when the wrapper itself regresses and leaks a secret.
    status_is_correct = (
        completed.returncode == 0
        if classification == "PASS"
        else completed.returncode != 0
    )
    output_is_exact = (completed.stdout + completed.stderr) == f"{classification}\n"
    if not status_is_correct or not output_is_exact:
        pytest.fail("replacement migration classification mismatch", pytrace=False)
    for value in (
        PRIVATE_SENTINEL,
        PROJECT,
        DEVELOPMENT,
        STAGING,
        API,
        POSTGRES,
        DEPLOYMENT,
    ):
        if value in completed.stdout or value in completed.stderr:
            pytest.fail("replacement migration output not sanitized", pytrace=False)


def test_classification_assertion_does_not_echo_leaked_process_output() -> None:
    """M-5: even a failing acceptance assertion retains only fixed text."""
    leaked = subprocess.CompletedProcess(
        args=["synthetic"], returncode=1, stdout=PRIVATE_SENTINEL, stderr=""
    )
    with pytest.raises(pytest.fail.Exception) as caught:
        _assert_classification(leaked, "FAIL_GUARD")
    if str(caught.value) != "replacement migration classification mismatch":
        pytest.fail("classification assertion leaked diagnostic details", pytrace=False)


@pytest.mark.parametrize(
    ("changed", "source_sha"),
    (
        ({"RAILWAY_PROJECT_ID": OTHER}, SOURCE_SHA),
        ({"RAILWAY_ENVIRONMENT_ID": STAGING}, SOURCE_SHA),
        ({"RAILWAY_SERVICE_ID": POSTGRES}, SOURCE_SHA),
        ({"RAILWAY_SERVICE_NAME": "Postgres"}, SOURCE_SHA),
        ({"RAILWAY_ENVIRONMENT_NAME": "production"}, SOURCE_SHA),
        ({"TAILTAG_REPLACEMENT_POSTGRES_SERVICE_ID": API}, SOURCE_SHA),
        ({"TAILTAG_REPLACEMENT_POSTGRES_SERVICE_ID": "not-a-uuid"}, SOURCE_SHA),
        ({"RAILWAY_DEPLOYMENT_ID": "not-a-uuid"}, SOURCE_SHA),
        ({"RAILWAY_DEPLOYMENT_ID": ""}, SOURCE_SHA),
        ({"DJANGO_SETTINGS_MODULE": "config.settings.local"}, SOURCE_SHA),
        ({}, None),
        ({}, "malformed-source-sha"),
    ),
)
def test_invalid_runtime_identity_stops_before_setup_or_migration(
    tmp_path: Path, changed: Mapping[str, str], source_sha: object
) -> None:
    """M-1: no old, swapped, absent or malformed identity reaches Django."""
    completed, setup_marker, migration_marker = _run_wrapper(
        tmp_path,
        environment=_environment(
            "postgresql://local:local@127.0.0.1:1/does_not_exist", changed
        ),
        source_sha=source_sha,
        observe_setup=True,
        observe_migration=True,
    )

    _assert_classification(completed, "FAIL_GUARD")
    assert not setup_marker.exists()
    assert not migration_marker.exists()


@pytest.mark.parametrize(
    "missing",
    (
        "RAILWAY_PROJECT_ID",
        "RAILWAY_ENVIRONMENT_ID",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_SERVICE_ID",
        "RAILWAY_SERVICE_NAME",
        "RAILWAY_DEPLOYMENT_ID",
        "TAILTAG_REPLACEMENT_POSTGRES_SERVICE_ID",
        "DJANGO_SETTINGS_MODULE",
    ),
)
def test_missing_runtime_fields_stop_before_django_setup(
    tmp_path: Path, missing: str
) -> None:
    """M-1: every part of the replacement target and runtime identity is required."""
    environment = _environment("postgresql://local:local@127.0.0.1:1/does_not_exist")
    environment.pop(missing)
    completed, setup_marker, migration_marker = _run_wrapper(
        tmp_path,
        environment=environment,
        observe_setup=True,
        observe_migration=True,
    )
    _assert_classification(completed, "FAIL_GUARD")
    assert not setup_marker.exists()
    assert not migration_marker.exists()


@pytest.mark.parametrize("phase", ("", "ready", "Candidate", PRIVATE_SENTINEL))
def test_staging_requires_a_finite_explicit_phase_before_setup(
    tmp_path: Path, phase: str
) -> None:
    """M-1: Staging phase is an explicit candidate/canonical state."""
    environment = _environment(
        "postgresql://local:local@127.0.0.1:1/does_not_exist",
        {
            **_runtime("staging"),
            "TAILTAG_STAGING_TARGET_PHASE": phase,
        },
    )
    completed, setup_marker, migration_marker = _run_wrapper(
        tmp_path,
        environment=environment,
        observe_setup=True,
        observe_migration=True,
    )

    _assert_classification(completed, "FAIL_GUARD")
    assert not setup_marker.exists()
    assert not migration_marker.exists()


def test_staging_missing_phase_stops_before_setup(tmp_path: Path) -> None:
    """M-1: Staging cannot default to candidate or canonical mode."""
    environment = _environment(
        "postgresql://local:local@127.0.0.1:1/does_not_exist",
        _runtime("staging"),
    )
    environment.pop("TAILTAG_STAGING_TARGET_PHASE")
    completed, setup_marker, migration_marker = _run_wrapper(
        tmp_path,
        environment=environment,
        observe_setup=True,
        observe_migration=True,
    )
    _assert_classification(completed, "FAIL_GUARD")
    assert not setup_marker.exists()
    assert not migration_marker.exists()


@pytest.mark.parametrize("existing_phase", (None, "invalid"))
def test_duplicate_phase_variable_cannot_replace_existing_readiness_setting(
    tmp_path: Path,
    disposable_database: tuple[str, str, str],
    existing_phase: str | None,
) -> None:
    """M-1: a second phase namespace cannot authorize Staging migration."""
    url, name, cluster = disposable_database
    environment = _environment(
        url,
        {
            **_runtime("staging"),
            "TAILTAG_REPLACEMENT_STAGING_PHASE": "candidate",
        },
    )
    if existing_phase is None:
        environment.pop("TAILTAG_STAGING_TARGET_PHASE")
    else:
        environment["TAILTAG_STAGING_TARGET_PHASE"] = existing_phase
    completed, setup_marker, migration_marker = _run_wrapper(
        tmp_path,
        environment=environment,
        database_digests={"staging": _database_digest("staging", name, cluster)},
        before_import=(
            "import django.core.management as management\n"
            "management.call_command = lambda *args, **kwargs: None\n"
        ),
        observe_setup=True,
        observe_migration=True,
    )
    _assert_classification(completed, "FAIL_GUARD")
    assert not setup_marker.exists()
    assert not migration_marker.exists()


def test_executable_entrypoint_rejects_unpinned_target_with_fixed_output() -> None:
    """M-1/M-5: the actual ``python -m`` path has no unguarded fallback."""
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "config.replacement_migrate"],
            cwd=API_ROOT,
            env=_environment(
                "postgresql://local:local@127.0.0.1:1/does_not_exist",
                {"RAILWAY_PROJECT_ID": OTHER},
            ),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("replacement migration entrypoint timed out", pytrace=False)
    _assert_classification(completed, "FAIL_GUARD")


@pytest.fixture
def disposable_database() -> Iterator[tuple[str, str, str]]:
    """Make an isolated local database; never connect to a Railway resource."""
    assert not os.environ.get("RAILWAY_PROJECT_ID")
    base_url = os.environ["DATABASE_URL"]
    parsed = urlsplit(base_url)
    assert parsed.scheme in {"postgres", "postgresql"}
    assert parsed.hostname in {"127.0.0.1", "localhost", "postgres"}
    name = f"tt_replacement_migrate_{uuid.uuid4().hex}"
    database_url = urlunsplit(parsed._replace(path=f"/{name}"))
    with psycopg.connect(base_url, autocommit=True) as control:
        row = control.execute(
            "SELECT (pg_control_system()).system_identifier"
        ).fetchone()
        assert row is not None
        cluster = str(row[0])
        control.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield database_url, name, cluster
        finally:
            control.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def test_real_migration_uses_verified_default_physical_connection(
    tmp_path: Path, disposable_database: tuple[str, str, str]
) -> None:
    """M-2/M-4: actual migrate and post-migrate never open a second default handle."""
    url, name, cluster = disposable_database
    connection_count = tmp_path / "default-connection-count"
    probe = (
        "import django.db.backends.utils as db_utils\n"
        "import django.db.backends.postgresql.base as pg_base\n"
        "from django.db.migrations.executor import MigrationExecutor\n"
        "_real_execute = db_utils.CursorWrapper.execute\n"
        "_real_migrate = MigrationExecutor.migrate\n"
        "_real_new_connection = pg_base.DatabaseWrapper.get_new_connection\n"
        "_verified_connection = []\n"
        "_default_connections = []\n"
        "def _observed_new_connection(self, params):\n"
        "    result = _real_new_connection(self, params)\n"
        "    if self.alias == 'default':\n"
        "        _default_connections.append(result)\n"
        f"        Path({str(connection_count)!r}).write_text(str(len(_default_connections)))\n"
        "    return result\n"
        "def _observed_execute(self, sql, params=None):\n"
        "    if 'pg_control_system' in str(sql):\n"
        "        _verified_connection.append(self.db.connection)\n"
        "    return _real_execute(self, sql, params)\n"
        "def _observed_migrate(self, *args, **kwargs):\n"
        "    if not _verified_connection or self.connection.connection is not _verified_connection[-1]:\n"
        "        raise RuntimeError('connection-changed-before-migration')\n"
        "    return _real_migrate(self, *args, **kwargs)\n"
        "pg_base.DatabaseWrapper.get_new_connection = _observed_new_connection\n"
        "db_utils.CursorWrapper.execute = _observed_execute\n"
        "MigrationExecutor.migrate = _observed_migrate\n"
    )
    completed, _, migration_marker = _run_wrapper(
        tmp_path,
        environment=_environment(url),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        before_main=probe,
        observe_migration=True,
    )

    _assert_classification(completed, "PASS")
    assert migration_marker.read_text() == "x"
    assert connection_count.read_text() == "1"
    with psycopg.connect(url) as connection:
        row = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'django_migrations')"
        ).fetchone()
        assert row == (True,)


@pytest.mark.parametrize(
    "digest_kind",
    ("wrong-cluster", "wrong-name", "wrong-service", "missing", "runtime-spoof"),
)
def test_wrong_or_missing_code_owned_database_binding_denies_before_migrate(
    tmp_path: Path,
    disposable_database: tuple[str, str, str],
    digest_kind: str,
) -> None:
    """M-2/M-3: runtime declarations cannot replace an independent DB pin."""
    url, name, cluster = disposable_database
    digest = _database_digest("development", name, cluster)
    if digest_kind == "wrong-cluster":
        digest = _database_digest("development", name, "999999999999")
    elif digest_kind == "wrong-name":
        digest = _database_digest("development", f"{name}_old", cluster)
    elif digest_kind == "wrong-service":
        digest = _database_digest("development", name, cluster, service=OTHER)
    elif digest_kind == "missing":
        digest = ""
    elif digest_kind == "runtime-spoof":
        digest = _database_digest("development", name, "999999999999")
    expected = {} if digest_kind == "missing" else {"development": digest}
    environment = _environment(
        url,
        {
            "TAILTAG_EXPECTED_DATABASE_DIGEST": _database_digest(
                "development", name, cluster
            )
        },
    )
    completed, setup_marker, migration_marker = _run_wrapper(
        tmp_path,
        environment=environment,
        database_digests=expected,
        observe_setup=True,
        observe_migration=True,
    )

    _assert_classification(completed, "FAIL_GUARD")
    assert not setup_marker.exists()
    assert not migration_marker.exists()


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql://local:local@127.0.0.1/no_explicit_port",
        "postgresql://local:local@:5432/no_host",
        "postgresql://local:local@127.0.0.1:5432/",
    ),
)
def test_incomplete_default_database_configuration_denies_before_migrate(
    tmp_path: Path, database_url: str
) -> None:
    """M-2/M-3: a complete production default NAME/HOST/PORT is mandatory."""
    completed, setup_marker, migration_marker = _run_wrapper(
        tmp_path,
        environment=_environment(database_url),
        observe_setup=True,
        observe_migration=True,
    )
    _assert_classification(completed, "FAIL_GUARD")
    assert not setup_marker.exists()
    assert not migration_marker.exists()


@pytest.mark.parametrize("error_kind", ("query", "privilege"))
def test_identity_query_error_denies_before_migrate_and_does_not_leak(
    tmp_path: Path, disposable_database: tuple[str, str, str], error_kind: str
) -> None:
    """M-3/M-5: query and privilege failure cannot become a migration attempt."""
    url, name, cluster = disposable_database
    exception = (
        f"RuntimeError({PRIVATE_SENTINEL!r})"
        if error_kind == "query"
        else f"psycopg.errors.InsufficientPrivilege({PRIVATE_SENTINEL!r})"
    )
    broken_query = (
        "import psycopg\n"
        "import django.db.backends.utils as db_utils\n"
        "_real_execute = db_utils.CursorWrapper.execute\n"
        "def _broken_execute(self, sql, params=None):\n"
        "    if 'pg_control_system' in str(sql):\n"
        f"        raise {exception}\n"
        "    return _real_execute(self, sql, params)\n"
        "db_utils.CursorWrapper.execute = _broken_execute\n"
    )
    completed, setup_marker, migration_marker = _run_wrapper(
        tmp_path,
        environment=_environment(url),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        before_main=broken_query,
        observe_setup=True,
        observe_migration=True,
    )
    _assert_classification(completed, "FAIL_GUARD")
    assert not setup_marker.exists()
    assert not migration_marker.exists()


def test_staging_cannot_use_development_database_digest(
    tmp_path: Path, disposable_database: tuple[str, str, str]
) -> None:
    """M-2/M-3: a valid Staging API tuple cannot adopt Development's DB pin."""
    url, name, cluster = disposable_database
    completed, _, migration_marker = _run_wrapper(
        tmp_path,
        environment=_environment(url, _runtime("staging")),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        observe_migration=True,
    )
    _assert_classification(completed, "FAIL_GUARD")
    assert not migration_marker.exists()


@pytest.mark.parametrize("phase", ("candidate", "canonical"))
def test_both_finite_staging_phases_allow_the_same_verified_migrate_command(
    tmp_path: Path,
    disposable_database: tuple[str, str, str],
    phase: str,
) -> None:
    """M-1/M-4: candidate and canonical are the only accepted Staging phases."""
    url, name, cluster = disposable_database
    marker = tmp_path / "staging-migrate-called"
    command_spy = (
        "import django.core.management as management\n"
        "def _observed_command(*args, **kwargs):\n"
        "    if args[0] != 'migrate' or kwargs.get('database') != 'default':\n"
        "        raise RuntimeError('wrong-migration-command')\n"
        f"    Path({str(marker)!r}).write_text('x')\n"
        "management.call_command = _observed_command\n"
    )
    completed, _, _ = _run_wrapper(
        tmp_path,
        environment=_environment(
            url,
            {
                **_runtime("staging"),
                "TAILTAG_STAGING_TARGET_PHASE": phase,
            },
        ),
        database_digests={"staging": _database_digest("staging", name, cluster)},
        before_import=command_spy,
    )
    _assert_classification(completed, "PASS")
    assert marker.read_text() == "x"


def test_configured_database_name_must_equal_the_connected_name(
    tmp_path: Path, disposable_database: tuple[str, str, str]
) -> None:
    """M-2/M-3: a matching digest cannot excuse a configured/connected mismatch."""
    url, _name, cluster = disposable_database
    changed_result = (
        "import django.db.backends.utils as db_utils\n"
        "_real_execute = db_utils.CursorWrapper.execute\n"
        "_real_getattr = db_utils.CursorWrapper.__getattr__\n"
        "def _observed_execute(self, sql, params=None):\n"
        "    self._tt_identity_query = 'pg_control_system' in str(sql)\n"
        "    return _real_execute(self, sql, params)\n"
        "def _observed_getattr(self, attr):\n"
        "    value = _real_getattr(self, attr)\n"
        "    if attr == 'fetchone' and self.__dict__.get('_tt_identity_query', False):\n"
        "        def _fake_fetchone():\n"
        "            result = value()\n"
        "            return ('other_connected_database', result[1])\n"
        "        return _fake_fetchone\n"
        "    return value\n"
        "db_utils.CursorWrapper.execute = _observed_execute\n"
        "db_utils.CursorWrapper.__getattr__ = _observed_getattr\n"
    )
    completed, _, migration_marker = _run_wrapper(
        tmp_path,
        environment=_environment(url),
        database_digests={
            "development": _database_digest(
                "development", "other_connected_database", cluster
            )
        },
        before_main=changed_result,
        observe_migration=True,
    )
    _assert_classification(completed, "FAIL_GUARD")
    assert not migration_marker.exists()


def test_production_settings_failure_does_not_leak_its_private_value(
    tmp_path: Path, disposable_database: tuple[str, str, str]
) -> None:
    """M-5: even settings import errors have only the fixed guard result."""
    url, name, cluster = disposable_database
    completed, _, migration_marker = _run_wrapper(
        tmp_path,
        environment=_environment(url, {"DJANGO_SECRET_KEY": ""}),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        observe_migration=True,
    )
    _assert_classification(completed, "FAIL_GUARD")
    assert not migration_marker.exists()


def test_closed_verified_connection_cannot_reconnect_before_first_write(
    tmp_path: Path, disposable_database: tuple[str, str, str]
) -> None:
    """M-4: migrate must not silently reconnect after the verified handle closes."""
    url, name, cluster = disposable_database
    close_before_command = (
        "import django.core.management as management\n"
        "from django.db import connections\n"
        "_real_call = management.call_command\n"
        "def _close_before_migrate(*args, **kwargs):\n"
        "    connections['default'].close()\n"
        "    return _real_call(*args, **kwargs)\n"
        "management.call_command = _close_before_migrate\n"
    )
    completed, _, _ = _run_wrapper(
        tmp_path,
        environment=_environment(url),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        before_import=close_before_command,
    )
    _assert_classification(completed, "FAIL_MIGRATION")
    with psycopg.connect(url) as connection:
        row = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'django_migrations')"
        ).fetchone()
        assert row == (False,)


def test_fresh_default_wrapper_cannot_connect_after_identity_verification(
    tmp_path: Path, disposable_database: tuple[str, str, str]
) -> None:
    """M-4: a new default DatabaseWrapper cannot evade the original handle seal."""
    url, name, cluster = disposable_database
    calls = tmp_path / "migration-invocations"
    connections_opened = tmp_path / "default-connections-opened"
    attempt = (
        "import django.core.management as management\n"
        "import django.db.backends.postgresql.base as pg_base\n"
        "from django.db import connections\n"
        "_real_new_connection = pg_base.DatabaseWrapper.get_new_connection\n"
        "_opened = []\n"
        "def _count_new_connection(self, params):\n"
        "    result = _real_new_connection(self, params)\n"
        "    if self.alias == 'default':\n"
        "        _opened.append(result)\n"
        f"        Path({str(connections_opened)!r}).write_text(str(len(_opened)))\n"
        "    return result\n"
        "def _fresh_wrapper_migration(*args, **kwargs):\n"
        f"    Path({str(calls)!r}).write_text('x')\n"
        "    if args[0] != 'migrate' or kwargs.get('database') != 'default':\n"
        "        raise RuntimeError('wrong-migration-command')\n"
        "    with connections['default'].cursor() as cursor:\n"
        "        cursor.execute('CREATE TABLE tt_first_wrapper_probe (id integer)')\n"
        "    new_default = connections.create_connection('default')\n"
        "    with new_default.cursor() as cursor:\n"
        "        cursor.execute('CREATE TABLE tt_fresh_wrapper_probe (id integer)')\n"
        f"    raise RuntimeError({PRIVATE_SENTINEL!r})\n"
        "pg_base.DatabaseWrapper.get_new_connection = _count_new_connection\n"
        "management.call_command = _fresh_wrapper_migration\n"
    )
    completed, _, _ = _run_wrapper(
        tmp_path,
        environment=_environment(url),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        before_import=attempt,
    )
    _assert_classification(completed, "FAIL_MIGRATION")
    assert calls.read_text() == "x"
    assert connections_opened.read_text() == "1"
    with psycopg.connect(url) as connection:
        first = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'tt_first_wrapper_probe')"
        ).fetchone()
        second = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'tt_fresh_wrapper_probe')"
        ).fetchone()
        assert first == (True,)
        assert second == (False,)


def test_substituted_open_handle_cannot_write_before_first_migration_write(
    tmp_path: Path, disposable_database: tuple[str, str, str]
) -> None:
    """M-4: checking only an open handle would allow an unverified replacement."""
    url, name, cluster = disposable_database
    calls = tmp_path / "migration-invocations"
    attempt = (
        "import django.core.management as management\n"
        "from django.db import connections\n"
        "import psycopg\n"
        "def _substitute_handle(*args, **kwargs):\n"
        f"    Path({str(calls)!r}).write_text('x')\n"
        "    if args[0] != 'migrate' or kwargs.get('database') != 'default':\n"
        "        raise RuntimeError('wrong-migration-command')\n"
        "    default = connections['default']\n"
        "    verified = default.connection\n"
        "    substitute = psycopg.connect(os.environ['DATABASE_URL'], autocommit=True)\n"
        "    default.connection = substitute\n"
        "    try:\n"
        "        with default.cursor() as cursor:\n"
        "            cursor.execute('CREATE TABLE tt_substituted_handle_probe (id integer)')\n"
        "    finally:\n"
        "        default.connection = verified\n"
        "        substitute.close()\n"
        f"    raise RuntimeError({PRIVATE_SENTINEL!r})\n"
        "management.call_command = _substitute_handle\n"
    )
    completed, _, _ = _run_wrapper(
        tmp_path,
        environment=_environment(url),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        before_import="import os\n" + attempt,
    )
    _assert_classification(completed, "FAIL_MIGRATION")
    assert calls.read_text() == "x"
    with psycopg.connect(url) as connection:
        row = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'tt_substituted_handle_probe')"
        ).fetchone()
        assert row == (False,)


def test_post_write_failure_is_sanitized_and_never_retried_or_reversed(
    tmp_path: Path, disposable_database: tuple[str, str, str]
) -> None:
    """M-4/M-5: after a write, a closed handle cannot authorize another write."""
    url, name, cluster = disposable_database
    marker = tmp_path / "migration-invocations"
    partial_migration = (
        "import django.core.management as management\n"
        "from django.db import connections\n"
        "def _partial_migration(*args, **kwargs):\n"
        f"    _marker = Path({str(marker)!r})\n"
        "    _marker.write_text(_marker.read_text() + 'x' if _marker.exists() else 'x')\n"
        "    if args[0] != 'migrate' or kwargs.get('database') != 'default':\n"
        "        raise RuntimeError('wrong-migration-command')\n"
        "    with connections['default'].cursor() as cursor:\n"
        "        cursor.execute('CREATE TABLE tt_partial_migration_probe (id integer)')\n"
        "    connections['default'].close()\n"
        "    with connections['default'].cursor() as cursor:\n"
        "        cursor.execute('CREATE TABLE tt_forbidden_reconnect_probe (id integer)')\n"
        f"    raise RuntimeError({PRIVATE_SENTINEL!r})\n"
        "management.call_command = _partial_migration\n"
    )
    completed, _, _ = _run_wrapper(
        tmp_path,
        environment=_environment(url),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        before_import=partial_migration,
    )
    _assert_classification(completed, "FAIL_MIGRATION")
    assert marker.read_text() == "x"
    with psycopg.connect(url) as connection:
        first = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'tt_partial_migration_probe')"
        ).fetchone()
        second = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'tt_forbidden_reconnect_probe')"
        ).fetchone()
        assert first == (True,)
        assert second == (False,)


@pytest.mark.parametrize("phase", ("setup", "migration"))
def test_process_descriptor_output_and_raw_exception_are_suppressed(
    tmp_path: Path,
    disposable_database: tuple[str, str, str],
    phase: str,
) -> None:
    """M-5: direct fd writes and exceptions cannot expose private values."""
    url, name, cluster = disposable_database
    if phase == "setup":
        poison = (
            "import django\n"
            "def _noisy_setup(*args, **kwargs):\n"
            f"    os.write(1, {PRIVATE_SENTINEL!r}.encode())\n"
            f"    os.write(2, {PRIVATE_SENTINEL!r}.encode())\n"
            f"    raise RuntimeError({PRIVATE_SENTINEL!r})\n"
            "django.setup = _noisy_setup\n"
        )
        expected = "FAIL_GUARD"
    else:
        poison = (
            "import django.core.management as management\n"
            "def _noisy_migration(*args, **kwargs):\n"
            f"    os.write(1, {PRIVATE_SENTINEL!r}.encode())\n"
            f"    os.write(2, {PRIVATE_SENTINEL!r}.encode())\n"
            f"    raise RuntimeError({PRIVATE_SENTINEL!r})\n"
            "management.call_command = _noisy_migration\n"
        )
        expected = "FAIL_MIGRATION"
    completed, _, _ = _run_wrapper(
        tmp_path,
        environment=_environment(url),
        database_digests={
            "development": _database_digest("development", name, cluster)
        },
        before_import="import os\n" + poison,
    )
    _assert_classification(completed, expected)
