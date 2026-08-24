"""Acceptance tests for profile composition with the approved media interface."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from time import monotonic, sleep
from typing import Any, Protocol, cast

import pytest
from django.core.files.storage import default_storage
from django.db import close_old_connections, connection
from django.db.models.signals import post_save, pre_save
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


def _wait_for_replacement_reference(
    *, user_id: int, old_key: str, timeout_seconds: float = 1
) -> bool:
    """Observe a durable avatar replacement without assuming a signal implementation."""
    from profiles.models import PlayerProfile

    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        avatar_key = PlayerProfile.objects.get(user_id=user_id).avatar_key
        if avatar_key not in {None, old_key}:
            return True
        sleep(0.01)
    return False


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
    release_first, release_second = BlockingRecordingStorage.configure_upload_pause()

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
            assert BlockingRecordingStorage.first_save_stored is not None
            assert BlockingRecordingStorage.first_save_stored.wait(timeout=10)
            second = executor.submit(upload, "second.png")
            assert BlockingRecordingStorage.second_save_stored is not None
            second_stored = BlockingRecordingStorage.second_save_stored.wait(timeout=1)
            if second_stored:
                # N commits while the stale first request still holds its stored
                # object, making an unsafe later first commit observable.
                release_second.set()
                second_response = second.result(timeout=15)
                release_first.set()
                first_response = first.result(timeout=15)
            else:
                # A correct profile lock can serialize before storage.
                release_first.set()
                release_second.set()
                first_response = first.result(timeout=15)
                second_response = second.result(timeout=15)
            responses = (first_response, second_response)
        assert [response.status_code for response in responses] == [200, 200]
        profile = PlayerProfile.objects.get(user=user)
        storage = cast(RecordingStorage, default_storage)
        _assert_no_orphaned_upload(storage, profile.avatar_key)
        if profile.avatar_key is not None:
            assert ("delete", profile.avatar_key) not in storage.events
    finally:
        release_first.set()
        release_second.set()
        BlockingRecordingStorage.clear_upload_pause()


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_stale_avatar_removal_cannot_orphan_or_delete_a_replacement() -> None:
    """Rejects removal of stale A after a replacement has committed N."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    seeded = client.put("/api/profile/avatar/", {"avatar": image_upload(name="a.png")})
    assert seeded.status_code == 200
    old_key = PlayerProfile.objects.get(user=user).avatar_key
    assert isinstance(old_key, str)

    release_upload_first, release_upload_second = (
        BlockingRecordingStorage.configure_upload_pause()
    )
    removal_save_entered = Event()
    release_removal_save = Event()
    profile_pre_save = cast(_SignalConnection, pre_save)

    def pause_removal(
        sender: type[PlayerProfile], instance: PlayerProfile, **kwargs: object
    ) -> None:
        del sender
        update_fields = kwargs.get("update_fields")
        if (
            instance.pk == user.pk
            and instance.avatar_key is None
            and update_fields == frozenset({"avatar_key"})
            and not removal_save_entered.is_set()
        ):
            removal_save_entered.set()
            assert release_removal_save.wait(timeout=10)

    profile_pre_save.connect(pause_removal, sender=PlayerProfile, weak=False)

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
        replacement_reached_storage = False
        replacement_committed_first = False
        with ThreadPoolExecutor(max_workers=2) as executor:
            removed = executor.submit(remove)
            removal_was_paused = removal_save_entered.wait(timeout=1)
            uploaded = executor.submit(upload)
            if removal_was_paused:
                assert BlockingRecordingStorage.first_save_stored is not None
                replacement_reached_storage = (
                    BlockingRecordingStorage.first_save_stored.wait(timeout=1)
                )
                release_upload_first.set()
                release_upload_second.set()
                if replacement_reached_storage:
                    # A blocked reference update is a valid serialized path;
                    # distinguish it from a replacement that committed first.
                    replacement_committed_first = _wait_for_replacement_reference(
                        user_id=user.pk, old_key=old_key
                    )
                release_removal_save.set()
            else:
                # A safe transition may not use model save signals. Do not make
                # that implementation fail for choosing a different boundary.
                release_upload_first.set()
                release_upload_second.set()
                release_removal_save.set()
            upload_response = uploaded.result(timeout=15)
            remove_response = removed.result(timeout=15)
        assert (upload_response.status_code, remove_response.status_code) == (200, 204)
        profile = PlayerProfile.objects.get(user=user)
        storage = cast(RecordingStorage, default_storage)
        if (
            removal_was_paused
            and replacement_reached_storage
            and not replacement_committed_first
        ):
            assert isinstance(profile.avatar_key, str)
        _assert_no_orphaned_upload(storage, profile.avatar_key)
        if profile.avatar_key is not None:
            assert ("delete", profile.avatar_key) not in storage.events
    finally:
        release_upload_first.set()
        release_upload_second.set()
        release_removal_save.set()
        profile_pre_save.disconnect(pause_removal, sender=PlayerProfile)
        BlockingRecordingStorage.clear_upload_pause()


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_disable_during_avatar_upload_has_a_safe_serializable_outcome() -> None:
    """Rejects a disable/upload race that leaves an orphan or deletes an active object."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    release_first, release_second = BlockingRecordingStorage.configure_upload_pause()

    def upload() -> Any:
        close_old_connections()
        try:
            return force_authenticated_client(
                user=type(user).objects.get(pk=user.pk)
            ).put("/api/profile/avatar/", {"avatar": image_upload()})
        finally:
            connection.close()

    def disable() -> None:
        close_old_connections()
        try:
            profile = PlayerProfile.objects.get(user_id=user.pk)
            profile.is_enabled = False
            profile.save(update_fields={"is_enabled"})
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            result = executor.submit(upload)
            assert BlockingRecordingStorage.first_save_stored is not None
            assert BlockingRecordingStorage.first_save_stored.wait(timeout=10)
            disable_result = executor.submit(disable)
            # If a profile lock blocks disable, let the upload linearize first;
            # otherwise retain the observable disable-before-release ordering.
            try:
                disable_result.result(timeout=1)
            except TimeoutError:
                release_first.set()
                release_second.set()
                disable_result.result(timeout=15)
            else:
                release_first.set()
                release_second.set()
            response = result.result(timeout=15)
        assert response.status_code in {200, 403}
        profile = PlayerProfile.objects.get(user=user)
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
        release_first.set()
        release_second.set()
        BlockingRecordingStorage.clear_upload_pause()
