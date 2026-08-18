"""Independent acceptance contract for Clerk-to-TailTag identity resolution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import NoReturn

import psycopg
import pytest
from django.db import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    close_old_connections,
    connection,
    transaction,
)
from django.db.backends.utils import CursorWrapper
from django.test.utils import CaptureQueriesContext
from psycopg import errors
from psycopg.pq import ConnStatus, DiagnosticField
from pytest import MonkeyPatch

from accounts.models import User
from accounts.resolution import (
    EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT,
    ApplicationUserResolutionUnavailable,
    resolve_application_user,
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


def _fail_database_execution(monkeypatch: MonkeyPatch, error: DatabaseError) -> None:
    """Inject a database failure below the resolver's ORM lookup choice."""

    def raise_database_error(
        _cursor: CursorWrapper, _sql: str, _params: object = None
    ) -> NoReturn:
        raise error

    monkeypatch.setattr(CursorWrapper, "execute", raise_database_error)


@pytest.mark.django_db
def test_first_resolution_provisions_only_the_minimal_tailtag_user(
    monkeypatch: MonkeyPatch,
) -> None:
    manager = User.objects
    original_create_user = manager.create_user
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def observe_create_user(*args: object, **kwargs: object) -> User:
        calls.append((args, kwargs))
        return original_create_user(*args, **kwargs)

    monkeypatch.setattr(manager, "create_user", observe_create_user)
    user = resolve_application_user("user_first_use")

    assert len(calls) == 1
    positional, keyword = calls[0]
    assert not set(keyword) - {"clerk_user_id"}
    assert len(positional) + len(keyword) == 1
    assert positional == ("user_first_use",) or keyword == {
        "clerk_user_id": "user_first_use"
    }
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
            connection.close()

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


@pytest.mark.django_db(transaction=True)
def test_expected_unique_violation_rereads_the_winner_after_inner_savepoint_rollback(
    monkeypatch: MonkeyPatch,
) -> None:
    subject = "user_recover_after_savepoint"
    manager = User.objects
    original_create_user = manager.create_user
    original_get = manager.get

    def create_winner_on_a_separate_connection(*args: object, **kwargs: object) -> User:
        def create_winner() -> User:
            close_old_connections()
            try:
                return original_create_user(*args, **kwargs)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as executor:
            winner = executor.submit(create_winner).result(timeout=10)
        original_create_user(*args, **kwargs)
        return winner

    monkeypatch.setattr(manager, "create_user", create_winner_on_a_separate_connection)

    with transaction.atomic():
        resolved = resolve_application_user(subject)
        winner = original_get(clerk_user_id=subject)
        assert winner.pk == resolved.pk

    assert User.objects.filter(clerk_user_id=subject).count() == 1


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
        errors.ForeignKeyViolation(
            "test-only non-23505 expected-constraint sentinel",
            info={
                DiagnosticField.SQLSTATE: b"23503",
                DiagnosticField.CONSTRAINT_NAME: EXPECTED_CLERK_USER_ID_UNIQUE_CONSTRAINT.encode(),
            },
        ),
    ),
    ids=(
        "no-psycopg-cause",
        "missing-constraint-metadata",
        "non-23505-expected-constraint",
    ),
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
    _fail_database_execution(monkeypatch, error)

    with pytest.raises(ApplicationUserResolutionUnavailable) as raised:
        resolve_application_user(subject)

    rendered = f"{raised.value}\n{raised.value!r}"
    sensitive_values = [
        subject,
        "test-only database connection detail",
        str(cause),
        "connection",
        "constraint",
    ]
    if sqlstate := getattr(cause, "sqlstate", None):
        sensitive_values.append(str(sqlstate))
    for sensitive_value in sensitive_values:
        assert sensitive_value not in rendered


@pytest.mark.django_db
@pytest.mark.parametrize(
    "cause",
    (
        psycopg.OperationalError(
            "test-only empty-sqlstate sentinel",
            info={DiagnosticField.SQLSTATE: b""},
        ),
        psycopg.OperationalError(
            "test-only unrecognized-sqlstate sentinel",
            info={DiagnosticField.SQLSTATE: b"ZZ999"},
            pgconn=_BadPsycopgConnection(),
        ),
    ),
    ids=("empty-sqlstate-absent-connection", "unrecognized-sqlstate-bad-connection"),
)
def test_present_sqlstate_never_uses_the_connection_state_fallback(
    monkeypatch: MonkeyPatch, cause: BaseException
) -> None:
    """Only an exactly-None SQLSTATE permits client-side availability recovery."""
    error = _operational_error_with(cause)
    _fail_database_execution(monkeypatch, error)

    with pytest.raises(OperationalError) as raised:
        resolve_application_user("user_present_sqlstate_sentinel")

    assert raised.value is error


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
    _fail_database_execution(monkeypatch, error)

    with pytest.raises(type(error)) as raised:
        resolve_application_user("user_unclassified_database_failure")

    assert raised.value is error
