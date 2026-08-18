"""Independent acceptance contract for Clerk-to-TailTag identity resolution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import ClassVar, NoReturn

import psycopg
import pytest
from accounts.resolution import (
    EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT,
    ApplicationUserResolutionUnavailable,
    resolve_application_user,
)
from django.conf import settings
from django.db import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    close_old_connections,
    connection,
    transaction,
)
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import path
from psycopg import errors
from psycopg.pq import ConnStatus, DiagnosticField
from pytest import MonkeyPatch
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
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


class _BadPsycopgConnection:
    """Minimal test-only connection state supplied to psycopg's exception API."""

    status = ConnStatus.BAD


def _raise(error: BaseException) -> NoReturn:
    raise error


def _with_cause(error: BaseException, cause: BaseException) -> BaseException:
    try:
        raise error from cause
    except type(error) as raised:
        return raised


def _expected_unique_violation() -> errors.UniqueViolation:
    """Make structured psycopg metadata without relying on error-message parsing."""
    return errors.UniqueViolation(
        "test-only expected uniqueness failure",
        info={
            DiagnosticField.SQLSTATE: b"23505",
            DiagnosticField.CONSTRAINT_NAME: EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT.encode(),
        },
    )


@pytest.mark.django_db
def test_first_resolution_provisions_only_the_minimal_tailtag_user() -> None:
    user = resolve_application_user("user_first_use")

    assert user.clerk_user_id == "user_first_use"
    assert User.objects.filter(clerk_user_id="user_first_use").count() == 1
    assert not user.is_staff
    assert not user.is_superuser
    assert user.last_login is None
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_repeated_resolution_returns_the_same_unchanged_user() -> None:
    first = resolve_application_user("user_repeat")

    with CaptureQueriesContext(connection) as queries:
        second = resolve_application_user("user_repeat")

    assert second.pk == first.pk
    assert User.objects.filter(clerk_user_id="user_repeat").count() == 1
    assert second.last_login is None
    assert not any(
        query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for query in queries.captured_queries
    )


@pytest.mark.django_db
def test_distinct_and_case_distinct_subjects_get_distinct_users() -> None:
    exact = resolve_application_user("user_CaseSensitive")
    different_case = resolve_application_user("user_casesensitive")
    other = resolve_application_user("user_other")

    assert len({exact.pk, different_case.pk, other.pk}) == 3


@pytest.mark.django_db
def test_existing_administrative_user_is_returned_without_any_mutation() -> None:
    existing = User.objects.create_superuser(
        "user_existing_admin", password="deliberately-local-test-password"
    )
    before = {
        field.name: getattr(existing, field.name)
        for field in User._meta.concrete_fields
    }

    resolved = resolve_application_user("user_existing_admin")
    existing.refresh_from_db()

    assert resolved.pk == existing.pk
    assert {
        field.name: getattr(existing, field.name) for field in User._meta.concrete_fields
    } == before
    assert existing.is_staff
    assert existing.is_superuser
    assert existing.has_usable_password()


@pytest.mark.django_db(transaction=True)
def test_simultaneous_first_resolution_uses_the_database_unique_guard(
    monkeypatch: MonkeyPatch,
) -> None:
    subject = "user_concurrent_first_use"
    start_barrier = Barrier(2)
    insert_barrier = Barrier(2)
    manager = User.objects
    original_create_user = manager.create_user

    def synchronized_create_user(*args: object, **kwargs: object) -> User:
        insert_barrier.wait(timeout=10)
        return original_create_user(*args, **kwargs)

    monkeypatch.setattr(manager, "create_user", synchronized_create_user)

    def resolve_in_worker() -> int:
        close_old_connections()
        try:
            start_barrier.wait(timeout=10)
            return resolve_application_user(subject).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        returned_primary_keys = list(executor.map(lambda _: resolve_in_worker(), range(2)))

    winning_primary_key = User.objects.get(clerk_user_id=subject).pk
    assert set(returned_primary_keys) == {winning_primary_key}
    assert User.objects.filter(clerk_user_id=subject).count() == 1


@pytest.mark.django_db
def test_migrated_clerk_link_constraint_matches_the_recovery_identifier() -> None:
    constraints = connection.introspection.get_constraints(
        connection.cursor(), User._meta.db_table
    )
    constraint = constraints[EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT]

    assert constraint["unique"]
    assert constraint["columns"] == ["clerk_user_id"]


@pytest.mark.django_db
def test_expected_unique_violation_rereads_the_winner_after_inner_savepoint_rollback(
    monkeypatch: MonkeyPatch,
) -> None:
    subject = "user_recover_after_savepoint"
    winner = User.objects.create_user(subject)
    manager = User.objects
    original_get = manager.get
    lookup_count = 0

    def initially_miss(*args: object, **kwargs: object) -> User:
        nonlocal lookup_count
        lookup_count += 1
        if lookup_count == 1:
            raise User.DoesNotExist
        return original_get(*args, **kwargs)

    monkeypatch.setattr(manager, "get", initially_miss)

    with transaction.atomic():
        resolved = resolve_application_user(subject)
        assert User.objects.get(clerk_user_id=subject).pk == winner.pk

    assert resolved.pk == winner.pk
    assert lookup_count >= 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("subject", "create_conflict"),
    (
        ("user_primary_key_conflict", "primary-key"),
        ("user_nonempty_check_conflict", "nonempty-check"),
    ),
)
def test_unrelated_real_orm_integrity_failures_propagate_unchanged(
    monkeypatch: MonkeyPatch, subject: str, create_conflict: str
) -> None:
    existing = User.objects.create_user("user_existing_for_integrity")
    manager = User.objects

    def create_conflicting_row(*_: object, **__: object) -> User:
        if create_conflict == "primary-key":
            return User.objects.create(
                id=existing.pk,
                clerk_user_id="user_different_primary_key_conflict",
                password=existing.password,
            )
        return User.objects.create(clerk_user_id="", password=existing.password)

    monkeypatch.setattr(manager, "create_user", create_conflicting_row)

    with pytest.raises(IntegrityError) as raised:
        resolve_application_user(subject)

    constraint_name = raised.value.__cause__.diag.constraint_name  # type: ignore[union-attr]
    if create_conflict == "primary-key":
        assert constraint_name == "accounts_user_pkey"
    else:
        assert constraint_name == "accounts_user_clerk_user_id_not_empty"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cause",
    (
        None,
        errors.UniqueViolation(
            "test-only missing-constraint metadata",
            info={DiagnosticField.SQLSTATE: b"23505"},
        ),
    ),
    ids=("no-psycopg-cause", "missing-constraint-metadata"),
)
def test_integrity_error_without_the_expected_structured_metadata_propagates(
    monkeypatch: MonkeyPatch, cause: BaseException | None
) -> None:
    original = IntegrityError("test-only integrity sentinel")
    error = original if cause is None else _with_cause(original, cause)
    monkeypatch.setattr(User.objects, "create_user", lambda *_args, **_kwargs: _raise(error))

    with pytest.raises(IntegrityError) as raised:
        resolve_application_user("user_bad_integrity_metadata")

    assert raised.value is error


@pytest.mark.django_db
def test_expected_unique_metadata_without_a_winner_reraises_the_original_failure(
    monkeypatch: MonkeyPatch,
) -> None:
    original = _with_cause(IntegrityError("test-only original failure"), _expected_unique_violation())
    monkeypatch.setattr(User.objects, "create_user", lambda *_args, **_kwargs: _raise(original))

    with pytest.raises(IntegrityError) as raised:
        resolve_application_user("user_missing_winner")

    assert raised.value is original


def _operational_error_with(cause: BaseException | None) -> OperationalError:
    error = OperationalError("test-only database connection detail")
    return error if cause is None else _with_cause(error, cause)  # type: ignore[return-value]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cause",
    (
        errors.ConnectionFailure("test-only 08 detail"),
        errors.AdminShutdown("test-only 57P01 detail"),
        errors.CrashShutdown("test-only 57P02 detail"),
        errors.CannotConnectNow("test-only 57P03 detail"),
        psycopg.OperationalError("test-only absent-connection-state detail"),
        psycopg.OperationalError(
            "test-only bad-connection-state detail", pgconn=_BadPsycopgConnection()
        ),
    ),
    ids=(
        "08xxx",
        "57P01",
        "57P02",
        "57P03",
        "no-sqlstate-absent-connection",
        "no-sqlstate-bad-connection",
    ),
)
def test_only_confident_structured_availability_errors_become_provider_neutral(
    monkeypatch: MonkeyPatch, cause: BaseException
) -> None:
    subject = "user_availability_sentinel"
    error = _operational_error_with(cause)
    monkeypatch.setattr(User.objects, "get", lambda *_args, **_kwargs: _raise(error))

    with pytest.raises(ApplicationUserResolutionUnavailable) as raised:
        resolve_application_user(subject)

    rendered = f"{raised.value}\n{raised.value!r}"
    for sensitive_value in (
        subject,
        "test-only database connection detail",
        str(getattr(cause, "sqlstate", "")),
        "connection",
        "constraint",
    ):
        assert sensitive_value not in rendered


@pytest.mark.django_db
@pytest.mark.parametrize(
    "error",
    (
        _operational_error_with(errors.DiskFull("test-only 53 detail")),
        OperationalError("test-only plain Django operational error"),
        DatabaseError("test-only database sentinel"),
        IntegrityError("test-only integrity sentinel"),
    ),
    ids=("53xxx-resource", "plain-operational", "database", "integrity"),
)
def test_unclassified_database_failures_propagate_unchanged(
    monkeypatch: MonkeyPatch, error: DatabaseError
) -> None:
    monkeypatch.setattr(User.objects, "get", lambda *_args, **_kwargs: _raise(error))

    with pytest.raises(type(error)) as raised:
        resolve_application_user("user_unclassified_database_failure")

    assert raised.value is error


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION,
)
def test_successful_authentication_exposes_only_the_resolved_application_user(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ClerkSessionVerifier,
        "verify",
        lambda *_args, **_kwargs: VerifiedClerkIdentity(subject="user_test_subject"),
    )

    response = Client().get("/test/identity", HTTP_AUTHORIZATION="Bearer test")
    resolved_user = User.objects.get(clerk_user_id="user_test_subject")

    assert response.status_code == 200
    assert response.json() == {"user_id": resolved_user.pk, "auth_is_none": True}


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__, REST_FRAMEWORK=AUTHENTICATION_SETTINGS, CLERK_AUTHENTICATION=None
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
    DEBUG=False,
)
def test_malformed_credentials_are_a_generic_bearer_401() -> None:
    response = Client().get("/test/identity", HTTP_AUTHORIZATION="Basic credential")

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"
    assert "credential" not in response.content.decode()


@pytest.mark.django_db
@override_settings(
    ROOT_URLCONF=__name__,
    REST_FRAMEWORK=AUTHENTICATION_SETTINGS,
    CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION,
    DEBUG=False,
)
def test_resolution_unavailable_is_a_sanitized_fixed_503(monkeypatch: MonkeyPatch) -> None:
    sentinel_subject = "user_503_subject_sentinel"
    sentinel_detail = "database host and constraint detail sentinel"
    monkeypatch.setattr(
        ClerkSessionVerifier,
        "verify",
        lambda *_args, **_kwargs: VerifiedClerkIdentity(subject=sentinel_subject),
    )
    monkeypatch.setattr(
        drf_adapter,
        "resolve_application_user",
        lambda *_args, **_kwargs: _raise(
            ApplicationUserResolutionUnavailable(sentinel_detail)
        ),
    )

    response = Client().get("/test/identity", HTTP_AUTHORIZATION="Bearer test")
    body = response.content.decode()

    assert response.status_code == 503
    assert sentinel_subject not in body
    assert sentinel_detail not in body


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
    monkeypatch.setattr(
        ClerkSessionVerifier,
        "verify",
        lambda *_args, **_kwargs: VerifiedClerkIdentity(subject="user_500_subject"),
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
    assert sentinel_detail not in response.content.decode()


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


def test_global_authentication_contract_has_one_tailtag_class_and_no_permission_default() -> None:
    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "authentication.drf.TailTagAuthentication"
    ]
    assert "DEFAULT_PERMISSION_CLASSES" not in settings.REST_FRAMEWORK
