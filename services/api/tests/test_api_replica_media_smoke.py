"""Behavioral contract for the guarded replica media smoke and isolation probe (#357).

Fakes stand only at real boundaries: gcloud for Secret Manager, the S3 API
(through botocore's Stubber), the unsigned HTTP request, and the smoke runtime.
"""

from __future__ import annotations

import email.message
import io
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

import boto3
import pytest
from botocore.stub import Stubber
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import api_replica_media_smoke as replica_smoke

from tests.replica_contract import MEDIA_BUCKET, MEDIA_ENDPOINT, install_replica_pins

PROJECT = "fake-replica-project"
ISOLATION_BUCKET = "tailtag-replica-isolation-probe"
ACCESS_KEY_ID = "synthetic-access-key-id-0123456789"
SECRET_ACCESS_KEY = "synthetic-secret-access-key-0123456789"
OBJECT_KEY = "images/123e4567e89b12d3a456426614174000.png"
VALID_ENVIRONMENT = {
    "TAILTAG_REPLICA_MEDIA_SMOKE_CONFIRM": "run-r2-replica-media-storage-smoke",
    "TAILTAG_REPLICA_MEDIA_ENDPOINT_URL": MEDIA_ENDPOINT,
    "TAILTAG_REPLICA_MEDIA_BUCKET": MEDIA_BUCKET,
}
VALID_ARGUMENTS = ["--project", PROJECT, "--isolation-bucket", ISOLATION_BUCKET]
PRIVATE_VALUES = (
    MEDIA_ENDPOINT,
    MEDIA_BUCKET,
    ISOLATION_BUCKET,
    ACCESS_KEY_ID,
    SECRET_ACCESS_KEY,
    OBJECT_KEY,
    "X-Amz-Signature",
)
SUCCESS_STAGES = (
    "target replica media",
    "upload",
    "object exists",
    "presigned GET bytes",
    "delete",
    "object absent",
    "list buckets denied",
    "isolation bucket PUT denied",
    "isolation bucket GET denied",
    "unsigned GET denied",
    "unsigned object absent",
    "replica media smoke",
)


@pytest.fixture(autouse=True)
def replica_pins(monkeypatch: MonkeyPatch) -> None:
    install_replica_pins(monkeypatch)


class MemoryRuntime:
    """In-memory stand-in for the live storage runtime of the smoke sequence."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.events: list[str] = []

    def create_key(self) -> str:
        return OBJECT_KEY

    def canonical_content(self) -> bytes:
        return b"synthetic-canonical-image"

    def upload(self, *, key: str, content: bytes) -> None:
        self.events.append("upload")
        self.objects[key] = content

    def exists(self, *, key: str) -> bool:
        return key in self.objects

    def presign_get(self, *, key: str, expires_in: int) -> str:
        assert expires_in == 600
        return f"https://synthetic.example.test/{key}?X-Amz-Signature=synthetic"

    def fetch(self, *, url: str) -> bytes:
        return self.objects[OBJECT_KEY]

    def delete(self, *, key: str) -> None:
        self.events.append("delete")
        self.objects.pop(key, None)


class FakeBoundary:
    """The isolation boundary, with each probe's result chosen by the test."""

    def __init__(self, results: Mapping[str, str] | None = None) -> None:
        self.results = {
            "list_buckets": "denied",
            "put_other": "denied",
            "get_other": "denied",
            "unsigned_get": "denied",
            **(results or {}),
        }
        self.calls: list[str] = []

    def list_buckets(self) -> str:
        self.calls.append("list_buckets")
        return self.results["list_buckets"]

    def put_other(self, *, key: str, content: bytes) -> str:
        self.calls.append("put_other")
        return self.results["put_other"]

    def get_other(self, *, key: str) -> str:
        self.calls.append("get_other")
        return self.results["get_other"]

    def delete_other(self, *, key: str) -> None:
        self.calls.append("delete_other")

    def unsigned_get(self, *, key: str) -> tuple[str, int | None]:
        self.calls.append("unsigned_get")
        verdict = self.results["unsigned_get"]
        return verdict, {"denied": 403, "allowed": 200}.get(verdict)


class Recorder:
    """Fake gcloud plus the build seam, recording what each one saw."""

    def __init__(self, boundary: FakeBoundary | None = None) -> None:
        self.commands: list[list[str]] = []
        self.built_with: tuple[str, str] | None = None
        self.runtime = MemoryRuntime()
        self.boundary = boundary or FakeBoundary()

    def gcloud(self, command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        secret = command[command.index("--secret") + 1]
        value = {
            "media-access-key-id": ACCESS_KEY_ID,
            "media-secret-access-key": SECRET_ACCESS_KEY,
        }[secret]
        return subprocess.CompletedProcess(command, 0, f"{value}\n", "")

    def build(
        self, target: Any, access_key_id: str, secret_access_key: str
    ) -> tuple[MemoryRuntime, FakeBoundary]:
        self.built_with = (access_key_id, secret_access_key)
        return self.runtime, self.boundary


def run_main(
    monkeypatch: MonkeyPatch,
    recorder: Recorder,
    *,
    arguments: list[str] | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    monkeypatch.setattr(replica_smoke.shutil, "which", fake_which)
    monkeypatch.setattr(replica_smoke.subprocess, "run", recorder.gcloud)
    return replica_smoke.main(
        VALID_ARGUMENTS if arguments is None else arguments,
        environ=VALID_ENVIRONMENT if environment is None else environment,
        build=recorder.build,
    )


def fake_which(name: str) -> str:
    return f"/fake/{name}"


def assert_private_values_hidden(output: str) -> None:
    for value in PRIVATE_VALUES:
        assert value not in output


@pytest.mark.parametrize(
    ("arguments", "environment"),
    (
        pytest.param(VALID_ARGUMENTS, {}, id="no-confirmation"),
        pytest.param(
            VALID_ARGUMENTS,
            {**VALID_ENVIRONMENT, "TAILTAG_REPLICA_MEDIA_SMOKE_CONFIRM": "yes"},
            id="wrong-confirmation",
        ),
        pytest.param(
            VALID_ARGUMENTS,
            {
                **VALID_ENVIRONMENT,
                "TAILTAG_REPLICA_MEDIA_ENDPOINT_URL": "https://storage.other.example.test",
            },
            id="unpinned-endpoint",
        ),
        pytest.param(
            VALID_ARGUMENTS,
            {
                **VALID_ENVIRONMENT,
                "TAILTAG_REPLICA_MEDIA_BUCKET": "tailtag-staging-media",
            },
            id="unpinned-bucket",
        ),
        pytest.param(
            ["--project", PROJECT, "--isolation-bucket", MEDIA_BUCKET],
            VALID_ENVIRONMENT,
            id="isolation-bucket-is-the-replica-bucket",
        ),
        pytest.param(
            ["--project", PROJECT, "--isolation-bucket", "Not_A_Bucket"],
            VALID_ENVIRONMENT,
            id="malformed-isolation-bucket",
        ),
        pytest.param(
            ["--project", "x", "--isolation-bucket", ISOLATION_BUCKET],
            VALID_ENVIRONMENT,
            id="malformed-project",
        ),
        pytest.param(["--project", PROJECT], VALID_ENVIRONMENT, id="missing-bucket"),
    ),
)
def test_target_guard_stops_before_secrets_storage_or_network(
    monkeypatch: MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    arguments: list[str],
    environment: Mapping[str, str],
) -> None:
    """AC15: only the confirmed, pinned replica bucket can be targeted."""
    recorder = Recorder()

    status = run_main(
        monkeypatch, recorder, arguments=arguments, environment=environment
    )

    assert status == 1
    assert recorder.commands == []
    assert recorder.built_with is None
    captured = capfd.readouterr()
    assert "FAIL target configuration invalid" in captured.err
    assert_private_values_hidden(captured.out + captured.err)


def test_success_reads_two_secrets_runs_every_stage_and_prints_no_private_value(
    monkeypatch: MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """AC15, AC16: round trip, four denials and cleanup, with fixed stage lines only."""
    recorder = Recorder()

    status = run_main(monkeypatch, recorder)

    assert status == 0
    secrets = [command[command.index("--secret") + 1] for command in recorder.commands]
    assert secrets == ["media-access-key-id", "media-secret-access-key"]
    assert all(
        command[1:5] == ["secrets", "versions", "access", "latest"]
        and command[command.index("--project") + 1] == PROJECT
        for command in recorder.commands
    )
    assert recorder.built_with == (ACCESS_KEY_ID, SECRET_ACCESS_KEY)
    assert recorder.runtime.objects == {}
    captured = capfd.readouterr()
    assert captured.out.splitlines() == [
        *(f"PASS {stage}" for stage in SUCCESS_STAGES[:9]),
        "PASS unsigned GET denied (HTTP 403)",
        *(f"PASS {stage}" for stage in SUCCESS_STAGES[10:]),
    ]
    assert_private_values_hidden(captured.out + captured.err)


@pytest.mark.parametrize(
    ("results", "failed_stage"),
    (
        pytest.param({"list_buckets": "allowed"}, "list buckets denied", id="list"),
        pytest.param({"put_other": "allowed"}, "isolation bucket PUT denied", id="put"),
        pytest.param({"get_other": "allowed"}, "isolation bucket GET denied", id="get"),
        pytest.param({"unsigned_get": "allowed"}, "unsigned GET denied", id="unsigned"),
        pytest.param({"get_other": "error"}, "isolation bucket GET denied", id="error"),
        pytest.param(
            {"put_other": "error"}, "isolation bucket PUT denied", id="put-error"
        ),
    ),
)
def test_any_access_beyond_the_replica_bucket_fails_and_still_cleans_up(
    monkeypatch: MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    results: Mapping[str, str],
    failed_stage: str,
) -> None:
    """AC15: an allowed or inconclusive probe fails; run-owned objects never survive."""
    boundary = FakeBoundary(results)
    recorder = Recorder(boundary)

    status = run_main(monkeypatch, recorder)

    assert status == 1
    assert recorder.runtime.objects == {}
    # A PUT that was not denied may have written, so cleanup is attempted.
    assert ("delete_other" in boundary.calls) is (
        results.get("put_other", "denied") != "denied"
    )
    captured = capfd.readouterr()
    assert any(
        line.startswith(f"FAIL {failed_stage}") for line in captured.err.splitlines()
    )
    assert "FAIL replica media smoke" in captured.err
    assert_private_values_hidden(captured.out + captured.err)


def test_secret_read_failure_stops_before_storage_and_hides_gcloud_output(
    monkeypatch: MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """AC15: a missing secret version fails closed without echoing gcloud text."""
    recorder = Recorder()

    def failing_gcloud(
        command: list[str], **_: Any
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command, 1, "", f"denied {SECRET_ACCESS_KEY}"
        )

    monkeypatch.setattr(replica_smoke.shutil, "which", fake_which)
    monkeypatch.setattr(replica_smoke.subprocess, "run", failing_gcloud)

    status = replica_smoke.main(
        VALID_ARGUMENTS, environ=VALID_ENVIRONMENT, build=recorder.build
    )

    assert status == 1
    assert recorder.built_with is None
    captured = capfd.readouterr()
    assert "FAIL secret read" in captured.err
    assert_private_values_hidden(captured.out + captured.err)


def stubbed_boundary(opener: Any = None) -> tuple[Any, Stubber]:
    client: Any = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=MEDIA_ENDPOINT,
        region_name="auto",
        aws_access_key_id=ACCESS_KEY_ID,
        aws_secret_access_key=SECRET_ACCESS_KEY,
    )
    stubber = Stubber(client)
    boundary = replica_smoke.S3IsolationBoundary(
        client=client,
        endpoint_url=MEDIA_ENDPOINT,
        bucket_name=MEDIA_BUCKET,
        isolation_bucket=ISOLATION_BUCKET,
        opener=opener,
    )
    return boundary, stubber


@pytest.mark.parametrize(
    ("operation", "error_code", "status", "expected"),
    (
        pytest.param("list_buckets", "AccessDenied", 403, "denied", id="list-403"),
        pytest.param("put_object", "AccessDenied", 403, "denied", id="put-403"),
        pytest.param("get_object", "AccessDenied", 403, "denied", id="get-403"),
        pytest.param("get_object", "Unauthorized", 401, "denied", id="get-401"),
        pytest.param(
            "get_object", "NoSuchKey", 404, "allowed", id="get-reaches-bucket"
        ),
        pytest.param("get_object", "NoSuchBucket", 404, "error", id="get-no-bucket"),
        pytest.param("put_object", "InternalError", 500, "error", id="put-500"),
    ),
)
def test_s3_boundary_counts_only_401_and_403_as_denied(
    operation: str, error_code: str, status: int, expected: str
) -> None:
    """AC15: reaching the bucket at all is not a denial; a missing bucket is inconclusive."""
    boundary, stubber = stubbed_boundary()
    stubber.add_client_error(
        operation, service_error_code=error_code, http_status_code=status
    )
    with stubber:
        verdict = {
            "list_buckets": lambda: boundary.list_buckets(),
            "put_object": lambda: boundary.put_other(key=OBJECT_KEY, content=b"x"),
            "get_object": lambda: boundary.get_other(key=OBJECT_KEY),
        }[operation]()

    assert verdict == expected


def test_s3_boundary_counts_success_as_allowed() -> None:
    boundary, stubber = stubbed_boundary()
    stubber.add_response("list_buckets", {"Buckets": []})
    with stubber:
        assert boundary.list_buckets() == "allowed"


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status


class RecordingOpener:
    def __init__(self, status: int) -> None:
        self.status = status
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, **_: object) -> _Response:
        self.requests.append(request)
        if self.status >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                self.status,
                "synthetic",
                email.message.Message(),
                io.BytesIO(b""),
            )
        return _Response(self.status)


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        pytest.param(401, ("denied", 401), id="401"),
        pytest.param(403, ("denied", 403), id="403"),
        pytest.param(400, ("error", 400), id="400"),
        pytest.param(404, ("error", 404), id="404"),
        pytest.param(429, ("error", 429), id="429"),
        pytest.param(200, ("allowed", 200), id="200"),
        pytest.param(500, ("error", 500), id="500"),
    ),
)
def test_unsigned_get_sends_no_credentials_and_counts_only_401_and_403_as_denied(
    status: int, expected: tuple[str, int]
) -> None:
    """AC15: the anonymous read goes to the pinned path-style object URL, unsigned."""
    opener = RecordingOpener(status)
    boundary, _ = stubbed_boundary(opener)

    assert boundary.unsigned_get(key=OBJECT_KEY) == expected
    (request,) = opener.requests
    assert request.full_url == f"{MEDIA_ENDPOINT}/{MEDIA_BUCKET}/{OBJECT_KEY}"
    assert request.get_method() == "GET"
    assert not any(
        name.lower() == "authorization" for name, _ in request.header_items()
    )
    assert "X-Amz" not in request.full_url
