"""Acceptance contract for the hybrid replica Neon role provisioning script (#354).

These tests run the real script against a scratch database on the PostgreSQL
server the API test suite already uses. Only the secret writer is faked: the
real boundary is gcloud and Secret Manager. In CI the connecting user is a
superuser, which the script needs to create roles.
"""

from __future__ import annotations

import importlib
import os
import subprocess
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
ROLE_NAMES = ("migrator", "runtime", "maintainer")
SECRET_IDS = (
    "migrator-database-url",
    "runtime-database-url",
    "maintainer-database-url",
)
PROBE_FACTS = ("pg_control_system", "database_owner", "pg_signal_backend")
RESTRICTED_ADMIN = "tt_replica_roles_admin"

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
    """Remove the roles, including what they own in the scratch database."""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        for name in ROLE_NAMES:
            exists = conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)
            ).fetchone()
            if exists:
                if name == "maintainer":
                    # The maintainer owns the database; hand it back first.
                    run_ddl(conn, "REASSIGN OWNED BY {} TO CURRENT_USER", name)
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
        ("maintainer", False, False, False),
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
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(old_urls["maintainer-database-url"]).close()
    with psycopg.connect(new_urls["maintainer-database-url"], autocommit=True) as conn:
        assert conn.execute("SELECT current_user").fetchone() == ("maintainer",)


def test_secret_writer_passes_the_value_on_stdin_only(
    roles_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """AC12: gcloud gets the URL on stdin, never in argv, errors, or output."""
    secret = "postgresql://runtime:s3cr3t-value@ep-example.neon.test/tailtag"
    calls: list[tuple[list[str], object]] = []
    exit_codes = [0, 1]

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((list(command), kwargs.get("input")))
        return subprocess.CompletedProcess(command, exit_codes[len(calls) - 1], "", "")

    def fake_which(name: str) -> str:
        return f"/fake/{name}"

    monkeypatch.setattr(roles_module.shutil, "which", fake_which)
    monkeypatch.setattr(roles_module.subprocess, "run", fake_run)
    write_secret = roles_module._secret_writer("fake-replica-project")

    write_secret("runtime-database-url", secret)
    with pytest.raises(roles_module.RoleProvisioningError) as failure:
        write_secret("runtime-database-url", secret)

    assert [stdin for _, stdin in calls] == [secret, secret]
    assert all("s3cr3t" not in part for command, _ in calls for part in command)
    assert "s3cr3t" not in str(failure.value)
    captured = capfd.readouterr()
    assert "s3cr3t" not in captured.out + captured.err


@pytest.mark.parametrize(
    ("admin_port", "expected_port"),
    (pytest.param(":6543", 6543, id="explicit"), pytest.param("", 5432, id="omitted")),
)
def test_role_url_keeps_admin_endpoint_and_forces_verified_tls(
    roles_module: ModuleType, admin_port: str, expected_port: int
) -> None:
    """AC11/AC12: only the credentials change and TLS is always fully verified.

    Neon's URI has no port, but replica reset compares a numeric port, so the
    stored URL always names one.
    """
    password = "p@ss/w:o?r#d%+&="
    admin_url = (
        f"postgresql://tailtag_admin:admin-secret@ep-example.neon.test{admin_port}"
        "/tailtag?sslmode=require"
    )

    result: str = roles_module.role_url(admin_url, "migrator", password)

    parts = urlsplit(result)
    assert (parts.hostname, parts.port, parts.path) == (
        "ep-example.neon.test",
        expected_port,
        "/tailtag",
    )
    assert unquote(parts.username or "") == "migrator"
    assert unquote(parts.password or "") == password
    assert "admin-secret" not in result
    query = parse_qs(parts.query)
    assert query["sslmode"] == ["verify-full"]
    assert query["sslrootcert"] == ["system"]


def run_provision(
    roles_module: ModuleType, admin_url: str, **options: Any
) -> dict[str, str]:
    """Provision with the fake secret store and return what it was given."""
    writes, write_secret = recording_writer()
    roles_module.provision_roles(
        admin_url, write_secret=write_secret, enforce_tls=False, **options
    )
    return dict(writes)


def test_maintainer_is_bounded_owns_the_database_and_inherits_runtime(
    roles_module: ModuleType,
    clean_roles: str,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """AC15: maintainer is never privileged, owns the database, and gets runtime rights."""
    urls = run_provision(roles_module, clean_roles)

    with psycopg.connect(clean_roles, autocommit=True) as admin:
        flags = admin.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolcanlogin "
            "FROM pg_roles WHERE rolname = 'maintainer'"
        ).fetchone()
        member_of = {
            name
            for (name,) in admin.execute(
                "SELECT roleid::regrole::text FROM pg_auth_members "
                "WHERE member = 'maintainer'::regrole"
            ).fetchall()
        }
        owner = admin.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database "
            "WHERE datname = current_database()"
        ).fetchone()
    assert flags == (False, False, False, True, True)
    # Exact set: any extra membership, such as neon_superuser, is a failure.
    assert member_of == {"pg_signal_backend", "runtime"}
    assert owner == ("maintainer",)

    # Membership, not copied grants: a table made later is usable at once.
    with psycopg.connect(urls["migrator-database-url"], autocommit=True) as migrator:
        migrator.execute("CREATE TABLE sprockets (id serial PRIMARY KEY, name text)")
    with psycopg.connect(urls["maintainer-database-url"], autocommit=True) as conn:
        conn.execute("INSERT INTO sprockets (name) VALUES ('a')")
        assert conn.execute("SELECT count(*) FROM sprockets").fetchone() == (1,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("CREATE ROLE sneaky")

    captured = capfd.readouterr()
    assert (
        password_of(urls["maintainer-database-url"]) not in captured.out + captured.err
    )
    # R2: creating the role runs the probe, which reports every fact by name.
    assert all(fact in captured.out for fact in PROBE_FACTS)


@pytest.fixture
def restricted_admin_url(scratch_admin_url: str) -> Iterator[str]:
    """A Neon-like admin: CREATEROLE and CREATEDB, owns its database, not a superuser."""
    database = f"{SCRATCH_PREFIX}restricted_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(scratch_admin_url, autocommit=True) as conn:
        drop_roles(scratch_admin_url)
        run_ddl(conn, "DROP ROLE IF EXISTS {}", RESTRICTED_ADMIN)
        # nosemgrep: tailtag.django.dynamic-raw-sql
        conn.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN CREATEROLE CREATEDB PASSWORD 'sim-admin-pw'"
            ).format(sql.Identifier(RESTRICTED_ADMIN))
        )
        run_ddl(
            conn, "GRANT pg_signal_backend TO {} WITH ADMIN OPTION", RESTRICTED_ADMIN
        )
        # nosemgrep: tailtag.django.dynamic-raw-sql
        conn.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(database), sql.Identifier(RESTRICTED_ADMIN)
            )
        )
    parts = urlsplit(url_for_database(scratch_admin_url, database))
    host = f"{parts.hostname}:{parts.port}" if parts.port else str(parts.hostname)
    url = urlunsplit(parts._replace(netloc=f"{RESTRICTED_ADMIN}:sim-admin-pw@{host}"))
    try:
        yield url
    finally:
        with psycopg.connect(scratch_admin_url, autocommit=True) as conn:
            run_ddl(conn, "DROP DATABASE IF EXISTS {} WITH (FORCE)", database)
            drop_roles(scratch_admin_url)
            run_ddl(conn, "DROP ROLE IF EXISTS {}", RESTRICTED_ADMIN)


def test_reruns_after_ownership_moved_work_for_a_non_superuser_admin(
    roles_module: ModuleType, restricted_admin_url: str
) -> None:
    """AC15: Neon's admin is not a superuser, so reruns must not need schema ownership."""
    first = run_provision(roles_module, restricted_admin_url)
    second = run_provision(roles_module, restricted_admin_url)
    rotated = run_provision(roles_module, restricted_admin_url, rotate=True)

    assert second == {}
    assert sorted(rotated) == sorted(SECRET_IDS)
    with psycopg.connect(rotated["migrator-database-url"], autocommit=True) as migrator:
        migrator.execute("CREATE TABLE cogs (id serial PRIMARY KEY, name text)")
    with psycopg.connect(rotated["runtime-database-url"], autocommit=True) as runtime:
        runtime.execute("INSERT INTO cogs (name) VALUES ('a')")
    with psycopg.connect(rotated["maintainer-database-url"], autocommit=True) as conn:
        assert conn.execute("SELECT count(*) FROM cogs").fetchone() == (1,)
        owner = conn.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database "
            "WHERE datname = current_database()"
        ).fetchone()
        assert owner == ("maintainer",)
    # A plain rerun once migrator-owned tables exist (migrator password unknown)
    # must still raise nothing and write nothing.
    assert run_provision(roles_module, restricted_admin_url) == {}
    with psycopg.connect(rotated["runtime-database-url"], autocommit=True) as runtime:
        runtime.execute("INSERT INTO cogs (name) VALUES ('b')")
    assert sorted(first) == sorted(SECRET_IDS)


def state_snapshot(admin_url: str) -> list[Any]:
    """Everything the probe could plausibly change: roles, memberships, owner, ACLs."""
    queries: tuple[LiteralString, ...] = (
        (
            "SELECT rolname, rolsuper, rolcanlogin, rolpassword FROM pg_authid "
            "WHERE rolname IN ('migrator', 'runtime', 'maintainer') ORDER BY 1"
        ),
        (
            "SELECT roleid::regrole::text, member::regrole::text FROM pg_auth_members "
            "WHERE member IN ('migrator'::regrole, 'runtime'::regrole, "
            "'maintainer'::regrole) ORDER BY 1, 2"
        ),
        (
            "SELECT pg_get_userbyid(datdba), datacl::text FROM pg_database "
            "WHERE datname = current_database()"
        ),
        "SELECT nspacl::text FROM pg_namespace WHERE nspname = 'public'",
        "SELECT defaclrole::regrole::text, defaclacl::text FROM pg_default_acl ORDER BY 1",
    )
    with psycopg.connect(admin_url, autocommit=True) as conn:
        return [conn.execute(query).fetchall() for query in queries]


def test_probe_reports_three_facts_read_only_and_without_secrets(
    roles_module: ModuleType,
    clean_roles: str,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """AC15: the probe passes on a healthy maintainer, prints no secret, changes nothing."""
    urls = run_provision(roles_module, clean_roles)
    maintainer_url = urls["maintainer-database-url"]
    capfd.readouterr()
    before = state_snapshot(clean_roles)

    roles_module.probe_maintainer(maintainer_url, enforce_tls=False)

    assert state_snapshot(clean_roles) == before
    captured = capfd.readouterr()
    output = captured.out + captured.err
    assert all(fact in captured.out for fact in PROBE_FACTS)
    assert password_of(maintainer_url) not in output
    assert "postgresql://" not in output


@pytest.mark.parametrize(
    ("fact", "break_it"),
    [
        ("pg_signal_backend", "REVOKE pg_signal_backend FROM maintainer"),
        ("database_owner", "ALTER DATABASE {db} OWNER TO CURRENT_USER"),
        (
            "pg_control_system",
            "REVOKE EXECUTE ON FUNCTION pg_control_system() FROM PUBLIC",
        ),
    ],
)
def test_probe_fails_naming_each_missing_capability(
    roles_module: ModuleType,
    clean_roles: str,
    capfd: pytest.CaptureFixture[str],
    fact: str,
    break_it: str,
) -> None:
    """AC15: a missing capability must fail loudly and name which one is missing."""
    urls = run_provision(roles_module, clean_roles)
    maintainer_url = urls["maintainer-database-url"]
    with psycopg.connect(clean_roles, autocommit=True) as admin:
        database = admin.execute("SELECT current_database()").fetchone()
        assert database is not None
        statement = sql.SQL(cast(LiteralString, break_it)).format(  # type: ignore[arg-type]
            db=sql.Identifier(database[0])
        )
        admin.execute(statement)
    try:
        capfd.readouterr()
        with pytest.raises(roles_module.RoleProvisioningError) as failure:
            roles_module.probe_maintainer(maintainer_url, enforce_tls=False)
    finally:
        if fact == "pg_control_system":
            with psycopg.connect(clean_roles, autocommit=True) as admin:
                admin.execute("GRANT EXECUTE ON FUNCTION pg_control_system() TO PUBLIC")

    assert fact in str(failure.value)
    assert password_of(maintainer_url) not in str(failure.value)
    captured = capfd.readouterr()
    assert password_of(maintainer_url) not in captured.out + captured.err


def test_probe_flag_reads_the_secret_and_changes_nothing(
    roles_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """AC15: --probe alone reads Secret Manager, never terraform or a secret write."""
    secret_url = "postgresql://maintainer:pr0be-s3cret@127.0.0.1:1/tailtag"
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, secret_url, "")

    def fake_which(name: str) -> str:
        return f"/fake/{name}"

    monkeypatch.setattr(roles_module.shutil, "which", fake_which)
    monkeypatch.setattr(roles_module.subprocess, "run", fake_run)

    status = roles_module.main(["--project", "fake-replica-project", "--probe"])

    assert status == 1  # the fake endpoint is unreachable, so the probe fails
    flat = [" ".join(command) for command in commands]
    assert any("maintainer-database-url" in line for line in flat)
    assert not any("terraform" in line for line in flat)
    assert not any("versions add" in line for line in flat)
    captured = capfd.readouterr()
    assert "pr0be-s3cret" not in captured.out + captured.err
    assert "postgresql://" not in captured.out + captured.err


@pytest.mark.parametrize(
    "admin_url",
    (
        pytest.param(None, id="unset"),
        pytest.param(
            "postgresql://maintainer:not-the-admin@ep-example.neon.test/tailtag",
            id="application-role",
        ),
        pytest.param("https://ep-example.neon.test/tailtag", id="not-postgres"),
    ),
)
def test_admin_url_comes_only_from_the_environment_and_names_the_admin(
    roles_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    admin_url: str | None,
) -> None:
    """AC15: the admin URL is never read from Terraform, where the database owner
    now reports as maintainer, and a missing or wrong URL stops before any change."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, "", "")

    def fake_which(name: str) -> str:
        return f"/fake/{name}"

    monkeypatch.setattr(roles_module.shutil, "which", fake_which)
    monkeypatch.setattr(roles_module.subprocess, "run", fake_run)
    if admin_url is None:
        monkeypatch.delenv("NEON_ADMIN_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("NEON_ADMIN_DATABASE_URL", admin_url)

    status = roles_module.main(["--project", "fake-replica-project"])

    assert status == 1
    assert commands == []
    captured = capfd.readouterr()
    assert "NEON_ADMIN_DATABASE_URL" in captured.err
    assert "not-the-admin" not in captured.out + captured.err
    assert "ep-example" not in captured.out + captured.err


LIMIT_ROLES = ("runtime", "migrator", "maintainer")
LIMIT_CHECKS = (
    "create_table",
    "alter_table",
    "drop_table",
    "truncate_table",
    "create_role",
    "grant_option",
    "rolsuper",
    "rolcreaterole",
    "rolcreatedb",
    "rolbypassrls",
    "pg_signal_backend",
)


def provision_with_target(roles_module: ModuleType, admin_url: str) -> dict[str, str]:
    """Provision the roles and let migrator build the table the probe aims at."""
    urls = run_provision(roles_module, admin_url)
    with psycopg.connect(urls["migrator-database-url"], autocommit=True) as migrator:
        migrator.execute("CREATE TABLE sprockets (id serial PRIMARY KEY, name text)")
        migrator.execute("INSERT INTO sprockets (name) VALUES ('kept')")
    return {role: urls[f"{role}-database-url"] for role in LIMIT_ROLES}


def test_limits_probe_matches_the_approved_grant_set_and_changes_nothing(
    roles_module: ModuleType,
    clean_roles: str,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """AC13: every role sits exactly on its grant set, and every attempt rolls back."""
    role_urls = provision_with_target(roles_module, clean_roles)
    capfd.readouterr()
    before = state_snapshot(clean_roles)

    roles_module.probe_limits(
        role_urls, admin_url=clean_roles, table="sprockets", enforce_tls=False
    )

    assert state_snapshot(clean_roles) == before
    with psycopg.connect(clean_roles, autocommit=True) as admin:
        columns = admin.execute(
            "SELECT attname FROM pg_attribute WHERE attrelid = 'sprockets'::regclass "
            "AND attnum > 0 AND NOT attisdropped ORDER BY attnum"
        ).fetchall()
        rows = admin.execute("SELECT name FROM sprockets").fetchall()
        probe_tables = admin.execute(
            "SELECT count(*) FROM pg_class WHERE relname LIKE 'tt\\_limits\\_%'"
        ).fetchone()
    assert columns == [("id",), ("name",)]
    assert rows == [("kept",)]
    assert probe_tables == (0,)

    captured = capfd.readouterr()
    output = captured.out + captured.err
    for role in LIMIT_ROLES:
        for check in LIMIT_CHECKS:
            assert f"limits {role} {check}: ok" in captured.out
    assert "FAILED" not in output
    assert "limits admin" in captured.out
    for url in role_urls.values():
        assert password_of(url) not in output
    assert "postgresql://" not in output


@pytest.mark.parametrize(
    ("drift", "failed_cell"),
    (
        pytest.param(
            "GRANT TRUNCATE ON sprockets TO runtime",
            "runtime truncate_table",
            id="runtime-gains-truncate",
        ),
        pytest.param(
            "ALTER ROLE maintainer CREATEROLE",
            "maintainer rolcreaterole",
            id="maintainer-gains-createrole",
        ),
        pytest.param(
            "REVOKE pg_signal_backend FROM maintainer",
            "maintainer pg_signal_backend",
            id="maintainer-loses-signal",
        ),
    ),
)
def test_limits_probe_names_each_cell_off_the_grant_set(
    roles_module: ModuleType,
    clean_roles: str,
    capfd: pytest.CaptureFixture[str],
    drift: LiteralString,
    failed_cell: str,
) -> None:
    """AC13: an extra or a missing privilege fails the probe and names the cell."""
    role_urls = provision_with_target(roles_module, clean_roles)
    with psycopg.connect(clean_roles, autocommit=True) as admin:
        admin.execute(drift)
    capfd.readouterr()

    with pytest.raises(roles_module.RoleProvisioningError) as raised:
        roles_module.probe_limits(role_urls, table="sprockets", enforce_tls=False)

    assert failed_cell in str(raised.value)
    assert f"limits {failed_cell}: FAILED" in capfd.readouterr().out


def test_limits_flag_reads_the_three_role_secrets_and_writes_nothing(
    roles_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """AC13: --limits reads only the role URLs from Secret Manager and prints none."""
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        role = next(name for name in LIMIT_ROLES if f"{name}-database-url" in command)
        url = f"postgresql://{role}:l1mit-{role}-s3cret@127.0.0.1:1/tailtag"
        return subprocess.CompletedProcess(command, 0, url, "")

    def fake_which(name: str) -> str:
        return f"/fake/{name}"

    monkeypatch.setattr(roles_module.shutil, "which", fake_which)
    monkeypatch.setattr(roles_module.subprocess, "run", fake_run)
    monkeypatch.delenv("NEON_ADMIN_DATABASE_URL", raising=False)

    status = roles_module.main(["--project", "fake-replica-project", "--limits"])

    assert status == 1  # the fake endpoint is unreachable, so the probe fails
    flat = [" ".join(command) for command in commands]
    assert all(
        any(f"{role}-database-url" in line for line in flat) for role in LIMIT_ROLES
    )
    assert not any("versions add" in line for line in flat)
    captured = capfd.readouterr()
    assert "s3cret" not in captured.out + captured.err
    assert "postgresql://" not in captured.out + captured.err
