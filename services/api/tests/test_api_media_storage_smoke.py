"""Behavioral contract for the guarded live media-storage smoke command."""

from __future__ import annotations

import builtins
import http.client
import io
import logging
import socket
import sys
import urllib.request
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import IO, NoReturn, Self
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from _pytest.capture import CaptureResult
from _pytest.logging import LogCaptureFixture
from django.core.files.storage import FileSystemStorage, InMemoryStorage
from PIL import Image
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import api_media_storage_smoke as smoke

VALID_ENVIRONMENT = {
    "RAILWAY_ENVIRONMENT_NAME": "development",
    "RAILWAY_SERVICE_NAME": "api",
    "TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM": "run-r2-development-media-storage-smoke",
}
SENSITIVE_VALUES = (
    "r2-development-bucket-synthetic",
    "https://synthetic.r2.example/private?X-Amz-Signature=synthetic-signature",
    "AKIA_SYNTHETIC_ACCESS_KEY",
    "synthetic-secret-access-key",
    "images/123e4567e89b12d3a456426614174000.png",
    "synthetic-response-body",
    "X-Amz-Signature=synthetic-signature",
)


class SensitiveSyntheticError(Exception):
    """An external-boundary error whose content must never be rendered."""


class RecordingRuntime:
    """Offline fake for the live operation boundaries, including cleanup faults."""

    def __init__(
        self,
        *,
        failure: str | None = None,
        object_survives_delete: bool = False,
    ) -> None:
        self.events: list[str] = []
        self.failure = failure
        self.object_survives_delete = object_survives_delete
        self.key = "images/123e4567e89b12d3a456426614174000.png"
        self.content = b"synthetic-canonical-image-content"
        self.url = (
            "https://synthetic.r2.example/private?"
            "X-Amz-Expires=600&X-Amz-Signature=synthetic-signature"
        )

    def _raise_when(self, stage: str) -> None:
        if self.failure == stage:
            raise SensitiveSyntheticError(
                "r2-development-bucket-synthetic "
                "AKIA_SYNTHETIC_ACCESS_KEY synthetic-secret-access-key "
                "https://synthetic.r2.example/private?"
                "X-Amz-Signature=synthetic-signature synthetic-response-body"
            )

    def create_key(self) -> str:
        self.events.append("create-key")
        self._raise_when("create-key")
        return self.key

    def canonical_content(self) -> bytes:
        self.events.append("canonical-content")
        self._raise_when("canonical-content")
        return self.content

    def upload(self, *, key: str, content: bytes) -> None:
        self.events.append("upload")
        assert key == self.key
        assert content == self.content
        self._raise_when("upload")

    def exists(self, *, key: str) -> bool:
        event = (
            "exists-after-delete" if "delete" in self.events else "exists-after-upload"
        )
        self.events.append(event)
        assert key == self.key
        self._raise_when(event)
        if event == "exists-after-upload":
            return self.failure != "missing-after-upload"
        return self.object_survives_delete

    def presign_get(self, *, key: str, expires_in: int) -> str:
        self.events.append("presign")
        assert key == self.key
        assert expires_in == 600
        self._raise_when("presign")
        return self.url

    def fetch(self, *, url: str) -> bytes:
        self.events.append("fetch")
        assert url == self.url
        self._raise_when("fetch")
        return b"different-bytes" if self.failure == "byte-mismatch" else self.content

    def delete(self, *, key: str) -> None:
        self.events.append("delete")
        assert key == self.key
        self._raise_when("delete")


class _Response:
    """Minimal injected HTTP response for concrete redirect-boundary tests."""

    def __init__(self, *, status: int, body: bytes = b"") -> None:
        self.status = status
        self.body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self.body


class RecordingOpener:
    """Concrete-runtime HTTP seam that makes any second (redirected) call visible."""

    def __init__(self, *responses: _Response) -> None:
        self.responses = list(responses)
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, **_kwargs: object) -> _Response:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("redirect handling made an unexpected extra request")
        return self.responses.pop(0)


class FakeS3MediaStorage:
    """Storage double that exposes the concrete Django storage operation contract."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []
        self.saved_content: bytes | None = None
        self.url_value = "https://synthetic.r2.example/private?X-Amz-Expires=600"

    def save(self, name: str, content: IO[bytes]) -> str:
        self.events.append(("save", name))
        self.saved_content = content.read()
        return name

    def exists(self, name: str) -> bool:
        self.events.append(("exists", name))
        return True

    def url(self, name: str) -> str:
        self.events.append(("url", name))
        return self.url_value

    def delete(self, name: str) -> None:
        self.events.append(("delete", name))


def prohibit_outbound_network(monkeypatch: MonkeyPatch) -> None:
    """Every ordinary test must replace its external boundaries explicitly."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("ordinary media smoke tests must remain offline")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(http.client.HTTPConnection, "request", no_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", no_network)
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", no_network)
    for client_type in (httpx.Client, httpx.AsyncClient):
        monkeypatch.setattr(client_type, "request", no_network)
        monkeypatch.setattr(client_type, "send", no_network)


@pytest.fixture(autouse=True)
def no_ordinary_outbound_network(monkeypatch: MonkeyPatch) -> None:
    prohibit_outbound_network(monkeypatch)


def assert_sanitized(
    outcome: object,
    captured: CaptureResult[str],
    caplog: LogCaptureFixture,
    *errors: BaseException,
) -> None:
    """Ensure untrusted storage material cannot cross a supported boundary."""
    rendered = "\n".join(
        (
            repr(outcome),
            captured.out,
            captured.err,
            caplog.text,
            *(f"{error!s}\n{error!r}" for error in errors),
        )
    )
    for value in SENSITIVE_VALUES:
        assert value not in rendered


@pytest.mark.parametrize(
    "environment",
    (
        {},
        {**VALID_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "Development"},
        {**VALID_ENVIRONMENT, "RAILWAY_SERVICE_NAME": "API"},
        {**VALID_ENVIRONMENT, "RAILWAY_SERVICE_NAME": "worker"},
        {**VALID_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "production"},
        {
            **VALID_ENVIRONMENT,
            "TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM": "yes",
        },
        {
            **VALID_ENVIRONMENT,
            "RAILWAY_ENVIRONMENT_NAME": (
                "development https://synthetic.r2.example/private?"
                "X-Amz-Signature=synthetic-signature"
            ),
        },
    ),
)
def test_invalid_or_non_development_target_stops_before_every_runtime_boundary(
    environment: Mapping[str, str],
) -> None:
    """Identity and fixed confirmation are exact, case-sensitive fail-closed guards."""
    runtime = RecordingRuntime()

    outcome = smoke.run(environment, runtime)

    assert not outcome.succeeded
    assert runtime.events == []


def test_successful_run_uses_only_the_required_order_and_exact_expiry() -> None:
    """The live path verifies the private object before and after its fixed-lifetime read."""
    runtime = RecordingRuntime()

    outcome = smoke.run(VALID_ENVIRONMENT, runtime)

    assert outcome.succeeded
    assert runtime.events == [
        "create-key",
        "canonical-content",
        "upload",
        "exists-after-upload",
        "presign",
        "fetch",
        "delete",
        "exists-after-delete",
    ]
    assert parse_qs(urlsplit(runtime.url).query) == {
        "X-Amz-Expires": ["600"],
        "X-Amz-Signature": ["synthetic-signature"],
    }


@pytest.mark.parametrize("storage", (FileSystemStorage(), InMemoryStorage()))
def test_concrete_runtime_rejects_local_or_in_memory_default_storage(
    monkeypatch: MonkeyPatch, storage: object
) -> None:
    """The opt-in command cannot silently fall back to local or in-memory storage."""
    monkeypatch.setattr(smoke, "storages", {"default": storage})

    with pytest.raises(smoke.SmokeFailure):
        smoke.DefaultSmokeRuntime()


def test_concrete_runtime_uses_django_s3_storage_for_get_presign_with_fixed_expiry(
    monkeypatch: MonkeyPatch,
) -> None:
    """The concrete adapter delegates reads to the configured S3 storage, never a URL shim."""
    storage = FakeS3MediaStorage()
    monkeypatch.setattr(smoke, "S3MediaStorage", FakeS3MediaStorage)
    monkeypatch.setattr(smoke, "storages", {"default": storage})

    runtime = smoke.DefaultSmokeRuntime()
    url = runtime.presign_get(
        key="images/123e4567e89b12d3a456426614174000.png", expires_in=600
    )

    assert url == storage.url_value
    assert storage.events == [("url", "images/123e4567e89b12d3a456426614174000.png")]
    assert parse_qs(urlsplit(url).query)["X-Amz-Expires"] == ["600"]
    with pytest.raises(smoke.SmokeFailure):
        runtime.presign_get(
            key="images/123e4567e89b12d3a456426614174000.png", expires_in=599
        )


def test_concrete_runtime_fetch_rejects_redirect_without_following_it(
    monkeypatch: MonkeyPatch,
) -> None:
    """Bearer reads are redirect-free so a signed URL cannot be forwarded elsewhere."""
    storage = FakeS3MediaStorage()
    monkeypatch.setattr(smoke, "S3MediaStorage", FakeS3MediaStorage)
    monkeypatch.setattr(smoke, "storages", {"default": storage})
    opener = RecordingOpener(_Response(status=302), _Response(status=200, body=b"bad"))

    runtime = smoke.DefaultSmokeRuntime(opener=opener)

    with pytest.raises(smoke.SmokeFailure):
        runtime.fetch(url=storage.url_value)
    assert len(opener.requests) == 1


def test_concrete_runtime_builds_a_no_redirect_default_opener(
    monkeypatch: MonkeyPatch,
) -> None:
    """The default bearer-URL client installs the explicit redirect-rejection handler."""
    storage = FakeS3MediaStorage()
    opener = RecordingOpener()
    captured_handlers: list[object] = []

    def build_opener(*handlers: object) -> RecordingOpener:
        captured_handlers.extend(handlers)
        return opener

    monkeypatch.setattr(smoke, "S3MediaStorage", FakeS3MediaStorage)
    monkeypatch.setattr(smoke, "storages", {"default": storage})
    monkeypatch.setattr(smoke.urllib.request, "build_opener", build_opener)

    runtime = smoke.DefaultSmokeRuntime()

    assert runtime._opener is opener  # pyright: ignore[reportPrivateUsage]
    no_redirect = next(
        handler
        for handler in captured_handlers
        if isinstance(handler, smoke._NoRedirect)  # pyright: ignore[reportPrivateUsage]
    )
    assert (
        no_redirect.redirect_request(
            urllib.request.Request(storage.url_value),
            None,
            302,
            "Found",
            {},
            "https://redirected.synthetic.example/",
        )
        is None
    )


def test_concrete_runtime_creates_opaque_key_and_in_memory_canonical_image(
    monkeypatch: MonkeyPatch,
) -> None:
    """Live input is generated in memory, canonicalized, and never read from a fixture."""
    storage = FakeS3MediaStorage()
    monkeypatch.setattr(smoke, "S3MediaStorage", FakeS3MediaStorage)
    monkeypatch.setattr(smoke, "storages", {"default": storage})
    expected_keys = iter(
        (
            "images/11111111111111111111111111111111.png",
            "images/22222222222222222222222222222222.png",
        )
    )
    requested_extensions: list[str] = []

    def create_image_key(extension: str) -> str:
        requested_extensions.append(extension)
        return next(expected_keys)

    def no_file_read(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError(
            "the media smoke must not read repository or user image data"
        )

    monkeypatch.setattr(builtins, "open", no_file_read)
    monkeypatch.setattr(io, "open", no_file_read)
    monkeypatch.setattr(Path, "read_bytes", no_file_read)
    monkeypatch.setattr(smoke, "create_image_key", create_image_key)
    runtime = smoke.DefaultSmokeRuntime()
    key = runtime.create_key()
    second_key = runtime.create_key()
    content = runtime.canonical_content()

    assert (key, second_key) == (
        "images/11111111111111111111111111111111.png",
        "images/22222222222222222222222222222222.png",
    )
    assert requested_extensions == ["png", "png"]
    assert isinstance(content, bytes)
    assert content
    with Image.open(BytesIO(content)) as image:
        assert image.format in {"JPEG", "PNG", "WEBP"}
        assert image.size == (1, 1)


@pytest.mark.parametrize(
    "failure",
    (
        "canonical-content",
        "upload",
        "exists-after-upload",
        "missing-after-upload",
        "presign",
        "fetch",
        "byte-mismatch",
    ),
)
def test_reachable_primary_failure_still_deletes_then_checks_absence(
    failure: str,
) -> None:
    """An allocated key always reaches both cleanup actions, regardless of primary failure."""
    runtime = RecordingRuntime(failure=failure)

    outcome = smoke.run(VALID_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert runtime.events[0] == "create-key"
    assert runtime.events[-2:] == ["delete", "exists-after-delete"]


@pytest.mark.parametrize("failure", ("delete", "exists-after-delete"))
def test_cleanup_errors_are_fatal_and_do_not_skip_the_independent_absence_check(
    failure: str,
) -> None:
    """Cleanup is not best effort: both operations run and either failure fails the smoke."""
    runtime = RecordingRuntime(failure=failure)

    outcome = smoke.run(VALID_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert runtime.events[-2:] == ["delete", "exists-after-delete"]


def test_surviving_object_after_delete_is_a_fatal_smoke_result() -> None:
    """A successful delete call is insufficient until absence is independently confirmed."""
    runtime = RecordingRuntime(object_survives_delete=True)

    outcome = smoke.run(VALID_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert runtime.events[-2:] == ["delete", "exists-after-delete"]


@pytest.mark.parametrize(
    ("object_survives_delete", "expected_exists"), ((False, False), (True, True))
)
def test_recording_runtime_models_storage_exists_after_delete(
    object_survives_delete: bool, expected_exists: bool
) -> None:
    """The offline fake retains Django Storage.exists semantics during cleanup."""
    runtime = RecordingRuntime(object_survives_delete=object_survives_delete)
    runtime.events.append("delete")

    assert runtime.exists(key=runtime.key) is expected_exists


@pytest.mark.parametrize(
    "environment",
    (
        {},
        {
            key: value
            for key, value in VALID_ENVIRONMENT.items()
            if key != "RAILWAY_ENVIRONMENT_NAME"
        },
        {
            key: value
            for key, value in VALID_ENVIRONMENT.items()
            if key != "RAILWAY_SERVICE_NAME"
        },
        {
            key: value
            for key, value in VALID_ENVIRONMENT.items()
            if key != "TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM"
        },
        {**VALID_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "Development"},
        {**VALID_ENVIRONMENT, "RAILWAY_SERVICE_NAME": "API"},
        {**VALID_ENVIRONMENT, "RAILWAY_SERVICE_NAME": "worker"},
        {**VALID_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "production"},
        {**VALID_ENVIRONMENT, "TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM": "yes"},
        {
            **VALID_ENVIRONMENT,
            "RAILWAY_ENVIRONMENT_NAME": (
                "development https://synthetic.r2.example/private?"
                "X-Amz-Signature=synthetic-signature"
            ),
        },
    ),
)
def test_main_rejects_every_invalid_identity_before_django_or_runtime_initialization(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    environment: Mapping[str, str],
) -> None:
    """Every bad target fails before either concrete initialization boundary."""
    constructed = False
    setup_called = False

    def fail_if_constructed() -> RecordingRuntime:
        nonlocal constructed
        constructed = True
        raise AssertionError("runtime construction must follow target validation")

    def fail_if_setup() -> None:
        nonlocal setup_called
        setup_called = True
        raise AssertionError("Django setup must follow target validation")

    monkeypatch.setattr(smoke, "DefaultSmokeRuntime", fail_if_constructed)
    monkeypatch.setattr(sys, "argv", ["api_media_storage_smoke.py"])
    monkeypatch.setattr(smoke.os, "environ", environment)
    monkeypatch.setattr(smoke.django, "setup", fail_if_setup)

    assert smoke.main() != 0
    assert not constructed
    assert not setup_called
    captured = capsys.readouterr()
    assert captured.err == "FAIL target configuration invalid\n"
    for value in SENSITIVE_VALUES:
        assert value not in captured.out + captured.err


def test_main_rejects_arguments_before_django_or_runtime_initialization(
    monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The only supported entry point has no CLI arguments or secret flags."""
    constructed = False
    setup_called = False

    def fail_if_constructed() -> RecordingRuntime:
        nonlocal constructed
        constructed = True
        raise AssertionError("runtime construction must follow argument validation")

    def fail_if_setup() -> None:
        nonlocal setup_called
        setup_called = True
        raise AssertionError("Django setup must follow argument validation")

    monkeypatch.setattr(smoke, "DefaultSmokeRuntime", fail_if_constructed)
    monkeypatch.setattr(smoke.django, "setup", fail_if_setup)
    monkeypatch.setattr(sys, "argv", ["api_media_storage_smoke.py", "--unsafe"])

    assert smoke.main() != 0
    assert not constructed
    assert not setup_called
    assert capsys.readouterr().err == "FAIL media storage smoke arguments invalid\n"


def test_main_output_is_fixed_stage_level_and_suppresses_hostile_storage_details(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    """Operator output exposes only safe target/stage status, never boundary material."""
    runtime = RecordingRuntime(failure="fetch")
    monkeypatch.setattr(smoke, "DefaultSmokeRuntime", lambda: runtime)
    monkeypatch.setattr(sys, "argv", ["api_media_storage_smoke.py"])
    monkeypatch.setattr(smoke.os, "environ", VALID_ENVIRONMENT)
    caplog.set_level(logging.DEBUG)

    assert smoke.main() != 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL presigned GET bytes\nFAIL media storage smoke\n"
    assert_sanitized(smoke.run(VALID_ENVIRONMENT, runtime), captured, caplog)


def test_main_success_reports_only_safe_pass_stages(
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    """A live success reports the safe target and fixed successes, never object details."""
    runtime = RecordingRuntime()
    monkeypatch.setattr(smoke, "DefaultSmokeRuntime", lambda: runtime)
    monkeypatch.setattr(sys, "argv", ["api_media_storage_smoke.py"])
    monkeypatch.setattr(smoke.os, "environ", VALID_ENVIRONMENT)
    caplog.set_level(logging.DEBUG)

    assert smoke.main() == 0

    output = capsys.readouterr().out
    assert output.splitlines() == [
        "PASS target development/api",
        "PASS upload",
        "PASS object exists",
        "PASS presigned GET bytes",
        "PASS delete",
        "PASS object absent",
        "PASS media storage smoke",
    ]
    assert caplog.text == ""
    for value in SENSITIVE_VALUES:
        assert value not in output
