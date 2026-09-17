"""Acceptance tests for #204's fail-closed reset configuration and identity guards."""

from __future__ import annotations

import importlib
import os
import sys
import uuid
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, Self, cast

import psycopg
import pytest
from django.conf import settings
from django.db import connection
from psycopg import sql

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
RESET_ID = uuid.UUID("2b859e84-1d92-4a8a-a72b-d3567219288d")
MEDIA_KEY = "images/0123456789abcdef0123456789abcdef.png"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


@pytest.fixture
def safety() -> Any:
    """Load the approved guard only once the production module exists."""
    assert (API_ROOT / "rehearsal" / "safety.py").is_file()
    return cast(Any, importlib.import_module("rehearsal.safety"))


def reset_environment(**overrides: str) -> dict[str, str]:
    """Return one complete, separately supplied Staging reset configuration."""
    return {
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "RAILWAY_PROJECT_ID": "85324de4-be6a-49c3-a3f9-6cac13877849",
        "RAILWAY_ENVIRONMENT_ID": "5f4ab4f2-af14-4b2b-a4c3-3344d281fe5e",
        "RAILWAY_SERVICE_ID": "2247da27-97df-4d5d-b1dc-d21eeb7901d9",
        "TAILTAG_STAGING_RESET_ENABLED": "true",
        "TAILTAG_STAGING_RESET_ID": str(RESET_ID),
        "TAILTAG_STAGING_DATABASE_SYSTEM_ID": "742391",
        "TAILTAG_STAGING_DATABASE_HOST": "staging-postgres.internal",
        "TAILTAG_STAGING_DATABASE_PORT": "5432",
        "TAILTAG_STAGING_DATABASE_NAME": "tailtag_staging",
        "TAILTAG_STAGING_RESET_OWNER_CLERK_ID": "user_rehearsal_owner",
        "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID": "user_rehearsal_catcher",
        "TAILTAG_STAGING_RESET_MEDIA_KEY": MEDIA_KEY,
        **overrides,
    }


def record_call(calls: list[object]) -> None:
    """Record an unsafe-configuration guard invocation if one occurs."""
    calls.append(1)


def record_callback(calls: list[object]) -> Callable[[object], None]:
    """Return a named typed guard callback for fail-before-work assertions."""

    def callback(_: object) -> None:
        record_call(calls)

    return callback


def require_row(value: tuple[object, ...] | None) -> tuple[object, ...]:
    assert value is not None
    return value


def test_baseline_constants_freeze_the_small_versioned_fixture(
    safety: ModuleType,
) -> None:
    """AC-2/3: implementation cannot silently grow or randomize the baseline."""
    baseline = importlib.import_module("rehearsal.baseline")

    assert baseline.BASELINE_VERSION == 1
    assert baseline.OWNER_ALIAS == "owner"
    assert baseline.CATCHER_ALIAS == "catcher"
    assert baseline.CONVENTION_NAME == "TailTag Canonical Rehearsal"
    assert baseline.FIRST_FURSUIT_TAILTAG_ID == uuid.UUID(
        "e43be4ef-36d6-4a38-bf65-20f8675c2a31"
    )
    assert baseline.SECOND_FURSUIT_TAILTAG_ID == uuid.UUID(
        "f858b9fb-8a1a-4f87-9e6f-683cead8a7b2"
    )
    assert safety.ResetConfiguration.__dataclass_params__.frozen is True


def test_load_configuration_returns_only_canonical_typed_reset_facts(
    safety: ModuleType,
) -> None:
    """AC-5: configuration must be explicit and cannot leak unrelated values."""
    environment = reset_environment(EXTRA_SECRET="must-not-be-retained")

    configuration = safety.load_configuration(environment)

    assert configuration == safety.ResetConfiguration(
        environment_id=RESET_ID,
        cluster_identifier="742391",
        database_host="staging-postgres.internal",
        database_port="5432",
        database_name="tailtag_staging",
        owner_clerk_id="user_rehearsal_owner",
        catcher_clerk_id="user_rehearsal_catcher",
        media_key=MEDIA_KEY,
    )
    assert "must-not-be-retained" not in repr(configuration)


@pytest.mark.parametrize(
    "overrides",
    (
        {"RAILWAY_ENVIRONMENT_NAME": "development"},
        {"RAILWAY_ENVIRONMENT_NAME": "Staging"},
        {"RAILWAY_ENVIRONMENT_NAME": "production"},
        {"RAILWAY_ENVIRONMENT_NAME": "preview"},
        {"RAILWAY_PROJECT_ID": "00000000-0000-0000-0000-000000000000"},
        {"RAILWAY_ENVIRONMENT_ID": "00000000-0000-0000-0000-000000000000"},
        {"RAILWAY_SERVICE_ID": "00000000-0000-0000-0000-000000000000"},
        {"TAILTAG_STAGING_RESET_ENABLED": "false"},
        {"TAILTAG_STAGING_RESET_ENABLED": "True"},
        {"TAILTAG_STAGING_RESET_ID": str(RESET_ID).upper()},
        {"TAILTAG_STAGING_RESET_ID": "00000000-0000-0000-0000-000000000000"},
        {"TAILTAG_STAGING_RESET_ID": "2b859e84-1d92-1a8a-a72b-d3567219288d"},
        {"TAILTAG_STAGING_RESET_ID": "not-a-uuid"},
        {"TAILTAG_STAGING_DATABASE_SYSTEM_ID": "742391.0"},
        {"TAILTAG_STAGING_DATABASE_SYSTEM_ID": "-742391"},
        {"TAILTAG_STAGING_DATABASE_HOST": "Staging-Postgres.Internal"},
        {"TAILTAG_STAGING_DATABASE_PORT": "05432"},
        {"TAILTAG_STAGING_DATABASE_PORT": "0"},
        {"TAILTAG_STAGING_DATABASE_NAME": "postgres"},
        {"TAILTAG_STAGING_DATABASE_NAME": "tailtag staging"},
        {"TAILTAG_STAGING_RESET_OWNER_CLERK_ID": ""},
        {"TAILTAG_STAGING_RESET_OWNER_CLERK_ID": " owner"},
        {"TAILTAG_STAGING_RESET_CATCHER_CLERK_ID": "user_rehearsal_owner"},
        {"TAILTAG_STAGING_RESET_CATCHER_CLERK_ID": ""},
        {"TAILTAG_STAGING_RESET_CATCHER_CLERK_ID": "catcher "},
        {"TAILTAG_STAGING_RESET_MEDIA_KEY": "avatars/rehearsal-owner.png"},
        {"TAILTAG_STAGING_RESET_MEDIA_KEY": "images/not-an-opaque-key.png"},
    ),
)
def test_unsafe_reset_configuration_is_denied_before_database_or_asset_work(
    safety: ModuleType, monkeypatch: pytest.MonkeyPatch, overrides: Mapping[str, str]
) -> None:
    """AC-5/SECURITY: malformed, copied, or non-Staging inputs fail closed."""
    database_calls: list[object] = []
    asset_calls: list[object] = []
    monkeypatch.setattr(safety, "validate_database", record_callback(database_calls))
    monkeypatch.setattr(safety, "validate_identity", record_callback(asset_calls))

    with pytest.raises(safety.ResetSafetyError):
        safety.load_configuration(reset_environment(**overrides))

    assert database_calls == []
    assert asset_calls == []


@pytest.mark.parametrize(
    "missing_name",
    (
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_ENVIRONMENT_ID",
        "RAILWAY_SERVICE_ID",
        "TAILTAG_STAGING_RESET_ENABLED",
        "TAILTAG_STAGING_RESET_ID",
        "TAILTAG_STAGING_DATABASE_SYSTEM_ID",
        "TAILTAG_STAGING_DATABASE_HOST",
        "TAILTAG_STAGING_DATABASE_PORT",
        "TAILTAG_STAGING_DATABASE_NAME",
        "TAILTAG_STAGING_RESET_OWNER_CLERK_ID",
        "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID",
        "TAILTAG_STAGING_RESET_MEDIA_KEY",
    ),
)
def test_each_required_reset_configuration_value_is_mandatory(
    safety: ModuleType, missing_name: str
) -> None:
    """AC-5: no omitted target binding may acquire an implicit default."""
    environment = reset_environment()
    del environment[missing_name]

    with pytest.raises(safety.ResetSafetyError):
        safety.load_configuration(environment)


@pytest.mark.django_db(transaction=True)
def test_validate_database_requires_the_effective_django_target_and_cluster(
    safety: ModuleType,
) -> None:
    """AC-5: a valid-looking sentinel configuration cannot target another database."""
    database = settings.DATABASES["default"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        name, system_identifier = cursor.fetchone()

    configuration = safety.ResetConfiguration(
        environment_id=RESET_ID,
        cluster_identifier=str(system_identifier),
        database_host=str(database["HOST"]),
        database_port=str(database["PORT"]),
        database_name=str(name),
        owner_clerk_id="user_rehearsal_owner",
        catcher_clerk_id="user_rehearsal_catcher",
        media_key=MEDIA_KEY,
    )

    safety.validate_database(configuration)

    for unsafe_configuration in (
        replace(configuration, database_name=f"{name}_wrong_target"),
        replace(configuration, database_host="wrong-target.internal"),
        replace(configuration, database_port="6543"),
        replace(configuration, cluster_identifier="999999999"),
    ):
        with pytest.raises(safety.ResetSafetyError):
            safety.validate_database(unsafe_configuration)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "catalog_relation",
    ("pg_prepared_xacts", "pg_subscription"),
)
def test_validate_database_denies_catalog_maintenance_hazards(
    safety: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    catalog_relation: str,
) -> None:
    """AC-5/6: prepared work or logical replication blocks destructive maintenance."""
    database = settings.DATABASES["default"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        name, system_identifier = cursor.fetchone()
    configuration = safety.ResetConfiguration(
        RESET_ID,
        str(system_identifier),
        str(database["HOST"]),
        str(database["PORT"]),
        str(name),
        "user_rehearsal_owner",
        "user_rehearsal_catcher",
        MEDIA_KEY,
    )
    original_cursor = safety.connection.cursor

    class HazardCursor:
        def __init__(self) -> None:
            self.delegate = original_cursor()
            self.hazard_query = False

        def __enter__(self) -> Self:
            self.delegate.__enter__()
            return self

        def __exit__(self, *args: object) -> None:
            self.delegate.__exit__(*args)

        def execute(self, query: str, *args: object, **kwargs: object) -> object:
            self.hazard_query = catalog_relation in query
            if self.hazard_query:
                return None
            return self.delegate.execute(query, *args, **kwargs)

        def fetchone(self) -> object:
            return (1,) if self.hazard_query else self.delegate.fetchone()

    monkeypatch.setattr(safety.connection, "cursor", HazardCursor)

    with pytest.raises(safety.ResetSafetyError):
        safety.validate_database(configuration)


@pytest.mark.django_db(transaction=True)
def test_validate_database_denies_a_real_non_superuser_role(
    safety: ModuleType,
) -> None:
    """AC-5/6: the executor must prove actual superuser privilege before maintenance."""
    database = settings.DATABASES["default"]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        name, system_identifier = cursor.fetchone()
    configuration = safety.ResetConfiguration(
        RESET_ID,
        str(system_identifier),
        str(database["HOST"]),
        str(database["PORT"]),
        str(name),
        "user_rehearsal_owner",
        "user_rehearsal_catcher",
        MEDIA_KEY,
    )
    role_name = f"tt_reset_test_{uuid.uuid4().hex}"
    create_role = sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role_name))
    drop_role = sql.SQL("DROP ROLE {}").format(sql.Identifier(role_name))
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as control:
        current_user = str(
            require_row(control.execute("SELECT current_user").fetchone())[0]
        )
        control.execute(create_role)
        control.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(role_name), sql.Identifier(current_user)
            )
        )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET ROLE {}")
                .format(sql.Identifier(role_name))
                .as_string(connection.connection)
            )
        with pytest.raises(safety.ResetSafetyError):
            safety.validate_database(configuration)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as control:
            control.execute(
                sql.SQL("REVOKE {} FROM {}").format(
                    sql.Identifier(role_name), sql.Identifier(current_user)
                )
            )
            control.execute(drop_role)
