"""Offline acceptance contract for the guarded replica Clerk smoke command (#355).

The flow, claim rules and output discipline are shared with the Staging smoke and
covered in `test_api_staging_auth_smoke.py`. These cases cover what the replica
profile changes: the pinned target, Clerk instance, synthetic user and portal origin.
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
from collections.abc import Mapping
from types import ModuleType
from typing import Any, NoReturn, cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pytest import MonkeyPatch

from authentication.clerk import ClerkSessionVerifier, ClerkVerificationConfiguration
from config import replica_binding
from tests import replica_contract as contract
from tests.test_api_staging_auth_smoke import (
    PROMPTED_SECRET,
    PROMPTED_TOKEN,
    STAGING_ENVIRONMENT,
    SYNTHETIC_SESSION_ID,
    SYNTHETIC_USER_ID,
    ApiResponse,
    FakeClerk,
    FakeUser,
    RecordingOpener,
    RecordingRuntime,
    SmokeOutcome,
    instance_fingerprint,
    issue_session_token,
    prohibit_outbound_network,
)

PINNED_FINGERPRINT = "4f93c7ed6c240ce2"
PORTAL_ORIGIN = "https://accounts.replica.tailtag.app"
STAGING_PORTAL_ORIGIN = "https://accounts.staging.tailtag.app"
RUN_APP_HOST = "tailtag-api-replica-synthetic-uc.a.example.test"
REPLICA_URL = f"https://{RUN_APP_HOST}"
REPLICA_ENVIRONMENT = {
    "TAILTAG_REPLICA_AUTH_SMOKE_CONFIRM": "run-clerk-replica-auth-smoke",
    "TAILTAG_REPLICA_API_BASE_URL": REPLICA_URL,
    "CLERK_REPLICA_SMOKE_USER_ID": SYNTHETIC_USER_ID,
}
RAILWAY_ENVIRONMENT = {
    "RAILWAY_ENVIRONMENT_NAME": "staging",
    "RAILWAY_SERVICE_NAME": "api",
}
REPLICA_USER = {"tailtag_environment": "replica", "tailtag_synthetic": True}
SUCCESS_LINES = (
    "PASS target replica/api",
    "PASS baseline API smoke",
    "PASS Clerk Production instance",
    "PASS synthetic user",
    "PASS session token",
    "PASS authenticated API",
    "PASS cleanup",
    "PASS Replica authenticated API smoke",
)
FAILURE_LINES = {
    "target": "FAIL target replica/api",
    "baseline": "FAIL baseline API smoke",
    "instance": "FAIL Clerk Production instance",
    "user": "FAIL synthetic user",
    "verify": "FAIL session token",
    "api-me": "FAIL authenticated API",
    "cleanup": "FAIL cleanup",
}


@pytest.fixture(autouse=True)
def no_ordinary_outbound_network(monkeypatch: MonkeyPatch) -> None:
    prohibit_outbound_network(monkeypatch)


@pytest.fixture(autouse=True)
def pinned_run_app_host(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        replica_binding,
        "_EXPECTED_HOST_DIGEST",
        contract.host_digest(RUN_APP_HOST),
    )


@pytest.fixture
def replica_smoke() -> ModuleType:
    return importlib.import_module("scripts.api_replica_auth_smoke")


@pytest.fixture
def staging_smoke() -> ModuleType:
    return importlib.import_module("scripts.api_staging_auth_smoke")


class ReplicaRuntime(RecordingRuntime):
    """The shared recording runtime, pointed at the replica base URL."""

    def run_baseline(self, *, base_url: str) -> bool:
        assert base_url == REPLICA_URL
        return super().run_baseline(base_url=STAGING_ENVIRONMENT["API_BASE_URL"])

    def request_current_user(self, *, base_url: str, bearer_token: str) -> None:
        assert base_url == REPLICA_URL
        super().request_current_user(
            base_url=STAGING_ENVIRONMENT["API_BASE_URL"], bearer_token=bearer_token
        )


def replica_verifier(
    signing_key: rsa.RSAPrivateKey, parties: tuple[str, ...] = (PORTAL_ORIGIN,)
) -> ClerkSessionVerifier:
    return ClerkSessionVerifier(
        ClerkVerificationConfiguration(
            jwt_key=public_pem(signing_key), authorized_parties=parties
        )
    )


def public_pem(signing_key: rsa.RSAPrivateKey) -> str:
    return (
        signing_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )


def concrete_runtime(
    replica_smoke: ModuleType,
    *,
    clerk: FakeClerk | None = None,
    verifier: object | None = None,
    opener: RecordingOpener | None = None,
    pinned_instance: bool = True,
) -> object:
    profile = replica_smoke.REPLICA_PROFILE
    if pinned_instance:
        profile = dataclasses.replace(
            profile, instance_fingerprint=instance_fingerprint()
        )
    fake_clerk = clerk or FakeClerk(user=FakeUser(public_metadata=REPLICA_USER))

    def clerk_factory(_secret: str) -> FakeClerk:
        return fake_clerk

    return importlib.import_module(
        "scripts.api_staging_auth_smoke"
    ).DefaultSmokeRuntime(
        clerk_factory=clerk_factory,
        verifier=verifier,
        opener=opener or RecordingOpener(ApiResponse(200, b'{"id": 1}')),
        profile=profile,
    )


def run(
    replica_smoke: ModuleType,
    staging_smoke: ModuleType,
    environment: Mapping[str, str],
    runtime: object,
) -> SmokeOutcome:
    return cast(
        SmokeOutcome,
        staging_smoke.run(environment, runtime, replica_smoke.REPLICA_PROFILE),
    )


def test_replica_pins_are_frozen_public_constants(replica_smoke: ModuleType) -> None:
    """Failure modes 2 and 3: the replica Clerk instance and origin are not inputs."""
    assert replica_smoke.REPLICA_CLERK_INSTANCE_FINGERPRINT == PINNED_FINGERPRINT
    assert replica_smoke.REPLICA_CLERK_PORTAL_ORIGIN == PORTAL_ORIGIN
    profile = replica_smoke.REPLICA_PROFILE
    assert profile.instance_fingerprint == PINNED_FINGERPRINT
    assert profile.portal_origin == PORTAL_ORIGIN
    assert profile.environment == "replica"


@pytest.mark.parametrize(
    "environment",
    (
        {},
        {**REPLICA_ENVIRONMENT, "TAILTAG_REPLICA_AUTH_SMOKE_CONFIRM": "wrong"},
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_AUTH_SMOKE_CONFIRM": "run-clerk-staging-auth-smoke",
        },
        {**REPLICA_ENVIRONMENT, "TAILTAG_REPLICA_API_BASE_URL": ""},
        {**REPLICA_ENVIRONMENT, "CLERK_REPLICA_SMOKE_USER_ID": ""},
        # Wrong hosts, including the legacy `*.a.run.app` style and Staging.
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": "https://tailtag-api-replica-xyz-uc.a.run.app",
        },
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": "https://staging.tailtag.app",
        },
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": "https://other.invalid",
        },
        # Anything but exactly `https://<pinned host>`.
        {**REPLICA_ENVIRONMENT, "TAILTAG_REPLICA_API_BASE_URL": f"{REPLICA_URL}/"},
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": f"{REPLICA_URL}/api/me/",
        },
        {**REPLICA_ENVIRONMENT, "TAILTAG_REPLICA_API_BASE_URL": f"{REPLICA_URL}?x=1"},
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": f"https://user:pass@{RUN_APP_HOST}",
        },
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": f"http://{RUN_APP_HOST}",
        },
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": f"HTTPS://{RUN_APP_HOST}",
        },
        {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": f"https://{RUN_APP_HOST}:8443",
        },
        # Failure modes 1 and 2: a complete Staging or Railway target is not a replica one.
        STAGING_ENVIRONMENT,
        {**STAGING_ENVIRONMENT, "TAILTAG_REPLICA_API_BASE_URL": REPLICA_URL},
        {
            key: value
            for key, value in {**REPLICA_ENVIRONMENT, **RAILWAY_ENVIRONMENT}.items()
            if key != "TAILTAG_REPLICA_API_BASE_URL"
        },
    ),
)
def test_only_the_pinned_replica_target_is_accepted_before_prompt_or_provider_access(
    replica_smoke: ModuleType,
    staging_smoke: ModuleType,
    environment: Mapping[str, str],
) -> None:
    runtime = ReplicaRuntime()

    outcome = run(replica_smoke, staging_smoke, environment, runtime)

    assert not outcome.succeeded
    assert cast(Any, outcome).primary_stage == "target replica/api"
    assert runtime.events == []


def test_replica_target_runs_the_baseline_against_the_replica_url_first(
    replica_smoke: ModuleType, staging_smoke: ModuleType
) -> None:
    runtime = ReplicaRuntime()

    outcome = run(
        replica_smoke,
        staging_smoke,
        {**REPLICA_ENVIRONMENT, **RAILWAY_ENVIRONMENT},
        runtime,
    )

    assert outcome.succeeded
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


def test_main_emits_the_fixed_replica_success_stages_only(
    replica_smoke: ModuleType,
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:

    def replica_runtime(profile: object) -> ReplicaRuntime:
        return ReplicaRuntime()

    monkeypatch.setattr(replica_smoke, "DefaultSmokeRuntime", replica_runtime)
    monkeypatch.setattr(staging_smoke.os, "environ", REPLICA_ENVIRONMENT)
    monkeypatch.setattr(sys, "argv", ["api_replica_auth_smoke.py"])

    assert replica_smoke.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert tuple(captured.out.splitlines()) == SUCCESS_LINES


@pytest.mark.parametrize("failure", tuple(FAILURE_LINES))
def test_main_failure_output_is_fixed_replica_stages_without_identifiers(
    replica_smoke: ModuleType,
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
) -> None:
    """Failure mode 4: no secret, session, token, user ID or host is printed."""
    environment = REPLICA_ENVIRONMENT
    if failure == "target":
        environment = {
            **REPLICA_ENVIRONMENT,
            "TAILTAG_REPLICA_API_BASE_URL": "https://x.invalid",
        }

        def no_runtime(*_args: object, **_kwargs: object) -> NoReturn:
            raise AssertionError("invalid target must precede runtime construction")

        monkeypatch.setattr(replica_smoke, "DefaultSmokeRuntime", no_runtime)
    else:
        runtime = ReplicaRuntime(failure=failure, private_value=RUN_APP_HOST)

        def failing_runtime(profile: object) -> ReplicaRuntime:
            return runtime

        monkeypatch.setattr(replica_smoke, "DefaultSmokeRuntime", failing_runtime)
    monkeypatch.setattr(staging_smoke.os, "environ", environment)
    monkeypatch.setattr(sys, "argv", ["api_replica_auth_smoke.py"])

    assert replica_smoke.main() == 1
    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    for private in (
        PROMPTED_SECRET,
        PROMPTED_TOKEN,
        SYNTHETIC_SESSION_ID,
        SYNTHETIC_USER_ID,
        RUN_APP_HOST,
        "Traceback",
    ):
        assert private not in rendered
    lines = tuple(line for line in rendered.splitlines() if line)
    pass_lines = tuple(line for line in lines if line.startswith("PASS "))
    assert pass_lines == SUCCESS_LINES[: len(pass_lines)]
    assert tuple(line for line in lines if line.startswith("FAIL ")) == (
        FAILURE_LINES[failure],
    )


def test_main_rejects_arguments_before_constructing_a_live_runtime(
    replica_smoke: ModuleType,
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def no_runtime(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("argument validation must precede any live operation")

    monkeypatch.setattr(replica_smoke, "DefaultSmokeRuntime", no_runtime)
    monkeypatch.setattr(staging_smoke.os, "environ", REPLICA_ENVIRONMENT)
    monkeypatch.setattr(sys, "argv", ["api_replica_auth_smoke.py", PROMPTED_SECRET])

    assert replica_smoke.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL target replica/api\n"


def test_prompts_name_the_replica_not_staging(
    replica_smoke: ModuleType, staging_smoke: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    class Tty:
        def isatty(self) -> bool:
            return True

    prompts: list[str] = []
    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(sys, "stderr", Tty())

    def hidden_input(prompt: str, *, stream: object) -> str:
        prompts.append(prompt)
        return "hidden"

    monkeypatch.setattr(staging_smoke.getpass, "getpass", hidden_input)
    runtime = concrete_runtime(replica_smoke)

    runtime.prompt_secret()  # type: ignore[attr-defined]
    runtime.prompt_session_id()  # type: ignore[attr-defined]
    runtime.prompt_session_token()  # type: ignore[attr-defined]

    assert prompts == [
        "Clerk Replica Production secret:",
        "Clerk Replica smoke-only session ID:",
        "Clerk Replica session token:",
    ]


def test_wrong_clerk_instance_fingerprint_is_refused(
    replica_smoke: ModuleType,
) -> None:
    """Failure mode 2: only the pinned replica instance passes, not another one."""
    smoke_failure = cast(
        type[Exception],
        importlib.import_module("scripts.api_staging_auth_smoke").SmokeFailure,
    )
    # The default fake instance does not hash to the pinned replica fingerprint.
    runtime = concrete_runtime(replica_smoke, pinned_instance=False)
    with pytest.raises(smoke_failure):
        runtime.validate_production_instance(secret=PROMPTED_SECRET)  # type: ignore[attr-defined]

    concrete_runtime(replica_smoke).validate_production_instance(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET
    )


@pytest.mark.parametrize(
    "metadata",
    (
        {"tailtag_environment": "staging", "tailtag_synthetic": True},
        {"tailtag_environment": "development", "tailtag_synthetic": True},
        {"tailtag_synthetic": True},
        {"tailtag_environment": "replica"},
        {"tailtag_environment": "replica", "tailtag_synthetic": "true"},
    ),
)
def test_synthetic_user_must_be_marked_for_the_replica(
    replica_smoke: ModuleType, metadata: Mapping[str, object]
) -> None:
    """Failure mode 2: a Staging synthetic user is not a replica synthetic user."""
    smoke_failure = cast(
        type[Exception],
        importlib.import_module("scripts.api_staging_auth_smoke").SmokeFailure,
    )
    runtime = concrete_runtime(
        replica_smoke, clerk=FakeClerk(user=FakeUser(public_metadata=metadata))
    )

    with pytest.raises(smoke_failure):
        runtime.validate_synthetic_user(  # type: ignore[attr-defined]
            secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
        )

    concrete_runtime(replica_smoke).validate_synthetic_user(  # type: ignore[attr-defined]
        secret=PROMPTED_SECRET, user_id=SYNTHETIC_USER_ID
    )


@pytest.fixture
def signing_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_token_with_the_staging_portal_origin_is_refused_even_if_the_verifier_accepts_it(
    replica_smoke: ModuleType, signing_key: rsa.RSAPrivateKey
) -> None:
    """Failure mode 3: the profile checks `azp` itself, beyond the verifier."""
    smoke_failure = cast(
        type[Exception],
        importlib.import_module("scripts.api_staging_auth_smoke").SmokeFailure,
    )
    runtime = concrete_runtime(
        replica_smoke,
        verifier=replica_verifier(signing_key, (PORTAL_ORIGIN, STAGING_PORTAL_ORIGIN)),
    )

    runtime.verify_session_token(  # type: ignore[attr-defined]
        token=issue_session_token(signing_key, {"azp": PORTAL_ORIGIN}),
        session_id=SYNTHETIC_SESSION_ID,
        user_id=SYNTHETIC_USER_ID,
    )
    with pytest.raises(smoke_failure):
        runtime.verify_session_token(  # type: ignore[attr-defined]
            token=issue_session_token(signing_key, {"azp": STAGING_PORTAL_ORIGIN}),
            session_id=SYNTHETIC_SESSION_ID,
            user_id=SYNTHETIC_USER_ID,
        )


def test_default_verifier_pins_the_replica_party_and_ignores_the_staging_one(
    replica_smoke: ModuleType,
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    """Failure mode 3: with no injected verifier, only the replica origin verifies."""
    smoke_failure = cast(type[Exception], staging_smoke.SmokeFailure)
    runtime = concrete_runtime(replica_smoke)
    claims = {
        "session_id": SYNTHETIC_SESSION_ID,
        "user_id": SYNTHETIC_USER_ID,
    }

    monkeypatch.setattr(
        staging_smoke.os,
        "environ",
        {
            "CLERK_JWT_KEY": public_pem(signing_key),
            "CLERK_AUTHORIZED_PARTIES": STAGING_PORTAL_ORIGIN,
        },
    )
    runtime.verify_session_token(  # type: ignore[attr-defined]
        token=issue_session_token(signing_key, {"azp": PORTAL_ORIGIN}), **claims
    )
    with pytest.raises(smoke_failure):
        runtime.verify_session_token(  # type: ignore[attr-defined]
            token=issue_session_token(signing_key, {"azp": STAGING_PORTAL_ORIGIN}),
            **claims,
        )

    monkeypatch.setattr(staging_smoke.os, "environ", {})
    with pytest.raises(smoke_failure):
        runtime.verify_session_token(  # type: ignore[attr-defined]
            token=issue_session_token(signing_key, {"azp": PORTAL_ORIGIN}), **claims
        )


def test_full_replica_flow_passes_with_fake_provider_and_calls_me_on_the_replica(
    replica_smoke: ModuleType,
    staging_smoke: ModuleType,
    monkeypatch: MonkeyPatch,
    signing_key: rsa.RSAPrivateKey,
) -> None:
    opener = RecordingOpener(ApiResponse(200, b'{"id": 1}'))
    clerk = FakeClerk(user=FakeUser(public_metadata=REPLICA_USER))
    token = issue_session_token(signing_key, {"azp": PORTAL_ORIGIN})
    runtime = concrete_runtime(
        replica_smoke,
        clerk=clerk,
        verifier=replica_verifier(signing_key),
        opener=opener,
    )
    baselines: list[str] = []

    def baseline(*, base_url: str) -> bool:
        baselines.append(base_url)
        return True

    monkeypatch.setattr(runtime, "run_baseline", baseline)
    monkeypatch.setattr(runtime, "prompt_secret", lambda: PROMPTED_SECRET)
    monkeypatch.setattr(runtime, "prompt_session_id", lambda: SYNTHETIC_SESSION_ID)
    monkeypatch.setattr(runtime, "prompt_session_token", lambda: token)

    outcome = run(
        replica_smoke,
        staging_smoke,
        {**REPLICA_ENVIRONMENT, **RAILWAY_ENVIRONMENT},
        runtime,
    )

    assert outcome.succeeded
    assert baselines == [REPLICA_URL]
    assert [request.full_url for request in opener.requests] == [
        f"{REPLICA_URL}/api/me/"
    ]
    assert opener.requests[0].get_header("Authorization") == f"Bearer {token}"
    assert clerk.sessions.calls == [
        ("get", {"session_id": SYNTHETIC_SESSION_ID}),
        ("revoke", {"session_id": SYNTHETIC_SESSION_ID}),
    ]
