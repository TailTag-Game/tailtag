"""Real PostgreSQL serialization and lock-order acceptance evidence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from django.db import close_old_connections, connection
from django.test import override_settings

from accounts.models import User
from tests.authentication_support import force_authenticated_client
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record
from tests.profile_test_support import (
    BLOCKING_RECORDING_STORAGES,
    BlockingRecordingStorage,
    image_upload,
)


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_concurrent_replacements_serialize_and_never_delete_the_final_key() -> None:
    owner = create_eligible_user()
    record = create_fursuit_record(owner=owner)
    start = Barrier(2)
    release_first, release_second = BlockingRecordingStorage.configure_upload_pause()

    def replace() -> int:
        close_old_connections()
        try:
            user = User.objects.get(pk=owner.pk)
            start.wait(timeout=10)
            return (
                force_authenticated_client(user=user)
                .put(f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()})
                .status_code
            )
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(replace), pool.submit(replace)
            assert (
                BlockingRecordingStorage.first_save_stored is not None
                and BlockingRecordingStorage.first_save_stored.wait(10)
            )
            release_first.set()
            assert (
                BlockingRecordingStorage.second_save_stored is not None
                and BlockingRecordingStorage.second_save_stored.wait(10)
            )
            release_second.set()
            assert sorted((first.result(15), second.result(15))) == [200, 200]
    finally:
        BlockingRecordingStorage.clear_upload_pause()
    record.refresh_from_db()
    from django.core.files.storage import default_storage

    assert default_storage.exists(record.photo_key)


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_second_same_fursuit_upload_waits_until_first_commit_and_old_cleanup_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The advisory scope includes old-object cleanup, not just the database write."""
    from django.core.files.storage import default_storage

    owner = create_eligible_user()
    record = create_fursuit_record(owner=owner)
    start = Barrier(2)
    release_first, release_second = BlockingRecordingStorage.configure_upload_pause()
    cleanup_entered, release_cleanup = Event(), Event()
    original_delete = default_storage.delete

    def pause_old_cleanup(key: str) -> None:
        if key == record.photo_key:
            cleanup_entered.set()
            assert release_cleanup.wait(10)
        original_delete(key)

    monkeypatch.setattr(default_storage, "delete", pause_old_cleanup)

    def replace() -> int:
        close_old_connections()
        try:
            start.wait(timeout=10)
            user = User.objects.get(pk=owner.pk)
            return (
                force_authenticated_client(user=user)
                .put(f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()})
                .status_code
            )
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(replace), pool.submit(replace)
            assert BlockingRecordingStorage.first_save_stored is not None
            assert BlockingRecordingStorage.first_save_stored.wait(10)
            release_first.set()
            assert cleanup_entered.wait(10)
            assert BlockingRecordingStorage.second_save_stored is not None
            assert not BlockingRecordingStorage.second_save_stored.wait(0.2)
            release_cleanup.set()
            assert BlockingRecordingStorage.second_save_stored.wait(10)
            release_second.set()
            assert sorted((first.result(15), second.result(15))) == [200, 200]
    finally:
        BlockingRecordingStorage.clear_upload_pause()


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_different_fursuits_can_enter_storage_concurrently() -> None:
    owner = create_eligible_user()
    first_record = create_fursuit_record(owner=owner)
    second_record = create_fursuit_record(owner=owner)
    start = Barrier(2)
    release_first, release_second = BlockingRecordingStorage.configure_upload_pause()

    def replace(record_id: int) -> int:
        close_old_connections()
        try:
            start.wait(timeout=10)
            user = User.objects.get(pk=owner.pk)
            return (
                force_authenticated_client(user=user)
                .put(f"/api/fursuits/{record_id}/photo/", {"photo": image_upload()})
                .status_code
            )
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = (
                pool.submit(replace, first_record.id),
                pool.submit(replace, second_record.id),
            )
            assert BlockingRecordingStorage.first_save_stored is not None
            assert BlockingRecordingStorage.second_save_stored is not None
            assert BlockingRecordingStorage.first_save_stored.wait(10)
            assert BlockingRecordingStorage.second_save_stored.wait(10)
            release_first.set()
            release_second.set()
            assert sorted((first.result(15), second.result(15))) == [200, 200]
    finally:
        BlockingRecordingStorage.clear_upload_pause()


@pytest.mark.django_db(transaction=True)
@override_settings(STORAGES=BLOCKING_RECORDING_STORAGES)
def test_disablement_committed_after_upload_before_reference_commit_forbids_and_compensates() -> (
    None
):
    owner = create_eligible_user()
    record = create_fursuit_record(owner=owner)
    release_first, _release_second = BlockingRecordingStorage.configure_upload_pause()
    from django.core.files.storage import default_storage

    assert isinstance(default_storage, BlockingRecordingStorage)

    def replace() -> int:
        close_old_connections()
        try:
            user = User.objects.get(pk=owner.pk)
            return (
                force_authenticated_client(user=user)
                .put(f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()})
                .status_code
            )
        finally:
            connection.close()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            write = pool.submit(replace)
            assert BlockingRecordingStorage.first_save_stored is not None
            assert BlockingRecordingStorage.first_save_stored.wait(10)
            from profiles.models import PlayerProfile

            PlayerProfile.objects.filter(user=owner).update(is_enabled=False)
            release_first.set()
            assert write.result(15) == 403
            assert [event[0] for event in default_storage.events] == ["save", "delete"]
    finally:
        BlockingRecordingStorage.clear_upload_pause()


@pytest.mark.django_db
def test_write_committed_before_disablement_stays_durable_but_later_writes_are_forbidden() -> (
    None
):
    from profiles.models import PlayerProfile

    owner = create_eligible_user()
    record = create_fursuit_record(owner=owner)
    client = force_authenticated_client(user=owner)
    assert (
        client.patch(
            f"/api/fursuits/{record.id}/",
            {"name": "Committed"},
            content_type="application/json",
        ).status_code
        == 200
    )
    PlayerProfile.objects.filter(user=owner).update(is_enabled=False)
    record.refresh_from_db()
    assert record.name == "Committed"
    assert (
        client.patch(
            f"/api/fursuits/{record.id}/",
            {"name": "Too late"},
            content_type="application/json",
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_commit_transactions_lock_profile_before_fursuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Records the externally relevant SQL row-lock acquisition order."""
    from fursuits.models import Fursuit
    from profiles.models import PlayerProfile

    owner = create_eligible_user()
    record = create_fursuit_record(owner=owner)
    order: list[str] = []
    profile_lock = PlayerProfile.objects.select_for_update
    fursuit_lock = Fursuit.objects.select_for_update

    def record_profile_lock(*args: object, **kwargs: object) -> object:
        order.append("profile")
        return profile_lock(*args, **kwargs)

    def record_fursuit_lock(*args: object, **kwargs: object) -> object:
        order.append("fursuit")
        return fursuit_lock(*args, **kwargs)

    monkeypatch.setattr(PlayerProfile.objects, "select_for_update", record_profile_lock)
    monkeypatch.setattr(Fursuit.objects, "select_for_update", record_fursuit_lock)
    assert (
        force_authenticated_client(user=owner)
        .patch(
            f"/api/fursuits/{record.id}/",
            {"name": "Renamed"},
            content_type="application/json",
        )
        .status_code
        == 200
    )
    assert order[:2] == ["profile", "fursuit"]


@pytest.mark.django_db
def test_fursuit_advisory_namespace_is_negative_and_disjoint_from_profile_avatar_namespace() -> (
    None
):
    from fursuits.services import fursuit_advisory_lock_key

    assert fursuit_advisory_lock_key(42) < 0
    assert fursuit_advisory_lock_key(42) != 42
