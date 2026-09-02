"""Persistent public TailTag identity acceptance contract for fursuits."""

from __future__ import annotations

import uuid

import pytest
from django.db import connection

from fursuits.models import Fursuit
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record


@pytest.mark.django_db
def test_tailtag_id_is_non_null_unique_read_only_uuid_with_per_record_default() -> None:
    field = Fursuit._meta.get_field("tailtag_id")
    assert field.default is uuid.uuid4
    assert field.null is False
    assert field.unique is True
    assert field.editable is False

    owner = create_eligible_user()
    first = create_fursuit_record(owner=owner, name="First identity")
    second = create_fursuit_record(owner=owner, name="Second identity")
    assert isinstance(first.tailtag_id, uuid.UUID)
    assert isinstance(second.tailtag_id, uuid.UUID)
    assert first.tailtag_id != second.tailtag_id
    assert first.tailtag_id != first.id


@pytest.mark.django_db(transaction=True)
def test_tailtag_id_migration_backfills_each_existing_fursuit_distinctly() -> None:
    """Pre-existing rows gain independent UUIDs, not one migration-time default."""
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    executor.migrate([("fursuits", "0001_initial")])
    try:
        old_apps = executor.loader.project_state([("fursuits", "0001_initial")]).apps
        OldUser = old_apps.get_model("accounts", "User")
        OldFursuit = old_apps.get_model("fursuits", "Fursuit")
        owner = OldUser.objects.create(
            clerk_user_id="user_tailtag_migration_owner",
            password="!",
            is_staff=False,
            is_superuser=False,
        )
        first = OldFursuit.objects.create(
            owner_id=owner.pk,
            name="Migration First",
            photo_key="images/11111111111111111111111111111111.png",
            is_enabled=True,
        )
        second = OldFursuit.objects.create(
            owner_id=owner.pk,
            name="Migration Second",
            photo_key="images/22222222222222222222222222222222.png",
            is_enabled=True,
        )
        executor = MigrationExecutor(connection)
        executor.migrate([("fursuits", "0002_fursuit_tailtag_id")])
        NewFursuit = executor.loader.project_state(
            [("fursuits", "0002_fursuit_tailtag_id")]
        ).apps.get_model("fursuits", "Fursuit")
        values = list(
            NewFursuit.objects.filter(pk__in=[first.pk, second.pk]).values_list(
                "tailtag_id", flat=True
            )
        )
        assert len(values) == len(set(values)) == 2
        assert all(isinstance(value, uuid.UUID) for value in values)
    finally:
        MigrationExecutor(connection).migrate(latest)
