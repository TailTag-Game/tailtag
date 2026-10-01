"""Acceptance tests for dependency health telemetry (#214).

Database attempts run through the real backend named by the real settings. Each
test builds its own connection so the suite's default connection is never
broken. Real failures (unknown role or database, a refused port, a server that
never answers) are preferred; the psycopg connect call is substituted only to
raise provider messages that cannot be produced safely here. Storage goes
through `S3MediaStorage` with the existing `client_factory` seam, plus one real
boto3 client against a local HTTP server to prove the count is per call, not
per internal retry. Signals are read back from the stdout JSON lines and the
Sentry metrics as sent. Contract values are written literally.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, NoReturn, cast

import psycopg
import pytest
import sentry_sdk
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.utils import ConnectionHandler, OperationalError
from django.test import Client, override_settings
from pytest import MonkeyPatch
from sentry_sdk.types import Metric

from config.settings.base import database_from_url
from media.storage import S3MediaStorage
from observability.dependencies import (
    DatabaseConnectionReason,
    DependencyOutcome,
    DependencySignal,
    StorageReason,
)
from observability.logging import ALLOWED_EXTRA_FIELDS
from observability.privacy import scrub_metric
from tests.observability_test_support import (
    CapturingTransport,
    JsonLogCapture,
    capture_json_stdout,
    identity,
    sentry_capturing,
)
from tests.test_health import LOCAL_STORAGES, configure_local_profile
from tests.test_media_storage import FakeS3Client, StaticClientFactory

ATTEMPTS = "tailtag.db.connection.attempts"
DURATION = "tailtag.db.connection.duration"
OPERATIONS = "tailtag.media.storage.operations"

EXPECTED_SIGNALS = {ATTEMPTS, DURATION, OPERATIONS}
EXPECTED_OUTCOMES = {"succeeded", "failed"}
EXPECTED_DATABASE_REASONS = {
    "timeout",
    "too_many_connections",
    "unreachable",
    "rejected",
    "other",
}
EXPECTED_STORAGE_REASONS = {
    "unavailable",
    "access_denied",
    "not_found",
    "throttled",
    "server_error",
    "other",
}
RPC_METHODS = ("PutObject", "GetObject", "HeadObject", "DeleteObject")

# Synthetic values that must never reach a metric attribute or a log line.
HOST = "sentinel-db-host.invalid"
ROLE = "sentinel_role_7f3a"
DATABASE = "sentinel_db_7f3a"
PASSWORD = "sentinel-password-7f3a"
PORT_PHRASE = "port 54329"
BUCKET = "sentinel-bucket-7f3a"
ENDPOINT = "https://sentinel-storage-host.invalid"
ACCESS_KEY = "sentinel-access-key-7f3a"
SECRET_KEY = "sentinel-secret-key-7f3a"
KEY_HEX = "5e47a1c0f00dfeedbeefcafe5e47a1c0"
KEY = f"images/{KEY_HEX}.jpg"
SIGNED_URL = "https://sentinel-signed.invalid/object?X-Amz-Signature=sentinelsig7f3a"
PROVIDER_TEXT = "sentinel-provider-response-7f3a"
STORAGE_MESSAGE = (
    f"{PROVIDER_TEXT} bucket={BUCKET} key={KEY} access={ACCESS_KEY} url={SIGNED_URL}"
)
SENTINELS = (
    HOST,
    ROLE,
    DATABASE,
    PASSWORD,
    PORT_PHRASE,
    BUCKET,
    ENDPOINT,
    "sentinel-storage-host",
    ACCESS_KEY,
    SECRET_KEY,
    KEY_HEX,
    "sentinelsig7f3a",
    PROVIDER_TEXT,
)

DATABASE_SENTINEL_OVERRIDES: dict[str, object] = {
    "HOST": HOST,
    "PORT": "54329",
    "USER": ROLE,
    "NAME": DATABASE,
    "PASSWORD": PASSWORD,
}


@dataclass(frozen=True)
class Observed:
    logs: JsonLogCapture
    transport: CapturingTransport

    def points(self, signal: str) -> list[dict[str, Any]]:
        """Metrics of one signal as sent, without the attributes the SDK adds itself."""
        sentry_sdk.flush()
        return [
            {
                "type": metric["type"],
                "value": metric["value"],
                "unit": metric.get("unit"),
                "attributes": {
                    key: entry["value"]
                    for key, entry in metric["attributes"].items()
                    if not key.startswith("sentry.")
                },
            }
            for metric in self.transport.metrics()
            if metric["name"] == signal
        ]

    def lines(self, signal: str) -> list[dict[str, Any]]:
        return [line for line in self.logs.lines() if line.get("event") == signal]

    def emitted_text(self) -> str:
        sentry_sdk.flush()
        return self.logs.text + self.transport.serialized()


@pytest.fixture
def observed() -> Iterator[Observed]:
    with sentry_capturing(identity()) as transport, capture_json_stdout() as logs:
        yield Observed(logs, transport)


def _assert_nothing_leaked(observed: Observed) -> None:
    text = observed.emitted_text()
    assert [sentinel for sentinel in SENTINELS if sentinel in text] == []


# --- AC-1: configuration ---


def test_database_configuration_uses_telemetry_backend_and_bounded_connect_timeout() -> (
    None
):
    """AC-1, AC-10: every environment built from a URL gets the backend and 5 seconds."""
    configuration = database_from_url("postgresql://user:secret@db.internal:5432/app")

    assert configuration["ENGINE"] == "observability.postgresql"
    options = cast(dict[str, object], configuration["OPTIONS"])
    assert options["connect_timeout"] == 5
    assert "pool" not in options
    assert configuration.get("CONN_MAX_AGE", 0) == 0


# --- AC-6: the privacy policy accepts exactly the dependency values ---


def _kept_attributes(key: str, value: str) -> dict[str, Any]:
    metric = cast(Metric, {"name": "tailtag.test.taxonomy", "attributes": {key: value}})
    return dict(scrub_metric(metric, None)["attributes"])


def test_taxonomy_is_frozen_and_every_value_survives_the_privacy_filter() -> None:
    """AC-6: a renamed value breaks dashboards; an unlisted one is silently dropped.

    Values go through `scrub_metric`, the production hook, so this fails if the
    allow-lists are not derived from the enumerations. An `rpc.method` outside
    the four storage calls must still be rejected, so the set stays bounded.
    """
    assert {str(signal) for signal in DependencySignal} >= EXPECTED_SIGNALS
    assert {str(outcome) for outcome in DependencyOutcome} >= EXPECTED_OUTCOMES
    assert {
        str(reason) for reason in DatabaseConnectionReason
    } >= EXPECTED_DATABASE_REASONS
    assert {str(reason) for reason in StorageReason} >= EXPECTED_STORAGE_REASONS

    for outcome in DependencyOutcome:
        assert _kept_attributes("tailtag.outcome", outcome) == {
            "tailtag.outcome": str(outcome)
        }
    for reason in (*DatabaseConnectionReason, *StorageReason):
        assert _kept_attributes("tailtag.reason", reason) == {
            "tailtag.reason": str(reason)
        }
    for method in RPC_METHODS:
        assert _kept_attributes("rpc.method", method) == {"rpc.method": method}
    assert _kept_attributes("rpc.method", "CopyObject") == {}
    assert "rpc_method" in ALLOWED_EXTRA_FIELDS


# --- Database: AC-2, AC-3, AC-5, AC-7 ---


def _isolated_connection(**overrides: object) -> BaseDatabaseWrapper:
    """A separate wrapper built from the real settings; the default one is untouched."""
    configured = {**settings.DATABASES["default"], **overrides}
    return ConnectionHandler({"default": configured})["default"]


def _raise_on_connect(monkeypatch: MonkeyPatch, error: BaseException) -> None:
    """Substitute only the psycopg connect call, to raise a provider message."""

    def connect(*_args: object, **_kwargs: object) -> NoReturn:
        raise error

    monkeypatch.setattr(psycopg, "connect", connect)


def _assert_one_attempt(
    observed: Observed, outcome: str, reason: str | None = None
) -> None:
    """Exactly one count and one duration, on both channels, with bounded attributes."""
    attributes = {"tailtag.outcome": outcome}
    if reason is not None:
        attributes["tailtag.reason"] = reason
    assert observed.points(ATTEMPTS) == [
        {"type": "counter", "value": 1.0, "unit": None, "attributes": attributes}
    ]
    [duration] = observed.points(DURATION)
    assert duration["type"] == "distribution"
    assert duration["unit"] == "millisecond"
    assert duration["value"] >= 0
    assert duration["attributes"] == {"tailtag.outcome": outcome}

    lines = observed.lines(ATTEMPTS)
    if outcome == "succeeded":
        assert lines == []
        return
    [line] = lines
    assert line["level"] == "warn"
    assert line["tailtag_outcome"] == outcome
    assert line.get("tailtag_reason") == reason
    assert isinstance(line["duration_ms"], (int, float))
    assert line["duration_ms"] >= 0
    _assert_nothing_leaked(observed)


@pytest.mark.django_db
def test_successful_connection_records_one_attempt_and_duration(
    observed: Observed,
) -> None:
    """AC-2: the real settings route new connections through the recording backend.

    Further queries on the open connection are not attempts.
    """
    wrapper = _isolated_connection()
    try:
        wrapper.ensure_connection()
        with wrapper.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.execute("SELECT 2")
    finally:
        wrapper.close()

    _assert_one_attempt(observed, "succeeded")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("message", "reason"),
    (
        pytest.param(
            f'connection failed: connection to server at "{HOST}", {PORT_PHRASE} failed: FATAL:  sorry, too many clients already',
            "too_many_connections",
            id="too-many-clients",
        ),
        pytest.param(
            f'connection failed: connection to server at "{HOST}", {PORT_PHRASE} failed: FATAL:  remaining connection slots are reserved for roles with the SUPERUSER attribute',
            "too_many_connections",
            id="reserved-slots",
        ),
        pytest.param(
            f'connection failed: could not translate host name "{HOST}" to address: Name or service not known',
            "unreachable",
            id="unresolvable-host",
        ),
        pytest.param(
            f'connection failed: connection to server at "{HOST}", {PORT_PHRASE} failed: FATAL:  no pg_hba.conf entry for host "{HOST}", user "{ROLE}", database "{DATABASE}", no encryption',
            "rejected",
            id="no-pg-hba-entry",
        ),
        pytest.param(
            f'SSL error: certificate verify failed for "{HOST}" (role {ROLE}, database {DATABASE}, password {PASSWORD})',
            "other",
            id="unrecognized",
        ),
    ),
)
def test_provider_messages_are_classified_and_the_original_error_propagates(
    observed: Observed, monkeypatch: MonkeyPatch, message: str, reason: str
) -> None:
    """AC-2, AC-3, AC-5, AC-7: each message class, carrying sentinels, yields its reason only."""
    raised = psycopg.OperationalError(message)
    _raise_on_connect(monkeypatch, raised)
    wrapper = _isolated_connection(**DATABASE_SENTINEL_OVERRIDES)

    with pytest.raises(OperationalError) as caught:
        wrapper.ensure_connection()

    assert caught.value.__cause__ is raised
    _assert_one_attempt(observed, "failed", reason)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        pytest.param({"USER": ROLE}, "rejected", id="unknown-role"),
        pytest.param({"NAME": DATABASE}, "rejected", id="unknown-database"),
    ),
)
def test_a_real_login_refusal_is_rejected(
    observed: Observed, overrides: dict[str, object], reason: str
) -> None:
    """AC-3, AC-7: the real server's wording for an unknown role or database."""
    wrapper = _isolated_connection(**overrides)

    with pytest.raises(OperationalError):
        wrapper.ensure_connection()

    _assert_one_attempt(observed, "failed", reason)


@pytest.mark.django_db
def test_a_real_refused_connection_is_unreachable(observed: Observed) -> None:
    """AC-3: libpq's refused-connection wording, from a port nothing listens on."""
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        closed_port = reserved.getsockname()[1]
    wrapper = _isolated_connection(HOST="127.0.0.1", PORT=str(closed_port))

    with pytest.raises(OperationalError):
        wrapper.ensure_connection()

    _assert_one_attempt(observed, "failed", "unreachable")


@pytest.mark.django_db
def test_an_endpoint_that_never_answers_fails_as_a_timeout_in_bounded_time(
    observed: Observed,
) -> None:
    """AC-1, AC-3: a real server that accepts TCP and stays silent.

    The configured value (5) is asserted above; waiting that long here would only
    slow the suite, so the real settings are used with the smallest timeout libpq
    honors (2 seconds). The wait must end near that bound, far below psycopg's
    130-second default and Gunicorn's 30-second worker timeout.
    """
    options = {**settings.DATABASES["default"].get("OPTIONS", {}), "connect_timeout": 2}
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen(1)
        wrapper = _isolated_connection(
            HOST="127.0.0.1", PORT=str(silent.getsockname()[1]), OPTIONS=options
        )
        started = time.monotonic()
        with pytest.raises(OperationalError):
            wrapper.ensure_connection()
        elapsed = time.monotonic() - started

    assert elapsed < 10
    _assert_one_attempt(observed, "failed", "timeout")


# --- AC-8: readiness ---


@pytest.mark.django_db
def test_readiness_stays_unavailable_and_records_the_failed_attempt(
    client: Client, monkeypatch: MonkeyPatch, observed: Observed
) -> None:
    """AC-8: same 503 and body; one recorded attempt with its reason, nothing leaked."""
    _raise_on_connect(
        monkeypatch,
        psycopg.OperationalError(
            f'connection failed: connection to server at "{HOST}", {PORT_PHRASE} failed: FATAL:  sorry, too many clients already'
        ),
    )
    configure_local_profile(monkeypatch)
    # Readiness reads `django.db.connection`; swap in a separate wrapper so the
    # suite's own connection is not disturbed.
    original = connections["default"]
    connections["default"] = _isolated_connection(**DATABASE_SENTINEL_OVERRIDES)
    try:
        with override_settings(
            DEBUG=True, CLERK_AUTHENTICATION=None, STORAGES=LOCAL_STORAGES
        ):
            response = client.get("/health/ready")
    finally:
        connections["default"] = original

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"
    _assert_one_attempt(observed, "failed", "too_many_connections")


# --- Storage: AC-4, AC-5, AC-7 ---


def _client_error(
    code: str, status: int, message: str = STORAGE_MESSAGE
) -> ClientError:
    response: dict[str, Any] = {
        "Error": {"Code": code, "Message": message},
        "ResponseMetadata": {"HTTPStatusCode": status},
    }
    return ClientError(cast(Any, response), "DeleteObject")


def _storage(client: FakeS3Client) -> S3MediaStorage:
    return S3MediaStorage(
        endpoint_url=ENDPOINT,
        bucket_name=BUCKET,
        region_name="auto",
        access_key_id=ACCESS_KEY,
        secret_access_key=SECRET_KEY,
        client_factory=StaticClientFactory(client),
    )


def _save(storage: S3MediaStorage) -> None:
    storage.save(KEY, ContentFile(b"content"))


def _open(storage: S3MediaStorage) -> None:
    storage.open(KEY)  # pyright: ignore[reportUnknownMemberType] - return type is irrelevant here.


def _exists(storage: S3MediaStorage) -> None:
    storage.exists(KEY)


def _size(storage: S3MediaStorage) -> None:
    storage.size(KEY)


def _delete(storage: S3MediaStorage) -> None:
    storage.delete(KEY)


# Every storage method that reaches the network, with the S3 call it makes.
STORAGE_CALLS: tuple[Any, ...] = (
    pytest.param(_save, "PutObject", id="save"),
    pytest.param(_open, "GetObject", id="open"),
    pytest.param(_exists, "HeadObject", id="exists"),
    pytest.param(_size, "HeadObject", id="size"),
    pytest.param(_delete, "DeleteObject", id="delete"),
)


def _assert_one_operation(
    observed: Observed, method: str, outcome: str, reason: str | None = None
) -> None:
    attributes = {"rpc.method": method, "tailtag.outcome": outcome}
    if reason is not None:
        attributes["tailtag.reason"] = reason
    assert observed.points(OPERATIONS) == [
        {"type": "counter", "value": 1.0, "unit": None, "attributes": attributes}
    ]
    lines = observed.lines(OPERATIONS)
    if outcome == "succeeded":
        assert lines == []
        return
    [line] = lines
    assert line["level"] == "warn"
    assert line["tailtag_outcome"] == outcome
    assert line.get("tailtag_reason") == reason
    assert line["rpc_method"] == method
    _assert_nothing_leaked(observed)


@pytest.mark.parametrize(("call", "method"), STORAGE_CALLS)
def test_each_storage_call_records_one_succeeded_operation(
    observed: Observed,
    call: Callable[[S3MediaStorage], None],
    method: str,
) -> None:
    """AC-4, AC-5: one count per call, named by the S3 operation; no success log line."""
    call(_storage(FakeS3Client()))

    _assert_one_operation(observed, method, "succeeded")


def test_a_missing_object_answered_by_exists_is_a_success(observed: Observed) -> None:
    """AC-4: `exists()` turns absence into its answer, so the call succeeded."""
    client = FakeS3Client()
    client.head_error = _client_error("NoSuchKey", 404)

    assert _storage(client).exists(KEY) is False

    _assert_one_operation(observed, "HeadObject", "succeeded")


def test_read_url_signing_records_nothing(observed: Observed) -> None:
    """AC-4: signing makes no network call, so it is not an operation."""
    _storage(FakeS3Client()).url(KEY)

    assert observed.points(OPERATIONS) == []
    assert observed.lines(OPERATIONS) == []


@pytest.mark.parametrize(("call", "method"), STORAGE_CALLS)
def test_each_failed_storage_call_names_its_operation_and_reraises(
    observed: Observed,
    call: Callable[[S3MediaStorage], None],
    method: str,
) -> None:
    """AC-4, AC-5: a failure keeps its operation name and the original error."""
    client = FakeS3Client()
    raised = _client_error("AccessDenied", 403)
    client.error = raised

    with pytest.raises(ClientError) as caught:
        call(_storage(client))

    assert caught.value is raised
    _assert_one_operation(observed, method, "failed", "access_denied")


FAILING_ENDPOINT_URL = f"{ENDPOINT}/{BUCKET}/{KEY}?X-Amz-Signature=sentinelsig7f3a"


@pytest.mark.parametrize(
    ("error", "reason"),
    (
        pytest.param(
            EndpointConnectionError(endpoint_url=FAILING_ENDPOINT_URL),
            "unavailable",
            id="endpoint-connection",
        ),
        pytest.param(
            ConnectTimeoutError(endpoint_url=FAILING_ENDPOINT_URL),
            "unavailable",
            id="connect-timeout",
        ),
        pytest.param(
            ReadTimeoutError(endpoint_url=FAILING_ENDPOINT_URL),
            "unavailable",
            id="read-timeout",
        ),
        pytest.param(
            _client_error("Unrecognized", 401), "access_denied", id="http-401"
        ),
        pytest.param(
            _client_error("Unrecognized", 403), "access_denied", id="http-403"
        ),
        pytest.param(
            _client_error("AccessDenied", 400), "access_denied", id="AccessDenied"
        ),
        pytest.param(
            _client_error("InvalidAccessKeyId", 400),
            "access_denied",
            id="InvalidAccessKeyId",
        ),
        pytest.param(
            _client_error("SignatureDoesNotMatch", 400),
            "access_denied",
            id="SignatureDoesNotMatch",
        ),
        pytest.param(_client_error("Unrecognized", 404), "not_found", id="http-404"),
        pytest.param(_client_error("NoSuchKey", 400), "not_found", id="NoSuchKey"),
        pytest.param(_client_error("Unrecognized", 429), "throttled", id="http-429"),
        pytest.param(_client_error("Unrecognized", 503), "throttled", id="http-503"),
        pytest.param(_client_error("SlowDown", 400), "throttled", id="SlowDown"),
        pytest.param(_client_error("Throttling", 400), "throttled", id="Throttling"),
        pytest.param(
            _client_error("RequestLimitExceeded", 400),
            "throttled",
            id="RequestLimitExceeded",
        ),
        pytest.param(
            _client_error("InternalError", 500), "server_error", id="http-500"
        ),
        pytest.param(_client_error("BadGateway", 502), "server_error", id="http-502"),
        pytest.param(_client_error("MalformedXML", 400), "other", id="client-error"),
        pytest.param(RuntimeError(STORAGE_MESSAGE), "other", id="non-provider-error"),
    ),
)
def test_storage_failures_are_classified_and_contained(
    observed: Observed, error: BaseException, reason: str
) -> None:
    """AC-4, AC-5, AC-7: each reason in the taxonomy, with sentinels in every message."""
    client = FakeS3Client()
    client.error = error

    with pytest.raises(type(error)) as caught:
        _storage(client).delete(KEY)

    assert caught.value is error
    _assert_one_operation(observed, "DeleteObject", "failed", reason)


class _ThrottlingHandler(BaseHTTPRequestHandler):
    """A local S3 stand-in that always answers 503 SlowDown and counts requests."""

    requests = 0

    def do_DELETE(self) -> None:
        type(self).requests += 1
        body = (
            '<?xml version="1.0" encoding="UTF-8"?><Error><Code>SlowDown</Code>'
            f"<Message>{STORAGE_MESSAGE}</Message></Error>"
        ).encode()
        self.send_response(503)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@contextmanager
def _throttling_endpoint() -> Generator[str]:
    _ThrottlingHandler.requests = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ThrottlingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_call_the_real_client_retries_is_still_one_operation(
    observed: Observed,
) -> None:
    """AC-4: counting sits at the storage call, not on boto's internal attempts.

    A real boto3 client (no factory) talks to a local HTTP server that throttles
    every request, so boto's standard retry mode really retries. The server sees
    more than one request; telemetry records one failed call.
    """
    with _throttling_endpoint() as endpoint:
        storage = S3MediaStorage(
            endpoint_url=endpoint,
            bucket_name=BUCKET,
            region_name="auto",
            access_key_id=ACCESS_KEY,
            secret_access_key=SECRET_KEY,
        )
        with pytest.raises(ClientError):
            storage.delete(KEY)
        attempts_seen = _ThrottlingHandler.requests

    assert attempts_seen > 1
    _assert_one_operation(observed, "DeleteObject", "failed", "throttled")
