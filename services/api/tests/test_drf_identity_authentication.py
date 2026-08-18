"""Independent assembled-DRF acceptance contract for Clerk identity resolution."""

from __future__ import annotations

from typing import ClassVar, NoReturn

import pytest
import yaml
from django.conf import settings
from django.http import HttpRequest
from django.test import Client, override_settings
from django.urls import path
from pytest import MonkeyPatch
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from accounts.models import User
from accounts.resolution import ApplicationUserResolutionUnavailable
from authentication import drf as drf_adapter
from authentication.clerk import (
    ClerkSessionVerifier,
    ClerkVerificationConfiguration,
    VerifiedClerkIdentity,
)


class RequestIdentityView(APIView):
    """Test-only public endpoint exposing the assembled DRF request contract."""

    permission_classes: ClassVar[list[type[AllowAny]]] = [AllowAny]

    def get(self, request: object) -> Response:
        user = request.user  # type: ignore[attr-defined]
        return Response({"user_id": user.pk, "auth_is_none": request.auth is None})  # type: ignore[attr-defined]


class ProtectedIdentityView(APIView):
    """Test-only protected endpoint used solely to prove the Bearer challenge."""

    permission_classes: ClassVar[list[type[IsAuthenticated]]] = [IsAuthenticated]

    def get(self, request: object) -> Response:
        return Response({"user_id": request.user.pk})  # type: ignore[attr-defined]


urlpatterns = [
    path("test/identity", RequestIdentityView.as_view()),
    path("test/protected", ProtectedIdentityView.as_view()),
]

AUTHENTICATION_SETTINGS = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["authentication.drf.TailTagAuthentication"],
}
TEST_CLERK_CONFIGURATION = ClerkVerificationConfiguration(
    jwt_key="test-only-not-used-by-patched-verifier",
    authorized_parties=("http://testserver",),
)


def _raise(error: BaseException) -> NoReturn:
    raise error


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION,
)
def test_successful_authentication_exposes_only_the_resolved_application_user(
    monkeypatch: MonkeyPatch,
) -> None:
    verified_requests: list[HttpRequest] = []

    def verify(
        _verifier: ClerkSessionVerifier, request: HttpRequest
    ) -> VerifiedClerkIdentity:
        verified_requests.append(request)
        return VerifiedClerkIdentity(subject="user_test_subject")

    monkeypatch.setattr(
        ClerkSessionVerifier,
        "verify",
        verify,
    )

    response = Client().get("/test/identity", HTTP_AUTHORIZATION="Bearer test")
    resolved_user = User.objects.get(clerk_user_id="user_test_subject")

    assert response.status_code == 200
    assert response.json() == {"user_id": resolved_user.pk, "auth_is_none": True}
    assert len(verified_requests) == 1
    assert isinstance(verified_requests[0], HttpRequest)
    assert not isinstance(verified_requests[0], Request)


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=None,
)
def test_explicitly_disabled_authentication_remains_anonymous_without_boundary_calls(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_if_called(*_: object, **__: object) -> NoReturn:
        raise AssertionError("disabled authentication must not invoke a boundary")

    monkeypatch.setattr(ClerkSessionVerifier, "verify", fail_if_called)
    monkeypatch.setattr(drf_adapter, "resolve_application_user", fail_if_called)

    response = Client().get("/test/identity")

    assert response.status_code == 200
    assert response.json() == {"user_id": None, "auth_is_none": True}


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION,
)
def test_enabled_headerless_authentication_remains_anonymous_without_resolution(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail_if_resolved(*_: object, **__: object) -> NoReturn:
        raise AssertionError(
            "headerless authentication must not resolve a TailTag user"
        )

    monkeypatch.setattr(ClerkSessionVerifier, "verify", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(drf_adapter, "resolve_application_user", fail_if_resolved)

    response = Client().get("/test/identity")

    assert response.status_code == 200
    assert response.json() == {"user_id": None, "auth_is_none": True}


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION,
    DEBUG=False,
)
def test_malformed_credentials_are_a_generic_bearer_401() -> None:
    response = Client().get("/test/identity", HTTP_AUTHORIZATION="Basic credential")

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": str(AuthenticationFailed().detail)}


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION,
    DEBUG=False,
)
def test_resolution_unavailable_has_one_fixed_sanitized_503_body(
    monkeypatch: MonkeyPatch,
) -> None:
    sentinels = iter(
        (
            ("user_503_first_subject", "first psycopg cause detail sentinel"),
            ("user_503_second_subject", "second psycopg cause detail sentinel"),
            ("user_503_detail_subject", "fixed DRF detail code sentinel"),
        )
    )
    active_subject = ""

    def verify(*_: object, **__: object) -> VerifiedClerkIdentity:
        nonlocal active_subject
        active_subject, _ = next(sentinels)
        return VerifiedClerkIdentity(subject=active_subject)

    details = iter(
        (
            "first psycopg cause detail sentinel",
            "second psycopg cause detail sentinel",
            "fixed DRF detail code sentinel",
        )
    )
    monkeypatch.setattr(ClerkSessionVerifier, "verify", verify)
    monkeypatch.setattr(
        drf_adapter,
        "resolve_application_user",
        lambda *_args, **_kwargs: _raise(
            ApplicationUserResolutionUnavailable(next(details))
        ),
    )

    responses = [
        Client().get("/test/identity", HTTP_AUTHORIZATION="Bearer test")
        for _ in range(2)
    ]
    bodies = [response.content.decode() for response in responses]

    assert [response.status_code for response in responses] == [503, 503]
    assert bodies[0] == bodies[1]
    for body, (subject, detail) in zip(
        bodies,
        (
            ("user_503_first_subject", "first psycopg cause detail sentinel"),
            ("user_503_second_subject", "second psycopg cause detail sentinel"),
        ),
        strict=True,
    ):
        assert subject not in body
        assert detail not in body

    drf_response = RequestIdentityView.as_view()(
        APIRequestFactory().get("/test/identity", HTTP_AUTHORIZATION="Bearer test")
    )
    detail = drf_response.data["detail"]

    assert drf_response.status_code == 503
    assert str(detail) == "Service temporarily unavailable."
    assert detail.code == "service_unavailable"


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION,
    DEBUG=False,
)
def test_unexpected_resolution_failure_follows_the_generic_500_path(
    monkeypatch: MonkeyPatch,
) -> None:
    sentinel_detail = "unexpected resolver detail sentinel"
    sentinel_subject = "user_500_subject_sentinel"
    monkeypatch.setattr(
        ClerkSessionVerifier,
        "verify",
        lambda *_args, **_kwargs: VerifiedClerkIdentity(subject=sentinel_subject),
    )
    monkeypatch.setattr(
        drf_adapter,
        "resolve_application_user",
        lambda *_args, **_kwargs: _raise(RuntimeError(sentinel_detail)),
    )

    response = Client(raise_request_exception=False).get(
        "/test/identity", HTTP_AUTHORIZATION="Bearer test"
    )

    assert response.status_code == 500
    body = response.content.decode()
    assert sentinel_detail not in body
    assert sentinel_subject not in body


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION,
)
def test_missing_credentials_on_a_protected_view_receive_a_bearer_challenge() -> None:
    response = Client().get("/test/protected")

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


def test_global_authentication_contract_has_one_tailtag_class_and_no_permission_default() -> (
    None
):
    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "authentication.drf.TailTagAuthentication"
    ]
    assert "DEFAULT_PERMISSION_CLASSES" not in settings.REST_FRAMEWORK


def test_identity_authentication_adds_no_production_routes(client: Client) -> None:
    schema_response = client.get("/api/schema/")

    assert client.post("/api/auth/signup", data={}).status_code == 404
    assert client.get("/api/fursuits").status_code == 404
    assert schema_response.status_code == 200
    assert set(yaml.safe_load(schema_response.content)["paths"]) == {"/api/schema/"}
