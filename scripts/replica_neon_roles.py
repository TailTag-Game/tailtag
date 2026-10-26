"""Create the TailTag hybrid replica database roles on Neon (#354, #355).

Terraform owns the Neon project and its admin role. This script owns the three
application roles and their privileges, because the Neon provider cannot grant
schema privileges:

* `migrator` can build and change the schema.
* `runtime` can only read and write rows.
* `maintainer` runs the reset job. It owns the database, belongs to
  `pg_signal_backend`, and inherits `runtime` rows access. It is never a
  superuser and never joins `neon_superuser`.

Run it with `task replica-neon-roles -- --project <gcp-project-id>`. It reads the
`tailtag_admin` URL from the `NEON_ADMIN_DATABASE_URL` environment variable and
writes each new role URL straight to Secret Manager. Terraform output cannot
supply that URL: the Neon provider reports the database owner, which is
`maintainer`, as the branch role. After it creates or rotates `maintainer`, a read-only probe connects as
that role and reports three facts by name. Run only the probe with `--probe`,
which reads the maintainer URL from Secret Manager. `--limits` reads every role
URL from Secret Manager and checks each role against its approved grant set
(#357); every attempted change rolls back. A password or URL is never
printed, logged, or written to disk, and error messages never include one.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

import certifi
import psycopg
from psycopg import sql

MIGRATOR = "migrator"
RUNTIME = "runtime"
MAINTAINER = "maintainer"
ROLES = (MIGRATOR, RUNTIME, MAINTAINER)
SECRET_IDS = {
    MIGRATOR: "migrator-database-url",
    RUNTIME: "runtime-database-url",
    MAINTAINER: "maintainer-database-url",
}
ADMIN_URL_VARIABLE = "NEON_ADMIN_DATABASE_URL"
# The approved grant set of each role (#357 AC13). `--limits` attempts each
# operation inside a transaction that always rolls back, and reads each fact
# from the catalog. A cell is ok when the role can do exactly what is listed.
LIMIT_OPERATIONS: tuple[tuple[str, str], ...] = (
    ("create_table", "CREATE TABLE tt_limits_probe (id integer)"),
    ("alter_table", "ALTER TABLE {table} ADD COLUMN tt_limits_probe integer"),
    ("drop_table", "DROP TABLE {table}"),
    ("truncate_table", "TRUNCATE {table}"),
    ("create_role", "CREATE ROLE tt_limits_probe NOLOGIN"),
)
LIMIT_FACTS: tuple[tuple[str, str], ...] = (
    # GRANT by a non-owner only warns, so the grant option is read instead.
    ("grant_option", "SELECT has_table_privilege({table}, 'SELECT WITH GRANT OPTION')"),
    ("rolsuper", "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"),
    (
        "rolcreaterole",
        "SELECT rolcreaterole FROM pg_roles WHERE rolname = current_user",
    ),
    ("rolcreatedb", "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user"),
    ("rolbypassrls", "SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user"),
    (
        "pg_signal_backend",
        "SELECT pg_has_role(current_user, 'pg_signal_backend', 'MEMBER')",
    ),
)
APPROVED_LIMITS: dict[str, frozenset[str]] = {
    RUNTIME: frozenset(),
    MIGRATOR: frozenset(
        {"create_table", "alter_table", "drop_table", "truncate_table", "grant_option"}
    ),
    # Owning the database makes maintainer own `public`, so it can create
    # tables and drop any table there. Reset needs the ownership.
    MAINTAINER: frozenset({"create_table", "drop_table", "pg_signal_backend"}),
}
_ADMIN_REPORT_FACTS = ("rolsuper", "rolcreaterole", "rolcreatedb", "rolbypassrls")
_LIMITS_TABLE = "django_migrations"
_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_COMMAND_TIMEOUT_SECONDS = 120
_DEFAULT_PORT = 5432


class RoleProvisioningError(Exception):
    """A failure whose message is safe to print: it never holds a URL or password."""


def role_url(
    admin_url: str, role: str, password: str, *, enforce_tls: bool = True
) -> str:
    """Return the admin URL with its credentials replaced by the role's.

    The host, port, and database stay the same. The port is always explicit,
    5432 when the admin URL omits it, because replica reset compares a numeric
    port. With `enforce_tls`, the query always asks for a fully verified
    connection, even if the admin URL does not.
    """
    parts = urlsplit(admin_url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = f":{parts.port or _DEFAULT_PORT}"
    netloc = f"{quote(role, safe='')}:{quote(password, safe='')}@{host}{port}"
    query = parts.query
    if enforce_tls:
        pairs = [
            (name, value)
            for name, value in parse_qsl(parts.query, keep_blank_values=True)
            if name not in {"sslmode", "sslrootcert"}
        ]
        pairs += [("sslmode", "verify-full"), ("sslrootcert", "system")]
        query = urlencode(pairs)
    return urlunsplit(parts._replace(netloc=netloc, query=query))


def provision_roles(
    admin_url: str,
    *,
    write_secret: Callable[[str, str], None],
    rotate: bool = False,
    enforce_tls: bool = True,
) -> None:
    """Create or update the roles and hand each fresh role URL to `write_secret`.

    A role that already exists keeps its password unless `rotate` is true, and no
    secret is written for it. When `maintainer` gets a new password, the probe
    runs after its secret is stored. The function is safe to run again.
    """
    passwords: dict[str, str] = {}
    try:
        with _connect(admin_url, enforce_tls=enforce_tls) as admin:
            _create_roles(admin, passwords, rotate)
            _grant_maintainer_memberships(admin)
            # The schema grants and the ownership move run once. After the move,
            # `public` belongs to maintainer (pg_database_owner), and the admin
            # reaches it only through its maintainer membership.
            if _database_owner(admin) != MAINTAINER:
                _grant_schema_access(admin)
                _transfer_database_ownership(admin)
            if MIGRATOR in passwords:
                migrator_url = role_url(
                    admin_url, MIGRATOR, passwords[MIGRATOR], enforce_tls=enforce_tls
                )
                with _connect(migrator_url, enforce_tls=enforce_tls) as migrator:
                    _grant_runtime_data_access(migrator, default_privileges=True)
            else:
                print(
                    "notice: the migrator password is not known in this run, so "
                    "default privileges were left as they are; use --rotate to "
                    "reapply them.",
                    file=sys.stderr,
                )
                _grant_runtime_data_access(admin, default_privileges=False)
    except psycopg.Error as error:
        raise RoleProvisioningError(
            f"database step failed ({type(error).__name__}, "
            f"SQLSTATE {error.sqlstate or 'unknown'}); run again with --rotate "
            "if a role was created but its secret was not stored"
        ) from None

    for role in ROLES:
        if role in passwords:
            write_secret(
                SECRET_IDS[role],
                role_url(admin_url, role, passwords[role], enforce_tls=enforce_tls),
            )

    if MAINTAINER in passwords:
        probe_maintainer(
            role_url(
                admin_url, MAINTAINER, passwords[MAINTAINER], enforce_tls=enforce_tls
            ),
            enforce_tls=enforce_tls,
        )


def probe_maintainer(maintainer_url: str, *, enforce_tls: bool = True) -> None:
    """Check read-only that `maintainer` can do its reset work, or raise.

    Each fact prints one line with a fixed word, never a value. All facts run
    before the function raises, so the error names every fact that failed.
    """
    checks: tuple[tuple[str, str], ...] = (
        ("pg_control_system", "SELECT count(*) FROM pg_control_system()"),
        (
            "database_owner",
            (
                "SELECT pg_get_userbyid(datdba) = current_user FROM pg_database "
                "WHERE datname = current_database()"
            ),
        ),
        (
            "pg_signal_backend",
            "SELECT pg_has_role(current_user, 'pg_signal_backend', 'USAGE')",
        ),
    )
    failed: list[str] = []
    try:
        with _connect(maintainer_url, enforce_tls=enforce_tls) as connection:
            for fact, query in checks:
                try:
                    row = connection.execute(sql.SQL(query)).fetchone()  # type: ignore[arg-type]
                    passed = row is not None and bool(row[0])
                except psycopg.Error:
                    passed = False
                print(f"probe {fact}: {'ok' if passed else 'FAILED'}")
                if not passed:
                    failed.append(fact)
    except psycopg.Error as error:
        raise RoleProvisioningError(
            f"the maintainer probe could not connect ({type(error).__name__}, "
            f"SQLSTATE {error.sqlstate or 'unknown'})"
        ) from None
    if failed:
        raise RoleProvisioningError(
            f"the maintainer probe failed these facts: {', '.join(failed)}"
        )


def probe_limits(
    role_urls: Mapping[str, str],
    *,
    admin_url: str | None = None,
    table: str = _LIMITS_TABLE,
    enforce_tls: bool = True,
) -> None:
    """Check each role against its approved grant set, or raise naming every off cell.

    Every attempt runs in a savepoint that always rolls back, inside a
    transaction that also rolls back, so nothing persists. The admin role is
    reported only: it is the owner's break-glass role and has no grant set here.
    """
    failed: list[str] = []
    for role in ROLES:
        approved = APPROVED_LIMITS[role]
        try:
            with _connect(role_urls[role], enforce_tls=enforce_tls) as connection:
                observed = _observe_limits(connection, table)
        except psycopg.Error as error:
            raise RoleProvisioningError(
                f"the limits probe could not finish as {role} "
                f"({type(error).__name__}, SQLSTATE {error.sqlstate or 'unknown'})"
            ) from None
        for check, allowed in observed:
            cell = f"{role} {check}"
            expected = check in approved
            if allowed is expected:
                print(f"limits {cell}: ok")
                continue
            if allowed is None:
                print(f"limits {cell}: FAILED (error)")
            else:
                found = "allowed" if allowed else "denied"
                wanted = "allowed" if expected else "denied"
                print(f"limits {cell}: FAILED ({found}, expected {wanted})")
            failed.append(cell)
    if admin_url is not None:
        _report_admin(admin_url, enforce_tls=enforce_tls)
    if failed:
        raise RoleProvisioningError(
            f"the limits probe found cells off the grant set: {', '.join(failed)}"
        )


def _observe_limits(
    connection: psycopg.Connection, table: str
) -> list[tuple[str, bool | None]]:
    """Return each check as allowed, denied, or None for any other error."""
    observed: list[tuple[str, bool | None]] = []
    with connection.transaction(force_rollback=True):
        connection.execute("SET LOCAL lock_timeout = '2s'")
        connection.execute("SET LOCAL statement_timeout = '5s'")
        for check, template in LIMIT_OPERATIONS:
            # The template is a constant above; the table is a quoted identifier.
            statement = sql.SQL(template).format(table=sql.Identifier(table))  # type: ignore[arg-type]
            try:
                with connection.transaction(force_rollback=True):
                    # nosemgrep: tailtag.django.dynamic-raw-sql
                    connection.execute(statement)
                observed.append((check, True))
            except psycopg.errors.InsufficientPrivilege:
                observed.append((check, False))
            except psycopg.Error:
                observed.append((check, None))
        for check, template in LIMIT_FACTS:
            query = sql.SQL(template).format(table=sql.Literal(table))  # type: ignore[arg-type]
            try:
                with connection.transaction(force_rollback=True):
                    # nosemgrep: tailtag.django.dynamic-raw-sql
                    row = connection.execute(query).fetchone()
                observed.append((check, None if row is None else bool(row[0])))
            except psycopg.Error:
                observed.append((check, None))
    return observed


def _report_admin(admin_url: str, *, enforce_tls: bool) -> None:
    """Print the admin role's attributes, with no verdict."""
    facts = dict(LIMIT_FACTS)
    try:
        with _connect(admin_url, enforce_tls=enforce_tls) as connection:
            for fact in _ADMIN_REPORT_FACTS:
                # nosemgrep: tailtag.django.dynamic-raw-sql
                row = connection.execute(sql.SQL(facts[fact])).fetchone()  # type: ignore[arg-type]
                value = "true" if row is not None and row[0] else "false"
                print(f"limits admin {fact}: {value} (report only)")
    except psycopg.Error as error:
        raise RoleProvisioningError(
            f"the limits probe could not report the admin role "
            f"({type(error).__name__}, SQLSTATE {error.sqlstate or 'unknown'})"
        ) from None


def _connect(url: str, *, enforce_tls: bool) -> psycopg.Connection:
    """Open an autocommit connection, verifying the server when `enforce_tls` is set.

    The OpenSSL inside the psycopg wheel has no usable default CA path on some
    hosts, so `sslrootcert=system` fails there. This script's own connections use
    the certifi CA bundle instead. The stored URLs keep `sslrootcert=system`.
    """
    if not enforce_tls:
        return psycopg.connect(url, autocommit=True)
    return psycopg.connect(
        url, autocommit=True, sslmode="verify-full", sslrootcert=certifi.where()
    )


def _create_roles(
    admin: psycopg.Connection, passwords: dict[str, str], rotate: bool
) -> None:
    existing = {
        name
        for (name,) in admin.execute(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", (list(ROLES),)
        ).fetchall()
    }
    for role in ROLES:
        if role in existing and not rotate:
            continue
        password = secrets.token_urlsafe(32)
        # Neon syncs roles to its control plane, which refuses pre-hashed
        # passwords, so the plain password goes over the verified TLS
        # connection and the server hashes it.
        # Only maintainer inherits, so it can use the runtime table grants.
        inherit = "INHERIT" if role == MAINTAINER else "NOINHERIT"
        if role in existing:
            statement = sql.SQL("ALTER ROLE {} PASSWORD {}")
        else:
            statement = sql.SQL(
                "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                + inherit
                + " PASSWORD {}"
            )
        admin.execute(statement.format(sql.Identifier(role), sql.Literal(password)))
        passwords[role] = password


def _grant_maintainer_memberships(admin: psycopg.Connection) -> None:
    """Put maintainer in `pg_signal_backend` and `runtime`; a repeat is a no-op."""
    for group in ("pg_signal_backend", RUNTIME):
        admin.execute(
            sql.SQL("GRANT {} TO {}").format(
                sql.Identifier(group), sql.Identifier(MAINTAINER)
            )
        )


def _database_owner(admin: psycopg.Connection) -> str:
    row = admin.execute(
        "SELECT pg_get_userbyid(datdba) FROM pg_database "
        "WHERE datname = current_database()"
    ).fetchone()
    assert row is not None
    return str(row[0])


def _transfer_database_ownership(admin: psycopg.Connection) -> None:
    """Make maintainer own the database.

    Neon's admin is not a superuser, so the transfer needs the admin to hold
    maintainer membership with SET first. `ALTER DATABASE ... OWNER` also needs
    CREATEDB, which Neon's admin role has.
    """
    database = admin.execute("SELECT current_database()").fetchone()
    assert database is not None
    maintainer = sql.Identifier(MAINTAINER)
    admin.execute(sql.SQL("GRANT {} TO CURRENT_USER WITH SET TRUE").format(maintainer))
    admin.execute(
        sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
            sql.Identifier(database[0]), maintainer
        )
    )


def _grant_schema_access(admin: psycopg.Connection) -> None:
    database = admin.execute("SELECT current_database()").fetchone()
    assert database is not None
    admin.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    for role in ROLES:
        admin.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database[0]), sql.Identifier(role)
            )
        )
    admin.execute(
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
            sql.Identifier(MIGRATOR)
        )
    )
    admin.execute(
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(RUNTIME))
    )


def _grant_runtime_data_access(
    connection: psycopg.Connection, *, default_privileges: bool
) -> None:
    """Give `runtime` row access to existing and, when allowed, future objects.

    The statements are built with `psycopg.sql` identifiers, so the dynamic-SQL
    Semgrep rule is waived on each call.
    """
    runtime = sql.Identifier(RUNTIME)
    if default_privileges:
        # Run as migrator, so the defaults cover the tables migrator creates.
        # nosemgrep: tailtag.django.dynamic-raw-sql
        connection.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
            ).format(runtime)
        )
        # nosemgrep: tailtag.django.dynamic-raw-sql
        connection.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT USAGE, SELECT ON SEQUENCES TO {}"
            ).format(runtime)
        )
    # nosemgrep: tailtag.django.dynamic-raw-sql
    connection.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
        ).format(runtime)
    )
    # nosemgrep: tailtag.django.dynamic-raw-sql
    connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
            runtime
        )
    )


def _read_admin_url(environ: Mapping[str, str]) -> str:
    """Return the admin URL from the environment, refusing an application role."""
    admin_url = environ.get(ADMIN_URL_VARIABLE, "").strip()
    try:
        parts = urlsplit(admin_url)
        user = unquote(parts.username or "")
        valid = (
            parts.scheme in {"postgres", "postgresql"}
            and bool(parts.hostname)
            and bool(parts.password)
            and bool(user)
            and user not in ROLES
        )
    except ValueError:
        valid = False
    if not valid:
        raise RoleProvisioningError(
            f"{ADMIN_URL_VARIABLE} must hold the Neon admin role's postgresql URL; "
            "copy the tailtag_admin connection string from the Neon console and "
            f"enter it with: read -rs {ADMIN_URL_VARIABLE} && export {ADMIN_URL_VARIABLE}"
        )
    return admin_url


def _secret_writer(project: str) -> Callable[[str, str], None]:
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise RoleProvisioningError(
            "gcloud is not on PATH; install the Google Cloud CLI and sign in"
        )

    def write_secret(secret_id: str, value: str) -> None:
        result = subprocess.run(
            [
                gcloud,
                "secrets",
                "versions",
                "add",
                secret_id,
                "--project",
                project,
                "--data-file=-",
            ],
            input=value,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise RoleProvisioningError(
                f"gcloud could not store secret {secret_id} (exit {result.returncode}); "
                "run again with --rotate to issue a new password"
            )
        print(f"stored a new version of secret {secret_id}")

    return write_secret


def _read_role_url(project: str, role: str) -> str:
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise RoleProvisioningError(
            "gcloud is not on PATH; install the Google Cloud CLI and sign in"
        )
    secret_id = SECRET_IDS[role]
    result = subprocess.run(
        [
            gcloud,
            "secrets",
            "versions",
            "access",
            "latest",
            "--secret",
            secret_id,
            "--project",
            project,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=_COMMAND_TIMEOUT_SECONDS,
    )
    url = result.stdout.strip()
    if result.returncode != 0 or not url:
        raise RoleProvisioningError(
            f"gcloud could not read secret {secret_id} (exit {result.returncode}); "
            "run the role script without --probe or --limits first"
        )
    return url


def main(argv: Sequence[str] | None = None) -> int:
    """Run the role setup and return the process exit status."""
    parser = argparse.ArgumentParser(
        prog="replica_neon_roles",
        description=(
            "Create the replica migrator, runtime, and maintainer roles on Neon, "
            "probe the maintainer role with --probe, or check every role against "
            "its approved grant set with --limits."
        ),
    )
    parser.add_argument(
        "--project", required=True, help="Google Cloud project id for Secret Manager"
    )
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="issue new passwords for roles that already exist",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help=(
            "only run the read-only maintainer probe, with the URL read from "
            "Secret Manager; nothing is changed"
        ),
    )
    parser.add_argument(
        "--limits",
        action="store_true",
        help=(
            "only check each role against its approved grant set, with the URLs "
            "read from Secret Manager; every attempt rolls back"
        ),
    )
    arguments = parser.parse_args(argv)
    if not _PROJECT_ID.fullmatch(arguments.project):
        print("error: --project is not a valid project id", file=sys.stderr)
        return 2

    if arguments.limits:
        try:
            role_urls = {
                role: _read_role_url(arguments.project, role) for role in ROLES
            }
            admin_url = (
                _read_admin_url(os.environ)
                if os.environ.get(ADMIN_URL_VARIABLE)
                else None
            )
            probe_limits(role_urls, admin_url=admin_url)
        except RoleProvisioningError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        except subprocess.TimeoutExpired:
            print("error: a command timed out", file=sys.stderr)
            return 1
        print("every role matches its approved grant set")
        return 0

    if arguments.probe:
        try:
            probe_maintainer(_read_role_url(arguments.project, MAINTAINER))
        except RoleProvisioningError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        except subprocess.TimeoutExpired:
            print("error: a command timed out", file=sys.stderr)
            return 1
        print("the maintainer probe passed")
        return 0

    try:
        admin_url = _read_admin_url(os.environ)
        write_secret = _secret_writer(arguments.project)
        provision_roles(
            admin_url,
            write_secret=write_secret,
            rotate=arguments.rotate,
            enforce_tls=True,
        )
    except RoleProvisioningError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("error: a command timed out", file=sys.stderr)
        return 1
    print("replica Neon roles are ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
