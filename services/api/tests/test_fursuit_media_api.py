"""Strict multipart and media-lifecycle behavior at the fursuit boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Never, Protocol, cast

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.core.handlers.wsgi import WSGIRequest
from django.test import RequestFactory, override_settings
from django.test.client import BOUNDARY, encode_multipart

from media.images import ImageRejectionCode, ImageValidationError
from tests.authentication_support import force_authenticated_client
from tests.fursuit_test_support import (
    assert_fursuit_response,
    create_eligible_user,
    create_fursuit_record,
    raw_client_request,
)
from tests.profile_test_support import (
    RECORDING_STORAGES,
    RecordingStorage,
    image_upload,
)


class _BytesRequestFactory(Protocol):
    def generic(
        self, method: str, path: str, data: bytes, content_type: str
    ) -> WSGIRequest: ...


@dataclass(frozen=True, slots=True)
class _UploadDescriptor:
    name: str = "avatar.png"


type _PayloadValue = str | _UploadDescriptor
type _PayloadDescriptor = dict[str, _PayloadValue | tuple[_PayloadValue, ...]]


def _materialize_payload(descriptor: _PayloadDescriptor) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in descriptor.items():
        if isinstance(value, tuple):
            payload[key] = [
                image_upload(name=item.name)
                if isinstance(item, _UploadDescriptor)
                else item
                for item in value
            ]
        else:
            payload[key] = (
                image_upload(name=value.name)
                if isinstance(value, _UploadDescriptor)
                else value
            )
    return payload


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path_kind", "payload_descriptor"),
    (
        ("create", {}),
        ("create", {"name": "Valid"}),
        ("create", {"photo": _UploadDescriptor()}),
        (
            "create",
            {"name": "Valid", "photo": _UploadDescriptor(), "extra": "x"},
        ),
        ("replace", {"name": "Forbidden", "photo": _UploadDescriptor()}),
        ("replace", {}),
        ("replace", {"photo": _UploadDescriptor(), "extra": "x"}),
    ),
)
def test_multipart_endpoints_reject_missing_forbidden_and_additional_entries(
    path_kind: str, payload_descriptor: _PayloadDescriptor
) -> None:
    user = create_eligible_user()
    client = force_authenticated_client(user=user)
    payload = _materialize_payload(payload_descriptor)
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
@pytest.mark.parametrize(
    ("path_kind", "payload_descriptor"),
    (
        (
            "create",
            {"name": ("Valid", "Repeated"), "photo": (_UploadDescriptor(),)},
        ),
        (
            "create",
            {
                "name": ("Valid",),
                "photo": (_UploadDescriptor(), _UploadDescriptor("again.png")),
            },
        ),
        (
            "create",
            {"name": ("Valid",), "photo": (_UploadDescriptor(),), "owner": ("1",)},
        ),
        (
            "create",
            {
                "name": ("Valid",),
                "photo": (_UploadDescriptor(),),
                "is_enabled": ("true",),
            },
        ),
        (
            "create",
            {
                "name": (_UploadDescriptor("name.png"),),
                "photo": (_UploadDescriptor(),),
            },
        ),
        ("create", {"name": ("Valid",), "photo": ("not-a-file",)}),
        (
            "create",
            {
                "name": ("Valid",),
                "photo": (_UploadDescriptor(),),
                "extra": (_UploadDescriptor("extra.png"),),
            },
        ),
        (
            "replace",
            {"photo": (_UploadDescriptor(), _UploadDescriptor("again.png"))},
        ),
        (
            "replace",
            {"name": ("Forbidden",), "photo": (_UploadDescriptor(),)},
        ),
        ("replace", {"photo": (_UploadDescriptor(),), "extra": ("value",)}),
        ("replace", {"photo": (_UploadDescriptor(),), "owner": ("1",)}),
        ("replace", {"photo": ("not-a-file",)}),
        (
            "replace",
            {
                "photo": (_UploadDescriptor(),),
                "extra": (_UploadDescriptor("extra.png"),),
            },
        ),
    ),
    ids=(
        "create-repeated-name",
        "create-repeated-photo",
        "create-owner",
        "create-enabled",
        "create-name-file",
        "create-photo-value",
        "create-extra-file",
        "replace-repeated-photo",
        "replace-name",
        "replace-extra-value",
        "replace-owner",
        "replace-photo-value",
        "replace-extra-file",
    ),
)
def test_raw_multivalued_multipart_inputs_are_closed_per_entry(
    path_kind: str, payload_descriptor: _PayloadDescriptor
) -> None:
    """Rejects repeated parts after proving the raw body parses to duplicate lists."""
    user = create_eligible_user()
    client = force_authenticated_client(user=user)
    payload = _materialize_payload(payload_descriptor)
    path = (
        "/api/fursuits/"
        if path_kind == "create"
        else f"/api/fursuits/{create_fursuit_record(owner=user).id}/photo/"
    )
    body = encode_multipart(BOUNDARY, payload)
    probe = cast(_BytesRequestFactory, RequestFactory()).generic(
        "POST",
        path,
        data=body,
        content_type=f"multipart/form-data; boundary={BOUNDARY}",
    )
    for key, raw_values in payload.items():
        values = (
            cast(list[object], raw_values)
            if isinstance(raw_values, list)
            else [raw_values]
        )
        expected_post = [
            value for value in values if not isinstance(value, UploadedFile)
        ]
        expected_files = [value for value in values if isinstance(value, UploadedFile)]
        assert len(probe.POST.getlist(key)) == len(expected_post)
        assert len(probe.FILES.getlist(key)) == len(expected_files)
    response = raw_client_request(
        client,
        method="POST" if path_kind == "create" else "PUT",
        path=path,
        data=body,
        content_type=f"multipart/form-data; boundary={BOUNDARY}",
    )
    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "path"),
    (("post", "/api/fursuits/"), ("put", "/api/fursuits/{id}/photo/")),
)
def test_media_writes_reject_json_and_non_multipart_requests(
    method: str, path: str
) -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    response = getattr(force_authenticated_client(user=user), method)(
        path.format(id=record.id),
        {"name": "Valid", "photo": "not-a-file"},
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("code", tuple(ImageRejectionCode))
def test_each_image_rejection_is_a_safe_photo_field_error(
    monkeypatch: pytest.MonkeyPatch, code: ImageRejectionCode
) -> None:
    from media import service

    def reject_image(*_args: object, **_kwargs: object) -> Never:
        raise ImageValidationError(code)

    monkeypatch.setattr(
        service,
        "store_image",
        reject_image,
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
@pytest.mark.parametrize("code", tuple(ImageRejectionCode))
def test_replacement_maps_each_stable_image_rejection_to_a_safe_photo_error(
    monkeypatch: pytest.MonkeyPatch, code: ImageRejectionCode
) -> None:
    from media import service

    user = create_eligible_user()
    record = create_fursuit_record(owner=user)

    def reject_image(*_args: object, **_kwargs: object) -> Never:
        raise ImageValidationError(code)

    monkeypatch.setattr(
        service,
        "store_image",
        reject_image,
    )
    response = force_authenticated_client(user=user).put(
        f"/api/fursuits/{record.id}/photo/", {"photo": image_upload(name="secret.png")}
    )
    assert response.status_code == 400 and set(response.json()) == {"photo"}
    assert "secret.png" not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ("create", "replace"))
def test_unexpected_storage_failures_remain_5xx(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from media import service

    user = create_eligible_user()
    record = create_fursuit_record(owner=user)

    def fail_storage(*_args: object, **_kwargs: object) -> Never:
        raise RuntimeError("unexpected storage sentinel")

    monkeypatch.setattr(
        service,
        "store_image",
        fail_storage,
    )
    client = force_authenticated_client(user=user)
    client.raise_request_exception = False
    response = (
        client.post("/api/fursuits/", {"name": "Valid", "photo": image_upload()})
        if operation == "create"
        else client.put(f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()})
    )
    assert response.status_code >= 500
    assert "unexpected storage sentinel" not in response.content.decode()


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_replacement_commits_new_reference_before_old_cleanup_and_url_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    before = record.updated_at
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    storage.save(record.photo_key, image_upload())
    old_key = record.photo_key
    original_delete = storage.delete

    def assert_committed_before_cleanup(key: str) -> None:
        assert key == old_key
        record.refresh_from_db()
        assert record.photo_key != old_key
        original_delete(key)

    monkeypatch.setattr(storage, "delete", assert_committed_before_cleanup)
    response = force_authenticated_client(user=user).put(
        f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()}
    )
    assert response.status_code == 200
    assert_fursuit_response(response)
    record.refresh_from_db()
    assert record.updated_at > before
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

    def fail_url(_key: str) -> Never:
        raise RuntimeError("url failure")

    monkeypatch.setattr(
        storage,
        "url",
        fail_url,
    )
    client = force_authenticated_client(user=user)
    client.raise_request_exception = False
    response = client.put(
        f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()}
    )
    record.refresh_from_db()
    assert response.status_code >= 500 and record.photo_key != old


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_replacement_commit_failure_compensates_and_cleanup_failure_preserves_primary_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new upload is compensated, but cleanup must never hide commit failure."""
    from fursuits import services

    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    failure = RuntimeError("commit failure sentinel")

    def fail_commit(*_args: object, **_kwargs: object) -> Never:
        raise failure

    def fail_cleanup(_key: str) -> Never:
        raise RuntimeError("cleanup failure")

    monkeypatch.setattr(
        services,
        "_commit_replaced_fursuit_photo",
        fail_commit,
    )
    monkeypatch.setattr(
        storage,
        "delete",
        fail_cleanup,
    )
    with pytest.raises(RuntimeError) as raised:
        services.replace_fursuit_photo(user, fursuit_id=record.id, photo=image_upload())
    assert raised.value is failure


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_old_cleanup_failure_keeps_new_reference_and_logs_only_sanitized_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    old_key = record.photo_key
    storage = default_storage
    assert isinstance(storage, RecordingStorage)

    def fail_cleanup(_key: str) -> Never:
        raise RuntimeError("bucket credential secret")

    monkeypatch.setattr(
        storage,
        "delete",
        fail_cleanup,
    )
    response = force_authenticated_client(user=user).put(
        f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()}
    )
    record.refresh_from_db()
    assert response.status_code == 200 and record.photo_key != old_key
    assert "bucket credential secret" not in caplog.text
    assert "Media cleanup failed after replacement commit." in caplog.text
