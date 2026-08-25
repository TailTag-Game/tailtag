"""Real PostgreSQL serialization and lock-order acceptance evidence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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


@pytest.mark.django_db
def test_fursuit_advisory_namespace_is_negative_and_disjoint_from_profile_avatar_namespace() -> (
    None
):
    from fursuits.services import fursuit_advisory_lock_key

    assert fursuit_advisory_lock_key(42) < 0
    assert fursuit_advisory_lock_key(42) != 42
