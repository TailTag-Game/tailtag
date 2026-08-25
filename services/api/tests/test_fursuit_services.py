"""Domain-service acceptance tests; deliberately no view/serializer coupling."""

from __future__ import annotations

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings
from django.utils import timezone
from fursuits.services import (
    FursuitWriteIneligibleError,
    create_fursuit,
    get_owned_fursuit,
    require_fursuit_write_eligible,
    update_fursuit_name,
)

from accounts.models import User
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
    for shape in ("incomplete", "disabled", "inconsistent"):
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
        else:
            PlayerProfile.objects.create(
                user=candidate,
                handle="inconsistent_1",
                display_name="Inconsistent",
                onboarding_completed_at=None,
            )
        with pytest.raises(FursuitWriteIneligibleError):
            require_fursuit_write_eligible(candidate)


@pytest.mark.django_db
def test_create_and_update_only_persist_server_controlled_fields_and_noop_does_not_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = create_eligible_user()
    created = create_fursuit(
        owner, name="  Fi\u006e\u0303 Wolf ", upload=image_upload()
    )
    assert (created.owner_id, created.name, created.is_enabled) == (
        owner.id,
        "Fiñ Wolf",
        True,
    )
    assert isinstance(created.photo_key, str) and created.photo_key
    timestamp = created.updated_at
    saves = 0
    original = type(created).save

    def record_save(record: object, *args: object, **kwargs: object) -> object:
        nonlocal saves
        saves += 1
        return original(record, *args, **kwargs)

    monkeypatch.setattr(type(created), "save", record_save)
    assert update_fursuit_name(owner, created, name=" Fiñ   Wolf ") is created
    created.refresh_from_db()
    assert saves == 0 and created.updated_at == timestamp
    update_fursuit_name(owner, created, name="Renamed")
    created.refresh_from_db()
    assert created.name == "Renamed" and created.updated_at > timestamp


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
    monkeypatch.setattr(
        services,
        "_commit_created_fursuit",
        lambda *args, **kwargs: (_ for _ in ()).throw(failure),
    )
    with pytest.raises(RuntimeError) as raised:
        create_fursuit(owner, name="New", upload=image_upload())
    assert raised.value is failure
    assert [event[0] for event in storage.events] == ["save", "delete"]


@pytest.mark.django_db
def test_owned_lookup_conceals_cross_owner() -> None:
    from fursuits.models import Fursuit

    owned = create_fursuit_record(owner=create_eligible_user())
    with pytest.raises(Fursuit.DoesNotExist):
        get_owned_fursuit(create_eligible_user(), owned.id)
