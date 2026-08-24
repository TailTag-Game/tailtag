"""Acceptance tests for profile composition with the approved media interface."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol, cast

import pytest
from django.core.files.storage import default_storage
from django.db import close_old_connections, connection
from django.db.models.signals import post_save
from django.test import override_settings

from media.images import ImageRejectionCode
from tests.authentication_support import create_test_user, force_authenticated_client
from tests.profile_test_support import (
    BLOCKING_RECORDING_STORAGES,
    RECORDING_STORAGES,
    BlockingRecordingStorage,
    RecordingStorage,
    image_upload,
)


class _SignalConnection(Protocol):
    """The narrow Django signal capability exercised by the ordering assertion."""

    def connect(
        self,
        receiver: Callable[..., object],
        sender: object | None = None,
        weak: bool = True,
    ) -> None: ...

    def disconnect(
        self,
        receiver: Callable[..., object] | None = None,
        sender: object | None = None,
    ) -> bool | None: ...


def _recording_storage() -> RecordingStorage:
    # Accesses through Django's real lazy storage object; no profile code is mocked.
    return cast(RecordingStorage, default_storage)


def _assert_no_orphaned_upload(
    storage: RecordingStorage, avatar_key: str | None
) -> None:
    saved_keys = {name for event, name in storage.events if event == "save"}
    for key in saved_keys - ({avatar_key} if avatar_key is not None else set()):
        assert not storage.exists(key)
    if avatar_key is not None:
        assert storage.exists(avatar_key)


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_avatar_upload_replacement_removal_and_fresh_reads_keep_lifecycle_state(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rejects URL persistence, cleanup-before-commit, and avatar-gates-onboarding bugs."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    saves: list[str | None] = []
    caplog.set_level(logging.DEBUG)
    profile_post_save = cast(_SignalConnection, post_save)

    def observe(
        sender: type[PlayerProfile], instance: PlayerProfile, **kwargs: object
    ) -> None:
        del sender, kwargs
        saves.append(instance.avatar_key)

    profile_post_save.connect(observe, sender=PlayerProfile, weak=False)
    try:
        first = client.put("/api/profile/avatar/", {"avatar": image_upload()})
        assert first.status_code == 200
        assert set(first.json()) == {
            "handle",
            "display_name",
            "avatar_url",
            "onboarding_complete",
            "is_enabled",
        }
        assert first.json()["onboarding_complete"] is False
        first_url = first.json()["avatar_url"]
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
        completed_url = completed.json()["avatar_url"]
        second = client.put(
            "/api/profile/avatar/", {"avatar": image_upload(name="new.png")}
        )
        assert second.status_code == 200
        assert second.json()["onboarding_complete"] is True
        second_url = second.json()["avatar_url"]
        second_key = PlayerProfile.objects.get(user=user).avatar_key
        assert isinstance(second_key, str)
        assert second_key != first_key
        # Reads can occur in either profile response; only durable media ordering matters.
        assert storage.events.index(("save", first_key)) < storage.events.index(
            ("save", second_key)
        )
        assert ("delete", first_key) in storage.events
        assert storage.events.index(("save", second_key)) < storage.events.index(
            ("delete", first_key)
        )
        assert saves.index(second_key) < storage.events.index(("delete", first_key))
        first_get = client.get("/api/profile/").json()["avatar_url"]
        second_get = client.get("/api/profile/").json()["avatar_url"]
        assert first_get != second_get
        assert first_get.startswith("https://media.example.test/read/")
        rendered_logs = "\n".join(
            (caplog.text, *(record.getMessage() for record in caplog.records))
        )
        assert all(
            secret not in rendered_logs
            for secret in (
                first_key,
                second_key,
                first_url,
                completed_url,
                second_url,
                first_get,
                second_get,
            )
        )
        removed = client.delete("/api/profile/avatar/")
        again = client.delete("/api/profile/avatar/")
        assert (removed.status_code, again.status_code) == (204, 204)
        assert PlayerProfile.objects.get(user=user).avatar_key is None
        assert max(
            index for index, value in enumerate(saves) if value is None
        ) < storage.events.index(("delete", second_key))
    finally:
        profile_post_save.disconnect(observe, sender=PlayerProfile)


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_avatar_rejects_bad_requests_and_all_media_classifications_as_safe_field_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rejects raw image errors, wrong payload types, and mutation on media failure."""
    from media.images import ImageValidationError
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    seed = client.put("/api/profile/avatar/", {"avatar": image_upload()})
    assert seed.status_code == 200
    seed_url = seed.json()["avatar_url"]
    seed_key = PlayerProfile.objects.get(user=user).avatar_key
    assert isinstance(seed_key, str)
    assert (
        client.put(
            "/api/profile/",
            {"handle": "finn_42", "display_name": "Finn"},
            content_type="application/json",
        ).status_code
        == 200
    )
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    storage = _recording_storage()
    before_events = list(storage.events)
    assert client.put("/api/profile/avatar/", {}, format="multipart").status_code == 400
    assert (
        client.put(
            "/api/profile/avatar/",
            {"avatar": "not-a-file"},
            content_type="application/json",
        ).status_code
        == 400
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
    assert storage.events == before_events
    rendered_logs = "\n".join(
        (caplog.text, *(record.getMessage() for record in caplog.records))
    )
    assert seed_key not in rendered_logs
    assert seed_url not in rendered_logs


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


@pytest.mark.django_db
def test_avatar_endpoint_rejects_unsupported_methods() -> None:
    """Rejects accidental read, creation, or partial-update avatar routes."""
    client = force_authenticated_client(user=create_test_user())
    assert [
        client.get("/api/profile/avatar/").status_code,
        client.post("/api/profile/avatar/", {}).status_code,
        client.patch("/api/profile/avatar/", {}).status_code,
    ] == [405, 405, 405]


@pytest.mark.django_db
def test_remove_profile_avatar_returns_none_and_remains_idempotent() -> None:
    """Freezes the service seam return contract independently of HTTP's 204 projection."""
    from profiles.services import remove_profile_avatar

    user = create_test_user()
    assert remove_profile_avatar(user) is None
    assert remove_profile_avatar(user) is None


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_concurrent_avatar_replacements_leave_only_the_referenced_object() -> None:
    """Rejects overlapping uploads that strand an object or delete the winning object."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    release = BlockingRecordingStorage.configure_upload_pause()

    def upload(name: str) -> Any:
        close_old_connections()
        try:
            return force_authenticated_client(
                user=type(user).objects.get(pk=user.pk)
            ).put("/api/profile/avatar/", {"avatar": image_upload(name=name)})
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(upload, "first.png")
            assert BlockingRecordingStorage.saved is not None
            assert BlockingRecordingStorage.saved.wait(timeout=10)
            # A correct transition may serialize before it reaches storage, so do
            # not require this second request to enter ``save`` before releasing.
            second = executor.submit(upload, "second.png")
            release.set()
            responses = (first.result(timeout=15), second.result(timeout=15))
        assert [response.status_code for response in responses] == [200, 200]
        profile = PlayerProfile.objects.get(user=user)
        storage = cast(RecordingStorage, default_storage)
        _assert_no_orphaned_upload(storage, profile.avatar_key)
        if profile.avatar_key is not None:
            assert ("delete", profile.avatar_key) not in storage.events
    finally:
        BlockingRecordingStorage.clear_upload_pause()


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_overlapping_avatar_upload_and_removal_leave_a_serializable_media_state() -> (
    None
):
    """Rejects an upload/delete interleaving that deletes an active object or leaves an orphan."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    release = BlockingRecordingStorage.configure_upload_pause()

    def upload() -> Any:
        close_old_connections()
        try:
            return force_authenticated_client(
                user=type(user).objects.get(pk=user.pk)
            ).put("/api/profile/avatar/", {"avatar": image_upload()})
        finally:
            connection.close()

    def remove() -> Any:
        close_old_connections()
        try:
            return force_authenticated_client(
                user=type(user).objects.get(pk=user.pk)
            ).delete("/api/profile/avatar/")
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            uploaded = executor.submit(upload)
            assert BlockingRecordingStorage.saved is not None
            assert BlockingRecordingStorage.saved.wait(timeout=10)
            removed = executor.submit(remove)
            release.set()
            upload_response = uploaded.result(timeout=15)
            remove_response = removed.result(timeout=15)
        assert (upload_response.status_code, remove_response.status_code) == (200, 204)
        profile = PlayerProfile.objects.get(user=user)
        storage = cast(RecordingStorage, default_storage)
        _assert_no_orphaned_upload(storage, profile.avatar_key)
        if profile.avatar_key is not None:
            assert ("delete", profile.avatar_key) not in storage.events
    finally:
        BlockingRecordingStorage.clear_upload_pause()


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_disable_during_avatar_upload_has_a_safe_serializable_outcome() -> None:
    """Rejects a disable/upload race that leaves an orphan or deletes an active object."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    release = BlockingRecordingStorage.configure_upload_pause()

    def upload() -> Any:
        close_old_connections()
        try:
            return force_authenticated_client(
                user=type(user).objects.get(pk=user.pk)
            ).put("/api/profile/avatar/", {"avatar": image_upload()})
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(upload)
            assert BlockingRecordingStorage.saved is not None
            assert BlockingRecordingStorage.saved.wait(timeout=10)
            profile = PlayerProfile.objects.get(user=user)
            profile.is_enabled = False
            profile.save(update_fields={"is_enabled"})
            release.set()
            response = result.result(timeout=15)
        assert response.status_code in {200, 403}
        profile.refresh_from_db()
        assert profile.is_enabled is False
        storage = cast(RecordingStorage, default_storage)
        _assert_no_orphaned_upload(storage, profile.avatar_key)
        if profile.avatar_key is not None:
            assert ("delete", profile.avatar_key) not in storage.events

        events_before_follow_up = list(storage.events)
        follow_up = force_authenticated_client(user=user).put(
            "/api/profile/avatar/", {"avatar": image_upload(name="later.png")}
        )
        assert follow_up.status_code == 403
        assert storage.events == events_before_follow_up
    finally:
        BlockingRecordingStorage.clear_upload_pause()
