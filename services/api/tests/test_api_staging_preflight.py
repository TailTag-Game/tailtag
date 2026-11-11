"""Offline acceptance contract for the credential-free Staging target guard."""

from __future__ import annotations

import importlib
import io
import json
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import HTTPMessage, IncompleteRead
from pathlib import Path
from types import ModuleType
from typing import NoReturn, Self, cast

import pytest
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_preflight.py"
STAGING_URL = "https://staging.tailtag.app"
SOURCE_SHA = "c070f413eec1518459f1fef21b471642765a54e9"
RAILWAY_SHAPED_DEPLOYMENT_ID = "93de11d6-714f-405a-b931-a9b567d5ec1e"
SECOND_SOURCE_SHA = "d" * 40
SENSITIVE_DIAGNOSTIC = "preflight-private-diagnostic-secret"

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@dataclass
class Response:
    """Small urllib-shaped response with bounded-read observations."""

    status: int = 200
    body: bytes = b"{}"
    url: str = STAGING_URL + "/health/identity"

    def __post_init__(self) -> None:
        self.read_sizes: list[int] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self.body if size < 0 else self.body[:size]


class RecordingOpener:
    """Normal urllib transport boundary, never a real outbound request."""

    def __init__(self, result: Response | BaseException) -> None:
        self.result = result
        self.calls: list[tuple[urllib.request.Request, dict[str, object]]] = []

    def open(self, request: urllib.request.Request, **kwargs: object) -> Response:
        self.calls.append((request, kwargs))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.fixture(autouse=True)
def no_ordinary_outbound_network(monkeypatch: MonkeyPatch) -> None:
    """A missing mock must fail offline rather than contact any destination."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("Staging preflight acceptance tests must remain offline")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)


@pytest.fixture
def preflight() -> ModuleType:
    """Load the small primitive only after its approved public file exists."""
    assert SCRIPT.is_file(), "scripts/api_staging_preflight.py must exist"
    return importlib.import_module("scripts.api_staging_preflight")


def identity(**overrides: object) -> dict[str, object]:
    """Return a valid public Render identity tuple and nothing else."""
    return {
        "source_sha": SOURCE_SHA,
        "deployment_id": None,
        "environment": "staging",
        **overrides,
    }


def ready(**overrides: object) -> dict[str, object]:
    """Return the only readiness body acceptable to a traffic guard."""
    return {"status": "ok", **overrides}


def fetch_sequence(
    monkeypatch: MonkeyPatch, preflight: ModuleType, responses: list[object]
) -> list[str]:
    """Install the approved normal-request seam and retain requested URLs."""
    calls: list[str] = []

    def fetch(url: str) -> object:
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    return calls


@pytest.mark.parametrize("source_sha", (SOURCE_SHA, SECOND_SOURCE_SHA))
def test_render_staging_returns_only_the_stable_observed_identity(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    source_sha: str,
) -> None:
    """AC-5/6/7: exact Staging origin, identity, readiness, and recheck all pass."""
    calls = fetch_sequence(
        monkeypatch,
        preflight,
        [
            identity(source_sha=source_sha),
            ready(),
            identity(source_sha=source_sha),
        ],
    )

    observed = preflight.validate_render_staging_target()

    assert observed == identity(source_sha=source_sha)
    assert set(observed) == {"source_sha", "deployment_id", "environment"}
    assert calls == [
        STAGING_URL + "/health/identity",
        STAGING_URL + "/health/ready",
        STAGING_URL + "/health/identity",
    ]


@pytest.mark.parametrize(
    "untrusted_identity",
    (
        {},
        {"source_sha": SOURCE_SHA, "deployment_id": None},
        {**identity(), "unexpected": SENSITIVE_DIAGNOSTIC},
        identity(source_sha=None),
        identity(source_sha=1),
        identity(source_sha=[]),
        identity(source_sha="A" * 40),
        identity(source_sha="a" * 39),
        identity(deployment_id=RAILWAY_SHAPED_DEPLOYMENT_ID),
        identity(deployment_id=1),
        identity(deployment_id=[]),
        identity(deployment_id="93DE11D6-714F-405A-B931-A9B567D5EC1E"),
        identity(deployment_id="not-a-uuid"),
        identity(environment="development"),
        identity(environment="production"),
        identity(environment="preview"),
        identity(environment=None),
        identity(environment=object()),
        [],
    ),
    ids=(
        "empty",
        "missing-environment",
        "extra-field",
        "null-sha",
        "integer-sha",
        "list-sha",
        "uppercase-sha",
        "short-sha",
        "railway-shaped-deployment-id",
        "integer-deployment-id",
        "list-deployment-id",
        "noncanonical-uuid",
        "malformed-uuid",
        "development",
        "production",
        "unknown-environment",
        "null-environment",
        "wrong-environment-type",
        "non-object",
    ),
)
def test_untrusted_first_identity_denies_before_readiness(
    preflight: ModuleType, monkeypatch: MonkeyPatch, untrusted_identity: object
) -> None:
    """AC-6/7: malformed, extra, null, or non-Staging identity is not sufficient."""
    calls = fetch_sequence(monkeypatch, preflight, [untrusted_identity])

    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_render_staging_target()

    assert calls == [STAGING_URL + "/health/identity"]


@pytest.mark.parametrize(
    "untrusted_readiness",
    (
        {},
        {"status": "unavailable"},
        {"status": "ok", "detail": SENSITIVE_DIAGNOSTIC},
        {"status": None},
        {"status": 200},
        [],
    ),
    ids=("empty", "unavailable", "extra-field", "null", "wrong-type", "non-object"),
)
def test_untrusted_readiness_denies_before_second_identity(
    preflight: ModuleType, monkeypatch: MonkeyPatch, untrusted_readiness: object
) -> None:
    """AC-2/6: only exact passing readiness permits the bounded identity recheck."""
    calls = fetch_sequence(
        monkeypatch,
        preflight,
        [identity(), untrusted_readiness],
    )

    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_render_staging_target()

    assert calls == [
        STAGING_URL + "/health/identity",
        STAGING_URL + "/health/ready",
    ]


def test_identity_change_during_preflight_denies_traffic(
    preflight: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """AC-6/7/8: readiness does not authorize a deployment that changed mid-check."""
    calls = fetch_sequence(
        monkeypatch,
        preflight,
        [
            identity(),
            ready(),
            identity(source_sha=SECOND_SOURCE_SHA),
        ],
    )

    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_render_staging_target()

    assert calls[-1] == STAGING_URL + "/health/identity"


def test_fetch_json_uses_one_proxy_free_no_redirect_bounded_https_request(
    preflight: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """AC-5/6/SECURITY: transport disables ambient proxies and redirect following."""
    response = Response(body=json.dumps(identity()).encode())
    opener = RecordingOpener(response)
    handlers: list[object] = []

    def build_opener(*provided_handlers: object) -> RecordingOpener:
        handlers.extend(provided_handlers)
        return opener

    monkeypatch.setattr(preflight.urllib.request, "build_opener", build_opener)

    assert preflight._fetch_json(STAGING_URL + "/health/identity") == identity()
    assert len(opener.calls) == 1
    request, options = opener.calls[0]
    assert request.full_url == STAGING_URL + "/health/identity"
    assert request.get_method() == "GET"
    assert options == {"timeout": 5}
    assert response.read_sizes == [4097]
    proxy_handlers = [
        handler
        for handler in handlers
        if isinstance(handler, urllib.request.ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert cast(dict[str, str], vars(proxy_handlers[0])["proxies"]) == {}
    redirect_handlers = [
        handler
        for handler in handlers
        if isinstance(handler, urllib.request.HTTPRedirectHandler)
    ]
    assert redirect_handlers
    redirect_request = urllib.request.Request(STAGING_URL + "/redirect")
    redirect_headers = HTTPMessage()
    redirect_headers["Location"] = STAGING_URL + "/health/identity"
    assert all(
        handler.redirect_request(
            redirect_request,
            io.BytesIO(),
            302,
            "Found",
            redirect_headers,
            STAGING_URL + "/health/identity",
        )
        is None
        for handler in redirect_handlers
    )


@pytest.mark.parametrize(
    "response",
    (
        Response(status=503, body=b'{"status":"unavailable"}'),
        Response(body=b"not-json"),
        Response(body=b"x" * 4097),
        Response(
            body=(
                b'{"source_sha":"c070f413eec1518459f1fef21b471642765a54e9",'
                b'"deployment_id":"93de11d6-714f-405a-b931-a9b567d5ec1e",'
                b'"environment":"development","environment":"staging"}'
            )
        ),
        Response(url="https://redirected.example/health/identity"),
    ),
    ids=(
        "unsuccessful-status",
        "invalid-json",
        "oversized",
        "duplicate-key",
        "redirect",
    ),
)
def test_fetch_json_denies_uncertain_or_redirected_http_response(
    preflight: ModuleType, monkeypatch: MonkeyPatch, response: Response
) -> None:
    """AC-6/9: status, JSON, size, duplicate keys, and redirects fail closed."""
    opener = RecordingOpener(response)

    def build_opener(*_: object) -> RecordingOpener:
        return opener

    monkeypatch.setattr(preflight.urllib.request, "build_opener", build_opener)

    with pytest.raises(preflight.TargetSafetyError):
        preflight._fetch_json(STAGING_URL + "/health/identity")


@pytest.mark.parametrize(
    "failure",
    (
        urllib.error.URLError(SENSITIVE_DIAGNOSTIC),
        TimeoutError(SENSITIVE_DIAGNOSTIC),
    ),
    ids=("transport", "timeout"),
)
def test_fetch_json_hides_network_failures(
    preflight: ModuleType, monkeypatch: MonkeyPatch, failure: BaseException
) -> None:
    """AC-6/9/RELIABILITY: unavailable transport cannot leak provider diagnostics."""
    opener = RecordingOpener(failure)

    def build_opener(*_: object) -> RecordingOpener:
        return opener

    monkeypatch.setattr(preflight.urllib.request, "build_opener", build_opener)

    with pytest.raises(preflight.TargetSafetyError) as raised:
        preflight._fetch_json(STAGING_URL + "/health/identity")

    assert SENSITIVE_DIAGNOSTIC not in str(raised.value)


def test_fetch_json_hides_incomplete_response_diagnostic(
    preflight: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """AC-6/9: truncated HTTP bodies are uncertain and cannot disclose their bytes."""
    opener = RecordingOpener(
        IncompleteRead(SENSITIVE_DIAGNOSTIC.encode("utf-8"), expected=4096)
    )

    def build_opener(*_: object) -> RecordingOpener:
        return opener

    monkeypatch.setattr(preflight.urllib.request, "build_opener", build_opener)

    with pytest.raises(preflight.TargetSafetyError) as raised:
        preflight._fetch_json(STAGING_URL + "/health/identity")

    assert SENSITIVE_DIAGNOSTIC not in str(raised.value)


def test_fetch_json_hides_recursion_failure_from_small_deeply_nested_json(
    preflight: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """AC-6/9: adversarial but bounded JSON parser failures deny without details."""
    deeply_nested_json = b"[" * 1100 + b"0" + b"]" * 1100
    assert len(deeply_nested_json) <= 4096
    opener = RecordingOpener(Response(body=deeply_nested_json))

    def build_opener(*_: object) -> RecordingOpener:
        return opener

    monkeypatch.setattr(preflight.urllib.request, "build_opener", build_opener)

    with pytest.raises(preflight.TargetSafetyError) as raised:
        preflight._fetch_json(STAGING_URL + "/health/identity")

    assert "RecursionError" not in str(raised.value)


def test_main_prints_only_validated_identity_json(
    preflight: ModuleType, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-7/9: CLI success emits only the captured three-field safe tuple."""

    def validated_identity() -> dict[str, object]:
        return identity()

    monkeypatch.setattr(preflight, "validate_render_staging_target", validated_identity)
    monkeypatch.setattr(sys, "argv", ["api_staging_preflight.py", "--render-staging"])

    assert preflight.main() == 0
    captured = capsys.readouterr()

    assert captured.err == ""
    assert json.loads(captured.out) == identity()
    assert set(json.loads(captured.out)) == {
        "source_sha",
        "deployment_id",
        "environment",
    }


@pytest.mark.parametrize(
    "arguments",
    (
        [],
        ["--render-staging", "unexpected"],
    ),
    ids=("missing", "extra"),
)
def test_main_denies_bad_argument_count_without_default_target(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    """AC-5/9: the CLI requires exactly one explicit safe target argument."""

    def unexpected_target() -> NoReturn:
        raise AssertionError("invalid arguments must not begin target validation")

    monkeypatch.setattr(preflight, "validate_render_staging_target", unexpected_target)
    monkeypatch.setattr(sys, "argv", ["api_staging_preflight.py", *arguments])

    assert preflight.main() == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert SENSITIVE_DIAGNOSTIC not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "argument", ("https://other.invalid", "https://staging.tailtag.app")
)
def test_main_denies_any_url_argument_before_transport(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argument: str,
) -> None:
    """#412: the retired URL form is refused; only the named Render flags run."""

    def unexpected_fetch(_: str) -> NoReturn:
        raise AssertionError("unsafe origin must not reach transport")

    monkeypatch.setattr(preflight, "_fetch_json", unexpected_fetch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_preflight.py", argument],
    )

    assert preflight.main() == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert SENSITIVE_DIAGNOSTIC not in captured.err
    assert "Traceback" not in captured.err


def test_main_sanitizes_preflight_failure(
    preflight: ModuleType, monkeypatch: MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-9/SECURITY: preflight diagnostics never cross the command boundary."""

    def denied() -> NoReturn:
        raise preflight.TargetSafetyError(SENSITIVE_DIAGNOSTIC)

    monkeypatch.setattr(preflight, "validate_render_staging_target", denied)
    monkeypatch.setattr(sys, "argv", ["api_staging_preflight.py", "--render-staging"])

    assert preflight.main() == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert SENSITIVE_DIAGNOSTIC not in captured.err
    assert "Traceback" not in captured.err
