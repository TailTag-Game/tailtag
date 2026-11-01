"""Count a PITR restore of Render Staging over `render ssh` (#410 AC13).

The local launcher `scripts/api_staging_render_ssh.py restore-count` starts
this module with `python -m rehearsal.render_restore_count` in an interactive
`render ssh` session. Before the prompt, it binds the Render Staging runtime,
the image build, and the pinned private values. It reads the URL of the new
database at a hidden prompt. It accepts only a Render internal host name that
differs from the live Staging database, so Staging cannot pass as its own
restore. It counts every public table in a
read-only transaction with the same code as the row-count job. It passes only
when the digest of those counts equals the digest that the job recorded.

It prints the counts for the record, then one result line. It never prints the
URL or a database error, so no line can carry a credential.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
import warnings
from typing import TYPE_CHECKING, Final, NoReturn

if TYPE_CHECKING:
    from rehearsal.safety import ResetConfiguration

RESULT_PREFIX: Final = "TAILTAG-RENDER-RESTORE "
_OPERATION: Final = "restore-count"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}")
# The internal URL names a Render database host. An IP address or an alias
# could reach the live Staging database under another name, so neither passes.
_INTERNAL_HOST: re.Pattern[str] = re.compile(r"dpg-[a-z0-9]+-a")
# libpq applies these after the URL check, and they can point anywhere.
_REDIRECTING_ENVIRONMENT: Final = ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")
_CONNECT_TIMEOUT_SECONDS: Final = 10


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError


class _Failure(Exception):
    def __init__(self, phase: str) -> None:
        super().__init__(phase)
        self.phase = phase


def _arguments(argv: list[str] | None) -> tuple[str, str]:
    parser = _SafeArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--expected-counts", required=True)
    try:
        arguments = parser.parse_args(argv)
    except (SystemExit, ValueError):
        raise _Failure("arguments") from None
    if _DIGEST.fullmatch(arguments.expected_counts) is None:
        raise _Failure("arguments")
    return arguments.source_sha, arguments.expected_counts


def _bind(source_sha: str) -> ResetConfiguration:
    """Require a real terminal, Render Staging, an image built from S, and pins."""
    from rehearsal import render_job

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise _Failure("terminal")
    try:
        render_job._bind_runtime(source_sha)  # pyright: ignore[reportPrivateUsage]
        return render_job._configuration()  # pyright: ignore[reportPrivateUsage]
    except render_job._Failure as failure:  # pyright: ignore[reportPrivateUsage]
        raise _Failure(failure.phase) from None


def _read_url() -> str:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass("Recovery database URL: ")
    except (getpass.GetPassWarning, EOFError, OSError):
        raise _Failure("terminal") from None


def _label(host: object) -> str:
    return str(host).split(".", 1)[0].lower()


def _check_target(url: str, configuration: ResetConfiguration) -> None:
    """Accept only a Render internal host that is not the live Staging database."""
    import os

    import psycopg
    from django.conf import settings
    from psycopg.conninfo import conninfo_to_dict

    try:
        parameters = conninfo_to_dict(url)
    except psycopg.Error:
        raise _Failure("url") from None
    host = parameters.get("host")
    # A host address or a service file can point anywhere, whatever the name.
    if (
        not isinstance(host, str)
        or not host
        or host.startswith("/")
        or "," in host
        or {"hostaddr", "service"} & set(parameters)
        or any(os.environ.get(name) for name in _REDIRECTING_ENVIRONMENT)
        or _INTERNAL_HOST.fullmatch(host) is None
    ):
        raise _Failure("url")
    staging = {
        _label(configuration.database_host),
        _label(settings.DATABASES["default"].get("HOST")),
    }
    if _label(host) in staging:
        raise _Failure("target")


def _count(url: str, configuration: ResetConfiguration) -> dict[str, object]:
    """Count the new database in a read-only transaction, then read its ID."""
    import psycopg

    from rehearsal.row_counts import count_rows, digest

    try:
        with psycopg.connect(url, connect_timeout=_CONNECT_TIMEOUT_SECONDS) as conn:
            conn.read_only = True
            with conn.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                counts = count_rows(cursor)
            conn.rollback()
            same_system_identifier: bool | None
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT system_identifier::text FROM pg_control_system()"
                    )
                    [(system_identifier,)] = cursor.fetchall()
                same_system_identifier = (
                    system_identifier == configuration.cluster_identifier
                )
            except psycopg.Error:
                same_system_identifier = None
            conn.rollback()
    except Exception:  # noqa: BLE001 - never leak a URL or a database value
        raise _Failure("query") from None
    return {
        "tables": len(counts),
        "counts": counts,
        "counts_sha256": digest(counts),
        "same_system_identifier": same_system_identifier,
    }


def _run(argv: list[str] | None) -> tuple[int, str]:
    try:
        source_sha, expected = _arguments(argv)
        configuration = _bind(source_sha)
        url = _read_url()
        _check_target(url, configuration)
        details = _count(url, configuration)
        # The counts are synthetic Staging facts, and the record needs them.
        print(json.dumps(details, sort_keys=True), flush=True)
        if details["counts_sha256"] != expected:
            raise _Failure("counts")
    except _Failure as failure:
        return 1, f"FAIL {_OPERATION} {failure.phase}"
    except BaseException as error:  # noqa: BLE001 - never success, always a line
        phase = "interrupted" if isinstance(error, KeyboardInterrupt) else "unknown"
        return 1, f"FAIL {_OPERATION} {phase}"
    return 0, f"PASS {_OPERATION}"


def main(argv: list[str] | None = None) -> int:
    status, result = _run(argv)
    # An interrupted prompt leaves the cursor mid-line, so start a new line.
    print("\n" + RESULT_PREFIX + result, flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
