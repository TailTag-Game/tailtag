"""Database and structured-error acceptance tests for player profiles."""

from __future__ import annotations

from typing import cast

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone
from psycopg import errors
from psycopg.pq import DiagnosticField

from tests.authentication_support import create_test_user

HANDLE_UNIQUE = "profiles_player_profile_handle_unique"
EXPECTED_CONSTRAINTS = {
    HANDLE_UNIQUE,
    "profiles_player_profile_handle_format",
    "profiles_player_profile_onboarding_state_consistent",
}


def _with_cause[ExceptionT: BaseException](
    error: ExceptionT, cause: BaseException
) -> ExceptionT:
    try:
        raise error from cause
    except type(error) as raised:
        return cast(ExceptionT, raised)


def _unique_violation(
    *, sqlstate: bytes = b"23505", constraint: str = HANDLE_UNIQUE
) -> errors.UniqueViolation:
    return errors.UniqueViolation(
        "hostile prose must not matter",
        info={
            DiagnosticField.SQLSTATE: sqlstate,
            DiagnosticField.CONSTRAINT_NAME: constraint.encode(),
        },
    )


@pytest.mark.django_db
def test_profile_uses_the_user_as_its_only_primary_key_and_has_all_named_constraints() -> (
    None
):
    """Rejects a surrogate profile identity or constraints renamed away from the contract."""
    from profiles.models import PlayerProfile

    assert PlayerProfile._meta.pk.name == "user"
    assert all(field.name != "id" for field in PlayerProfile._meta.concrete_fields)
    constraints = connection.introspection.get_constraints(
        connection.cursor(), PlayerProfile._meta.db_table
    )
    assert EXPECTED_CONSTRAINTS.issubset(constraints)
    assert constraints[HANDLE_UNIQUE]["unique"]


@pytest.mark.django_db
def test_profile_database_accepts_default_and_completed_shapes_but_rejects_invalid_ones() -> (
    None
):
    """Rejects relying only on serializers for the durable lifecycle and handle invariant."""
    from profiles.models import PlayerProfile

    default = PlayerProfile.objects.create(user=create_test_user())
    complete = PlayerProfile.objects.create(
        user=create_test_user(),
        handle="valid_1",
        display_name="Valid",
        onboarding_completed_at=timezone.now(),
    )
    assert default.onboarding_completed_at is None
    assert complete.user_id == complete.pk

    with pytest.raises(IntegrityError), transaction.atomic():
        PlayerProfile.objects.create(
            user=create_test_user(),
            handle="Bad-Handle",
            display_name="Valid",
            onboarding_completed_at=timezone.now(),
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        PlayerProfile.objects.create(user=create_test_user(), handle="partial_1")


@pytest.mark.parametrize(
    "cause",
    (
        _unique_violation(),
        _unique_violation(constraint="other_unique"),
        _unique_violation(sqlstate=b"23503"),
        errors.CheckViolation(
            "check",
            info={
                DiagnosticField.SQLSTATE: b"23514",
                DiagnosticField.CONSTRAINT_NAME: HANDLE_UNIQUE.encode(),
            },
        ),
        errors.ForeignKeyViolation(
            "fk",
            info={
                DiagnosticField.SQLSTATE: b"23503",
                DiagnosticField.CONSTRAINT_NAME: HANDLE_UNIQUE.encode(),
            },
        ),
        None,
    ),
    ids=(
        "expected",
        "other-constraint",
        "wrong-sqlstate",
        "check",
        "foreign-key",
        "bare",
    ),
)
def test_handle_unique_classifier_uses_only_structured_expected_postgresql_metadata(
    cause: BaseException | None,
) -> None:
    """Rejects matching exception prose, any 23505, or unrelated database constraints."""
    from profiles.services import _is_handle_unique_violation

    error = IntegrityError("duplicate handle according to hostile text")
    wrapped = error if cause is None else _with_cause(error, cause)
    assert _is_handle_unique_violation(wrapped) is (
        cause is not None
        and cause is not None
        and cause.diag.sqlstate == "23505"
        and cause.diag.constraint_name == HANDLE_UNIQUE
    )
