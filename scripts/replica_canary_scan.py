"""Search collected surfaces for the exact hybrid replica secret values (#357 AC18).

A canary scan searches for the exact secret values and reports only counts. The
operator first collects each surface into a local file or directory (logs,
Actions log archives, issue exports, Terraform outputs, a saved image), then
runs `task replica-canary-scan -- --project <id> NAME=PATH ...`.

The scan reads six secrets from Secret Manager into memory. For a database URL
it searches for the password, which every copy of the URL contains, both as
written in the URL and percent-decoded. The Neon
admin URL is added when `NEON_ADMIN_DATABASE_URL` is set. `clerk-jwt-key` is a
public key and `sentry-dsn` has no value until #358, so neither is searched.
Files, gzip, zip and tar members are read, nested up to four levels. Output
names a surface and a secret alias, never a value. Exit 0 means no match, 1
means a match, and 2 means the scan could not run safely or left a compressed
blob closed.
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlsplit

SECRET_IDS: Final = (
    "django-secret-key",
    "migrator-database-url",
    "runtime-database-url",
    "maintainer-database-url",
    "media-access-key-id",
    "media-secret-access-key",
)
ADMIN_URL_VARIABLE: Final = "NEON_ADMIN_DATABASE_URL"
_ADMIN_ALIAS: Final = "neon-admin-database-url"
_PROJECT_ID: Final = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
_SURFACE_NAME: Final = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
_MINIMUM_NEEDLE_LENGTH: Final = 16
_MAXIMUM_DEPTH: Final = 4
# Signatures of compressed or archived data that the scan leaves closed: gzip,
# zip and tar past the depth limit or unreadable, and zstd, xz and bzip2.
_CLOSED_PREFIXES: Final = (
    b"\x1f\x8b",
    b"PK\x03\x04",
    b"\x28\xb5\x2f\xfd",
    b"\xfd7zXZ\x00",
)
_COMMAND_TIMEOUT_SECONDS: Final = 60


class ScanError(Exception):
    """A failure whose message is safe to print: it never holds a value."""


def _needles(alias: str, value: str) -> tuple[bytes, ...]:
    """Return the searched bytes: a URL password as written and decoded, else the value."""
    forms = [value]
    if value.startswith(("postgres://", "postgresql://")):
        try:
            password = urlsplit(value).password
        except ValueError:
            password = None
        if not password:
            raise ScanError(f"secret {alias} is a database URL with no password")
        # A percent-encoded password can leak in either form.
        forms = list(dict.fromkeys((password, unquote(password))))
    if any(len(form) < _MINIMUM_NEEDLE_LENGTH for form in forms):
        raise ScanError(
            f"secret {alias} is under {_MINIMUM_NEEDLE_LENGTH} characters, "
            "so a count would not be meaningful"
        )
    return tuple(form.encode() for form in forms)


def _read_secret(project: str, secret_id: str) -> str:
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise ScanError(
            "gcloud is not on PATH; install the Google Cloud CLI and sign in"
        )
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
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        raise ScanError(
            f"gcloud could not read secret {secret_id} (exit {result.returncode})"
        )
    return value


def load_needles(
    project: str, environ: Mapping[str, str]
) -> dict[str, tuple[bytes, ...]]:
    needles = {
        secret_id: _needles(secret_id, _read_secret(project, secret_id))
        for secret_id in SECRET_IDS
    }
    admin_url = environ.get(ADMIN_URL_VARIABLE, "").strip()
    if admin_url:
        if not admin_url.startswith(("postgres://", "postgresql://")):
            raise ScanError(f"{ADMIN_URL_VARIABLE} is not a postgresql URL")
        needles[_ADMIN_ALIAS] = _needles(_ADMIN_ALIAS, admin_url)
    return needles


def _blobs(content: bytes, depth: int) -> Iterator[bytes]:
    """Yield the searchable bytes of one file, opening archives inside it."""
    if depth < _MAXIMUM_DEPTH:
        if content[:2] == b"\x1f\x8b":
            try:
                yield from _blobs(gzip.decompress(content), depth + 1)
                return
            except (OSError, EOFError):
                pass
        if content[:4] == b"PK\x03\x04":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    members = [archive.read(info) for info in archive.infolist()]
            except (zipfile.BadZipFile, OSError, RuntimeError):
                # RuntimeError: an encrypted member. The blob stays closed.
                members = None
            if members is not None:
                for member in members:
                    yield from _blobs(member, depth + 1)
                return
        if len(content) > 262 and content[257:262] == b"ustar":
            try:
                with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as archive:
                    members = [
                        extracted.read()
                        for info in archive.getmembers()
                        if info.isfile()
                        and (extracted := archive.extractfile(info)) is not None
                    ]
            except (tarfile.TarError, OSError):
                members = None
            if members is not None:
                for member in members:
                    yield from _blobs(member, depth + 1)
                return
    yield content


def _is_closed(blob: bytes) -> bool:
    """Return whether a leaf blob is still compressed or archived."""
    return (
        blob.startswith(_CLOSED_PREFIXES)
        or (len(blob) > 262 and blob[257:262] == b"ustar")
        or (blob[:3] == b"BZh" and blob[4:10] == b"1AY&SY")
    )


def scan_path(
    path: Path, needles: Mapping[str, tuple[bytes, ...]]
) -> tuple[Counter[str], int]:
    """Return the match count of each alias and the number of blobs left closed."""
    counts: Counter[str] = Counter()
    closed = 0
    files = (
        sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    )
    for file in files:
        for blob in _blobs(file.read_bytes(), 0):
            if _is_closed(blob):
                closed += 1
            for alias, forms in needles.items():
                found = sum(blob.count(form) for form in forms)
                if found:
                    counts[alias] += found
    return counts, closed


def _surfaces(specs: Sequence[str]) -> list[tuple[str, Path]]:
    if not specs:
        raise ScanError("name at least one surface as NAME=PATH")
    surfaces: list[tuple[str, Path]] = []
    for spec in specs:
        name, separator, raw_path = spec.partition("=")
        path = Path(raw_path)
        if not separator or not _SURFACE_NAME.fullmatch(name):
            raise ScanError(
                "each surface must be NAME=PATH with a short lowercase name"
            )
        if not path.exists():
            raise ScanError(f"surface {name} has no file or directory at its path")
        surfaces.append((name, path))
    return surfaces


def main(
    argv: Sequence[str] | None = None, *, environ: Mapping[str, str] = os.environ
) -> int:
    parser = argparse.ArgumentParser(
        prog="replica_canary_scan",
        description="Count exact replica secret values in collected surfaces.",
    )
    parser.add_argument("--project", required=True, help="Google Cloud project id")
    parser.add_argument("surfaces", nargs="*", metavar="NAME=PATH")
    arguments = parser.parse_args(argv)
    if not _PROJECT_ID.fullmatch(arguments.project):
        print("error: --project is not a valid project id", file=sys.stderr)
        return 2
    try:
        surfaces = _surfaces(arguments.surfaces)
        needles = load_needles(arguments.project, environ)
    except ScanError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print("error: a command timed out", file=sys.stderr)
        return 2

    total = 0
    total_closed = 0
    for name, path in surfaces:
        try:
            counts, closed = scan_path(path, needles)
        except OSError:
            print(f"error: could not read surface {name}", file=sys.stderr)
            return 2
        surface_total = sum(counts.values())
        total += surface_total
        total_closed += closed
        print(f"surface {name}: {surface_total} matches")
        for alias in sorted(counts):
            print(f"  {alias}: {counts[alias]}")
        if closed:
            print(f"  not opened: {closed}")
    if total:
        print("FAIL canary scan", file=sys.stderr)
        return 1
    if total_closed:
        # A closed blob could hide a value, so a zero count proves nothing.
        print("FAIL canary scan", file=sys.stderr)
        return 2
    print("PASS canary scan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
