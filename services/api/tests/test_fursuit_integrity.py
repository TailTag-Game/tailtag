"""PostgreSQL persistence and normalization acceptance contract for fursuits."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, models, transaction
from fursuits.normalization import FursuitNameError, normalize_fursuit_name

from fursuits.models import Fursuit
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record


def test_fursuit_model_has_the_exact_durable_shape() -> None:
    assert Fursuit._meta.pk.get_internal_type() == "BigAutoField"
    assert Fursuit._meta.ordering == ["id"]
    assert Fursuit._meta.get_field("owner").remote_field.on_delete is models.PROTECT
    assert Fursuit._meta.get_field("owner").remote_field.related_name == "fursuits"
    assert {constraint.name for constraint in Fursuit._meta.constraints} == {
        "fursuits_fursuit_name_not_empty",
        "fursuits_fursuit_photo_key_not_empty",
    }


@pytest.mark.django_db
def test_database_rejects_empty_values_and_protects_an_owner() -> None:
    user = create_eligible_user()
    for name, key in (("", "images/a.png"), ("Name", "")):
        with pytest.raises(IntegrityError), transaction.atomic():
            Fursuit.objects.create(owner=user, name=name, photo_key=key)
    create_fursuit_record(owner=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        user.delete()


@pytest.mark.django_db
def test_defaults_timestamps_ordering_and_non_unique_names() -> None:
    owner = create_eligible_user()
    first = create_fursuit_record(owner=owner, name="Twin")
    second = create_fursuit_record(owner=owner, name="Twin")
    assert first.is_enabled is True
    created_at = first.created_at
    updated_at = first.updated_at
    first.name = "Changed"
    first.save(update_fields=["name", "updated_at"])
    first.refresh_from_db()
    assert first.created_at == created_at
    assert first.updated_at > updated_at
    assert list(Fursuit.objects.values_list("id", flat=True)) == [first.id, second.id]


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        ("Fi\u006e\u0303", "Fiñ"),
        ("  Finn\u00a0\u2003Wolf ", "Finn Wolf"),
        ("x" * 50, "x" * 50),
    ),
)
def test_normalizes_unicode_names(value: str, expected: str) -> None:
    assert normalize_fursuit_name(value) == expected


@pytest.mark.parametrize(
    "value",
    (
        "",
        " \t\u00a0",
        "before\x00after",
        "before\u2028after",
        "before\u2029after",
        "x" * 51,
    ),
)
def test_normalization_rejects_empty_controls_separators_and_overlong_names(
    value: str,
) -> None:
    with pytest.raises(FursuitNameError):
        normalize_fursuit_name(value)
