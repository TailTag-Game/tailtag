"""PostgreSQL persistence and normalization acceptance contract for fursuits."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, models, transaction

from fursuits.models import Fursuit
from fursuits.normalization import FursuitNameError, normalize_fursuit_name
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
    owner = Fursuit._meta.get_field("owner")
    name = Fursuit._meta.get_field("name")
    key = Fursuit._meta.get_field("photo_key")
    enabled = Fursuit._meta.get_field("is_enabled")
    created = Fursuit._meta.get_field("created_at")
    updated = Fursuit._meta.get_field("updated_at")
    assert isinstance(owner, models.ForeignKey) and not owner.null
    assert (
        isinstance(name, models.CharField) and name.max_length == 50 and not name.null
    )
    assert isinstance(key, models.TextField) and not key.null
    assert isinstance(enabled, models.BooleanField) and enabled.default is True
    assert isinstance(created, models.DateTimeField) and not created.null
    assert isinstance(updated, models.DateTimeField) and not updated.null


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


@pytest.mark.django_db
def test_player_domain_services_cannot_mutate_an_existing_fursuit_owner() -> None:
    from fursuits.services import update_fursuit_name

    owner = create_eligible_user()
    different_user = create_eligible_user()
    record = create_fursuit_record(owner=owner)
    update_fursuit_name(owner, fursuit_id=record.id, name="Changed")
    record.refresh_from_db()
    assert record.owner_id == owner.id
    assert record.owner_id != different_user.id


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
