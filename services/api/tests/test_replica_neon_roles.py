"""Acceptance contract for the hybrid replica Neon role provisioning script (#354).

These tests run the real script against a scratch database on the PostgreSQL
server the API test suite already uses. Only the secret writer is faked: the
real boundary is gcloud and Secret Manager. In CI the connecting user is a
superuser, which the script needs to create roles.
"""

from __future__ import annotations

import importlib
import os
import sys
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any, LiteralString, cast
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "replica_neon_roles.py"
SCRATCH_PREFIX = "tt_replica_roles_"
ROLE_NAMES = ("migrator", "runtime")
SECRET_IDS = ("migrator-database-url", "runtime-database-url")

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture
def roles_module() -> ModuleType:
    """Load the script once it exists."""
    assert SCRIPT.is_file(), "scripts/replica_neon_roles.py must exist"
    return cast(Any, importlib.import_module("scripts.replica_neon_roles"))


def url_for_database(base_url: str, database: str) -> str:
    """Point a PostgreSQL URL at another database on the same server."""
    parts = urlsplit(base_url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def run_ddl(conn: psycopg.Connection[Any], template: LiteralString, name: str) -> None:
    """Run fixed test-only DDL with one quoted identifier."""
    # The template is a literal from this file; psycopg.sql.Identifier quotes the name.
    # nosemgrep: tailtag.django.dynamic-raw-sql
    conn.execute(sql.SQL(template).format(sql.Identifier(name)))


def drop_roles(admin_url: str) -> None:
    """Remove the two roles, including what they own in the scratch database."""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        for name in ROLE_NAMES:
            exists = conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)
            ).fetchone()
            if exists:
                run_ddl(conn, "DROP OWNED BY {}", name)
                run_ddl(conn, "DROP ROLE {}", name)


@pytest.fixture(scope="module")
def scratch_admin_url() -> Iterator[str]:
    """Give this module its own database; drop it and the roles afterwards."""
    base_url = os.environ["DATABASE_URL"]
    maintenance_url = url_for_database(base_url, "postgres")
    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        leftovers = conn.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE %s",
            (SCRATCH_PREFIX.replace("_", r"\_") + "%",),
        ).fetchall()
        for (leftover,) in leftovers:
            run_ddl(conn, "DROP DATABASE {} WITH (FORCE)", leftover)
        for name in ROLE_NAMES:
            run_ddl(conn, "DROP ROLE IF EXISTS {}", name)
        scratch = f"{SCRATCH_PREFIX}{uuid.uuid4().hex[:12]}"
        run_ddl(conn, "CREATE DATABASE {}", scratch)
    scratch_url = url_for_database(base_url, scratch)
    try:
        yield scratch_url
    finally:
        with psycopg.connect(maintenance_url, autocommit=True) as conn:
            run_ddl(conn, "DROP DATABASE IF EXISTS {} WITH (FORCE)", scratch)
            for name in ROLE_NAMES:
                run_ddl(conn, "DROP ROLE IF EXISTS {}", name)


@pytest.fixture
def clean_roles(scratch_admin_url: str) -> Iterator[str]:
    """Start every test with no roles so each run is a first run."""
    drop_roles(scratch_admin_url)
    yield scratch_admin_url
    drop_roles(scratch_admin_url)


def recording_writer() -> tuple[list[tuple[str, str]], Callable[[str, str], None]]:
    """Fake the secret store and keep every write in order."""
    writes: list[tuple[str, str]] = []

    def write_secret(secret_id: str, value: str) -> None:
        writes.append((secret_id, value))

    return writes, write_secret


def password_of(url: str) -> str:
    password = urlsplit(url).password
    assert password
    return unquote(password)


def test_roles_can_build_but_runtime_cannot_alter_schema(
    roles_module: ModuleType,
    clean_roles: str,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """AC11: migrator owns DDL, runtime is DML-only, no role is privileged."""
    writes, write_secret = recording_writer()

    roles_module.provision_roles(
        clean_roles, write_secret=write_secret, enforce_tls=False
    )

    assert sorted(secret_id for secret_id, _ in writes) == sorted(SECRET_IDS)
    urls = dict(writes)

    with psycopg.connect(urls["migrator-database-url"], autocommit=True) as migrator:
        migrator.execute("CREATE TABLE widgets (id serial PRIMARY KEY, name text)")

    with psycopg.connect(urls["runtime-database-url"], autocommit=True) as runtime:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            runtime.execute("CREATE TABLE intruder (id integer)")
        runtime.execute("INSERT INTO widgets (name) VALUES ('a')")
        runtime.execute("SELECT nextval('widgets_id_seq')")
        assert runtime.execute("SELECT count(*) FROM widgets").fetchone() == (1,)
        runtime.execute("UPDATE widgets SET name = 'b'")
        runtime.execute("DELETE FROM widgets")

    with psycopg.connect(clean_roles, autocommit=True) as admin:
        flags = admin.execute(
            "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
            "WHERE rolname = ANY(%s) ORDER BY rolname",
            (list(ROLE_NAMES),),
        ).fetchall()
    assert flags == [
        ("migrator", False, False, False),
        ("runtime", False, False, False),
    ]

    captured = capfd.readouterr()
    for _, url in writes:
        assert password_of(url) not in captured.out + captured.err


def test_second_run_changes_nothing(roles_module: ModuleType, clean_roles: str) -> None:
    """AC11: a rerun writes no secret, keeps passwords, and keeps default privileges."""
    first_writes, first_writer = recording_writer()
    roles_module.provision_roles(
        clean_roles, write_secret=first_writer, enforce_tls=False
    )
    urls = dict(first_writes)

    second_writes, second_writer = recording_writer()
    roles_module.provision_roles(
        clean_roles, write_secret=second_writer, enforce_tls=False
    )

    assert second_writes == []
    with psycopg.connect(urls["migrator-database-url"], autocommit=True) as migrator:
        migrator.execute("CREATE TABLE gadgets (id serial PRIMARY KEY, name text)")
    with psycopg.connect(urls["runtime-database-url"], autocommit=True) as runtime:
        runtime.execute("INSERT INTO gadgets (name) VALUES ('a')")
        assert runtime.execute("SELECT count(*) FROM gadgets").fetchone() == (1,)


def test_rotate_replaces_passwords_and_secrets(
    roles_module: ModuleType, clean_roles: str
) -> None:
    """AC11: --rotate is the recovery path, so it must issue new working secrets."""
    first_writes, first_writer = recording_writer()
    roles_module.provision_roles(
        clean_roles, write_secret=first_writer, enforce_tls=False
    )
    old_urls = dict(first_writes)

    rotated_writes, rotated_writer = recording_writer()
    roles_module.provision_roles(
        clean_roles, write_secret=rotated_writer, rotate=True, enforce_tls=False
    )

    assert sorted(secret_id for secret_id, _ in rotated_writes) == sorted(SECRET_IDS)
    new_urls = dict(rotated_writes)
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(old_urls["migrator-database-url"]).close()
    with psycopg.connect(
        new_urls["migrator-database-url"], autocommit=True
    ) as migrator:
        migrator.execute("CREATE TABLE gizmos (id serial PRIMARY KEY, name text)")
    with psycopg.connect(new_urls["runtime-database-url"], autocommit=True) as runtime:
        runtime.execute("INSERT INTO gizmos (name) VALUES ('a')")
        assert runtime.execute("SELECT count(*) FROM gizmos").fetchone() == (1,)


def test_role_url_keeps_admin_endpoint_and_forces_verified_tls(
    roles_module: ModuleType,
) -> None:
    """AC11/AC12: only the credentials change and TLS is always fully verified."""
    password = "p@ss/w:o?r#d%+&="
    admin_url = (
        "postgresql://tailtag_admin:admin-secret@ep-example.neon.test:6543/tailtag"
        "?sslmode=require"
    )

    result: str = roles_module.role_url(admin_url, "migrator", password)

    parts = urlsplit(result)
    assert (parts.hostname, parts.port, parts.path) == (
        "ep-example.neon.test",
        6543,
        "/tailtag",
    )
    assert unquote(parts.username or "") == "migrator"
    assert unquote(parts.password or "") == password
    assert "admin-secret" not in result
    query = parse_qs(parts.query)
    assert query["sslmode"] == ["verify-full"]
    assert query["sslrootcert"] == ["system"]
