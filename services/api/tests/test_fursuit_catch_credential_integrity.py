"""PostgreSQL persistence and protocol acceptance contract for credentials."""

from __future__ import annotations

import datetime

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
