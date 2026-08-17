"""Observable Clerk session-verification contract."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import FrozenInstanceError, fields
from typing import NoReturn

import httpx
import jwt
import pytest
from authentication.clerk import (
    ClerkSessionVerifier,
    ClerkVerificationConfiguration,
    VerifiedClerkIdentity,
)
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.http import HttpRequest
from pytest import LogCaptureFixture, MonkeyPatch
from rest_framework.exceptions import AuthenticationFailed

DEFAULT_CLAIMS = {
    "sub": "user_test_subject",
    "sid": "sess_test_session",
    "azp": "http://localhost:3000",
}
GENERIC_FAILURE_DETAIL = AuthenticationFailed().detail
TokenIssuer = Callable[..., str]


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    """Create a test-only signing key; it is never persisted or displayed."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def clerk_configuration(
    signing_key: rsa.RSAPrivateKey,
) -> ClerkVerificationConfiguration:
    """Configure the verifier with only the ephemeral public verification key."""
    public_key = (
        signing_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return ClerkVerificationConfiguration(
        jwt_key=public_key,
        authorized_parties=("http://localhost:3000",),
    )


@pytest.fixture
def verifier(
    clerk_configuration: ClerkVerificationConfiguration,
) -> ClerkSessionVerifier:
    """Provide the configured request-authentication boundary."""
    return ClerkSessionVerifier(clerk_configuration)


@pytest.fixture
def issue_token(signing_key: rsa.RSAPrivateKey) -> TokenIssuer:
    """Issue a short-lived, local RS256 token without exposing it in test output."""

    def issue(
        overrides: Mapping[str, object] | None = None,
        *,
        omit: frozenset[str] = frozenset(),
    ) -> str:
        now = int(time.time())
        claims: dict[str, object] = {
            **DEFAULT_CLAIMS,
            "iat": now,
            "nbf": now - 1,
            "exp": now + 60,
        }
        if overrides:
            claims.update(overrides)
        for claim_name in omit:
            claims.pop(claim_name)
        return jwt.encode(claims, signing_key, algorithm="RS256")

    return issue


def request_with_authorization(value: str | None) -> HttpRequest:
    """Build only the request state consumed by the verifier."""
    request = HttpRequest()
    if value is not None:
        request.META["HTTP_AUTHORIZATION"] = value
    return request


def assert_generic_failure(
    verifier: ClerkSessionVerifier, authorization: str
) -> AuthenticationFailed:
    """Assert that every supplied credential is normalized to one public failure."""
    with pytest.raises(AuthenticationFailed) as raised:
        verifier.verify(request_with_authorization(authorization))

    assert raised.value.detail == GENERIC_FAILURE_DETAIL
    return raised.value


def assert_failure_does_not_disclose(
    error: AuthenticationFailed,
    caplog: LogCaptureFixture,
    *sensitive_values: str,
) -> None:
    """Reject responses and log records that disclose verification material."""
    rendered_logs = "\n".join(record.getMessage() for record in caplog.records)
    rendered_error = f"{error.detail}\n{error}"
    for value in sensitive_values:
        assert value not in rendered_error
        assert value not in rendered_logs


def prohibit_network(monkeypatch: MonkeyPatch) -> None:
    """Fail immediately if authentication attempts any outbound HTTP request."""

    def no_network(*_: object, **__: object) -> NoReturn:
        raise AssertionError(
            "Clerk verification must not make an outbound HTTP request"
        )

    monkeypatch.setattr(httpx.Client, "request", no_network)
    monkeypatch.setattr(httpx.AsyncClient, "request", no_network)


def test_verified_identity_is_subject_only_and_immutable() -> None:
    """The downstream contract contains only the opaque verified subject."""
    identity = VerifiedClerkIdentity(subject="user_test_subject")

    assert identity == VerifiedClerkIdentity(subject="user_test_subject")
    assert {field.name for field in fields(identity)} == {"subject"}
    assert not hasattr(identity, "__dict__")
    with pytest.raises(FrozenInstanceError):
        identity.subject = "user_changed_subject"  # type: ignore[misc]


def test_valid_session_token_returns_exact_subject_identity(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
) -> None:
    """A valid Clerk session normalizes to the immutable subject-only identity."""
    identity = verifier.verify(request_with_authorization(f"Bearer {issue_token()}"))

    assert identity == VerifiedClerkIdentity(subject="user_test_subject")


@pytest.mark.parametrize(
    "claim_name, offset",
    (
        ("exp", -300),
        ("nbf", 300),
        ("iat", 300),
    ),
    ids=("expired", "not-yet-valid", "issued-in-the-future"),
)
def test_invalid_time_claims_fail_with_the_same_public_response(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
    claim_name: str,
    offset: int,
) -> None:
    """Expiry and all relevant time claims reject without a verification reason."""
    token = issue_token({claim_name: int(time.time()) + offset})
    error = assert_generic_failure(verifier, f"Bearer {token}")

    assert str(error) == str(AuthenticationFailed())


def test_wrong_signature_and_malformed_token_fail_generically(
    verifier: ClerkSessionVerifier,
) -> None:
    """Cryptographic and JWT-shape failures have the same external result."""
    wrong_signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_key_token = jwt.encode(
        {
            **DEFAULT_CLAIMS,
            "iat": int(time.time()),
            "nbf": int(time.time()) - 1,
            "exp": int(time.time()) + 60,
        },
        wrong_signing_key,
        algorithm="RS256",
    )
    malformed_token = "not.a.signed.jwt"

    assert_generic_failure(verifier, f"Bearer {wrong_key_token}")
    assert_generic_failure(verifier, f"Bearer {malformed_token}")


def test_arbitrary_issuer_is_not_an_independent_tailtag_policy(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
) -> None:
    """The configured instance key, not a local issuer rule, is the trust anchor."""
    token = issue_token({"iss": "https://unvalidated-issuer.invalid"})

    assert verifier.verify(
        request_with_authorization(f"Bearer {token}")
    ) == VerifiedClerkIdentity(subject="user_test_subject")


@pytest.mark.parametrize(
    "claim_overrides",
    (
        {"azp": "https://unapproved-origin.invalid"},
        {"azp": None},
    ),
    ids=("unapproved", "missing"),
)
def test_rejected_or_missing_authorized_party_fails_generically(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
    claim_overrides: Mapping[str, object],
) -> None:
    """The verified authorized party must be exactly in the configured allowlist."""
    if claim_overrides["azp"] is None:
        token = issue_token(omit=frozenset({"azp"}))
    else:
        token = issue_token(claim_overrides)

    assert_generic_failure(verifier, f"Bearer {token}")


@pytest.mark.parametrize(
    "invalid_sid",
    (None, "", " \t ", 99),
    ids=("missing", "empty", "whitespace", "non-string"),
)
def test_session_identifier_must_be_a_nonempty_string(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
    invalid_sid: object | None,
) -> None:
    """SDK-classified sessions still require TailTag's strict session binding."""
    if invalid_sid is None:
        token = issue_token(omit=frozenset({"sid"}))
    else:
        token = issue_token({"sid": invalid_sid})

    assert_generic_failure(verifier, f"Bearer {token}")


def test_custom_template_shaped_token_without_session_identifier_fails_generically(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
) -> None:
    """An otherwise valid custom-template JWT cannot impersonate a session token."""
    token = issue_token(
        {"template_claim": "custom-template-marker"}, omit=frozenset({"sid"})
    )

    assert_generic_failure(verifier, f"Bearer {token}")


@pytest.mark.parametrize(
    "invalid_subject",
    (None, "", " \t ", 99),
    ids=("missing", "empty", "whitespace", "non-string"),
)
def test_subject_must_be_a_nonempty_string_without_disclosing_payload(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
    caplog: LogCaptureFixture,
    invalid_subject: object | None,
) -> None:
    """Malformed subjects fail without returning or logging their JWT payload."""
    caplog.set_level(logging.DEBUG)
    if invalid_subject is None:
        token = issue_token(omit=frozenset({"sub"}))
    else:
        token = issue_token({"sub": invalid_subject})
    error = assert_generic_failure(verifier, f"Bearer {token}")

    assert_failure_does_not_disclose(error, caplog, token, "sess_test_session")


def test_no_authorization_header_returns_no_identity(
    verifier: ClerkSessionVerifier,
) -> None:
    """Only an absent header is treated as an anonymous request."""
    assert verifier.verify(request_with_authorization(None)) is None


@pytest.mark.parametrize(
    "authorization",
    (
        "Bearer",
        "Bearer ",
        "Basic token",
        "Bearer\ttoken",
        "Bearer one two",
        "Bearer token,another",
        "Bearer invalid@token",
        "Bearer one, Bearer two",
        "Bearer token Bearer another-token",
    ),
)
def test_supplied_noncanonical_authorization_values_fail_generically(
    verifier: ClerkSessionVerifier, authorization: str
) -> None:
    """Only one ASCII-space-delimited token68 Bearer credential is accepted."""
    assert_generic_failure(verifier, authorization)


@pytest.mark.parametrize("scheme_and_spacing", ("bearer ", "BEARER ", "Bearer    "))
def test_bearer_scheme_is_case_insensitive_and_allows_ascii_spaces(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
    scheme_and_spacing: str,
) -> None:
    """Permitted scheme case and spaces do not alter verification semantics."""
    token = issue_token()

    assert verifier.verify(
        request_with_authorization(f"{scheme_and_spacing}{token}")
    ) == VerifiedClerkIdentity(subject="user_test_subject")


@pytest.mark.parametrize("prefix", ("m2m_", "mt_", "oat_", "ak_"))
def test_non_session_credential_prefixes_fail_without_network_access(
    verifier: ClerkSessionVerifier, monkeypatch: MonkeyPatch, prefix: str
) -> None:
    """Only Clerk session tokens are accepted, never machine or API credentials."""
    prohibit_network(monkeypatch)

    assert_generic_failure(verifier, f"Bearer {prefix}test_credential")


def test_valid_verification_is_offline(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
    monkeypatch: MonkeyPatch,
) -> None:
    """Configured public-key verification must not reach Clerk or another service."""
    prohibit_network(monkeypatch)

    assert verifier.verify(
        request_with_authorization(f"Bearer {issue_token()}")
    ) == VerifiedClerkIdentity(subject="user_test_subject")


@pytest.mark.parametrize(
    "token_overrides, expected_sensitive_value",
    (
        (
            {"azp": "https://unapproved-origin.invalid"},
            "https://unapproved-origin.invalid",
        ),
        ({"sid": ""}, "user_test_subject"),
    ),
    ids=("authorized-party", "session"),
)
def test_rejected_credentials_do_not_leak_tokens_claims_or_sdk_reasons(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
    clerk_configuration: ClerkVerificationConfiguration,
    caplog: LogCaptureFixture,
    token_overrides: Mapping[str, object],
    expected_sensitive_value: str,
) -> None:
    """Representative parse, signature, party, and sid rejections remain opaque."""
    caplog.set_level(logging.DEBUG)
    token = issue_token(token_overrides)
    error = assert_generic_failure(verifier, f"Bearer {token}")
    key_fragment = clerk_configuration.jwt_key.splitlines()[1]

    assert_failure_does_not_disclose(
        error,
        caplog,
        token,
        key_fragment,
        "user_test_subject",
        "sess_test_session",
        expected_sensitive_value,
        "Signature verification failed",
        "Invalid authorized party",
    )


def test_parse_and_signature_failures_do_not_disclose_sensitive_material(
    verifier: ClerkSessionVerifier,
    issue_token: TokenIssuer,
    clerk_configuration: ClerkVerificationConfiguration,
    caplog: LogCaptureFixture,
) -> None:
    """Malformed and wrong-key inputs do not become authentication diagnostics."""
    caplog.set_level(logging.DEBUG)
    malformed = "malformed_token_that_must_not_be_reported"
    parse_error = assert_generic_failure(verifier, f"Bearer {malformed}")
    assert_failure_does_not_disclose(
        parse_error,
        caplog,
        malformed,
        clerk_configuration.jwt_key.splitlines()[1],
    )

    caplog.clear()
    wrong_signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_key_token = jwt.encode(
        {
            **DEFAULT_CLAIMS,
            "iat": int(time.time()),
            "nbf": int(time.time()) - 1,
            "exp": int(time.time()) + 60,
        },
        wrong_signing_key,
        algorithm="RS256",
    )
    signature_error = assert_generic_failure(verifier, f"Bearer {wrong_key_token}")
    assert_failure_does_not_disclose(
        signature_error,
        caplog,
        wrong_key_token,
        clerk_configuration.jwt_key.splitlines()[1],
        "user_test_subject",
        "sess_test_session",
        "Signature verification failed",
    )
