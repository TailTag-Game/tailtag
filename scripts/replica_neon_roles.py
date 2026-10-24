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
admin URL from Terraform output and writes each new role URL straight to Secret
Manager. After it creates or rotates `maintainer`, a read-only probe connects as
that role and reports three facts by name. Run only the probe with `--probe`,
which reads the maintainer URL from Secret Manager. A password or URL is never
printed, logged, or written to disk, and error messages never include one.
"""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

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
ADMIN_OUTPUT = "neon_admin_connection_uri"
DEFAULT_TERRAFORM_DIR = "infra/replica/foundation"
_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_COMMAND_TIMEOUT_SECONDS = 120


class RoleProvisioningError(Exception):
    """A failure whose message is safe to print: it never holds a URL or password."""


def role_url(
    admin_url: str, role: str, password: str, *, enforce_tls: bool = True
) -> str:
    """Return the admin URL with its credentials replaced by the role's.

    The host, port, and database stay the same. With `enforce_tls`, the query
    always asks for a fully verified connection, even if the admin URL does not.
    """
    parts = urlsplit(admin_url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port is not None else ""
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


def _read_admin_url(terraform_dir: str) -> str:
    terraform = shutil.which("terraform")
    if terraform is None:
        raise RoleProvisioningError(
            "terraform is not on PATH; install Terraform 1.17 and try again"
        )
    result = subprocess.run(
        [terraform, f"-chdir={terraform_dir}", "output", "-raw", ADMIN_OUTPUT],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=_COMMAND_TIMEOUT_SECONDS,
    )
    admin_url = result.stdout.strip()
    if result.returncode != 0 or not admin_url:
        raise RoleProvisioningError(
            f"terraform output {ADMIN_OUTPUT} failed (exit {result.returncode}); "
            f"apply {terraform_dir} first and check your Terraform credentials"
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


def _read_maintainer_url(project: str) -> str:
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise RoleProvisioningError(
            "gcloud is not on PATH; install the Google Cloud CLI and sign in"
        )
    secret_id = SECRET_IDS[MAINTAINER]
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
            "run the role script without --probe first"
        )
    return url


def main(argv: Sequence[str] | None = None) -> int:
    """Run the role setup and return the process exit status."""
    parser = argparse.ArgumentParser(
        prog="replica_neon_roles",
        description=(
            "Create the replica migrator, runtime, and maintainer roles on Neon, "
            "or probe the maintainer role with --probe."
        ),
    )
    parser.add_argument(
        "--project", required=True, help="Google Cloud project id for Secret Manager"
    )
    parser.add_argument(
        "--terraform-dir",
        default=DEFAULT_TERRAFORM_DIR,
        help="Terraform root that outputs the Neon admin URL",
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
    arguments = parser.parse_args(argv)
    if not _PROJECT_ID.fullmatch(arguments.project):
        print("error: --project is not a valid project id", file=sys.stderr)
        return 2

    if arguments.probe:
        try:
            probe_maintainer(_read_maintainer_url(arguments.project))
        except RoleProvisioningError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        except subprocess.TimeoutExpired:
            print("error: a command timed out", file=sys.stderr)
            return 1
        print("the maintainer probe passed")
        return 0

    try:
        write_secret = _secret_writer(arguments.project)
        admin_url = _read_admin_url(arguments.terraform_dir)
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
