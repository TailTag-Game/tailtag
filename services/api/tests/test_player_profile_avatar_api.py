"""Acceptance tests for profile composition with the approved media interface."""

from __future__ import annotations

import logging
from typing import cast

import pytest
from django.core.files.storage import default_storage
from django.db.models.signals import post_save
from django.test import override_settings

from media.images import ImageRejectionCode
from tests.authentication_support import create_test_user, force_authenticated_client
from tests.profile_test_support import RecordingStorage, image_upload

RECORDING_STORAGES = {
    "default": {"BACKEND": "tests.profile_test_support.RecordingStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _recording_storage() -> RecordingStorage:
    # Accesses through Django's real lazy storage object; no profile code is mocked.
    return cast(RecordingStorage, default_storage)


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_avatar_upload_replacement_removal_and_fresh_reads_keep_lifecycle_state() -> (
    None
):
    """Rejects URL persistence, cleanup-before-commit, and avatar-gates-onboarding bugs."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    saves: list[str | None] = []

    def observe(
        sender: type[PlayerProfile], instance: PlayerProfile, **kwargs: object
    ) -> None:
        del sender, kwargs
        saves.append(instance.avatar_key)

    post_save.connect(observe, sender=PlayerProfile, weak=False)
    try:
        first = client.put("/api/profile/avatar/", {"avatar": image_upload()})
        assert first.status_code == 200
        assert first.json()["onboarding_complete"] is False
        storage = _recording_storage()
        first_key = PlayerProfile.objects.get(user=user).avatar_key
        assert isinstance(first_key, str)
        assert all(
            "https://media.example.test/read/" not in str(value)
            for value in (first_key,)
        )
        completed = client.put(
            "/api/profile/",
            {"handle": "finn_42", "display_name": "Finn"},
            content_type="application/json",
        )
        assert completed.status_code == 200
        second = client.put(
            "/api/profile/avatar/", {"avatar": image_upload(name="new.png")}
        )
        assert second.status_code == 200
        assert second.json()["onboarding_complete"] is True
        second_key = PlayerProfile.objects.get(user=user).avatar_key
        assert second_key != first_key
        assert storage.events[:3] == [
            ("save", cast(str, first_key)),
            ("url", cast(str, first_key)),
            ("save", cast(str, second_key)),
        ]
        assert ("delete", cast(str, first_key)) in storage.events
        assert saves.index(cast(str, second_key)) < storage.events.index(
            ("delete", cast(str, first_key))
        )
        first_get = client.get("/api/profile/").json()["avatar_url"]
        second_get = client.get("/api/profile/").json()["avatar_url"]
        assert first_get != second_get
        assert first_get.startswith("https://media.example.test/read/")
        removed = client.delete("/api/profile/avatar/")
        again = client.delete("/api/profile/avatar/")
        assert (removed.status_code, again.status_code) == (204, 204)
        assert PlayerProfile.objects.get(user=user).avatar_key is None
        assert max(
            index for index, value in enumerate(saves) if value is None
        ) < storage.events.index(("delete", cast(str, second_key)))
    finally:
        post_save.disconnect(observe, sender=PlayerProfile)


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_avatar_rejects_bad_requests_and_all_media_classifications_as_safe_field_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rejects raw image errors, wrong payload types, and mutation on media failure."""
    from profiles.models import PlayerProfile

    from media.images import ImageValidationError

    user = create_test_user()
    client = force_authenticated_client(user=user)
    assert client.put("/api/profile/avatar/", {}, format="multipart").status_code == 400
    assert (
        client.put(
            "/api/profile/avatar/",
            {"avatar": "not-a-file"},
            content_type="application/json",
        ).status_code
        == 400
    )
    assert (
        client.put(
            "/api/profile/",
            {"handle": "finn_42", "display_name": "Finn"},
            content_type="application/json",
        ).status_code
        == 200
    )
    before = PlayerProfile.objects.get(user=user)
    initial_state = (
        before.handle,
        before.display_name,
        before.onboarding_completed_at,
        before.avatar_key,
    )
    for code in ImageRejectionCode:

        def reject(_upload: object, *, selected: ImageRejectionCode = code) -> None:
            raise ImageValidationError(selected)

        monkeypatch.setattr("media.service.normalize_image", reject)
        response = client.put("/api/profile/avatar/", {"avatar": image_upload()})
        assert response.status_code == 400
        assert set(response.json()) == {"avatar"}
        after = PlayerProfile.objects.get(user=user)
        assert (
            after.handle,
            after.display_name,
            after.onboarding_completed_at,
            after.avatar_key,
        ) == initial_state
    storage = _recording_storage()
    assert not storage.events


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_disabled_avatar_writes_are_forbidden_before_storage_or_validation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rejects an authorization check after upload and secrets leaked through avatar logs."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    profile = PlayerProfile.objects.create(user=user, is_enabled=False)
    client = force_authenticated_client(user=user)
    caplog.set_level(logging.DEBUG)
    assert (
        client.put("/api/profile/avatar/", {"avatar": image_upload()}).status_code
        == 403
    )
    assert client.delete("/api/profile/avatar/").status_code == 403
    profile.refresh_from_db()
    assert profile.avatar_key is None
    storage = _recording_storage()
    assert not storage.events
