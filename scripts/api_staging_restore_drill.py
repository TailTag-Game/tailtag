"""Guarded operator entry point for the TailTag #207 restore drill.

The command intentionally has no source, target, or environment arguments.
It can only restore the fixed canonical Staging source into a locally-created
Docker target after every positive guard has passed.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import os
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO, UnsupportedOperation
from pathlib import Path
from shutil import rmtree
from typing import Any, cast

CONFIRMATION = "restore-tailtag-staging-backup"
POSTGRES_IMAGE = "postgres:18"
TARGET_DATABASE = "tailtag_recovery"
ISSUE_LABEL = {"tailtag.issue": "207"}
_TUNNEL_LABELS = ("Host", "Port", "User", "Password", "Database", "URL")
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ID = "85324de4-be6a-49c3-a3f9-6cac13877849"
_ENVIRONMENT_ID = "5f4ab4f2-af14-4b2b-a4c3-3344d281fe5e"
_API_SERVICE_ID = "2247da27-97df-4d5d-b1dc-d21eeb7901d9"
_POSTGRES_SERVICE_ID = "3316216c-ecdd-474a-aebc-d9cab9986507"
_SCHEMA_MANIFEST_SOURCE_SHA = "856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a"
_APPROVED_RAILWAY_IDENTITY = (
    "Logged in as Finn the Panther (finn@finnthepanther.com) 👋"
)
_active_exact_source_root: Path | None = None
_active_exact_source_sha: str | None = None
_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "outcome",
        "mechanism",
        "selection_reason",
        "recovery_point_time",
        "source_sha",
        "source_deployment_fingerprint",
        "source_database_fingerprint",
        "source_postgres_major",
        "source_migration_leaves",
        "source_table_counts",
        "source_constraint_catalog_digest",
        "tool_versions",
        "target_class",
        "dump_started_at",
        "dump_completed_at",
        "restore_started_at",
        "restore_completed_at",
        "dump_duration_seconds",
        "restore_duration_seconds",
        "checks",
        "backend_usability",
        "staging_nonimpact",
        "cleanup_verified",
        "failure_stage",
        "limitations",
        "follow_up",
    }
)
_EVIDENCE_STAGES = frozenset(
    {
        "PREFLIGHT",
        "TUNNEL",
        "SNAPSHOT",
        "DUMP",
        "TARGET",
        "RESTORE",
        "INTEGRITY",
        "BACKEND",
        "NONIMPACT",
        "CLEANUP",
    }
)
_EVIDENCE_CHECK_NAMES = frozenset(
    {
        "dump_archive",
        "restore",
        "target_guard",
        "applied_migrations",
        "migration_leaves",
        "table_counts",
        "constraint_fingerprints",
        "profile_user_one_to_one",
        "fursuit_owner",
        "user_clerk_id_unique",
        "fursuit_tailtag_id_unique",
        "enrollment_relationships",
        "enrollment_unique",
        "enrollment_one_active",
        "activation_relationships",
        "activation_unique",
        "activation_state",
        "session_relationships",
        "session_state",
        "credential_relationships",
        "credential_unique",
        "credential_state",
        "catch_relationships",
        "catch_provenance",
        "catch_unique",
        "user_representative_read",
        "profile_representative_read",
        "fursuit_representative_read",
        "convention_representative_read",
        "enrollment_representative_read",
        "activation_representative_read",
        "session_representative_read",
        "credential_representative_read",
        "catch_representative_read",
    }
    | {
        f"{table}_constraints"
        for table in (
            "accounts_user",
            "profiles_playerprofile",
            "fursuits_fursuit",
            "conventions_convention",
            "conventions_conventionenrollment",
            "conventions_fursuitactivation",
            "conventions_fursuitcatchsession",
            "conventions_fursuitcatchcredential",
            "catches_catch",
        )
    }
)
_EVIDENCE_CODES = frozenset(
    {
        "EXACT_SHA_UNAVAILABLE",
        "BACKEND_IMAGE_UNAVAILABLE",
        "BACKEND_PROOF_UNAVAILABLE",
        "LOCAL_CAPACITY_UNAVAILABLE",
        "PLATFORM_LIMITATION",
        "NO_FOLLOW_UP_REQUIRED",
        "CLEANUP_UNVERIFIED",
    }
)
_REPRESENTATIVE_CHECKS = {
    "accounts_user": "user_representative_read",
    "profiles_playerprofile": "profile_representative_read",
    "fursuits_fursuit": "fursuit_representative_read",
    "conventions_convention": "convention_representative_read",
    "conventions_conventionenrollment": "enrollment_representative_read",
    "conventions_fursuitactivation": "activation_representative_read",
    "conventions_fursuitcatchsession": "session_representative_read",
    "conventions_fursuitcatchcredential": "credential_representative_read",
    "catches_catch": "catch_representative_read",
}


class DrillDenied(RuntimeError):
    """A fail-closed guard denied an unsafe or incomplete operation."""


class CleanupUnverified(DrillDenied):
    """A task-created resource may remain; expose only its local handle."""

    def __init__(self, handle: str) -> None:
        super().__init__("task resource cleanup could not be verified")
        self.handle = handle


@dataclass(frozen=True)
class TunnelDetails:
    host: str
    port: int
    user: str
    password: str
    database: str
    url: str


@dataclass
class SourceSnapshot:
    """The live read-only transaction that makes facts and dump one snapshot."""

    connection: Any
    snapshot: str

    def query(self, sql: str) -> list[dict[str, object]]:
        with self.connection.cursor() as cursor:
            cursor.execute(sql)
            columns = [column.name for column in cursor.description or ()]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

    def close(self) -> None:
        try:
            self.connection.rollback()
        finally:
            self.connection.close()


def verify_railway_identity() -> None:
    """Refuse any authenticated Railway action outside the approved identity."""
    result = _run("railway", "whoami")
    if result.stdout.strip() != _APPROVED_RAILWAY_IDENTITY:
        raise DrillDenied("Railway identity mismatch")


def open_railway_tunnel() -> tuple[Any, TunnelDetails]:
    """Open only the pinned Staging Postgres loopback tunnel.

    No connection detail is logged; process output exists only long enough to
    parse its complete labelled tunnel description in memory.
    """
    verify_railway_identity()
    tunnel = subprocess.Popen(
        (
            "railway",
            "connect",
            "Postgres",
            "--tunnel-only",
            "--project",
            _PROJECT_ID,
            "--environment",
            _ENVIRONMENT_ID,
        ),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if tunnel.stdout is None:
        cleanup_task_resources((tunnel,), ())
        raise DrillDenied("Railway tunnel stream unavailable")
    # Read bounded bytes so a partial line cannot block past the deadline.
    output = bytearray()
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([tunnel.stdout], [], [], 0.25)
            chunk = os.read(tunnel.stdout.fileno(), 1024) if ready else b""
            if chunk:
                output.extend(chunk)
                if len(output) > 4096:
                    raise DrillDenied("invalid tunnel details")
                try:
                    return tunnel, parse_tunnel_details(
                        output.decode("utf-8", errors="replace")
                    )
                except DrillDenied:
                    pass
            elif tunnel.poll() is not None:
                break
    except BaseException:  # Every tunnel parse failure must reap the process.
        if not cleanup_task_resources((tunnel,), ()):
            raise DrillDenied("Railway tunnel cleanup could not be verified") from None
        raise
    if not cleanup_task_resources((tunnel,), ()):
        raise DrillDenied("Railway tunnel cleanup could not be verified")
    raise DrillDenied("Railway tunnel unavailable")


def parse_tunnel_details(output: str) -> TunnelDetails:
    """Accept exactly one complete Railway loopback tunnel description.

    Railway text is untrusted process output.  It is parsed only into memory
    and no parsing failure includes that text in an error or evidence record.
    """
    values: dict[str, str] = {}
    pattern = re.compile(r"^(Host|Port|User|Password|Database|URL):[ \t]*(.+)$")
    for line in output.splitlines():
        match = pattern.fullmatch(line.strip())
        if match is None:
            continue
        key, value = match.groups()
        if key in values or not value.strip():
            raise DrillDenied("invalid tunnel details")
        values[key] = value.strip()
    if set(values) != set(_TUNNEL_LABELS):
        raise DrillDenied("incomplete tunnel details")
    if values["Host"] != "127.0.0.1":
        raise DrillDenied("tunnel is not loopback-only")
    try:
        port = int(values["Port"])
    except ValueError as error:
        raise DrillDenied("invalid tunnel port") from error
    if not 1 <= port <= 65535:
        raise DrillDenied("invalid tunnel port")
    return TunnelDetails(
        host=values["Host"],
        port=port,
        user=values["User"],
        password=values["Password"],
        database=values["Database"],
        url=values["URL"],
    )


def open_source_snapshot(details: TunnelDetails) -> SourceSnapshot:
    """Export a snapshot from a source connection that cannot issue writes."""
    try:
        psycopg = importlib.import_module("psycopg")
    except ImportError as error:  # pragma: no cover - environment gate.
        raise DrillDenied("PostgreSQL client library unavailable") from error
    connection: Any | None = None
    try:
        connection = cast(Any, psycopg).connect(
            host=details.host,
            port=details.port,
            user=details.user,
            password=details.password,
            dbname=details.database,
            options="-c default_transaction_read_only=on",
            autocommit=False,
        )
        active_connection = cast(Any, connection)
        with active_connection.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SHOW transaction_isolation")
            isolation_row = cursor.fetchone()
            if (
                not isinstance(isolation_row, tuple)
                or len(isolation_row) != 1
                or not isinstance(isolation_row[0], str)
                or isolation_row[0].strip().lower() != "repeatable read"
            ):
                raise DrillDenied("source snapshot isolation unavailable")
            cursor.execute("SELECT pg_export_snapshot()")
            row = cursor.fetchone()
        typed_row = cast(tuple[object, ...], row)
        if (
            not isinstance(row, tuple)
            or len(typed_row) != 1
            or not isinstance(typed_row[0], str)
        ):
            raise DrillDenied("source snapshot export unavailable")
        return SourceSnapshot(connection=active_connection, snapshot=typed_row[0])
    except Exception as error:
        if connection is not None:
            connection.close()
        if isinstance(error, DrillDenied):
            raise
        raise DrillDenied("source snapshot unavailable") from None


def dump_snapshot_to_target(
    details: TunnelDetails, snapshot: SourceSnapshot, container_id: str
) -> int:
    """Stream a custom archive to target tmpfs without a host dump artifact."""
    environment = {
        "PGPASSWORD": details.password,
        "PGOPTIONS": "-c default_transaction_read_only=on",
    }
    dump: subprocess.Popen[bytes] | None = None
    receiver: subprocess.Popen[bytes] | None = None
    transferred = 0
    try:
        dump = subprocess.Popen(
            (
                "pg_dump",
                "--host",
                details.host,
                "--port",
                str(details.port),
                "--username",
                details.user,
                "--dbname",
                details.database,
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--snapshot",
                snapshot.snapshot,
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, **environment},
            start_new_session=True,
        )
        receiver = subprocess.Popen(
            (
                "docker",
                "exec",
                "-i",
                container_id,
                "sh",
                "-c",
                "cat > /backup/recovery.dump",
            ),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if dump.stdout is None or receiver.stdin is None:
            raise DrillDenied("dump stream unavailable")
        deadline = time.monotonic() + 1800
        try:
            dump_fd = dump.stdout.fileno()
            receiver_fd = receiver.stdin.fileno()
            os.set_blocking(dump_fd, False)
            os.set_blocking(receiver_fd, False)
        except (AttributeError, OSError, UnsupportedOperation):
            raise DrillDenied("dump stream does not expose OS pipes") from None
        pending = bytearray()
        end_of_dump = False
        try:
            while not end_of_dump or pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DrillDenied("custom dump timed out")
                # Do not read another chunk until the receiver consumes the
                # current one; the host buffer is bounded to one chunk.
                readable = [dump_fd] if not end_of_dump and not pending else []
                writable = [receiver_fd] if pending else []
                readable, writable, _ = select.select(
                    readable, writable, [], min(1, remaining)
                )
                if dump_fd in readable:
                    try:
                        chunk = os.read(dump_fd, 1024 * 1024)
                    except BlockingIOError:
                        chunk = None
                    if chunk is None:
                        pass
                    elif chunk:
                        pending.extend(chunk)
                    else:
                        end_of_dump = True
                if receiver_fd in writable:
                    try:
                        written = os.write(receiver_fd, pending)
                    except BlockingIOError:
                        written = 0
                    if written < 0:
                        raise DrillDenied("custom dump stream failed")
                    if written:
                        del pending[:written]
                        transferred += written
        finally:
            os.set_blocking(dump_fd, True)
            os.set_blocking(receiver_fd, True)
        receiver.stdin.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DrillDenied("custom dump timed out")
        if (
            dump.wait(timeout=remaining) != 0
            or receiver.wait(timeout=max(1, deadline - time.monotonic())) != 0
            or transferred == 0
        ):
            raise DrillDenied("custom dump failed")
        return transferred
    except BaseException:
        if not cleanup_task_resources((dump, receiver), ()):
            raise DrillDenied("dump process cleanup could not be verified") from None
        raise


def validate_archive(container_id: str) -> None:
    """Prove the streamed custom archive is readable before restore begins."""
    _run(
        "docker", "exec", container_id, "pg_restore", "--list", "/backup/recovery.dump"
    )


def restore_archive(container_id: str) -> None:
    """Restore the already-validated archive into the fixed target database."""
    _run(
        "docker",
        "exec",
        container_id,
        "pg_restore",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-acl",
        "--username",
        "postgres",
        "--dbname",
        TARGET_DATABASE,
        "/backup/recovery.dump",
        timeout=900,
    )


def recovery_query_executor(container_id: str) -> Callable[[str], object]:
    """Return a fixed-target, read-only SQL executor with structured rows only."""
    if not re.fullmatch(r"[0-9a-f]{64}", container_id):
        raise DrillDenied("invalid recovery target identity")

    def execute(sql: str) -> object:
        try:
            result = _run(
                "docker",
                "exec",
                "-i",
                container_id,
                "psql",
                "--no-psqlrc",
                "--csv",
                "--quiet",
                "--set",
                "ON_ERROR_STOP=1",
                "--username",
                "postgres",
                "--dbname",
                TARGET_DATABASE,
                input=f"BEGIN READ ONLY; {sql}; ROLLBACK;",
                timeout=60,
            )
        except subprocess.SubprocessError:
            raise DrillDenied("recovery integrity query failed") from None
        rows: list[dict[str, object]] = []
        for row in csv.DictReader(StringIO(result.stdout)):
            rows.append(
                {
                    key: int(value)
                    if value is not None and re.fullmatch(r"-?[0-9]+", value)
                    else value
                    for key, value in row.items()
                    if key is not None
                }
            )
        return rows

    return execute


def backend_read_only_proof(image: str, recovery_container_id: str) -> str:
    """Run no-server Django ORM reads in a disposable sibling container."""
    if not re.fullmatch(r"[0-9a-f]{64}", recovery_container_id):
        raise DrillDenied("invalid recovery target identity")
    command = (
        "import django; django.setup(); "
        "from accounts.models import User; from profiles.models import PlayerProfile; "
        "from fursuits.models import Fursuit; from conventions.models import Convention, ConventionEnrollment, FursuitActivation, FursuitCatchSession, FursuitCatchCredential; "
        "from catches.models import Catch; "
        "models=(User, PlayerProfile, Fursuit, Convention, ConventionEnrollment, FursuitActivation, FursuitCatchSession, FursuitCatchCredential, Catch); "
        "assert all(not model.objects.exists() or model.objects.order_by('pk').first() is not None for model in models)"
    )
    name = f"tailtag-207-backend-{uuid.uuid4().hex}"
    _assert_container_name_available(name)
    try:
        started = _run(
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            "tailtag.issue=207",
            "--network",
            f"container:{recovery_container_id}",
            "--env",
            "DATABASE_URL=postgresql://postgres@127.0.0.1:5432/tailtag_recovery",
            "--env",
            "DJANGO_SECRET_KEY=tailtag-recovery-read-only-proof",
            "--env",
            "CLERK_AUTHENTICATION_ENABLED=false",
            "--env",
            "DJANGO_SETTINGS_MODULE=config.settings.local",
            "--env",
            "PGOPTIONS=-c default_transaction_read_only=on",
            image,
            "python",
            "-c",
            command,
        )
        container_id = started.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise DrillDenied("backend proof container identity unavailable")
    except BaseException:  # Docker may create a container before reporting failure.
        if not _cleanup_failed_container_start(name, image):
            raise CleanupUnverified(name) from None
        raise
    try:
        waited = _run("docker", "wait", container_id)
        if waited.stdout.strip() != "0":
            raise DrillDenied("backend read-only proof failed")
        return container_id
    finally:
        if not cleanup_task_resources((), (container_id,)):
            raise CleanupUnverified(container_id)


def validate_recovery_target(
    inspect: Mapping[str, Any], expected_id: str, image_id: str
) -> None:
    """Bind pg_restore to the exact freshly-created isolated Docker target."""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_id):
        raise DrillDenied("invalid recovery container identity")
    if inspect.get("Id") != expected_id or inspect.get("Image") != image_id:
        raise DrillDenied("recovery target identity changed")
    config = inspect.get("Config")
    host_config = inspect.get("HostConfig")
    mounts = inspect.get("Mounts")
    if (
        not isinstance(config, Mapping)
        or not isinstance(host_config, Mapping)
        or not isinstance(mounts, list)
    ):
        raise DrillDenied("recovery target inspection incomplete")
    typed_config = cast(Mapping[str, object], config)
    typed_host_config = cast(Mapping[str, object], host_config)
    typed_mounts = cast(list[object], mounts)
    if (
        typed_config.get("Image") != POSTGRES_IMAGE
        or typed_config.get("Labels") != ISSUE_LABEL
    ):
        raise DrillDenied("recovery target image or label mismatch")
    if typed_host_config.get("NetworkMode") != "none" or typed_host_config.get(
        "PortBindings"
    ) not in ({}, None):
        raise DrillDenied("recovery target is network reachable")
    tmpfs_destinations: set[str] = set()
    for mount in typed_mounts:
        if isinstance(mount, Mapping):
            typed_mount = cast(Mapping[str, object], mount)
            destination = typed_mount.get("Destination")
            if typed_mount.get("Type") == "tmpfs" and isinstance(destination, str):
                tmpfs_destinations.add(destination)
    if len(typed_mounts) != 2 or tmpfs_destinations != {
        "/var/lib/postgresql",
        "/backup",
    }:
        raise DrillDenied("recovery target storage is not disposable")


def cleanup_task_resources(
    processes: Iterable[Any],
    container_ids: Iterable[object],
    command_runner: Callable[..., object] | None = None,
) -> bool:
    """Terminate supplied processes and remove only captured full container IDs."""
    complete = True

    def run_cleanup_command(*command: str, **kwargs: Any) -> object:
        if command_runner is None:
            check = cast(bool, kwargs.pop("check", False))
            return cast(object, subprocess.run(command, check=check, **kwargs))
        return command_runner(command, **kwargs)

    for process in processes:
        try:
            if process is not None and process.poll() is None:
                pid = getattr(process, "pid", None)
                if isinstance(pid, int) and pid > 0:
                    os.killpg(pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=10)
        except Exception:  # noqa: BLE001 - cleanup must continue for every resource.
            complete = False
            if process is not None:
                try:
                    pid = getattr(process, "pid", None)
                    if isinstance(pid, int) and pid > 0:
                        os.killpg(pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    complete = False
    for container_id in container_ids:
        if not isinstance(container_id, str) or not re.fullmatch(
            r"[0-9a-f]{64}", container_id
        ):
            complete = False
            continue
        try:
            remove_options: dict[str, Any] = {
                "check": True,
                "capture_output": True,
                "text": True,
            }
            run_cleanup_command(
                "docker", "rm", "--force", container_id, **remove_options
            )
            inspection = run_cleanup_command(
                "docker",
                "container",
                "inspect",
                container_id,
                check=False,
                capture_output=True,
                text=True,
            )
            # Test seams may return a sentinel. A real subprocess result must
            # prove the full captured ID is no longer known to Docker.
            result_code = getattr(inspection, "returncode", None)
            if result_code is not None and result_code == 0:
                complete = False
        except Exception:  # noqa: BLE001
            complete = False
    return complete


def _run(*command: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("timeout", 300)
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        **kwargs,
    )


def _docker_inspect(container_id: str) -> Mapping[str, Any]:
    result = _run("docker", "inspect", container_id)
    parsed: object = json.loads(result.stdout)
    if not isinstance(parsed, list):
        raise DrillDenied("unable to inspect recovery target")
    items = cast(list[object], parsed)
    if len(items) != 1 or not isinstance(items[0], Mapping):
        raise DrillDenied("unable to inspect recovery target")
    return cast(Mapping[str, Any], items[0])


def _docker_image_id() -> str:
    image_id = _run("docker", "image", "inspect", POSTGRES_IMAGE, "--format", "{{.Id}}")
    value = image_id.stdout.strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise DrillDenied("recovery image identity unavailable")
    return value


def _assert_container_name_available(name: str) -> None:
    """Fail unless the generated name is provably absent before container creation."""
    result = subprocess.run(
        ("docker", "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.ID}}"),
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0 or result.stdout.strip():
        raise DrillDenied("task container name unavailable")


def _cleanup_failed_container_start(name: str, expected_image: str) -> bool:
    """Resolve an ambiguous Docker run result by exact name, label, and image."""
    inspected = subprocess.run(
        ("docker", "container", "inspect", name),
        check=False,
        text=True,
        capture_output=True,
    )
    if inspected.returncode != 0:
        absent = subprocess.run(
            (
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^/{name}$",
                "--format",
                "{{.ID}}",
            ),
            check=False,
            text=True,
            capture_output=True,
        )
        return absent.returncode == 0 and not absent.stdout.strip()
    try:
        objects: object = json.loads(inspected.stdout)
        if not isinstance(objects, list) or len(objects) != 1:
            return False
        item = objects[0]
        if not isinstance(item, Mapping):
            return False
        config = item.get("Config")
        if not isinstance(config, Mapping):
            return False
        container_id = item.get("Id")
        if (
            item.get("Name") != f"/{name}"
            or config.get("Image") != expected_image
            or config.get("Labels") != ISSUE_LABEL
            or not isinstance(container_id, str)
            or not re.fullmatch(r"[0-9a-f]{64}", container_id)
        ):
            return False
        return cleanup_task_resources((), (container_id,))
    except (TypeError, ValueError):
        return False


def _start_recovery_target(data_bytes: int, backup_bytes: int) -> str:
    nonce = uuid.uuid4().hex
    name = f"tailtag-207-recovery-{nonce}"
    # A name collision is a guard failure, never an invitation to reuse a target.
    _assert_container_name_available(name)
    try:
        result = _run(
            "docker",
            "run",
            "--pull=never",
            "--detach",
            "--name",
            name,
            "--label",
            "tailtag.issue=207",
            "--network",
            "none",
            "--mount",
            f"type=tmpfs,destination=/var/lib/postgresql,tmpfs-size={data_bytes}",
            "--mount",
            f"type=tmpfs,destination=/backup,tmpfs-size={backup_bytes}",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            f"POSTGRES_DB={TARGET_DATABASE}",
            POSTGRES_IMAGE,
        )
        container_id = result.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise DrillDenied("Docker did not return a full recovery target identity")
    except BaseException:  # Cleanup even when Docker omits the ID.
        if not _cleanup_failed_container_start(name, POSTGRES_IMAGE):
            raise CleanupUnverified(name) from None
        raise
    return container_id


def _wait_for_empty_postgres(container_id: str) -> None:
    deadline = time.monotonic() + 60
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            ready = subprocess.run(
                (
                    "docker",
                    "exec",
                    container_id,
                    "pg_isready",
                    "--host",
                    "127.0.0.1",
                    "--username",
                    "postgres",
                    "--dbname",
                    TARGET_DATABASE,
                ),
                check=False,
                text=True,
                capture_output=True,
                timeout=min(5, remaining),
            )
        except subprocess.TimeoutExpired:
            continue
        if ready.returncode == 0:
            break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    else:
        raise DrillDenied("recovery database did not become ready")
    version = _run(
        "docker",
        "exec",
        container_id,
        "psql",
        "--no-psqlrc",
        "--tuples-only",
        "--no-align",
        "--username",
        "postgres",
        "--dbname",
        TARGET_DATABASE,
        "--command",
        "SHOW server_version_num",
    ).stdout.strip()
    if not version.startswith("18"):
        raise DrillDenied("recovery database is not PostgreSQL 18")
    tables = _run(
        "docker",
        "exec",
        container_id,
        "psql",
        "--no-psqlrc",
        "--tuples-only",
        "--no-align",
        "--username",
        "postgres",
        "--dbname",
        TARGET_DATABASE,
        "--command",
        "SELECT count(*) FROM pg_tables WHERE schemaname='public'",
    ).stdout.strip()
    if tables != "0":
        raise DrillDenied("recovery database is not empty")


def _migration_leaves() -> frozenset[tuple[str, str]]:
    """Read the checked-out revision's leaf migration names without a database."""
    global _active_exact_source_root
    if _active_exact_source_root is None and _active_exact_source_sha is not None:
        _active_exact_source_root = _create_exact_source_worktree(
            _active_exact_source_sha
        )
    api_root = (_active_exact_source_root or _REPOSITORY_ROOT) / "services" / "api"
    leaves: set[tuple[str, str]] = set()
    migration_paths = {
        app: api_root / app / "migrations"
        for app in (
            "accounts",
            "catches",
            "conventions",
            "fursuits",
            "operator_audit",
            "profiles",
            "rehearsal",
        )
    }
    for app in ("admin", "auth", "contenttypes", "sessions"):
        package = importlib.import_module(f"django.contrib.{app}.migrations")
        package_file = getattr(package, "__file__", None)
        if not isinstance(package_file, str):
            raise DrillDenied("expected migration graph unavailable")
        migration_paths[app] = Path(package_file).parent
    for app, migrations_path in migration_paths.items():
        names = sorted(
            path.stem for path in migrations_path.glob("[0-9][0-9][0-9][0-9]_*.py")
        )
        if not names:
            raise DrillDenied("expected migration graph unavailable")
        leaves.add((app, names[-1]))
    return frozenset(leaves)


def _verify_manifest_revision(source_sha: str) -> None:
    """Bind the reviewed V0 manifest to the exact deployed schema revision."""
    if source_sha != _SCHEMA_MANIFEST_SOURCE_SHA:
        raise DrillDenied("deployed schema revision differs from reviewed manifest")
    paths = tuple(
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
    )
    unchanged = subprocess.run(
        ("git", "diff", "--quiet", source_sha, "--", *paths),
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
        check=False,
    )
    if unchanged.returncode != 0:
        raise DrillDenied("reviewed schema files differ from deployed revision")


def _active_staging_identity() -> Mapping[str, object]:
    """Use the existing fixed-origin health/identity check without its output."""
    from scripts.api_staging_preflight import TargetSafetyError, validate_target

    try:
        return validate_target("https://staging.tailtag.app")
    except TargetSafetyError as error:
        raise DrillDenied("canonical Staging preflight unavailable") from error


def _verify_exact_deployment(identity: Mapping[str, object]) -> None:
    """Join the active health identity to the pinned Railway API deployment."""
    from scripts.api_deployment_identity import join_deployment

    try:
        verify_railway_identity()
        identity_module = importlib.import_module("scripts.api_deployment_identity")
        query = cast(
            Callable[[str], Mapping[str, object]], identity_module._query_deployment
        )
        join_deployment(identity, query(cast(str, identity["deployment_id"])))
    except (KeyError, TypeError, ValueError, subprocess.SubprocessError) as error:
        raise DrillDenied("active deployment identity unavailable") from error


def _staging_database_fingerprint() -> str:
    """Verify the pinned API/Postgres URL and ready Postgres volume relationship."""
    try:
        reset_module = importlib.import_module("scripts.api_staging_reset_ssh")
        variables = cast(Callable[[str], dict[str, str]], reset_module._variables)
        verify_railway_identity()
        api = variables(_API_SERVICE_ID)
        verify_railway_identity()
        postgres = variables(_POSTGRES_SERVICE_ID)
        expected = {
            "RAILWAY_PROJECT_ID": _PROJECT_ID,
            "RAILWAY_ENVIRONMENT_ID": _ENVIRONMENT_ID,
            "RAILWAY_ENVIRONMENT_NAME": "staging",
        }
        if (
            any(
                api.get(key) != value or postgres.get(key) != value
                for key, value in expected.items()
            )
            or api.get("RAILWAY_SERVICE_ID") != _API_SERVICE_ID
            or postgres.get("RAILWAY_SERVICE_ID") != _POSTGRES_SERVICE_ID
            or not api.get("DATABASE_URL")
            or api["DATABASE_URL"] != postgres.get("DATABASE_URL")
        ):
            raise DrillDenied("canonical Staging database relationship unavailable")
        verify_railway_identity()
        status = json.loads(
            _run(
                "railway",
                "status",
                "--project",
                _PROJECT_ID,
                "--environment",
                _ENVIRONMENT_ID,
                "--json",
            ).stdout
        )
        if (
            not isinstance(status, Mapping)
            or status.get("id") != _PROJECT_ID
            or status.get("name") != "TailTag"
        ):
            raise DrillDenied("canonical Staging database relationship unavailable")
        environments = status.get("environments")
        if not isinstance(environments, Mapping):
            raise DrillDenied("canonical Staging database relationship unavailable")
        environment_edges = environments.get("edges")
        if not isinstance(environment_edges, list) or len(environment_edges) != 1:
            raise DrillDenied("canonical Staging database relationship unavailable")
        environment_edge = environment_edges[0]
        environment = (
            environment_edge.get("node")
            if isinstance(environment_edge, Mapping)
            else None
        )
        if (
            not isinstance(environment, Mapping)
            or environment.get("id") != _ENVIRONMENT_ID
            or environment.get("name") != "staging"
            or environment.get("deletedAt") is not None
        ):
            raise DrillDenied("canonical Staging database relationship unavailable")
        service_edges = status.get("services", {}).get("edges")
        if not isinstance(service_edges, list):
            raise DrillDenied("canonical Staging database relationship unavailable")
        services = {
            node.get("name"): node.get("id")
            for edge in service_edges
            if isinstance(edge, Mapping)
            and isinstance((node := edge.get("node")), Mapping)
        }
        if (
            services.get("api") != _API_SERVICE_ID
            or services.get("Postgres") != _POSTGRES_SERVICE_ID
        ):
            raise DrillDenied("canonical Staging database relationship unavailable")
        volume_edges = environment.get("volumeInstances", {}).get("edges")
        if not isinstance(volume_edges, list) or len(volume_edges) != 1:
            raise DrillDenied("canonical Staging database relationship unavailable")
        volume_edge = volume_edges[0]
        volume = volume_edge.get("node") if isinstance(volume_edge, Mapping) else None
        if (
            not isinstance(volume, Mapping)
            or volume.get("serviceId") != _POSTGRES_SERVICE_ID
            or volume.get("environmentId") != _ENVIRONMENT_ID
            or volume.get("state") != "READY"
            or volume.get("isPendingDeletion") is not False
            or volume.get("deletedAt") is not None
            or not isinstance(volume.get("id"), str)
            or re.fullmatch(r"[0-9a-f-]{36}", cast(str, volume.get("id"))) is None
        ):
            raise DrillDenied("canonical Staging database relationship unavailable")
        return sanitized_fingerprint(
            api["DATABASE_URL"]
            + "\n"
            + cast(str, volume["id"])
            + "\n"
            + _POSTGRES_SERVICE_ID
        )
    except (
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        raise DrillDenied(
            "canonical Staging database relationship unavailable"
        ) from error


def _capacity_bytes(snapshot: SourceSnapshot) -> tuple[int, int]:
    rows = snapshot.query("SELECT pg_database_size(current_database()) AS bytes")
    if len(rows) != 1 or not isinstance(rows[0].get("bytes"), int):
        raise DrillDenied("source database capacity unavailable")
    source_bytes = cast(int, rows[0]["bytes"])
    memory = _run("docker", "info", "--format", "{{.MemTotal}}").stdout.strip()
    if not memory.isdigit():
        raise DrillDenied("Docker memory capacity unavailable")
    data_bytes = max(2 * 1024**3, source_bytes * 4)
    backup_bytes = max(1024**3, source_bytes * 2)
    if data_bytes + backup_bytes > int(memory) // 2:
        raise DrillDenied("insufficient isolated recovery capacity")
    return data_bytes, backup_bytes


def _tool_versions() -> dict[str, str]:
    """Capture only the bounded local PostgreSQL client version numbers."""
    versions: dict[str, str] = {}
    for tool in ("pg_dump", "pg_restore"):
        output = _run(tool, "--version").stdout.strip()
        match = re.fullmatch(
            rf"{tool} \(PostgreSQL\) ([0-9]+\.[0-9]+(?:\.[0-9]+)?)", output
        )
        if match is None:
            raise DrillDenied("PostgreSQL client version unavailable")
        versions[tool] = match.group(1)
    return versions


def _create_exact_source_worktree(source_sha: str) -> Path:
    """Create a task-owned detached checkout of the observed deployed revision."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise DrillDenied("invalid deployed source identity")
    available = subprocess.run(
        ("git", "cat-file", "-e", f"{source_sha}^{{commit}}"),
        check=False,
        cwd=_REPOSITORY_ROOT,
        capture_output=True,
    )
    if available.returncode != 0:
        raise DrillDenied("exact deployed application revision unavailable locally")
    root = Path(tempfile.mkdtemp(prefix="tailtag-207-source-"))
    try:
        _run(
            "git",
            "worktree",
            "add",
            "--detach",
            str(root),
            source_sha,
            cwd=str(_REPOSITORY_ROOT),
        )
        if _run("git", "rev-parse", "HEAD", cwd=str(root)).stdout.strip() != source_sha:
            raise DrillDenied("detached source revision mismatch")
        return root
    except (DrillDenied, OSError, subprocess.SubprocessError):
        rmtree(root, ignore_errors=True)
        raise


def _remove_exact_source_worktree(root: Path) -> bool:
    try:
        _run(
            "git", "worktree", "remove", "--force", str(root), cwd=str(_REPOSITORY_ROOT)
        )
        rmtree(root, ignore_errors=True)
        return not root.exists()
    except (OSError, subprocess.SubprocessError):
        return False


def _build_exact_backend_image(source_sha: str) -> str:
    """Build the production image only from the verified detached checkout."""
    source_root = _active_exact_source_root
    if source_root is None:
        raise DrillDenied("exact source checkout unavailable")
    if (
        _run("git", "rev-parse", "HEAD", cwd=str(source_root)).stdout.strip()
        != source_sha
    ):
        raise DrillDenied("exact source checkout changed")
    image = _run(
        "docker",
        "build",
        "--quiet",
        "--target",
        "production",
        "--build-arg",
        f"RAILWAY_GIT_COMMIT_SHA={source_sha}",
        str(source_root / "services" / "api"),
        timeout=900,
    ).stdout.strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise DrillDenied("exact backend image build unavailable")
    return image


def _safe_failure() -> int:
    # Never include user input, subprocess output, URLs, or exception text.
    print(
        "restore drill refused or failed; consult sanitized evidence", file=sys.stderr
    )
    return 1


def _parse_cli(arguments: Sequence[str]) -> bool:
    # Do not use argparse: its normal diagnostics echo untrusted option values.
    return tuple(arguments) == ("--confirm", CONFIRMATION)


def main() -> int:
    """Run only with the fixed human confirmation phrase."""
    if not _parse_cli(sys.argv[1:]):
        return _safe_failure()
    # Live work is deliberately delegated to the tightly scoped helper.  This
    # makes every refusal before a subprocess start testable at the CLI seam.
    try:
        return run_drill()
    except Exception:  # noqa: BLE001 - sensitive command output must stay private.
        return _safe_failure()


def run_drill() -> int:
    """Run the fixed source/target drill and retain sanitized success or failure."""
    container_id: str | None = None
    tunnel: Any | None = None
    snapshot: Any | None = None
    source_root: Path | None = None
    before: Mapping[str, object] | None = None
    before_database: str | None = None
    recovery_point_time: str | None = None
    source_postgres_major: int | None = None
    source_migration_leaves: list[str] | None = None
    source_table_counts: dict[str, int] | None = None
    source_constraint_catalog_digest: str | None = None
    tool_versions: dict[str, str] | None = None
    dump_started_at: str | None = None
    dump_completed_at: str | None = None
    restore_started_at: str | None = None
    restore_completed_at: str | None = None
    dump_seconds = 0
    restore_seconds = 0
    checks: dict[str, str] = {}
    backend_usability = "NOT_EXERCISED"
    staging_nonimpact = "NOT_EXERCISED"
    stage = "PREFLIGHT"
    failure: BaseException | None = None
    global _active_exact_source_root, _active_exact_source_sha
    evidence_path = _evidence_attempt_path()
    try:
        context = _run(
            "docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"
        )
        if not context.stdout.strip().startswith("unix://"):
            raise DrillDenied("Docker context is not a local Unix socket")
        tool_versions = _tool_versions()
        before = _active_staging_identity()
        verify_railway_identity()
        _verify_exact_deployment(before)
        before_database = _staging_database_fingerprint()
        image_id = _docker_image_id()
        stage = "TUNNEL"
        tunnel, details = open_railway_tunnel()
        stage = "SNAPSHOT"
        snapshot = open_source_snapshot(details)
        recovery_point_time = utc_now()
        if isinstance(snapshot, SourceSnapshot):
            version_rows = snapshot.query("SHOW server_version_num")
            version_value = (
                version_rows[0].get("server_version_num")
                if len(version_rows) == 1
                else None
            )
            if not isinstance(version_value, str) or not version_value.isdigit():
                raise DrillDenied("source PostgreSQL version unavailable")
            source_postgres_major = int(version_value) // 10000
        else:  # Test-only dependency seam; production always uses SourceSnapshot.
            source_postgres_major = 18
        data_bytes, backup_bytes = _capacity_bytes(snapshot)
        from scripts.staging_restore_integrity import (
            collect_integrity,
            compare_integrity,
        )

        _active_exact_source_sha = cast(str, before["source_sha"])
        leaves = _migration_leaves()
        _verify_manifest_revision(cast(str, before["source_sha"]))
        source_root = _active_exact_source_root
        source_facts = collect_integrity(snapshot.query, leaves)
        source_migration_leaves = sorted(f"{app}.{name}" for app, name in leaves)
        source_table_counts = dict(source_facts.table_counts)
        source_constraint_catalog_digest = sanitized_fingerprint(
            json.dumps(source_facts.constraint_fingerprints, sort_keys=True)
        )
        stage = "TARGET"
        container_id = _start_recovery_target(data_bytes, backup_bytes)
        validate_recovery_target(_docker_inspect(container_id), container_id, image_id)
        _wait_for_empty_postgres(container_id)
        checks["target_guard"] = "PASS"
        stage = "DUMP"
        dump_started_at = utc_now()
        dump_started = time.monotonic()
        dump_snapshot_to_target(details, snapshot, container_id)
        dump_seconds = int(time.monotonic() - dump_started)
        dump_completed_at = utc_now()
        validate_archive(container_id)
        checks["dump_archive"] = "PASS"
        stage = "RESTORE"
        restore_started_at = utc_now()
        restore_started = time.monotonic()
        restore_archive(container_id)
        restore_seconds = int(time.monotonic() - restore_started)
        restore_completed_at = utc_now()
        checks["restore"] = "PASS"
        stage = "INTEGRITY"
        restored_facts = collect_integrity(
            recovery_query_executor(container_id), leaves
        )
        comparison = compare_integrity(source_facts, restored_facts)
        comparison_checks = cast(dict[str, str], getattr(comparison, "checks", {}))
        checks.update(comparison_checks)
        if comparison.overall_outcome != "PASS" or set(checks) != _EVIDENCE_CHECK_NAMES:
            raise DrillDenied("restored integrity proof failed")
        stage = "BACKEND"
        backend_read_only_proof(
            _build_exact_backend_image(cast(str, before["source_sha"])), container_id
        )
        backend_usability = "PASS"
        for table, check_name in _REPRESENTATIVE_CHECKS.items():
            if source_facts.representative_records[table]:
                checks[check_name] = "PASS"
        stage = "NONIMPACT"
        after = _active_staging_identity()
        _verify_exact_deployment(after)
        after_database = _staging_database_fingerprint()
        if before != after or before_database != after_database:
            raise DrillDenied("canonical Staging changed during drill")
        staging_nonimpact = "PASS"
    except BaseException as error:  # noqa: BLE001 - cleanup and sanitized failure evidence must run.
        failure = error
    finally:
        cleanup_ok = True
        if snapshot is not None:
            try:
                snapshot.close()
            except Exception:  # noqa: BLE001
                cleanup_ok = False
        source_root = _active_exact_source_root or source_root
        if source_root is not None:
            try:
                cleanup_ok = _remove_exact_source_worktree(source_root) and cleanup_ok
            except Exception:  # noqa: BLE001
                cleanup_ok = False
        _active_exact_source_root = None
        _active_exact_source_sha = None
        if tunnel is not None:
            try:
                cleanup_ok = cleanup_task_resources((tunnel,), ()) and cleanup_ok
            except Exception:  # noqa: BLE001
                cleanup_ok = False
        if container_id is not None:
            try:
                cleanup_ok = cleanup_task_resources((), (container_id,)) and cleanup_ok
            except Exception:  # noqa: BLE001
                cleanup_ok = False
    if failure is not None:
        stage_check = {
            "TARGET": "target_guard",
            "DUMP": "dump_archive",
            "RESTORE": "restore",
        }.get(stage)
        if stage_check is not None:
            checks[stage_check] = "FAIL"
        if stage == "BACKEND":
            backend_usability = "FAIL"
        if stage == "NONIMPACT":
            staging_nonimpact = "FAIL"
    if failure is None and not cleanup_ok:
        stage = "CLEANUP"
    if isinstance(failure, CleanupUnverified):
        cleanup_ok = False
    passed = failure is None and cleanup_ok
    evidence: dict[str, object] = {
        "schema_version": 1,
        "outcome": "GO" if passed else "FAIL",
        "mechanism": "logical_custom_pg_dump",
        "selection_reason": "PITR_DISABLED_NO_VOLUME_BACKUPS_LOGICAL_DUMP",
        "recovery_point_time": recovery_point_time,
        "source_sha": before.get("source_sha") if before is not None else None,
        "source_deployment_fingerprint": (
            sanitized_fingerprint(cast(str, before["deployment_id"]))
            if before is not None
            else None
        ),
        "source_database_fingerprint": before_database,
        "source_postgres_major": source_postgres_major,
        "source_migration_leaves": source_migration_leaves,
        "source_table_counts": source_table_counts,
        "source_constraint_catalog_digest": source_constraint_catalog_digest,
        "tool_versions": tool_versions,
        "target_class": "local_disposable_docker_tmpfs",
        "dump_started_at": dump_started_at,
        "dump_completed_at": dump_completed_at,
        "restore_started_at": restore_started_at,
        "restore_completed_at": restore_completed_at,
        "dump_duration_seconds": dump_seconds,
        "restore_duration_seconds": restore_seconds,
        "checks": checks,
        "backend_usability": backend_usability,
        "staging_nonimpact": staging_nonimpact,
        "cleanup_verified": cleanup_ok,
        "failure_stage": None if passed else stage,
        "limitations": [],
        "follow_up": [] if cleanup_ok else ["CLEANUP_UNVERIFIED"],
    }
    if not passed:
        evidence["local_recovery_handle"] = (
            failure.handle
            if isinstance(failure, CleanupUnverified)
            else container_id
            if not cleanup_ok
            else None
        )
    write_sanitized_evidence(evidence_path, evidence)
    if not passed:
        raise DrillDenied(f"restore drill failed at {stage}") from None
    return 0


def sanitized_fingerprint(value: str) -> str:
    """Return an opaque resource comparison token suitable for evidence."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> str:
    """Provide a fixed-format timestamp for a sanitized evidence writer."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _evidence_attempt_path() -> Path:
    """Return a non-reusable durable evidence name for this drill attempt."""
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return (
        _REPOSITORY_ROOT
        / "docs"
        / "development"
        / "staging-recovery"
        / f"{timestamp}-issue-207-restore-{uuid.uuid4().hex}.json"
    )


def write_sanitized_evidence(path: Path, evidence: Mapping[str, object]) -> None:
    """Atomically retain only the fixed, non-sensitive #207 evidence record."""
    outcome = evidence.get("outcome")
    expected_fields = _EVIDENCE_FIELDS | (
        {"local_recovery_handle"} if outcome == "FAIL" else set()
    )
    if frozenset(evidence) != expected_fields:
        raise DrillDenied("invalid evidence fields")
    checks = evidence.get("checks")
    limitations = evidence.get("limitations")
    follow_up = evidence.get("follow_up")
    failure_stage = evidence.get("failure_stage")
    migration_leaves = evidence.get("source_migration_leaves")
    table_counts = evidence.get("source_table_counts")
    tool_versions = evidence.get("tool_versions")
    if (
        evidence.get("schema_version") != 1
        or outcome not in {"GO", "FAIL"}
        or evidence.get("mechanism") != "logical_custom_pg_dump"
        or evidence.get("selection_reason")
        != "PITR_DISABLED_NO_VOLUME_BACKUPS_LOGICAL_DUMP"
        or evidence.get("target_class") != "local_disposable_docker_tmpfs"
        or (evidence.get("recovery_point_time") is None and outcome == "GO")
        or (
            evidence.get("recovery_point_time") is not None
            and not isinstance(evidence.get("recovery_point_time"), str)
        )
        or (evidence.get("source_sha") is None and outcome == "GO")
        or (
            evidence.get("source_sha") is not None
            and re.fullmatch(r"[0-9a-f]{40}", cast(str, evidence.get("source_sha")))
            is None
        )
        or any(
            (evidence.get(field) is None and outcome == "GO")
            or (
                evidence.get(field) is not None
                and re.fullmatch(r"[0-9a-f]{64}", cast(str, evidence.get(field)))
                is None
            )
            for field in (
                "source_deployment_fingerprint",
                "source_database_fingerprint",
            )
        )
        or (evidence.get("source_postgres_major") is None and outcome == "GO")
        or (
            evidence.get("source_postgres_major") is not None
            and not isinstance(evidence.get("source_postgres_major"), int)
        )
        or (
            outcome == "GO"
            and any(
                evidence.get(field) is None
                for field in (
                    "source_migration_leaves",
                    "source_table_counts",
                    "source_constraint_catalog_digest",
                    "tool_versions",
                    "dump_started_at",
                    "dump_completed_at",
                    "restore_started_at",
                    "restore_completed_at",
                )
            )
        )
        or (
            evidence.get("source_constraint_catalog_digest") is not None
            and re.fullmatch(
                r"[0-9a-f]{64}",
                cast(str, evidence.get("source_constraint_catalog_digest")),
            )
            is None
        )
        or any(
            not isinstance(evidence.get(field), int)
            or cast(int, evidence.get(field)) < 0
            for field in ("dump_duration_seconds", "restore_duration_seconds")
        )
        or evidence.get("backend_usability") not in {"PASS", "FAIL", "NOT_EXERCISED"}
        or evidence.get("staging_nonimpact") not in {"PASS", "FAIL", "NOT_EXERCISED"}
        or not isinstance(evidence.get("cleanup_verified"), bool)
        or (
            outcome == "GO"
            and (
                failure_stage is not None
                or evidence.get("cleanup_verified") is not True
                or evidence.get("backend_usability") != "PASS"
                or evidence.get("staging_nonimpact") != "PASS"
            )
        )
        or (outcome == "FAIL" and failure_stage not in _EVIDENCE_STAGES)
        or not isinstance(checks, Mapping)
        or not isinstance(limitations, list)
        or not isinstance(follow_up, list)
    ):
        raise DrillDenied("invalid sanitized evidence")
    try:
        for field in (
            "recovery_point_time",
            "dump_started_at",
            "dump_completed_at",
            "restore_started_at",
            "restore_completed_at",
        ):
            timestamp = evidence[field]
            if timestamp is not None:
                if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
                    raise ValueError
                datetime.fromisoformat(timestamp.removesuffix("Z") + "+00:00")
    except (TypeError, ValueError):
        raise DrillDenied("invalid sanitized evidence") from None
    typed_checks = cast(Mapping[object, object], checks)
    typed_limitations = cast(list[object], limitations)
    typed_follow_up = cast(list[object], follow_up)
    if (
        (outcome == "GO" and not checks)
        or any(
            name not in _EVIDENCE_CHECK_NAMES
            or value not in {"PASS", "FAIL", "NOT_EXERCISED"}
            for name, value in typed_checks.items()
        )
        or any(
            code not in _EVIDENCE_CODES
            for code in [*typed_limitations, *typed_follow_up]
        )
        or (
            migration_leaves is not None
            and (
                not isinstance(migration_leaves, list)
                or len(migration_leaves) > 100
                or any(
                    not isinstance(item, str)
                    or re.fullmatch(r"[a-z_]+\.[0-9]{4}_[a-z0-9_]+", item) is None
                    for item in migration_leaves
                )
            )
        )
        or (
            table_counts is not None
            and (
                not isinstance(table_counts, Mapping)
                or set(table_counts) != set(_REPRESENTATIVE_CHECKS)
                or any(
                    not isinstance(value, int) or not 0 <= value <= 1_000_000_000
                    for value in table_counts.values()
                )
            )
        )
        or (
            tool_versions is not None
            and (
                not isinstance(tool_versions, Mapping)
                or set(tool_versions) != {"pg_dump", "pg_restore"}
                or any(
                    not isinstance(value, str)
                    or re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", value) is None
                    for value in tool_versions.values()
                )
            )
        )
        or (
            outcome == "FAIL"
            and evidence.get("local_recovery_handle") is not None
            and re.fullmatch(
                r"(?:[0-9a-f]{64}|tailtag-207-(?:backend|recovery)-[0-9a-f]{32})",
                cast(str, evidence.get("local_recovery_handle")),
            )
            is None
        )
        or (
            outcome == "FAIL"
            and evidence.get("cleanup_verified") is True
            and evidence.get("local_recovery_handle") is not None
        )
    ):
        raise DrillDenied("invalid sanitized evidence")
    encoded = (
        json.dumps(dict(evidence), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    linked = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        # link(2) is an atomic create: unlike replace(2), it refuses to
        # overwrite an existing durable result for another attempt.
        os.link(temporary, path)
        linked = True
        temporary.unlink()
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except (OSError, TypeError, ValueError):
        if linked:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise DrillDenied("sanitized evidence write failed") from None


if __name__ == "__main__":
    raise SystemExit(main())
