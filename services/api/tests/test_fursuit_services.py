"""Domain-service acceptance tests; deliberately no view/serializer coupling."""

from __future__ import annotations

from typing import Never

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings
from django.utils import timezone

from accounts.models import User
from fursuits.models import Fursuit
from fursuits.services import (
    FursuitWriteIneligibleError,
    create_fursuit,
    get_owned_fursuit,
    replace_fursuit_photo,
    require_fursuit_write_eligible,
    update_fursuit_name,
)
from profiles.models import PlayerProfile
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record
from tests.profile_test_support import (
    RECORDING_STORAGES,
    RecordingStorage,
    image_upload,
)


@pytest.mark.django_db
def test_write_eligibility_is_read_only_and_rejects_every_bad_profile_shape() -> None:
    user = User.objects.create_user(clerk_user_id="user_missing_profile")
    before = PlayerProfile.objects.count()
    with pytest.raises(FursuitWriteIneligibleError):
        require_fursuit_write_eligible(user)
    assert PlayerProfile.objects.count() == before
    for shape in ("incomplete", "disabled"):
        candidate = User.objects.create_user(
            clerk_user_id=f"user_{shape}_{PlayerProfile.objects.count()}"
        )
        if shape == "incomplete":
            PlayerProfile.objects.create(user=candidate)
        elif shape == "disabled":
            PlayerProfile.objects.create(
                user=candidate,
                handle="disabled_1",
                display_name="Disabled",
                onboarding_completed_at=timezone.now(),
                is_enabled=False,
            )
        with pytest.raises(FursuitWriteIneligibleError):
            require_fursuit_write_eligible(candidate)


@pytest.mark.django_db
def test_create_and_update_only_persist_server_controlled_fields_and_noop_does_not_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_eligible_user()
    created = create_fursuit(owner, name="  Fi\u006e\u0303 Wolf ", photo=image_upload())
    assert (created.owner_id, created.name, created.is_enabled) == (
        owner.id,
        "Fiñ Wolf",
        True,
    )
    assert isinstance(created.photo_key, str) and created.photo_key
    timestamp = created.updated_at
    saves = 0
    original = type(created).save

    def record_save(record: Fursuit, *args: object, **kwargs: object) -> object:
        nonlocal saves
        saves += 1
        return original(record, *args, **kwargs)

    monkeypatch.setattr(type(created), "save", record_save)
    no_op = update_fursuit_name(owner, fursuit_id=created.id, name=" Fiñ   Wolf ")
    created.refresh_from_db()
    assert saves == 0 and created.updated_at == timestamp
    assert (no_op.pk, no_op.owner_id, no_op.name, no_op.updated_at) == (
        created.pk,
        created.owner_id,
        created.name,
        timestamp,
    )
    changed = update_fursuit_name(owner, fursuit_id=created.id, name="Renamed")
    created.refresh_from_db()
    assert created.name == "Renamed" and created.updated_at > timestamp
    assert (changed.pk, changed.name, changed.updated_at) == (
        created.pk,
        "Renamed",
        created.updated_at,
    )


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_create_saves_media_before_commit_and_compensates_commit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_eligible_user()
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    from fursuits import services

    failure = RuntimeError("commit sentinel")

    def fail_commit(*_args: object, **_kwargs: object) -> Never:
        raise failure

    monkeypatch.setattr(
        services,
        "_commit_created_fursuit",
        fail_commit,
    )
    with pytest.raises(RuntimeError) as raised:
        create_fursuit(owner, name="New", photo=image_upload())
    assert raised.value is failure
    assert [event[0] for event in storage.events] == ["save", "delete"]


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_create_compensation_does_not_replace_the_original_commit_failure_when_delete_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fursuits import services

    owner = create_eligible_user()
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    failure = RuntimeError("authoritative commit failure")

    def fail_commit(*_args: object, **_kwargs: object) -> Never:
        raise failure

    def fail_cleanup(_key: str) -> Never:
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(
        services,
        "_commit_created_fursuit",
        fail_commit,
    )
    monkeypatch.setattr(
        storage,
        "delete",
        fail_cleanup,
    )
    with pytest.raises(RuntimeError) as raised:
        create_fursuit(owner, name="New", photo=image_upload())
    assert raised.value is failure


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_replace_fursuit_photo_is_a_service_boundary_and_commits_before_old_cleanup() -> (
    None
):
    owner = create_eligible_user()
    record = create_fursuit_record(owner=owner)
    old_key = record.photo_key
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    replaced = replace_fursuit_photo(owner, fursuit_id=record.id, photo=image_upload())
    record.refresh_from_db()
    assert replaced.pk == record.pk
    assert replaced.photo_key == record.photo_key and record.photo_key != old_key
    assert [event[0] for event in storage.events] == ["save", "delete"]


@pytest.mark.django_db
def test_owned_lookup_conceals_cross_owner() -> None:
    from fursuits.models import Fursuit

    owned = create_fursuit_record(owner=create_eligible_user())
    with pytest.raises(Fursuit.DoesNotExist):
        get_owned_fursuit(create_eligible_user(), owned.id)
