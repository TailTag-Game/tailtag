"""Guarded live verification of the hybrid replica media bucket (#357).

It runs the Railway media smoke sequence against the pinned replica bucket, then
shows that the runtime keys reach nothing else: listing buckets, writing or
reading a second bucket, and reading an object without a signature must all be
denied. The runtime keys come from Secret Manager into memory only. Output is
fixed stage lines; no endpoint, bucket, key, object key or URL is printed.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

# The storage runtime reads settings for telemetry; no database is used.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.build")

from scripts import api_media_storage_smoke as smoke

from config.replica_binding import ReplicaBindingError, validate_media_target

_CONFIRMATION: Final = "run-r2-replica-media-storage-smoke"
_CONFIRM_VARIABLE: Final = "TAILTAG_REPLICA_MEDIA_SMOKE_CONFIRM"
_ENDPOINT_VARIABLE: Final = "TAILTAG_REPLICA_MEDIA_ENDPOINT_URL"
_BUCKET_VARIABLE: Final = "TAILTAG_REPLICA_MEDIA_BUCKET"
_SECRET_IDS: Final = ("media-access-key-id", "media-secret-access-key")
_PROJECT_ID: Final = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]")
_BUCKET_NAME: Final = re.compile(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]")
_REGION: Final = "auto"
_COMMAND_TIMEOUT_SECONDS: Final = 60
_FETCH_TIMEOUT_SECONDS: Final = 10
_DENIED_STATUSES: Final = frozenset({401, 403})
# Error codes that answer "this bucket does not exist" are inconclusive.
_MISSING_BUCKET_CODES: Final = frozenset({"NoSuchBucket"})
# R2 answers every unsigned S3 request with this 400, before it looks up the
# object (#357 live check). Any other 400 proves nothing.
_R2_UNSIGNED_REFUSAL: Final = ("InvalidArgument", "Authorization")
_ERROR_BODY_LIMIT: Final = 4096


class _Failed(Exception):
    """A failure whose stage name is safe to print."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


@dataclass(frozen=True, slots=True)
class ReplicaMediaTarget:
    project: str
    endpoint_url: str
    bucket_name: str
    isolation_bucket: str


class IsolationBoundary(Protocol):
    """Each probe returns `allowed`, `denied` or `error`."""

    def list_buckets(self) -> str: ...

    def put_other(self, *, key: str, content: bytes) -> str: ...

    def get_other(self, *, key: str) -> str: ...

    def delete_other(self, *, key: str) -> None: ...

    def unsigned_get(self, *, key: str) -> tuple[str, int | None]: ...


Build = Callable[
    [ReplicaMediaTarget, str, str], tuple[smoke.SmokeRuntime, IsolationBoundary]
]


class S3IsolationBoundary:
    """The live probes, with the runtime keys, against the S3 API and plain HTTPS."""

    def __init__(
        self,
        *,
        client: Any,
        endpoint_url: str,
        bucket_name: str,
        isolation_bucket: str,
        opener: Any = None,
    ) -> None:
        self._client = client
        self._endpoint_url = endpoint_url
        self._bucket_name = bucket_name
        self._isolation_bucket = isolation_bucket
        self._opener = (
            opener
            if opener is not None
            else urllib.request.build_opener(
                urllib.request.ProxyHandler({}), smoke._NoRedirect()
            )
        )

    def list_buckets(self) -> str:
        return self._attempt(
            lambda: self._client.list_buckets(), missing_is_allowed=False
        )

    def put_other(self, *, key: str, content: bytes) -> str:
        return self._attempt(
            lambda: self._client.put_object(
                Bucket=self._isolation_bucket, Key=key, Body=content
            ),
            missing_is_allowed=False,
        )

    def get_other(self, *, key: str) -> str:
        # A missing key still proves the request reached the bucket.
        return self._attempt(
            lambda: self._client.get_object(Bucket=self._isolation_bucket, Key=key),
            missing_is_allowed=True,
        )

    def delete_other(self, *, key: str) -> None:
        self._client.delete_object(Bucket=self._isolation_bucket, Key=key)

    def unsigned_get(self, *, key: str) -> tuple[str, int | None]:
        url = f"{self._endpoint_url}/{self._bucket_name}/{key}"
        request = urllib.request.Request(url, method="GET")
        body = b""
        try:
            with self._opener.open(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
                status = int(response.getcode())
        except urllib.error.HTTPError as error:
            status = error.code
            try:
                body = error.read(_ERROR_BODY_LIMIT)
            except Exception:  # noqa: BLE001 - an unread body proves nothing.
                body = b""
        except Exception:  # noqa: BLE001 - transport failures are inconclusive.
            return "error", None
        if 200 <= status < 300:
            return "allowed", status
        # 401, 403 and R2's unsigned-request 400 prove a refusal. A 404 or a
        # 429 proves nothing.
        if status in _DENIED_STATUSES or (
            status == 400 and _s3_error(body) == _R2_UNSIGNED_REFUSAL
        ):
            return "denied", status
        return "error", status

    @staticmethod
    def _attempt(call: Callable[[], object], *, missing_is_allowed: bool) -> str:
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            call()
        except ClientError as error:
            response = error.response
            code = str(response.get("Error", {}).get("Code", ""))
            status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status in _DENIED_STATUSES or code == "AccessDenied":
                return "denied"
            if code in _MISSING_BUCKET_CODES:
                return "error"
            if missing_is_allowed and status == 404:
                return "allowed"
            return "error"
        except BotoCoreError:
            return "error"
        return "allowed"


def _s3_error(body: bytes) -> tuple[str, str]:
    """Return the S3 error code and message of an XML error body, or blanks."""
    text = body.decode("utf-8", errors="replace")
    code = re.search(r"<Code>([^<]*)</Code>", text)
    message = re.search(r"<Message>([^<]*)</Message>", text)
    return (code.group(1) if code else "", message.group(1) if message else "")


def parse_target(
    arguments: Sequence[str], environ: Mapping[str, str]
) -> ReplicaMediaTarget | None:
    """Return the confirmed, pinned target, or None, with no network call."""
    parser = argparse.ArgumentParser(prog="api_replica_media_smoke", add_help=False)
    parser.add_argument("--project", required=True)
    parser.add_argument("--isolation-bucket", required=True)
    try:
        parsed, extra = parser.parse_known_args(list(arguments))
    except SystemExit:
        return None
    endpoint_url = environ.get(_ENDPOINT_VARIABLE, "")
    bucket_name = environ.get(_BUCKET_VARIABLE, "")
    if (
        extra
        or environ.get(_CONFIRM_VARIABLE) != _CONFIRMATION
        or not _PROJECT_ID.fullmatch(parsed.project)
        or not _BUCKET_NAME.fullmatch(parsed.isolation_bucket)
        or parsed.isolation_bucket == bucket_name
    ):
        return None
    try:
        validate_media_target(endpoint_url, bucket_name)
    except ReplicaBindingError:
        return None
    return ReplicaMediaTarget(
        project=parsed.project,
        endpoint_url=endpoint_url,
        bucket_name=bucket_name,
        isolation_bucket=parsed.isolation_bucket,
    )


def _read_secret(project: str, secret_id: str) -> str:
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        raise _Failed("secret read")
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
        raise _Failed("secret read")
    return value


def _build(
    target: ReplicaMediaTarget, access_key_id: str, secret_access_key: str
) -> tuple[smoke.SmokeRuntime, IsolationBoundary]:
    import boto3
    import django

    from media.storage import _S3_CLIENT_CONFIG, S3MediaStorage

    django.setup()
    storage = S3MediaStorage(
        endpoint_url=target.endpoint_url,
        bucket_name=target.bucket_name,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region_name=_REGION,
    )
    client = boto3.client(
        "s3",
        endpoint_url=target.endpoint_url,
        region_name=_REGION,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=_S3_CLIENT_CONFIG,
    )
    boundary = S3IsolationBoundary(
        client=client,
        endpoint_url=target.endpoint_url,
        bucket_name=target.bucket_name,
        isolation_bucket=target.isolation_bucket,
    )
    return smoke.DefaultSmokeRuntime(storage=storage), boundary


def _isolation_results(
    runtime: smoke.SmokeRuntime, boundary: IsolationBoundary
) -> list[tuple[str, bool]]:
    """Run every isolation probe; cleanup always runs and is its own result."""
    results: list[tuple[str, bool]] = [
        ("list buckets denied", boundary.list_buckets() == "denied")
    ]
    other_key = runtime.create_key()
    put_verdict = boundary.put_other(key=other_key, content=runtime.canonical_content())
    if put_verdict != "denied":
        # A PUT that was not denied may have written the object. The result is
        # already a FAIL, so a cleanup error changes nothing.
        try:
            boundary.delete_other(key=other_key)
        except Exception:  # noqa: BLE001, S110 - cleanup is best effort here.
            pass
    results.append(("isolation bucket PUT denied", put_verdict == "denied"))
    results.append(
        (
            "isolation bucket GET denied",
            boundary.get_other(key=runtime.create_key()) == "denied",
        )
    )

    key = runtime.create_key()
    unsigned_stage = "unsigned GET denied"
    try:
        runtime.upload(key=key, content=runtime.canonical_content())
        verdict, status = boundary.unsigned_get(key=key)
        if status is not None:
            unsigned_stage = f"{unsigned_stage} (HTTP {status})"
        results.append((unsigned_stage, verdict == "denied"))
    except Exception:  # noqa: BLE001 - storage failures are sanitized.
        results.append((unsigned_stage, False))
    finally:
        try:
            runtime.delete(key=key)
            absent = not runtime.exists(key=key)
        except Exception:  # noqa: BLE001 - cleanup failures are sanitized.
            absent = False
        results.append(("unsigned object absent", absent))
    return results


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    build: Build = _build,
) -> int:
    """Run the guarded smoke and isolation probes; return the exit status."""
    target = parse_target(sys.argv[1:] if argv is None else argv, environ)
    if target is None:
        print("FAIL target configuration invalid", file=sys.stderr)
        return 1
    try:
        access_key_id, secret_access_key = (
            _read_secret(target.project, secret_id) for secret_id in _SECRET_IDS
        )
        runtime, boundary = build(target, access_key_id, secret_access_key)
    except _Failed as failure:
        print(f"FAIL {failure.stage}", file=sys.stderr)
        print("FAIL replica media smoke", file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 - initialization failures are sanitized.
        print("FAIL storage runtime", file=sys.stderr)
        print("FAIL replica media smoke", file=sys.stderr)
        return 1

    # The target was already checked above; the smoke keeps its own sequence.
    outcome = smoke.run(environ, runtime, target_valid=lambda _environment: True)
    results: list[tuple[str, bool]] = [("target replica media", True)]
    if outcome.primary_stage is not None:
        results.append((outcome.primary_stage, False))
    if outcome.cleanup_stage is not None:
        results.append((outcome.cleanup_stage, False))
    if outcome.succeeded:
        results.extend(
            (stage, True)
            for stage in (
                "upload",
                "object exists",
                "presigned GET bytes",
                "delete",
                "object absent",
            )
        )
    try:
        results.extend(_isolation_results(runtime, boundary))
    except Exception:  # noqa: BLE001 - probe failures are sanitized.
        results.append(("isolation probes", False))

    passed = all(ok for _stage, ok in results)
    for stage, ok in results:
        if ok:
            print(f"PASS {stage}")
        else:
            print(f"FAIL {stage}", file=sys.stderr)
    if passed:
        print("PASS replica media smoke")
        return 0
    print("FAIL replica media smoke", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
