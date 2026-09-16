"""Offline acceptance contract for the guarded Staging Clerk smoke command."""

from __future__ import annotations

import getpass
import hashlib
import http.client
import importlib
import json
import socket
import sys
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, NoReturn, Protocol, Self, cast

import httpx
import jwt
import pytest
from _pytest.capture import CaptureResult
from clerk_backend_api import Clerk
from clerk_backend_api.models import Session
from clerk_backend_api.types import UNSET
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.http import HttpRequest
from pytest import MonkeyPatch
from rest_framework.exceptions import AuthenticationFailed

from authentication.clerk import ClerkSessionVerifier, ClerkVerificationConfiguration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_auth_smoke.py"
STAGING_URL = "https://staging.tailtag.app"
SYNTHETIC_USER_ID = "user_staging_smoke_synthetic"
SYNTHETIC_SESSION_ID = "sess_staging_smoke_synthetic"
PROMPTED_SECRET = "sk_live_staging_smoke_synthetic"
PROMPTED_TOKEN = "eyJ.synthetic.staging-session-token"
STAGING_ENVIRONMENT = {
    "RAILWAY_ENVIRONMENT_NAME": "staging",
    "RAILWAY_SERVICE_NAME": "api",
    "TAILTAG_STAGING_AUTH_SMOKE_CONFIRM": "run-clerk-staging-auth-smoke",
    "API_BASE_URL": STAGING_URL,
    "TAILTAG_STAGING_API_BASE_URL": STAGING_URL,
    "CLERK_STAGING_SMOKE_USER_ID": SYNTHETIC_USER_ID,
}
SENSITIVE_VALUES = (
    PROMPTED_SECRET,
    PROMPTED_TOKEN,
    SYNTHETIC_SESSION_ID,
    "sk_live_from_environment_must_not_be_read",
)
SYNTHETIC_PORTAL_ORIGIN = "https://accounts.staging.synthetic.invalid"
SYNTHETIC_INSTANCE_ID = "ins_staging_synthetic"
FROZEN_INSTANCE_FINGERPRINT = "eb6daf25d12b85eb"
FROZEN_PORTAL_ORIGIN = "https://accounts.staging.tailtag.app"
SUCCESS_LINES = (
    "PASS target staging/api",
    "PASS baseline API smoke",
    "PASS Clerk Production instance",
    "PASS synthetic user",
    "PASS session token",
    "PASS authenticated API",
    "PASS cleanup",
    "PASS Staging authenticated API smoke",
)
FAILURE_LINES = {
    "target": "FAIL target staging/api",
    "baseline": "FAIL baseline API smoke",
    "prompt-secret": "FAIL hidden input",
    "instance": "FAIL Clerk Production instance",
    "user": "FAIL synthetic user",
    "prompt-session": "FAIL smoke-only session",
    "session-get": "FAIL smoke-only session",
    "verify": "FAIL session token",
    "api-me": "FAIL authenticated API",
    "cleanup": "FAIL cleanup",
}


def prohibit_outbound_network(monkeypatch: MonkeyPatch) -> None:
    """The contract permits only injected Clerk and HTTP boundaries."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError("Staging auth smoke acceptance tests must remain offline")

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


@pytest.fixture
def staging_smoke() -> ModuleType:
    assert SCRIPT.is_file(), "scripts/api_staging_auth_smoke.py must exist"
    return importlib.import_module("scripts.api_staging_auth_smoke")


class SmokeOutcome(Protocol):
    @property
    def succeeded(self) -> bool: ...

    @property
    def cleanup_failed(self) -> bool: ...


@dataclass
class RecordingRuntime:
    """The approved orchestration seam, with no live provider or API access."""

    failure: str | None = None
    private_value: str = PROMPTED_TOKEN

    def __post_init__(self) -> None:
        self.events: list[str] = []

    def _fail(self, stage: str) -> None:
        if self.failure == stage:
            raise RuntimeError(f"private {stage} failure: {self.private_value}")
        if self.failure == f"{stage}-interrupt":
            raise KeyboardInterrupt
        if self.failure == f"{stage}-eof":
            raise EOFError

    def run_baseline(self, *, base_url: str) -> bool:
        self.events.append("baseline")
        assert base_url == STAGING_URL
        self._fail("baseline")
        return True

    def prompt_secret(self) -> str:
        self.events.append("prompt-secret")
        self._fail("prompt-secret")
        return PROMPTED_SECRET

    def validate_production_instance(self, *, secret: str) -> None:
        self.events.append("instance")
        assert secret == PROMPTED_SECRET
        self._fail("instance")

    def validate_synthetic_user(self, *, secret: str, user_id: str) -> None:
        self.events.append("user")
        assert secret == PROMPTED_SECRET
        assert user_id == SYNTHETIC_USER_ID
        self._fail("user")

    def prompt_session_id(self) -> str:
        self.events.append("prompt-session")
        self._fail("prompt-session")
        return SYNTHETIC_SESSION_ID

    def get_selected_session(
        self, *, secret: str, session_id: str, user_id: str
    ) -> None:
        self.events.append("session-get")
        assert secret == PROMPTED_SECRET
        assert session_id == SYNTHETIC_SESSION_ID
        assert user_id == SYNTHETIC_USER_ID
        self._fail("session-get")

    def prompt_session_token(self) -> str:
        self.events.append("prompt-token")
        self._fail("prompt-token")
        return PROMPTED_TOKEN

    def verify_session_token(
        self, *, token: str, session_id: str, user_id: str
    ) -> None:
        self.events.append("verify")
        assert token == PROMPTED_TOKEN
        assert session_id == SYNTHETIC_SESSION_ID
        assert user_id == SYNTHETIC_USER_ID
        self._fail("verify")

    def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
        self.events.append("api-me")
        assert base_url == STAGING_URL
        assert bearer_token == PROMPTED_TOKEN
        self._fail("api-me")

    def revoke_selected_session(self, *, secret: str, session_id: str) -> None:
        self.events.append("cleanup")
        assert secret == PROMPTED_SECRET
        assert session_id == SYNTHETIC_SESSION_ID
        self._fail("cleanup")


@dataclass(frozen=True)
class FakeInstance:
    id: str = SYNTHETIC_INSTANCE_ID
    environment_type: str = "production"


@dataclass(frozen=True)
class FakeUser:
    id: str = SYNTHETIC_USER_ID
    public_metadata: object = None


@dataclass(frozen=True)
class FakeSession:
    id: str = SYNTHETIC_SESSION_ID
    user_id: str = SYNTHETIC_USER_ID
    status: str = "active"
    actor: object = None


class FakeSessions:
    """Strict Clerk session boundary: only get and revoke are available."""

    def __init__(
        self,
        selected: FakeSession,
        revoked: FakeSession,
        get_error: BaseException | None = None,
    ) -> None:
        self.selected = selected
        self.revoked = revoked
        self.get_error = get_error
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.forbidden_attempts: list[str] = []

    def get(self, *, session_id: str) -> FakeSession:
        self.calls.append(("get", {"session_id": session_id}))
        if self.get_error is not None:
            raise self.get_error
        return self.selected

    def revoke(self, *, session_id: str) -> FakeSession:
        self.calls.append(("revoke", {"session_id": session_id}))
        return self.revoked

    def __getattr__(self, name: str) -> NoReturn:
        self.forbidden_attempts.append(name)
        raise AssertionError(f"unsupported Clerk session operation: {name}")


class FakeClerk:
    """Narrow fake matching the provider resources named by the frozen contract."""

    def __init__(
        self,
        *,
        instance: FakeInstance | None = None,
        user: FakeUser | None = None,
        selected: FakeSession | None = None,
        revoked: FakeSession | None = None,
        get_error: BaseException | None = None,
    ) -> None:
        self.instance = instance or FakeInstance()
        self.user = user or FakeUser(
            public_metadata={
                "tailtag_environment": "staging",
                "tailtag_synthetic": True,
            }
        )
        self.instance_settings = self
        self.users = self
        self.sessions = FakeSessions(
            selected := selected or FakeSession(),
            revoked
            or FakeSession(
                id=selected.id,
                user_id=selected.user_id,
                status="revoked",
                actor=selected.actor,
            ),
            get_error,
        )
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.forbidden_root_attempts: list[str] = []

    def get(self, **kwargs: str) -> FakeInstance | FakeUser:
        self.calls.append(("user" if kwargs else "instance", kwargs))
        return self.user if kwargs else self.instance

    def __getattr__(self, name: str) -> NoReturn:
        self.forbidden_root_attempts.append(name)
        raise AssertionError(f"unsupported Clerk root operation: {name}")


@dataclass
class ApiResponse:
    status: int
    body: bytes
    url: str = ""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def read(self) -> bytes:
        return self.body


class RecordingOpener:
    def __init__(self, response: ApiResponse) -> None:
        self.response = response
        self.requests: list[urllib.request.Request] = []

    def open(self, request: urllib.request.Request, **_kwargs: object) -> ApiResponse:
        self.requests.append(request)
        self.response.url = request.full_url
        return self.response


def instance_fingerprint(instance_id: str = SYNTHETIC_INSTANCE_ID) -> str:
    return hashlib.sha256(instance_id.encode("utf-8")).hexdigest()[:16]


def staging_verifier(signing_key: rsa.RSAPrivateKey) -> ClerkSessionVerifier:
    public_key = signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return ClerkSessionVerifier(
        ClerkVerificationConfiguration(
            jwt_key=public_key.decode("ascii"),
            authorized_parties=(SYNTHETIC_PORTAL_ORIGIN,),
        )
    )


def issue_session_token(
    signing_key: rsa.RSAPrivateKey,
    overrides: Mapping[str, object] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sid": SYNTHETIC_SESSION_ID,
        "sub": SYNTHETIC_USER_ID,
        "azp": SYNTHETIC_PORTAL_ORIGIN,
        "iat": now,
        "nbf": now - 1,
        "exp": now + 60,
    }
    if overrides:
        claims.update(overrides)
    return jwt.encode(claims, signing_key, algorithm="RS256")


def concrete_runtime(
    staging_smoke: ModuleType,
    *,
    clerk: FakeClerk,
    verifier: object,
    opener: RecordingOpener,
) -> object:
    def clerk_factory(_secret: str) -> FakeClerk:
        return clerk

    return staging_smoke.DefaultSmokeRuntime(
        clerk_factory=clerk_factory,
        verifier=verifier,
        opener=opener,
    )


def run(
    staging_smoke: ModuleType, environment: Mapping[str, str], runtime: RecordingRuntime
) -> SmokeOutcome:
    return cast(SmokeOutcome, staging_smoke.run(environment, runtime))


def assert_no_sensitive_output(captured: CaptureResult[str]) -> None:
    rendered = captured.out + captured.err
    for value in SENSITIVE_VALUES:
        assert value not in rendered


def test_staging_auth_smoke_entry_point_exists() -> None:
    """AC-4: Staging has its own Clerk Production live entry point."""
    assert SCRIPT.is_file(), "scripts/api_staging_auth_smoke.py must exist"


def test_canonical_production_instance_and_portal_origin_are_frozen_public_constants(
    staging_smoke: ModuleType,
) -> None:
    """AC-4 SECURITY: Staging identity is not a configurable operator choice."""
    assert (
        staging_smoke.STAGING_CLERK_INSTANCE_FINGERPRINT == FROZEN_INSTANCE_FINGERPRINT
    )
    assert staging_smoke.STAGING_CLERK_PORTAL_ORIGIN == FROZEN_PORTAL_ORIGIN


def test_authoritative_staging_flow_orders_selection_before_cleanup_and_token_use(
    staging_smoke: ModuleType,
) -> None:
    """AC-4/SECURITY: only authoritative selected-session state can reach the API."""
    runtime = RecordingRuntime()

    outcome = run(staging_smoke, STAGING_ENVIRONMENT, runtime)

    assert outcome.succeeded
    assert not outcome.cleanup_failed
    assert runtime.events == [
        "baseline",
        "prompt-secret",
        "instance",
        "user",
        "prompt-session",
        "session-get",
        "prompt-token",
        "verify",
        "api-me",
        "cleanup",
    ]


@pytest.mark.parametrize(
    "environment",
    (
        {},
        {**STAGING_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "Development"},
        {**STAGING_ENVIRONMENT, "RAILWAY_ENVIRONMENT_NAME": "production"},
        {**STAGING_ENVIRONMENT, "RAILWAY_SERVICE_NAME": "API"},
        {
            **STAGING_ENVIRONMENT,
            "TAILTAG_STAGING_AUTH_SMOKE_CONFIRM": "wrong-confirmation",
        },
        {
            key: value
            for key, value in STAGING_ENVIRONMENT.items()
            if key != "API_BASE_URL"
        },
        {
            **STAGING_ENVIRONMENT,
            "TAILTAG_STAGING_API_BASE_URL": "https://other.invalid",
        },
        {
            **STAGING_ENVIRONMENT,
            "API_BASE_URL": "https://other.invalid",
            "TAILTAG_STAGING_API_BASE_URL": "https://other.invalid",
        },
        {
            **STAGING_ENVIRONMENT,
            "API_BASE_URL": "https://user:pass@staging.tailtag.app",
        },
        {**STAGING_ENVIRONMENT, "API_BASE_URL": f"{STAGING_URL}/"},
        {**STAGING_ENVIRONMENT, "API_BASE_URL": f"{STAGING_URL}/api/me/"},
        {**STAGING_ENVIRONMENT, "API_BASE_URL": f"{STAGING_URL}?x=1"},
        {**STAGING_ENVIRONMENT, "API_BASE_URL": f"{STAGING_URL}#fragment"},
        {**STAGING_ENVIRONMENT, "API_BASE_URL": "http://staging.tailtag.app"},
        {**STAGING_ENVIRONMENT, "API_BASE_URL": "HTTPS://staging.tailtag.app"},
    ),
)
def test_only_exact_staging_target_is_accepted_before_prompt_or_provider_access(
    staging_smoke: ModuleType, environment: Mapping[str, str]
) -> None:
    """AC-2/4/9 SECURITY: malformed or non-Staging target metadata fails closed."""
    runtime = RecordingRuntime()

    outcome = run(staging_smoke, environment, runtime)

    assert not outcome.succeeded
    assert not outcome.cleanup_failed
    assert runtime.events == []


@pytest.mark.parametrize(
    "bad_secret", ("", "sk_test_not_production", "sk_live", "pk_live_x")
)
def test_non_production_secret_form_fails_before_provider_access(
    staging_smoke: ModuleType, bad_secret: str
) -> None:
    """AC-4 SECURITY: only a hidden Production backend secret reaches Clerk."""
    runtime = RecordingRuntime()
    runtime.prompt_secret = lambda: bad_secret  # type: ignore[method-assign]

    outcome = run(staging_smoke, STAGING_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert runtime.events == ["baseline"]


def test_ambient_clerk_credentials_are_not_an_input_path(
    staging_smoke: ModuleType,
) -> None:
    """AC-4 SECURITY: only the hidden prompt supplies the backend secret."""

    class EnvironmentGuard(Mapping[str, str]):
        def __iter__(self):
            return iter(STAGING_ENVIRONMENT)

        def __len__(self) -> int:
            return len(STAGING_ENVIRONMENT)

        def __getitem__(self, key: str) -> str:
            if key in {"CLERK_SECRET", "CLERK_SECRET_KEY", "CLERK_API_KEY"}:
                raise AssertionError(f"ambient Clerk credential accessed: {key}")
            return STAGING_ENVIRONMENT[key]

    runtime = RecordingRuntime()
    outcome = run(staging_smoke, EnvironmentGuard(), runtime)

    assert outcome.succeeded
    assert runtime.events[-1] == "cleanup"


@pytest.mark.parametrize(
    "failure",
    ("prompt-token", "prompt-token-interrupt", "prompt-token-eof", "verify", "api-me"),
)
def test_every_post_selection_failure_revokes_the_selected_session(
    staging_smoke: ModuleType, failure: str
) -> None:
    """AC-4/SECURITY: token prompt and verification cannot strand an owned session."""
    runtime = RecordingRuntime(failure=failure)

    outcome = run(staging_smoke, STAGING_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert runtime.events[-1] == "cleanup"
    assert runtime.events[:6] == [
        "baseline",
        "prompt-secret",
        "instance",
        "user",
        "prompt-session",
        "session-get",
    ]


@pytest.mark.parametrize("failure", ("prompt-session", "session-get"))
def test_no_cleanup_or_provider_mutation_precedes_authoritative_selection(
    staging_smoke: ModuleType, failure: str
) -> None:
    """AC-4/SECURITY: cleanup ownership starts only after exact sessions.get selection."""
    runtime = RecordingRuntime(failure=failure)

    outcome = run(staging_smoke, STAGING_ENVIRONMENT, runtime)

    assert not outcome.succeeded
    assert "cleanup" not in runtime.events
    assert "prompt-token" not in runtime.events
    assert "verify" not in runtime.events
    assert "api-me" not in runtime.events


def test_cleanup_failure_has_priority_over_an_earlier_primary_failure(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-4/RELIABILITY: a failed revoke is never masked by token/API failure."""
    runtime = RecordingRuntime(failure="verify")

    def failed_cleanup(*, secret: str, session_id: str) -> None:
        runtime.events.append("cleanup")
        raise RuntimeError("private revoke error")

    runtime.revoke_selected_session = failed_cleanup  # type: ignore[method-assign]
    outcome = run(staging_smoke, STAGING_ENVIRONMENT, runtime)
    assert not outcome.succeeded
    assert outcome.cleanup_failed

    monkeypatch.setattr(staging_smoke, "DefaultSmokeRuntime", lambda: runtime)
    monkeypatch.setattr(staging_smoke.os, "environ", STAGING_ENVIRONMENT)
    monkeypatch.setattr(sys, "argv", ["api_staging_auth_smoke.py"])
    assert staging_smoke.main() != 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL cleanup\n"
    assert_no_sensitive_output(captured)


def test_main_emits_only_the_fixed_success_stages(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-4/6: successful evidence is a fixed sanitized transcript."""
    monkeypatch.setattr(staging_smoke, "DefaultSmokeRuntime", RecordingRuntime)
    monkeypatch.setattr(staging_smoke.os, "environ", STAGING_ENVIRONMENT)
    monkeypatch.setattr(sys, "argv", ["api_staging_auth_smoke.py"])

    assert staging_smoke.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        "PASS target staging/api",
        "PASS baseline API smoke",
        "PASS Clerk Production instance",
        "PASS synthetic user",
        "PASS session token",
        "PASS authenticated API",
        "PASS cleanup",
        "PASS Staging authenticated API smoke",
    ]
    assert_no_sensitive_output(captured)


@pytest.mark.parametrize(
    ("failure", "environment"),
    (
        ("target", {**STAGING_ENVIRONMENT, "API_BASE_URL": "https://other.invalid"}),
        ("baseline", STAGING_ENVIRONMENT),
        ("prompt-secret", STAGING_ENVIRONMENT),
        ("instance", STAGING_ENVIRONMENT),
        ("user", STAGING_ENVIRONMENT),
        ("prompt-session", STAGING_ENVIRONMENT),
        ("session-get", STAGING_ENVIRONMENT),
        ("verify", STAGING_ENVIRONMENT),
        ("api-me", STAGING_ENVIRONMENT),
        ("cleanup", STAGING_ENVIRONMENT),
    ),
)
def test_main_failure_output_is_fixed_sanitized_stages_only(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
    environment: Mapping[str, str],
) -> None:
    """AC-4/6 SECURITY: every terminal failure emits only stable safe stage lines."""

    def execute(private_value: str) -> tuple[str, ...]:
        if failure == "target":

            def no_runtime() -> NoReturn:
                raise AssertionError("invalid target must precede runtime construction")

            monkeypatch.setattr(staging_smoke, "DefaultSmokeRuntime", no_runtime)
        else:
            runtime = RecordingRuntime(failure=failure, private_value=private_value)
            monkeypatch.setattr(staging_smoke, "DefaultSmokeRuntime", lambda: runtime)
        monkeypatch.setattr(staging_smoke.os, "environ", environment)
        monkeypatch.setattr(sys, "argv", ["api_staging_auth_smoke.py"])

        assert staging_smoke.main() != 0
        captured = capsys.readouterr()
        rendered = captured.out + captured.err
        assert private_value not in rendered
        assert "Traceback" not in rendered
        lines = tuple(line for line in rendered.splitlines() if line)
        pass_lines = tuple(line for line in lines if line.startswith("PASS "))
        fail_lines = tuple(line for line in lines if line.startswith("FAIL "))
        assert pass_lines == SUCCESS_LINES[: len(pass_lines)]
        assert fail_lines == (FAILURE_LINES[failure],)
        assert all(line in {*SUCCESS_LINES, FAILURE_LINES[failure]} for line in lines)
        return lines

    first = execute("private-first-value")
    second = execute("private-second-value")
    assert first == second


@pytest.mark.parametrize(
    "unsafe_input", (PROMPTED_SECRET, SYNTHETIC_SESSION_ID, PROMPTED_TOKEN)
)
def test_main_rejects_arguments_before_constructing_a_live_runtime(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    unsafe_input: str,
) -> None:
    """AC-4 SECURITY: secret/session/token command arguments have no fallback path."""

    def runtime_must_not_be_constructed() -> NoReturn:
        raise AssertionError("argument validation must precede any live operation")

    monkeypatch.setattr(
        staging_smoke, "DefaultSmokeRuntime", runtime_must_not_be_constructed
    )
    monkeypatch.setattr(staging_smoke.os, "environ", STAGING_ENVIRONMENT)
    monkeypatch.setattr(sys, "argv", ["api_staging_auth_smoke.py", unsafe_input])

    assert staging_smoke.main() != 0
    assert_no_sensitive_output(capsys.readouterr())


def test_hidden_tty_prompts_use_exact_labels_and_refuse_non_tty_input(
    staging_smoke: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """AC-4 SECURITY: all three sensitive values are terminal-only hidden prompts."""
    runtime = staging_smoke.DefaultSmokeRuntime()
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    class NotATty:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", NotATty())
    with pytest.raises(smoke_failure):
        runtime.prompt_secret()

    class Tty:
        def isatty(self) -> bool:
            return True

    prompts: list[tuple[str, object]] = []

    def hidden_input(prompt: str, *, stream: object) -> str:
        prompts.append((prompt, stream))
        return "hidden"

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(sys, "stderr", Tty())
    monkeypatch.setattr(staging_smoke.getpass, "getpass", hidden_input)

    assert runtime.prompt_secret() == "hidden"
    assert runtime.prompt_session_id() == "hidden"
    assert runtime.prompt_session_token() == "hidden"
    assert [prompt for prompt, _stream in prompts] == [
        "Clerk Staging Production secret:",
        "Clerk Staging smoke-only session ID:",
        "Clerk Staging session token:",
    ]
    assert all(stream is sys.stderr for _prompt, stream in prompts)


@pytest.mark.parametrize(
    "prompt_method",
    ("prompt_secret", "prompt_session_id", "prompt_session_token"),
)
def test_getpass_warning_fails_closed_before_echoed_secret_fallback(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    prompt_method: str,
) -> None:
    """AC-4 SECURITY: no unhidden fallback may consume an operator secret."""
    runtime = staging_smoke.DefaultSmokeRuntime()
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)
    raw_input_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class Tty:
        def __init__(self) -> None:
            self.writes: list[str] = []

        def isatty(self) -> bool:
            return True

        def write(self, value: str) -> int:
            self.writes.append(value)
            return len(value)

        def flush(self) -> None:
            return None

    def raw_input(*args: object, **kwargs: object) -> str:
        raw_input_calls.append((args, kwargs))
        return PROMPTED_SECRET

    stderr = Tty()
    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(staging_smoke.getpass, "_raw_input", raw_input)
    fallback_getpass = cast(Any, getpass.fallback_getpass)  # type: ignore[attr-defined]
    monkeypatch.setattr(staging_smoke.getpass, "getpass", fallback_getpass)

    with pytest.raises(smoke_failure) as raised:
        getattr(runtime, prompt_method)()

    assert str(raised.value) == "hidden input"
    assert raw_input_calls == []
    assert stderr.writes == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert_no_sensitive_output(captured)


def test_concrete_runtime_binds_the_canonical_production_instance_and_selection(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
) -> None:
    """AC-4 SECURITY: the concrete Clerk edge accepts only the approved instance/session."""
    clerk = FakeClerk()
    opener = RecordingOpener(ApiResponse(200, b'{"id": 1}'))
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_INSTANCE_FINGERPRINT", instance_fingerprint()
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    monkeypatch.setattr(
        staging_smoke.os,
        "environ",
        {**STAGING_ENVIRONMENT, "STAGING_CLERK_INSTANCE_FINGERPRINT": "override"},
    )
    runtime = concrete_runtime(
        staging_smoke,
        clerk=clerk,
        verifier=object(),
        opener=opener,
    )

    runtime.validate_production_instance(secret=PROMPTED_SECRET)  # type: ignore[attr-defined]
    runtime.validate_synthetic_user(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
    )
    runtime.get_selected_session(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET,
        session_id=SYNTHETIC_SESSION_ID,
        user_id=SYNTHETIC_USER_ID,
    )
    runtime.revoke_selected_session(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET, session_id=SYNTHETIC_SESSION_ID
    )

    assert clerk.calls == [
        ("instance", {}),
        ("user", {"user_id": SYNTHETIC_USER_ID}),
    ]
    assert clerk.sessions.calls == [
        ("get", {"session_id": SYNTHETIC_SESSION_ID}),
        ("revoke", {"session_id": SYNTHETIC_SESSION_ID}),
    ]


@pytest.mark.parametrize(
    "selection_error", (RuntimeError("provider down"), ValueError())
)
def test_concrete_sessions_get_error_never_attempts_create_mint_or_enumeration_fallback(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    selection_error: BaseException,
) -> None:
    """AC-4 SECURITY: a failed authoritative lookup cannot enter an alternate flow."""
    clerk = FakeClerk(get_error=selection_error)
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_INSTANCE_FINGERPRINT", instance_fingerprint()
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    runtime = concrete_runtime(
        staging_smoke,
        clerk=clerk,
        verifier=object(),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    runtime.validate_production_instance(secret=PROMPTED_SECRET)  # type: ignore[attr-defined]
    runtime.validate_synthetic_user(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
    )
    with pytest.raises(smoke_failure):
        runtime.get_selected_session(  # type: ignore[attr-defined]
            secret=PROMPTED_SECRET,
            session_id=SYNTHETIC_SESSION_ID,
            user_id=SYNTHETIC_USER_ID,
        )

    assert clerk.sessions.calls == [("get", {"session_id": SYNTHETIC_SESSION_ID})]
    assert clerk.sessions.forbidden_attempts == []
    assert clerk.forbidden_root_attempts == []


def test_strict_fake_records_a_caught_forbidden_clerk_root_attempt() -> None:
    """Test witness: caught root fallbacks remain observable to selection-error tests."""
    clerk = FakeClerk()

    try:
        clerk.sign_in_tokens.create()  # type: ignore[attr-defined]
    except AssertionError:
        pass

    assert clerk.forbidden_root_attempts == ["sign_in_tokens"]


def test_default_runtime_uses_only_hidden_values_not_ambient_session_or_token_inputs(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """AC-4 SECURITY: no secret, session ID, or token environment fallback exists."""

    class AmbientInputGuard(Mapping[str, str]):
        def __iter__(self):
            return iter(STAGING_ENVIRONMENT)

        def __len__(self) -> int:
            return len(STAGING_ENVIRONMENT)

        def __getitem__(self, key: str) -> str:
            if key in {
                "CLERK_SECRET",
                "CLERK_SECRET_KEY",
                "CLERK_STAGING_SMOKE_SESSION_ID",
                "CLERK_STAGING_SESSION_TOKEN",
                "CLERK_SESSION_TOKEN",
            }:
                raise AssertionError(f"ambient sensitive input accessed: {key}")
            return STAGING_ENVIRONMENT[key]

    clerk = FakeClerk()
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_INSTANCE_FINGERPRINT", instance_fingerprint()
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    monkeypatch.setattr(staging_smoke.os, "environ", AmbientInputGuard())
    runtime = concrete_runtime(
        staging_smoke,
        clerk=clerk,
        verifier=staging_verifier(signing_key),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )

    def baseline(*, base_url: str) -> bool:
        assert base_url == STAGING_URL
        return True

    monkeypatch.setattr(runtime, "run_baseline", baseline)
    monkeypatch.setattr(runtime, "prompt_secret", lambda: PROMPTED_SECRET)
    monkeypatch.setattr(runtime, "prompt_session_id", lambda: SYNTHETIC_SESSION_ID)
    monkeypatch.setattr(
        runtime, "prompt_session_token", lambda: issue_session_token(signing_key)
    )

    outcome = staging_smoke.run(STAGING_ENVIRONMENT, runtime)

    assert outcome.succeeded
    assert clerk.sessions.calls == [
        ("get", {"session_id": SYNTHETIC_SESSION_ID}),
        ("revoke", {"session_id": SYNTHETIC_SESSION_ID}),
    ]


def test_default_runtime_builds_and_uses_a_no_redirect_proxy_free_opener(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
) -> None:
    """AC-4 SECURITY: default HTTP construction cannot silently follow redirects."""
    opener = RecordingOpener(ApiResponse(302, b""))
    captured_handlers: list[object] = []

    def build_opener(*handlers: object) -> RecordingOpener:
        captured_handlers.extend(handlers)
        return opener

    monkeypatch.setattr(staging_smoke.urllib.request, "build_opener", build_opener)
    runtime = staging_smoke.DefaultSmokeRuntime()
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    with pytest.raises(smoke_failure):
        runtime.request_current_user(base_url=STAGING_URL, bearer_token=PROMPTED_TOKEN)

    assert len(opener.requests) == 1
    proxy_handlers = [
        handler
        for handler in captured_handlers
        if isinstance(handler, urllib.request.ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert cast(dict[str, object], vars(proxy_handlers[0])).get("proxies") == {}
    redirect_handlers = [
        handler
        for handler in captured_handlers
        if isinstance(handler, urllib.request.HTTPRedirectHandler)
    ]
    assert len(redirect_handlers) == 1
    redirect_handler = cast(Any, redirect_handlers[0])
    assert redirect_handler.redirect_request(None, None, 302, "", {}, "") is None


def test_default_runtime_closes_and_drops_all_real_clerk_http_clients(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """AC-4/TSC SECURITY: every default Clerk client is safe, closed, and dropped."""
    providers: list[Clerk] = []
    sync_clients: list[httpx.Client] = []
    async_clients: list[httpx.AsyncClient] = []

    def real_clerk_with_offline_resources(*args: object, **kwargs: object) -> Clerk:
        sync_client = kwargs.get("client")
        async_client = kwargs.get("async_client")
        assert isinstance(sync_client, httpx.Client)
        assert isinstance(async_client, httpx.AsyncClient)
        sync_clients.append(sync_client)
        async_clients.append(async_client)

        provider = cast(Clerk, cast(Any, Clerk)(*args, **kwargs))
        provider_resources = cast(Any, provider)
        provider_resources.instance_settings = SimpleNamespace(
            get=lambda: FakeInstance()
        )

        def get_synthetic_user(*, user_id: str) -> FakeUser:
            return FakeUser(
                id=user_id,
                public_metadata={
                    "tailtag_environment": "staging",
                    "tailtag_synthetic": True,
                },
            )

        provider_resources.users = SimpleNamespace(get=get_synthetic_user)
        provider_resources.sessions = FakeSessions(
            FakeSession(), FakeSession(status="revoked")
        )
        providers.append(provider)
        return provider

    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_INSTANCE_FINGERPRINT", instance_fingerprint()
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    monkeypatch.setattr(staging_smoke, "Clerk", real_clerk_with_offline_resources)
    runtime = staging_smoke.DefaultSmokeRuntime(
        verifier=staging_verifier(signing_key),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )

    def baseline(*, base_url: str) -> bool:
        return base_url == STAGING_URL

    monkeypatch.setattr(runtime, "run_baseline", baseline)
    monkeypatch.setattr(runtime, "prompt_secret", lambda: PROMPTED_SECRET)
    monkeypatch.setattr(runtime, "prompt_session_id", lambda: SYNTHETIC_SESSION_ID)
    monkeypatch.setattr(
        runtime, "prompt_session_token", lambda: issue_session_token(signing_key)
    )

    outcome = staging_smoke.run(STAGING_ENVIRONMENT, runtime)

    assert outcome.succeeded
    assert providers
    assert sync_clients and async_clients
    for client in sync_clients + async_clients:
        assert client.follow_redirects is False
        assert cast(Any, client)._trust_env is False
        assert client.is_closed
    runtime_values = cast(dict[str, object], vars(runtime)).values()
    assert all(
        value is not provider for provider in providers for value in runtime_values
    )


@pytest.mark.parametrize(
    ("instance", "user", "selected", "revoked"),
    (
        (FakeInstance(environment_type="development"), None, FakeSession(), None),
        (FakeInstance(id="ins_other_production"), None, FakeSession(), None),
        (
            FakeInstance(),
            FakeUser(id="user_other", public_metadata={}),
            FakeSession(),
            None,
        ),
        (
            FakeInstance(),
            FakeUser(id=cast(str, 1), public_metadata={}),
            FakeSession(),
            None,
        ),
        (
            FakeInstance(),
            FakeUser(id=cast(str, False), public_metadata={}),
            FakeSession(),
            None,
        ),
        (FakeInstance(), FakeUser(public_metadata=None), FakeSession(), None),
        (FakeInstance(), FakeUser(public_metadata=[]), FakeSession(), None),
        (
            FakeInstance(),
            FakeUser(
                public_metadata={
                    "tailtag_environment": "development",
                    "tailtag_synthetic": True,
                }
            ),
            FakeSession(),
            None,
        ),
        (
            FakeInstance(),
            FakeUser(public_metadata={"tailtag_environment": "staging"}),
            FakeSession(),
            None,
        ),
        (
            FakeInstance(),
            FakeUser(
                public_metadata={
                    "tailtag_environment": "Staging",
                    "tailtag_synthetic": True,
                }
            ),
            FakeSession(),
            None,
        ),
        (
            FakeInstance(),
            FakeUser(
                public_metadata={
                    "tailtag_environment": "staging",
                    "tailtag_synthetic": "true",
                }
            ),
            FakeSession(),
            None,
        ),
        (FakeInstance(), None, FakeSession(status="abandoned"), None),
        (FakeInstance(), None, FakeSession(actor={"id": "act_1"}), None),
        (FakeInstance(), None, FakeSession(actor={}), None),
        (FakeInstance(), None, FakeSession(actor=""), None),
        (FakeInstance(), None, FakeSession(actor=False), None),
        (FakeInstance(), None, FakeSession(actor=0), None),
        (FakeInstance(), None, FakeSession(user_id="user_other"), None),
        (FakeInstance(), None, FakeSession(id="sess_other"), None),
        (FakeInstance(), None, FakeSession(), FakeSession(status="active")),
        (
            FakeInstance(),
            None,
            FakeSession(),
            FakeSession(id="sess_other", status="revoked"),
        ),
    ),
)
def test_concrete_runtime_rejects_wrong_instance_user_or_session_response(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    instance: FakeInstance,
    user: FakeUser | None,
    selected: FakeSession,
    revoked: FakeSession | None,
) -> None:
    """AC-4 SECURITY: all provider metadata and get/revoke response fields are exact."""
    clerk = FakeClerk(instance=instance, user=user, selected=selected, revoked=revoked)
    runtime = concrete_runtime(
        staging_smoke,
        clerk=clerk,
        verifier=object(),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_INSTANCE_FINGERPRINT", instance_fingerprint()
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    if (
        instance.environment_type != "production"
        or instance.id != SYNTHETIC_INSTANCE_ID
    ):
        with pytest.raises(smoke_failure):
            runtime.validate_production_instance(secret=PROMPTED_SECRET)  # type: ignore[attr-defined]
        return

    runtime.validate_production_instance(secret=PROMPTED_SECRET)  # type: ignore[attr-defined]
    if user is not None:
        with pytest.raises(smoke_failure):
            runtime.validate_synthetic_user(  # type: ignore[attr-defined]
                secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
            )
        return

    runtime.validate_synthetic_user(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
    )
    if (
        selected.id != SYNTHETIC_SESSION_ID
        or selected.status != "active"
        or selected.actor is not None
        or selected.user_id != SYNTHETIC_USER_ID
    ):
        with pytest.raises(smoke_failure):
            runtime.get_selected_session(  # type: ignore[attr-defined]
                secret=PROMPTED_SECRET,
                session_id=SYNTHETIC_SESSION_ID,
                user_id=SYNTHETIC_USER_ID,
            )
        return

    runtime.get_selected_session(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET,
        session_id=SYNTHETIC_SESSION_ID,
        user_id=SYNTHETIC_USER_ID,
    )
    with pytest.raises(smoke_failure):
        runtime.revoke_selected_session(  # type: ignore[attr-defined]
            secret=PROMPTED_SECRET, session_id=SYNTHETIC_SESSION_ID
        )


@pytest.mark.parametrize("no_actor", (None, UNSET))
def test_concrete_runtime_accepts_sdk_no_actor_representations(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    no_actor: object,
) -> None:
    """AC-4 SECURITY: both Clerk no-actor representations permit selection only."""
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_INSTANCE_FINGERPRINT", instance_fingerprint()
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    clerk = FakeClerk(selected=FakeSession(actor=no_actor))
    runtime = concrete_runtime(
        staging_smoke,
        clerk=clerk,
        verifier=object(),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )

    runtime.validate_production_instance(secret=PROMPTED_SECRET)  # type: ignore[attr-defined]
    runtime.validate_synthetic_user(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
    )
    runtime.get_selected_session(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET,
        session_id=SYNTHETIC_SESSION_ID,
        user_id=SYNTHETIC_USER_ID,
    )

    assert clerk.sessions.calls == [("get", {"session_id": SYNTHETIC_SESSION_ID})]
    assert clerk.sessions.forbidden_attempts == []
    assert clerk.forbidden_root_attempts == []


def test_concrete_runtime_accepts_copied_sdk_unset_actor_from_omitted_payload(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
) -> None:
    """AC-4 SECURITY: an omitted Clerk actor field selects its real copied Unset."""
    selected = Session.model_validate(
        {
            "object": "session",
            "id": SYNTHETIC_SESSION_ID,
            "user_id": SYNTHETIC_USER_ID,
            "client_id": "client_staging_smoke_synthetic",
            "status": "active",
            "last_active_at": 1,
            "expire_at": 2,
            "abandon_at": 3,
            "updated_at": 4,
            "created_at": 5,
        }
    )
    assert selected.actor is not UNSET
    assert isinstance(selected.actor, type(UNSET))
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_INSTANCE_FINGERPRINT", instance_fingerprint()
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    clerk = FakeClerk(selected=cast(FakeSession, selected))
    runtime = concrete_runtime(
        staging_smoke,
        clerk=clerk,
        verifier=object(),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )

    runtime.validate_production_instance(secret=PROMPTED_SECRET)  # type: ignore[attr-defined]
    runtime.validate_synthetic_user(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
    )
    runtime.get_selected_session(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET,
        session_id=SYNTHETIC_SESSION_ID,
        user_id=SYNTHETIC_USER_ID,
    )

    assert clerk.sessions.calls == [("get", {"session_id": SYNTHETIC_SESSION_ID})]
    assert clerk.sessions.forbidden_attempts == []
    assert clerk.forbidden_root_attempts == []


@pytest.mark.parametrize(
    "user",
    (
        FakeUser(
            id="user_other",
            public_metadata={
                "tailtag_environment": "staging",
                "tailtag_synthetic": True,
            },
        ),
        FakeUser(
            id=cast(str, 1),
            public_metadata={
                "tailtag_environment": "staging",
                "tailtag_synthetic": True,
            },
        ),
        FakeUser(
            public_metadata={"tailtag_environment": "staging", "tailtag_synthetic": 1},
        ),
    ),
)
def test_concrete_runtime_rejects_isolated_user_identity_and_boolean_mutants(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    user: FakeUser,
) -> None:
    """AC-4 SECURITY: each synthetic user identity marker is independently exact."""
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_INSTANCE_FINGERPRINT", instance_fingerprint()
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    runtime = concrete_runtime(
        staging_smoke,
        clerk=FakeClerk(user=user),
        verifier=object(),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    runtime.validate_production_instance(secret=PROMPTED_SECRET)  # type: ignore[attr-defined]
    with pytest.raises(smoke_failure):
        runtime.validate_synthetic_user(  # type: ignore[attr-defined]
            secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
        )


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_concrete_runtime_uses_the_unchanged_verifier_then_exact_claim_guards(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """AC-4 SECURITY: a real signed ordinary token survives both trust boundaries."""
    runtime = concrete_runtime(
        staging_smoke,
        clerk=FakeClerk(),
        verifier=staging_verifier(signing_key),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    assert staging_smoke.MAX_PROVIDER_SESSION_TOKEN_LIFETIME_SECONDS == 60

    runtime.verify_session_token(  # type: ignore[attr-defined]
        token=issue_session_token(signing_key),
        session_id=SYNTHETIC_SESSION_ID,
        user_id=SYNTHETIC_USER_ID,
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"sid": None},
        {"sid": "sess_other"},
        {"sub": "user_other"},
        {"azp": "https://other.synthetic.invalid"},
        {"iat": "not-an-integer"},
        {"exp": "not-an-integer"},
        {"iat": int(time.time()) + 61, "exp": int(time.time()) + 60},
        {"iat": int(time.time()) - 61, "exp": int(time.time())},
        {"iat": int(time.time()), "exp": int(time.time()) + 61},
    ),
)
def test_concrete_runtime_rejects_untrusted_or_nonordinary_token_claims(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    signing_key: rsa.RSAPrivateKey,
    overrides: Mapping[str, object],
) -> None:
    """AC-4 SECURITY: signature-valid tokens still require exact smoke ownership."""
    runtime = concrete_runtime(
        staging_smoke,
        clerk=FakeClerk(),
        verifier=staging_verifier(signing_key),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    with pytest.raises(smoke_failure):
        runtime.verify_session_token(  # type: ignore[attr-defined]
            token=issue_session_token(signing_key, overrides),
            session_id=SYNTHETIC_SESSION_ID,
            user_id=SYNTHETIC_USER_ID,
        )


def test_concrete_runtime_rejects_a_token_that_fails_cryptographic_verification(
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """AC-4 SECURITY: a claim-shaped token cannot bypass the unchanged verifier."""
    untrusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    runtime = concrete_runtime(
        staging_smoke,
        clerk=FakeClerk(),
        verifier=staging_verifier(signing_key),
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    with pytest.raises(smoke_failure):
        runtime.verify_session_token(  # type: ignore[attr-defined]
            token=issue_session_token(untrusted_key),
            session_id=SYNTHETIC_SESSION_ID,
            user_id=SYNTHETIC_USER_ID,
        )


def test_verifier_failure_precedes_claim_use_and_provider_mutation(
    staging_smoke: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """AC-4 SECURITY: unverified claims cannot select or mutate a Clerk session."""

    class RejectingVerifier:
        def __init__(self) -> None:
            self.calls = 0

        def verify(self, _request: HttpRequest) -> None:
            self.calls += 1
            raise AuthenticationFailed()

    clerk = FakeClerk()
    verifier = RejectingVerifier()
    runtime = concrete_runtime(
        staging_smoke,
        clerk=clerk,
        verifier=verifier,
        opener=RecordingOpener(ApiResponse(200, b'{"id": 1}')),
    )
    monkeypatch.setattr(
        staging_smoke, "STAGING_CLERK_PORTAL_ORIGIN", SYNTHETIC_PORTAL_ORIGIN
    )
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    with pytest.raises(smoke_failure):
        runtime.verify_session_token(  # type: ignore[attr-defined]
            token=PROMPTED_TOKEN,
            session_id=SYNTHETIC_SESSION_ID,
            user_id=SYNTHETIC_USER_ID,
        )
    assert verifier.calls == 1
    assert clerk.sessions.calls == []


def test_concrete_api_boundary_is_one_no_redirect_canonical_bearer_request(
    staging_smoke: ModuleType,
) -> None:
    """AC-4: the authenticated Staging request is exact, bounded, and no-redirect."""
    opener = RecordingOpener(ApiResponse(200, json.dumps({"id": 1}).encode()))
    runtime = concrete_runtime(
        staging_smoke,
        clerk=FakeClerk(),
        verifier=object(),
        opener=opener,
    )

    runtime.request_current_user(  # type: ignore[attr-defined]
        base_url=STAGING_URL, bearer_token=PROMPTED_TOKEN
    )

    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.full_url == f"{STAGING_URL}/api/me/"
    assert request.method == "GET"
    assert request.get_header("Authorization") == f"Bearer {PROMPTED_TOKEN}"


@pytest.mark.parametrize(
    "response",
    (
        ApiResponse(302, b""),
        ApiResponse(200, b"not-json"),
        ApiResponse(200, b"[]"),
        ApiResponse(200, b'{"id": "not-an-int"}'),
        ApiResponse(200, b'{"id": 1, "unexpected": true}'),
    ),
)
def test_concrete_api_boundary_rejects_redirects_and_malformed_responses(
    staging_smoke: ModuleType, response: ApiResponse
) -> None:
    """AC-4 SECURITY: the smoke operation never follows or trusts malformed API output."""
    runtime = concrete_runtime(
        staging_smoke,
        clerk=FakeClerk(),
        verifier=object(),
        opener=RecordingOpener(response),
    )
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)

    with pytest.raises(smoke_failure):
        runtime.request_current_user(  # type: ignore[attr-defined]
            base_url=STAGING_URL, bearer_token=PROMPTED_TOKEN
        )
