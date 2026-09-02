"""PostgreSQL persistence and protocol acceptance contract for credentials."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any, NoReturn

import pytest
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from tests.catch_credential_test_support import (
    TOKEN_A,
    TOKEN_B,
    catch_credential_model,
    create_credential,
    create_credential_scenario,
)
from tests.fursuit_activation_test_support import create_activation_row


class _DiagnosticCause(Exception):
    def __init__(self, name: str) -> None:
        self.diag = SimpleNamespace(constraint_name=name)


def _with_constraint_cause(error: IntegrityError, name: str) -> IntegrityError:
    """Attach only structured diagnostic metadata; error prose is deliberately hostile."""
    cause = _DiagnosticCause(name)
    try:
        raise error from cause
    except IntegrityError as raised:
        return raised


def _raise(error: BaseException) -> NoReturn:
    raise error


@pytest.mark.django_db
def test_credential_history_has_protected_activation_shape_safe_representation_and_newest_order() -> (
    None
):
    """AC-03/16: rejects CASCADE, an exposed token repr, or non-historical ordering."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    model = catch_credential_model()
    fields = {field.name: field for field in model._meta.fields}
    assert isinstance(fields["id"], models.BigAutoField) and fields["id"].primary_key
    assert fields["activation"].remote_field.on_delete is models.PROTECT
    assert fields["activation"].remote_field.related_name == "catch_credentials"
    assert fields["token"].null is False and fields["token"].max_length == 43
    assert fields["revoked_at"].null is True
    assert fields["revocation_reason"].null is True
    assert model.objects.count() == 0  # Migration must not backfill credentials.
    first = create_credential(
        activation=activation,
        token=TOKEN_A,
        revoked_at=timezone.now(),
        revocation_reason="owner_rotation",
    )
    second = create_credential(activation=activation, token=TOKEN_B)
    assert list(model.objects.filter(activation=activation)) == [second, first]
    assert TOKEN_A not in str(first) and TOKEN_A not in repr(first)
    with pytest.raises(models.ProtectedError):
        activation.delete()


@pytest.mark.django_db
def test_named_constraints_reject_invalid_pairs_reasons_duplicate_tokens_and_two_currents() -> (
    None
):
    """AC-03/14: rejects weak paired fields, enums, global uniqueness, or partial uniqueness."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    model = catch_credential_model()
    constraints = model._meta.constraints
    assert all(constraint.name for constraint in constraints)
    assert any(
        isinstance(constraint, models.UniqueConstraint)
        and constraint.fields == ("token",)
        for constraint in constraints
    )
    assert any(
        isinstance(constraint, models.UniqueConstraint)
        and constraint.fields == ("activation",)
        and constraint.condition is not None
        for constraint in constraints
    )
    now = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
    for overrides in (
        {"revoked_at": now},
        {"revocation_reason": "operator"},
        {"revoked_at": now, "revocation_reason": "invalid"},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            create_credential(activation=activation, **overrides)
    create_credential(activation=activation, token=TOKEN_A)
    other = create_activation_row(
        fursuit=create_credential_scenario(clerk_user_id="credential_other").fursuit,
        convention=scenario.convention,
        active=True,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        create_credential(activation=other, token=TOKEN_A)
    with pytest.raises(IntegrityError), transaction.atomic():
        create_credential(activation=activation, token=TOKEN_B)


@pytest.mark.django_db
def test_credential_payload_protocol_is_exact_and_malformed_inputs_are_safe_and_nonpersistent() -> (
    None
):
    """AC-04/16: rejects permissive envelopes, normalization, or secret-bearing errors."""
    from conventions.catch_credentials import (
        CatchCredentialPayloadInvalidError,
        format_catch_credential_payload,
        parse_catch_credential_payload,
    )

    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    del activation
    model = catch_credential_model()
    assert format_catch_credential_payload(TOKEN_A) == f"tailtag:catch:v1:{TOKEN_A}"
    assert parse_catch_credential_payload(f"tailtag:catch:v1:{TOKEN_A}") == TOKEN_A
    malformed = (
        "",
        TOKEN_A,
        f" tailtag:catch:v1:{TOKEN_A}",
        f"tailtag:catch:v1:{TOKEN_A} ",
        f"tailtag:catch:v2:{TOKEN_A}",
        f"tailtag:catch:v1:{TOKEN_A[:-1]}",
        f"tailtag:catch:v1:{TOKEN_A}A",
        f"tailtag:catch:v1:{TOKEN_A[:-1]}=",
        f"tailtag:catch:v1:{TOKEN_A[:-1]}!",
        f"tailtag:catch:v1:{TOKEN_A[:-1]}é",
    )
    for value in malformed:
        before = model.objects.count()
        with pytest.raises(CatchCredentialPayloadInvalidError) as parsed:
            parse_catch_credential_payload(value)
        assert parsed.value.args == () and not str(parsed.value)
        assert model.objects.count() == before
    for token in ("", TOKEN_A[:-1], TOKEN_A + "A", TOKEN_A[:-1] + "!"):
        with pytest.raises(CatchCredentialPayloadInvalidError) as formatted:
            format_catch_credential_payload(token)
        assert formatted.value.args == () and token not in str(formatted.value)


@pytest.mark.django_db
def test_private_current_creation_generates_raw_token_once_and_formats_only_at_protocol_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-04: rejects envelope persistence, wrong entropy size, or implicit formatting."""
    from conventions import catch_credentials

    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    calls: list[int] = []

    def token_urlsafe(size: int) -> str:
        calls.append(size)
        return TOKEN_A

    monkeypatch.setattr(catch_credentials.secrets, "token_urlsafe", token_urlsafe)
    credential = catch_credentials._create_current_catch_credential(activation)
    assert calls == [32] and credential.token == TOKEN_A
    assert credential.token != catch_credentials.format_catch_credential_payload(
        credential.token
    )
    assert list(catch_credential_model().objects.values_list("token", flat=True)) == [
        TOKEN_A
    ]


@pytest.mark.django_db
def test_private_creation_retries_only_one_named_token_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-04/05: rejects message matching, no retry, or unbounded token collision loops."""
    from conventions import catch_credentials

    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    model = catch_credential_model()
    original_create = model.objects.create
    token_calls: list[int] = []
    create_calls = 0

    def token_urlsafe(size: int) -> str:
        token_calls.append(size)
        return TOKEN_A if len(token_calls) == 1 else TOKEN_B

    first = _with_constraint_cause(
        IntegrityError("hostile prose that happens to mention unique"),
        "conventions_catch_credential_token_unique",
    )

    def create(*args: Any, **kwargs: Any) -> Any:
        nonlocal create_calls
        create_calls += 1
        if create_calls == 1:
            _raise(first)
        return original_create(*args, **kwargs)

    monkeypatch.setattr(catch_credentials.secrets, "token_urlsafe", token_urlsafe)
    monkeypatch.setattr(model.objects, "create", create)
    credential = catch_credentials._create_current_catch_credential(activation)
    assert credential.token == TOKEN_B
    assert token_calls == [32, 32] and create_calls == 2

    second = _with_constraint_cause(
        IntegrityError("different hostile unique prose"),
        "conventions_catch_credential_token_unique",
    )
    monkeypatch.setattr(
        model.objects, "create", lambda *_args, **_kwargs: _raise(second)
    )
    with pytest.raises(IntegrityError) as raised:
        catch_credentials._create_current_catch_credential(
            create_activation_row(
                fursuit=create_credential_scenario(
                    clerk_user_id="retry_second"
                ).fursuit,
                convention=scenario.convention,
                active=True,
            )
        )
    assert raised.value is second


@pytest.mark.django_db
def test_private_creation_recovers_only_named_current_winner_and_preserves_transaction_usability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-05/14: rejects broad integrity recovery or a broken savepoint transaction."""
    from conventions import catch_credentials

    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    winner = create_credential(activation=activation, token=TOKEN_A)
    model = catch_credential_model()
    conflict = _with_constraint_cause(
        IntegrityError("hostile text has no authority"),
        "conventions_catch_credential_one_current_per_activation",
    )
    monkeypatch.setattr(
        model.objects, "create", lambda *_args, **_kwargs: _raise(conflict)
    )
    with transaction.atomic():
        assert catch_credentials._create_current_catch_credential(activation) == winner
        assert model.objects.filter(pk=winner.pk).exists()

    unrelated = _with_constraint_cause(
        IntegrityError("mentions token unique but wrong metadata"),
        "unrelated_constraint",
    )
    monkeypatch.setattr(
        model.objects, "create", lambda *_args, **_kwargs: _raise(unrelated)
    )
    with pytest.raises(IntegrityError) as raised:
        catch_credentials._create_current_catch_credential(activation)
    assert raised.value is unrelated


@pytest.mark.django_db
def test_private_revocation_is_one_terminal_current_to_historical_transition() -> None:
    """AC-03/06/08: rejects history rewrites or a no-op that fails to set terminal fields."""
    from conventions import catch_credentials
    from conventions.models import FursuitCatchCredentialRevocationReason

    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    credential = create_credential(activation=activation, token=TOKEN_A)
    now = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
    result = catch_credentials._revoke_current_catch_credential(
        activation,
        now=now,
        reason=FursuitCatchCredentialRevocationReason.OPERATOR,
    )
    assert result is not None
    credential.refresh_from_db()
    assert credential.revoked_at == now
    assert credential.revocation_reason == "operator"
    terminal = (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    )
    assert (
        catch_credentials._revoke_current_catch_credential(
            activation,
            now=now + datetime.timedelta(seconds=1),
            reason=FursuitCatchCredentialRevocationReason.ELIGIBILITY_LOST,
        )
        is None
    )
    credential.refresh_from_db()
    assert (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    ) == terminal
