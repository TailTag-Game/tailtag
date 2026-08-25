"""Strict multipart and media-lifecycle behavior at the fursuit boundary."""

from __future__ import annotations

import pytest
from django.core.files.storage import default_storage
from django.test import override_settings

from media.images import ImageRejectionCode, ImageValidationError
from tests.authentication_support import force_authenticated_client
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record
from tests.profile_test_support import (
    RECORDING_STORAGES,
    RecordingStorage,
    image_upload,
)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path_kind", "payload"),
    (
        ("create", {}),
        ("create", {"name": "Valid"}),
        ("create", {"photo": image_upload()}),
        ("create", {"name": "Valid", "photo": image_upload(), "extra": "x"}),
        ("replace", {"name": "Forbidden", "photo": image_upload()}),
        ("replace", {}),
        ("replace", {"photo": image_upload(), "extra": "x"}),
    ),
)
def test_multipart_endpoints_reject_missing_forbidden_and_additional_entries(
    path_kind: str, payload: dict[str, object]
) -> None:
    user = create_eligible_user()
    client = force_authenticated_client(user=user)
    path = (
        "/api/fursuits/"
        if path_kind == "create"
        else f"/api/fursuits/{create_fursuit_record(owner=user).id}/photo/"
    )
    response = (
        client.post(path, payload)
        if path_kind == "create"
        else client.put(path, payload)
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_repeated_multipart_values_and_files_are_not_collapsed_by_querydict_get() -> (
    None
):
    user = create_eligible_user()
    client = force_authenticated_client(user=user)
    response = client.post(
        "/api/fursuits/",
        {
            "name": ["Valid", "Other"],
            "photo": [image_upload(), image_upload(name="second.png")],
        },
    )
    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("code", tuple(ImageRejectionCode))
def test_each_image_rejection_is_a_safe_photo_field_error(
    monkeypatch: pytest.MonkeyPatch, code: ImageRejectionCode
) -> None:
    from media import service

    monkeypatch.setattr(
        service,
        "store_image",
        lambda *args, **kwargs: (_ for _ in ()).throw(ImageValidationError(code)),
    )
    response = force_authenticated_client(user=create_eligible_user()).post(
        "/api/fursuits/",
        {"name": "Valid", "photo": image_upload(name="secret-source-name.png")},
    )
    assert response.status_code == 400 and set(response.json()) == {"photo"}
    body = response.content.decode()
    for secret in ("secret-source-name", "Pillow", "bucket", "credential", "images/"):
        assert secret not in body


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_replacement_commits_new_reference_before_old_cleanup_and_url_generation() -> (
    None
):
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    storage.save(record.photo_key, image_upload())
    response = force_authenticated_client(user=user).put(
        f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()}
    )
    assert response.status_code == 200
    events = [event[0] for event in storage.events]
    assert events[-3:] == ["save", "delete", "url"]


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_post_commit_url_failure_does_not_revert_authoritative_photo_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    old = record.photo_key
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    monkeypatch.setattr(
        storage, "url", lambda _key: (_ for _ in ()).throw(RuntimeError("url failure"))
    )
    response = force_authenticated_client(user=user).put(
        f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()}
    )
    record.refresh_from_db()
    assert response.status_code >= 500 and record.photo_key != old
