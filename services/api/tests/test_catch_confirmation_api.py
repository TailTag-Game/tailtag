"""Acceptance contract for the privacy-preserving catch confirmation endpoint."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import cast
from unittest.mock import patch

import pytest
from django.test import Client
from rest_framework.test import APIClient

from catches.models import Catch
from catches.services import (
    CatchActiveConventionMismatchError,
    CatchAuthenticationError,
    CatchConfirmationResult,
    CatchConfirmationStatus,
    CatchParticipationIneligibleError,
    CatchSelfCatchError,
    CatchTargetInvalidError,
)
from tests.authentication_support import (
    fake_clerk_session_verification,
    force_authenticated_client,
)
from tests.catch_test_support import (
    CatchConfirmationScenario,
    catch_model,
    create_catch_confirmation_scenario,
)

PATH = "/api/catches/confirm/"
INVALID_PAYLOAD = {"payload": ["Invalid catch credential payload."]}
SHAPED_PAYLOAD = "tailtag:catch:v1:" + "A" * 43
INVALID_CREDENTIAL = "tailtag:catch:v0:" + "Z" * 43
FORM_PAYLOAD = "tailtag:catch:v1:" + "Y" * 43
MULTIPART_BOUNDARY = "TailTagCatchConfirmation"
INVALID_PROJECTION_PHOTO_KEY = "images/not-a-uuid.jpg"
DEEP_PAYLOAD_DEPTH = 10_000
DEEP_PAYLOAD_SENTINEL = "deep-json-payload-sentinel"
MULTIPART_BODY = (
    f"--{MULTIPART_BOUNDARY}\r\n"
    'Content-Disposition: form-data; name="payload"\r\n\r\n'
    f"{FORM_PAYLOAD}\r\n"
    f"--{MULTIPART_BOUNDARY}--\r\n"
).encode()


@dataclass(frozen=True)
class AuthenticatedCatchScenario:
    """An eligible persisted scenario and its authenticated API client."""

    scenario: CatchConfirmationScenario
    client: APIClient


def _authenticated_scenario() -> AuthenticatedCatchScenario:
    scenario = create_catch_confirmation_scenario()
    return AuthenticatedCatchScenario(
        scenario=scenario,
        client=force_authenticated_client(user=scenario.catcher_user),
    )


def _canonical_catch(scenario: CatchConfirmationScenario) -> Catch:
    """Create the canonical row returned by the mocked service boundary."""
    return cast(
        Catch,
        catch_model().objects.create(
            catcher_user=scenario.catcher_user,
            fursuit=scenario.fursuit,
            convention=scenario.convention,
            activation=scenario.activation,
            catch_session=scenario.catch_session,
        ),
    )


def _assert_success_projection(
    body: object,
    *,
    outcome: str,
    scenario: CatchConfirmationScenario,
    catch: Catch,
) -> None:
    assert isinstance(body, dict)
    data = cast(dict[str, object], body)
    assert set(data) == {"outcome", "catch"}
    assert data["outcome"] == outcome
    assert isinstance(data["catch"], dict)
    catch_data = cast(dict[str, object], data["catch"])
    assert set(catch_data) == {"id", "caught_at", "convention_id", "fursuit"}
    assert isinstance(catch_data["fursuit"], dict)
    fursuit_data = cast(dict[str, object], catch_data["fursuit"])
    assert set(fursuit_data) == {"tailtag_id", "name", "photo_url"}
    assert catch_data["id"] == catch.pk
    assert catch_data["convention_id"] == scenario.convention.pk
    assert fursuit_data == {
        "tailtag_id": str(scenario.fursuit.tailtag_id),
        "name": scenario.fursuit.name,
        "photo_url": "http://testserver/media/" + scenario.fursuit.photo_key,
    }
    caught_at = catch_data["caught_at"]
    assert isinstance(caught_at, str)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", caught_at)
    assert caught_at == catch.caught_at.isoformat().replace("+00:00", "Z")


def _assert_no_secret_or_provenance(
    body: object, scenario: CatchConfirmationScenario
) -> None:
    _assert_no_raw_credential(body, scenario)
    serialized = json.dumps(body, sort_keys=True)
    for forbidden in (
        "catcher",
        "owner",
        "activation",
        "catch_session",
        "credential",
        "token",
        "eligibility",
        "moderation",
    ):
        assert forbidden not in serialized


def _assert_no_raw_credential(
    body: object, scenario: CatchConfirmationScenario
) -> None:
    serialized = json.dumps(body, sort_keys=True)
    for secret in (scenario.payload, scenario.credential.token):
        assert secret not in serialized


def _assert_no_raw_credential_in_logs(
    caplog: pytest.LogCaptureFixture, *credentials: str
) -> None:
    for credential in credentials:
        assert credential not in caplog.text


@pytest.mark.django_db
def test_confirmation_route_requires_repository_bearer_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-01: reject a route that bypasses the standard authenticated boundary."""
    anonymous = Client().post(
        PATH, {"payload": "malformed"}, content_type="application/json"
    )

    assert anonymous.status_code == 401
    assert anonymous["WWW-Authenticate"] == "Bearer"
    assert anonymous.json() == {
        "detail": "Authentication credentials were not provided."
    }
    authenticated = _authenticated_scenario()
    verified = fake_clerk_session_verification(
        monkeypatch, subject=authenticated.scenario.catcher_user.clerk_user_id
    )
    catch = _canonical_catch(authenticated.scenario)
    with patch(
        "catches.views.confirm_catch",
        return_value=CatchConfirmationResult(catch, CatchConfirmationStatus.CREATED),
    ) as confirm:
        bearer = Client().post(
            PATH,
            {"payload": authenticated.scenario.payload},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer synthetic",
        )

    assert bearer.status_code == 201
    assert len(verified) == 1
    confirm.assert_called_once_with(
        authenticated.scenario.catcher_user, payload=authenticated.scenario.payload
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("body", "content_type"),
    (
        ({}, "application/json"),
        (
            {"payload": SHAPED_PAYLOAD, "extra": True},
            "application/json",
        ),
        ({"credential": SHAPED_PAYLOAD}, "application/json"),
        ({"payload": None}, "application/json"),
        ({"payload": 1}, "application/json"),
        ({"payload": [SHAPED_PAYLOAD]}, "application/json"),
        ({"payload": ""}, "application/json"),
        ({"payload": INVALID_CREDENTIAL}, "application/json"),
        ([], "application/json"),
        (b'{"payload": ', "application/json"),
        (f'{{"payload": "{SHAPED_PAYLOAD}"}}'.encode(), "text/plain"),
        (f"payload={FORM_PAYLOAD}".encode(), "application/x-www-form-urlencoded"),
        (
            MULTIPART_BODY,
            f"multipart/form-data; boundary={MULTIPART_BOUNDARY}",
        ),
    ),
)
def test_confirmation_rejects_non_json_or_noncanonical_payload_without_calling_service(
    body: object, content_type: str, caplog: pytest.LogCaptureFixture
) -> None:
    """AC-02: reject permissive/partially parsed input or validation that reaches service."""
    authenticated = _authenticated_scenario()
    with (
        caplog.at_level(logging.DEBUG, logger="catches.views"),
        patch("catches.views.confirm_catch") as confirm,
    ):
        response = authenticated.client.post(PATH, body, content_type=content_type)

    assert response.status_code == 400
    assert response.json() == INVALID_PAYLOAD
    confirm.assert_not_called()
    assert authenticated.scenario.payload not in response.content.decode()
    _assert_no_raw_credential_in_logs(
        caplog,
        authenticated.scenario.payload,
        SHAPED_PAYLOAD,
        INVALID_CREDENTIAL,
        FORM_PAYLOAD,
    )


@pytest.mark.django_db
def test_confirmation_sanitizes_deeply_nested_json_payload_before_service_invocation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-02/11: reject parser recursion without service invocation or diagnostics."""
    authenticated = _authenticated_scenario()
    body = (
        b'{"payload":'
        + b"[" * DEEP_PAYLOAD_DEPTH
        + f'"{DEEP_PAYLOAD_SENTINEL}"'.encode()
        + b"]" * DEEP_PAYLOAD_DEPTH
        + b"}"
    )
    with (
        caplog.at_level(logging.DEBUG, logger="catches.views"),
        patch("catches.views.confirm_catch") as confirm,
    ):
        response = authenticated.client.post(
            PATH, body, content_type="application/json"
        )

    assert response.status_code == 400
    assert response.json() == INVALID_PAYLOAD
    confirm.assert_not_called()
    view_log_text = "\n".join(
        record.getMessage()
        for record in caplog.records
        if record.name == "catches.views"
    )
    for diagnostic in (DEEP_PAYLOAD_SENTINEL, "RecursionError", "Traceback"):
        assert diagnostic not in view_log_text


@pytest.mark.django_db
def test_confirmation_passes_the_exact_user_and_opaque_payload_to_the_service(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-03: reject transformed payloads or HTTP-layer catch authority."""
    authenticated = _authenticated_scenario()
    catch = _canonical_catch(authenticated.scenario)
    result = CatchConfirmationResult(catch, CatchConfirmationStatus.CREATED)

    with (
        caplog.at_level(logging.DEBUG, logger="catches.views"),
        patch("catches.views.confirm_catch", return_value=result) as confirm,
    ):
        response = authenticated.client.post(
            PATH,
            {"payload": authenticated.scenario.payload},
            content_type="application/json",
        )

    assert response.status_code == 201
    confirm.assert_called_once_with(
        authenticated.scenario.catcher_user, payload=authenticated.scenario.payload
    )
    _assert_success_projection(
        response.json(),
        outcome="created",
        scenario=authenticated.scenario,
        catch=catch,
    )
    _assert_no_secret_or_provenance(response.json(), authenticated.scenario)
    _assert_no_raw_credential_in_logs(
        caplog, authenticated.scenario.payload, authenticated.scenario.credential.token
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "outcome", "http_status"),
    (
        (CatchConfirmationStatus.CREATED, "created", 201),
        (CatchConfirmationStatus.ALREADY_CAUGHT, "already_caught", 200),
    ),
)
def test_confirmation_outcomes_share_the_exact_safe_projection(
    status: CatchConfirmationStatus, outcome: str, http_status: int
) -> None:
    """AC-04/05/06/08: reject swapped outcomes, open schemas, or sensitive fields."""
    authenticated = _authenticated_scenario()
    catch = _canonical_catch(authenticated.scenario)
    with patch(
        "catches.views.confirm_catch",
        return_value=CatchConfirmationResult(catch, status),
    ):
        response = authenticated.client.post(
            PATH,
            {"payload": authenticated.scenario.payload},
            content_type="application/json",
        )

    assert response.status_code == http_status
    _assert_success_projection(
        response.json(), outcome=outcome, scenario=authenticated.scenario, catch=catch
    )
    _assert_no_secret_or_provenance(response.json(), authenticated.scenario)


@pytest.mark.django_db
def test_already_caught_response_preserves_the_service_returned_catch_without_mutation() -> (
    None
):
    """AC-05/07: reject retries that write a replacement or mutate provenance."""
    authenticated = _authenticated_scenario()
    catch = _canonical_catch(authenticated.scenario)
    before = {
        "id": catch.pk,
        "caught_at": catch.caught_at,
        "catcher_user_id": catch.catcher_user_id,
        "activation_id": catch.activation_id,
        "catch_session_id": catch.catch_session_id,
    }
    with patch(
        "catches.views.confirm_catch",
        return_value=CatchConfirmationResult(
            catch, CatchConfirmationStatus.ALREADY_CAUGHT
        ),
    ):
        response = authenticated.client.post(
            PATH,
            {"payload": authenticated.scenario.payload},
            content_type="application/json",
        )

    assert response.status_code == 200
    catch.refresh_from_db()
    assert {
        "id": catch.pk,
        "caught_at": catch.caught_at,
        "catcher_user_id": catch.catcher_user_id,
        "activation_id": catch.activation_id,
        "catch_session_id": catch.catch_session_id,
    } == before
    assert catch_model().objects.filter(pk=catch.pk).count() == 1
    _assert_success_projection(
        response.json(),
        outcome="already_caught",
        scenario=authenticated.scenario,
        catch=catch,
    )
    _assert_no_secret_or_provenance(response.json(), authenticated.scenario)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("error", "http_status", "expected"),
    (
        (
            CatchAuthenticationError(),
            401,
            {"detail": "Authentication credentials were not provided."},
        ),
        (
            CatchParticipationIneligibleError(),
            403,
            {
                "code": "catcher_ineligible",
                "detail": "You are not eligible to catch this target.",
            },
        ),
        (
            CatchActiveConventionMismatchError(),
            409,
            {
                "code": "active_convention_mismatch",
                "detail": "Your active convention does not match the catch target.",
            },
        ),
        (
            CatchSelfCatchError(),
            409,
            {
                "code": "self_catch_not_allowed",
                "detail": "You cannot catch your own fursuit.",
            },
        ),
        (
            CatchTargetInvalidError(),
            404,
            {
                "code": "catch_target_unavailable",
                "detail": "The catch target is unavailable.",
            },
        ),
    ),
)
def test_confirmation_maps_each_typed_service_error_to_its_closed_public_response(
    error: Exception, http_status: int, expected: dict[str, str]
) -> None:
    """AC-09: reject status/code/detail changes and diagnostic-bearing error bodies."""
    authenticated = _authenticated_scenario()
    with patch("catches.views.confirm_catch", side_effect=error):
        response = authenticated.client.post(
            PATH,
            {"payload": authenticated.scenario.payload},
            content_type="application/json",
        )

    assert response.status_code == http_status
    assert response.json() == expected
    assert set(response.json()) == set(expected)
    if isinstance(error, CatchAuthenticationError):
        assert response["WWW-Authenticate"] == "Bearer"
    _assert_no_raw_credential(response.json(), authenticated.scenario)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "target_condition",
    (
        "unknown",
        "revoked",
        "stale",
        "stopped",
        "expired",
        "disabled",
        "ineligible",
        "invalid_activation",
    ),
)
def test_all_target_invalid_conditions_have_the_same_privacy_collapsed_response(
    target_condition: str,
) -> None:
    """AC-10 privacy risk: reject target-state distinctions through any public output."""
    authenticated = _authenticated_scenario()
    del target_condition  # Test labels model private conditions, never request data.
    with patch("catches.views.confirm_catch", side_effect=CatchTargetInvalidError()):
        response = authenticated.client.post(
            PATH,
            {"payload": authenticated.scenario.payload},
            content_type="application/json",
        )

    assert (response.status_code, response.json()) == (
        404,
        {
            "code": "catch_target_unavailable",
            "detail": "The catch target is unavailable.",
        },
    )
    _assert_no_raw_credential(response.json(), authenticated.scenario)


@pytest.mark.django_db
def test_confirmation_sanitizes_unexpected_failures_and_logs_no_raw_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-11 privacy risk: reject raw payload/diagnostics in HTTP or catch-view logs."""
    authenticated = _authenticated_scenario()
    diagnostic = (
        f"catcher_id={authenticated.scenario.catcher_user.pk}; "
        f"constraint=catches_catcher_fursuit_convention_unique; "
        f"payload={authenticated.scenario.payload}; synthetic database diagnostic"
    )
    with (
        caplog.at_level(logging.ERROR, logger="catches.views"),
        patch("catches.views.confirm_catch", side_effect=RuntimeError(diagnostic)),
    ):
        response = authenticated.client.post(
            PATH,
            {"payload": authenticated.scenario.payload},
            content_type="application/json",
        )

    assert response.status_code == 500
    assert response.json() == {
        "code": "server_error",
        "detail": "An unexpected error occurred.",
    }
    assert set(response.json()) == {"code", "detail"}
    assert authenticated.scenario.payload not in response.content.decode()
    assert diagnostic not in response.content.decode()
    view_records = [
        record for record in caplog.records if record.name == "catches.views"
    ]
    assert view_records
    log_text = caplog.text
    assert authenticated.scenario.payload not in log_text
    assert diagnostic not in log_text


@pytest.mark.django_db
def test_confirmation_sanitizes_unexpected_success_projection_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """AC-11: reject projection exceptions that escape the sanitized HTTP boundary."""
    authenticated = _authenticated_scenario()
    authenticated.scenario.fursuit.photo_key = INVALID_PROJECTION_PHOTO_KEY
    authenticated.scenario.fursuit.save(update_fields=["photo_key", "updated_at"])
    catch = _canonical_catch(authenticated.scenario)
    with (
        caplog.at_level(logging.ERROR, logger="catches.views"),
        patch(
            "catches.views.confirm_catch",
            return_value=CatchConfirmationResult(
                catch, CatchConfirmationStatus.CREATED
            ),
        ),
    ):
        response = authenticated.client.post(
            PATH,
            {"payload": authenticated.scenario.payload},
            content_type="application/json",
        )

    assert response.status_code == 500
    assert response.json() == {
        "code": "server_error",
        "detail": "An unexpected error occurred.",
    }
    assert set(response.json()) == {"code", "detail"}
    response_text = response.content.decode()
    for sensitive_value in (
        authenticated.scenario.payload,
        authenticated.scenario.credential.token,
        INVALID_PROJECTION_PHOTO_KEY,
        "ValueError",
    ):
        assert sensitive_value not in response_text
    view_records = [
        record for record in caplog.records if record.name == "catches.views"
    ]
    assert len(view_records) == 1
    assert view_records[0].getMessage()
    assert view_records[0].args == ()
    log_text = caplog.text
    for sensitive_value in (
        authenticated.scenario.payload,
        authenticated.scenario.credential.token,
        INVALID_PROJECTION_PHOTO_KEY,
        "ValueError",
    ):
        assert sensitive_value not in log_text
