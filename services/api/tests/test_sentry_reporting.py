"""Acceptance tests for Sentry initialization, event hygiene, and reporting (#210)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
import sentry_sdk
from django.test import Client
from pytest_django.fixtures import SettingsWrapper

from config.build_identity import Identity
from observability.sentry import init_sentry
from tests.authentication_support import create_test_user, force_authenticated_client
from tests.observability_test_support import (
    BREADCRUMB_EXTRA,
    SOURCE_SHA,
    CapturingTransport,
    JsonLogCapture,
    capture_json_stdout,
    identity,
    reset_sentry,
    sentry_capturing,
)

BOOM_URLCONF = "tests.observability_test_support"
RAILWAY_ID = "NnpHMrRbT-6rmzcsHn5Ytg"
SECRET_HEADER = "synthetic-bearer-token-must-not-leak"
SECRET_QUERY = "synthetic-query-secret-must-not-leak"
SECRET_BODY = "synthetic-body-credential-must-not-leak"
SECRET_COOKIE = "synthetic-cookie-value-must-not-leak"
SECRETS = (SECRET_HEADER, SECRET_QUERY, SECRET_BODY, SECRET_COOKIE, BREADCRUMB_EXTRA)


@pytest.mark.parametrize("dsn", [None, ""])
def test_without_a_dsn_sentry_stays_uninitialized(dsn: str | None) -> None:
    """AC-8: local development and tests need no DSN and the API still runs."""
    reset_sentry()
    try:
        assert init_sentry(dsn, identity()) is False
        assert not sentry_sdk.get_client().is_active()
        assert Client().get("/health/live").status_code == 200
    finally:
        reset_sentry()


@pytest.mark.parametrize(
    ("build_identity", "environment", "release"),
    [
        (identity(), "development", SOURCE_SHA),
        (identity(environment=None), "unknown", SOURCE_SHA),
        (None, "unknown", None),
    ],
    ids=["full", "no-environment", "no-identity"],
)
def test_initialization_uses_the_privacy_preserving_options(
    monkeypatch: pytest.MonkeyPatch,
    build_identity: Identity | None,
    environment: str,
    release: str | None,
) -> None:
    """AC-8: the SDK defaults that would leak (locals, bodies, PII, logs) are off."""
    monkeypatch.setenv("SENTRY_RELEASE", "guessed-release-from-environment")
    with sentry_capturing(build_identity):
        options: dict[str, Any] = sentry_sdk.get_client().options

        assert options["send_default_pii"] is False
        assert options["include_local_variables"] is False
        assert options["max_request_body_size"] == "never"
        assert not options["enable_logs"]
        assert not options["_experiments"].get("enable_logs")
        assert options.get("traces_sample_rate") is None
        assert options.get("traces_sampler") is None
        assert options["environment"] == environment
        assert options["release"] == release


@pytest.mark.parametrize(
    ("build_identity", "environment", "release"),
    [
        (identity(), "development", SOURCE_SHA),
        (identity(source_sha=None, environment=None), "unknown", None),
        (None, "unknown", None),
    ],
    ids=["full", "unknown-parts", "no-identity"],
)
def test_events_carry_environment_and_release_only_from_build_identity(
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsWrapper,
    build_identity: Identity | None,
    environment: str,
    release: str | None,
) -> None:
    """AC-8, AC-9: SDK release/environment guesses never reach an event."""
    settings.ROOT_URLCONF = BOOM_URLCONF
    monkeypatch.setenv("SENTRY_RELEASE", "guessed-release-from-environment")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "guessed-environment")
    with sentry_capturing(build_identity) as transport:
        Client(raise_request_exception=False).get("/boom/1/")

    events = transport.events()
    assert events
    for event in events:
        assert event["environment"] == environment
        assert event.get("release") == release


def test_transaction_events_are_scrubbed_like_error_events() -> None:
    """AC-9: the transaction hook strips the same request fields and stray release."""
    event: dict[str, Any] = {
        "type": "transaction",
        "release": "guessed-release",
        "request": {
            "method": "GET",
            "query_string": f"token={SECRET_QUERY}",
            "data": {"password": SECRET_BODY},
            "cookies": {"sessionid": SECRET_COOKIE},
        },
    }
    with sentry_capturing(identity()):
        hook = sentry_sdk.get_client().options["before_send_transaction"]
        scrubbed = hook(event, {})

    assert scrubbed is not None
    assert not {"query_string", "data", "cookies"} & scrubbed.get("request", {}).keys()
    assert scrubbed.get("release") in (None, SOURCE_SHA)
    assert all(secret not in json.dumps(scrubbed) for secret in SECRETS)


def _send_hostile_request(client: Client, path: str) -> Any:
    client.cookies["sessionid"] = SECRET_COOKIE
    return client.post(
        f"{path}?token={SECRET_QUERY}",
        data=json.dumps({"password": SECRET_BODY}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {SECRET_HEADER}",
        HTTP_X_RAILWAY_REQUEST_ID=RAILWAY_ID,
    )


def _assert_reported_without_secrets(
    transport: CapturingTransport, capture: JsonLogCapture
) -> list[dict[str, Any]]:
    """AC-9, AC-11: correlated, request-field-free events; no secret anywhere."""
    events = transport.events()
    assert events
    [completion] = [
        line for line in capture.lines() if line["logger"] == "tailtag.request"
    ]
    for event in events:
        assert not {"query_string", "data", "cookies"} & event.get("request", {}).keys()
        assert event["tags"]["request_id"] == completion["request_id"]
        assert event["tags"]["railway_request_id"] == RAILWAY_ID
    for secret in SECRETS:
        assert secret not in transport.serialized()
        assert secret not in capture.text
    return events


def test_unhandled_exception_is_reported_without_request_secrets(
    settings: SettingsWrapper,
) -> None:
    """AC-9, AC-10, AC-11: an unhandled bug reaches Sentry; hostile inputs do not."""
    settings.ROOT_URLCONF = BOOM_URLCONF
    with sentry_capturing(identity()) as transport, capture_json_stdout() as capture:
        response = _send_hostile_request(
            Client(raise_request_exception=False), "/boom/424242/"
        )

    assert response.status_code == 500
    events = _assert_reported_without_secrets(transport, capture)
    assert any(
        value.get("type") == "RuntimeError"
        for event in events
        for value in event.get("exception", {}).get("values", [])
    )
    # The non-allow-listed logging extra is dropped from the breadcrumb, not the crumb.
    breadcrumbs = [
        crumb
        for event in events
        for crumb in event.get("breadcrumbs", {}).get("values", [])
    ]
    assert any(crumb.get("message") == "before failure" for crumb in breadcrumbs)


@pytest.mark.django_db
def test_existing_catch_error_log_without_exc_info_is_reported() -> None:
    """AC-10, AC-11: the sanitized 500 stays sanitized and still creates an event."""
    client = force_authenticated_client(user=create_test_user())
    with (
        sentry_capturing(identity()) as transport,
        capture_json_stdout() as capture,
        patch(
            "catches.views.FursuitCatchCredentialResolutionRequestSerializer.is_valid",
            side_effect=RuntimeError("synthetic boundary failure"),
        ),
    ):
        response = _send_hostile_request(client, "/api/catches/confirm/")

    assert response.status_code == 500
    assert response.json() == {
        "code": "server_error",
        "detail": "An unexpected error occurred.",
    }
    events = _assert_reported_without_secrets(transport, capture)
    assert any(
        event.get("logentry", {}).get("message")
        == "Unexpected catch confirmation failure."
        for event in events
    )
