"""Database and structured-error acceptance tests for player profiles."""

from __future__ import annotations

from typing import cast

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.backends.utils import CursorWrapper
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
    for handle, display_name, completed_at in (
        ("partial_1", None, None),
        (None, None, timezone.now()),
        (None, "Display", None),
        (None, "Display", timezone.now()),
        ("partial_2", None, timezone.now()),
        ("partial_3", "", timezone.now()),
        ("partial_4", "Display", None),
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            PlayerProfile.objects.create(
                user=create_test_user(),
                handle=handle,
                display_name=display_name,
                onboarding_completed_at=completed_at,
            )


@pytest.mark.parametrize(
    ("cause", "expected"),
    (
        (_unique_violation(), True),
        (_unique_violation(constraint="other_unique"), False),
        (_unique_violation(sqlstate=b"23503"), False),
        (
            errors.CheckViolation(
                "check",
                info={
                    DiagnosticField.SQLSTATE: b"23514",
                    DiagnosticField.CONSTRAINT_NAME: HANDLE_UNIQUE.encode(),
                },
            ),
            False,
        ),
        (
            errors.ForeignKeyViolation(
                "fk",
                info={
                    DiagnosticField.SQLSTATE: b"23503",
                    DiagnosticField.CONSTRAINT_NAME: HANDLE_UNIQUE.encode(),
                },
            ),
            False,
        ),
        (
            errors.InvalidSchemaName(
                "schema", info={DiagnosticField.SQLSTATE: b"3F000"}
            ),
            False,
        ),
        (
            errors.SyntaxError(
                "programming", info={DiagnosticField.SQLSTATE: b"42601"}
            ),
            False,
        ),
        (None, False),
    ),
    ids=(
        "expected",
        "other-constraint",
        "wrong-sqlstate",
        "check",
        "foreign-key",
        "schema",
        "programming",
        "bare",
    ),
)
def test_handle_unique_classifier_uses_only_structured_expected_postgresql_metadata(
    cause: BaseException | None, expected: bool
) -> None:
    """Rejects matching exception prose, any 23505, or unrelated database constraints."""
    from profiles.services import _is_handle_unique_violation

    error = IntegrityError("duplicate handle according to hostile text")
    wrapped = error if cause is None else _with_cause(error, cause)
    assert _is_handle_unique_violation(wrapped) is expected


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ("put", "patch"))
def test_text_write_services_propagate_unrelated_integrity_failures(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """Rejects text writers that convert every database integrity error into duplicate handle."""
    from profiles import services
    from profiles.models import PlayerProfile

    user = create_test_user()
    PlayerProfile.objects.create(
        user=user,
        handle="existing_1",
        display_name="Existing",
        onboarding_completed_at=timezone.now(),
    )
    original_execute = CursorWrapper.execute
    failure = _with_cause(
        IntegrityError("hostile unrelated integrity failure"),
        errors.CheckViolation(
            "hostile unrelated check failure",
            info={
                DiagnosticField.SQLSTATE: b"23514",
                DiagnosticField.CONSTRAINT_NAME: b"profiles_unrelated_check",
            },
        ),
    )

    def fail_update(cursor: CursorWrapper, sql: str, params: object = None) -> object:
        if sql.lstrip().upper().startswith("UPDATE"):
            raise failure
        return original_execute(cursor, sql, params)

    monkeypatch.setattr(CursorWrapper, "execute", fail_update)

    with pytest.raises(IntegrityError) as raised:
        if operation == "put":
            services.put_text_profile(user, handle="updated_1", display_name="Updated")
        else:
            services.patch_text_profile(user, handle="updated_1")

    assert raised.value is failure
