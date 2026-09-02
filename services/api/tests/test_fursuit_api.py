"""Black-box player API acceptance and authorization-ordering tests."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import cast

import pytest
from django.core.files.storage import default_storage
from django.db import connection
from django.test import Client, override_settings

from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import (
    TEST_CLERK_CONFIGURATION,
    force_authenticated_client,
)
from tests.fursuit_test_support import (
    assert_fursuit_data,
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


class AdvisoryLockObserver:
    """Record PostgreSQL advisory-lock acquisitions without coupling to imports."""

    _acquisition = re.compile(
        r"\bpg_(?:try_)?advisory_(?:xact_)?lock(?:_shared)?\s*\(", re.IGNORECASE
    )

    def __init__(self) -> None:
        self.acquisitions: list[tuple[str, object]] = []

    def __call__(
        self,
        execute: Callable[..., object],
        sql: str,
        params: object,
        many: bool,
        context: object,
    ) -> object:
        if self._acquisition.search(sql):
            self.acquisitions.append((sql, params))
        return execute(sql, params, many, context)


@pytest.mark.django_db
@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_fursuit_routes_require_bearer_authentication_and_reject_unsupported_methods() -> (
    None
):
    client = Client()
    for response in (
        client.get("/api/fursuits/"),
        client.post("/api/fursuits/", {}),
        client.patch("/api/fursuits/1/", {}, content_type="application/json"),
        client.put("/api/fursuits/1/photo/", {}),
    ):
        assert response.status_code == 401 and response["WWW-Authenticate"] == "Bearer"
    authenticated = force_authenticated_client(user=create_eligible_user())
    for method, path in (
        (authenticated.delete, "/api/fursuits/"),
        (authenticated.put, "/api/fursuits/1/"),
        (authenticated.delete, "/api/fursuits/1/photo/"),
    ):
        assert method(path).status_code == 405


@pytest.mark.django_db
def test_list_is_unpaginated_ascending_and_owner_scoped_but_readable_when_disabled() -> (
    None
):
    owner = create_eligible_user()
    other = create_eligible_user()
    first = create_fursuit_record(owner=owner, name="First")
    second = create_fursuit_record(owner=owner, name="Second")
    create_fursuit_record(owner=other)
    PlayerProfile.objects.filter(user=owner).update(is_enabled=False)
    response = force_authenticated_client(user=owner).get("/api/fursuits/")
    assert response.status_code == 200
    assert [
        assert_fursuit_data(data)["id"]
        for data in cast(list[dict[str, object]], response.json())
    ] == [first.id, second.id]


@pytest.mark.django_db
@pytest.mark.parametrize("profile_state", ("missing", "incomplete", "disabled"))
def test_owner_reads_remain_available_for_every_profile_state(
    profile_state: str,
) -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    if profile_state == "missing":
        PlayerProfile.objects.filter(user=user).delete()
    elif profile_state == "incomplete":
        PlayerProfile.objects.filter(user=user).update(
            onboarding_completed_at=None, handle=None, display_name=None
        )
    else:
        PlayerProfile.objects.filter(user=user).update(is_enabled=False)
    client = force_authenticated_client(user=user)
    listed = client.get("/api/fursuits/")
    detail = client.get(f"/api/fursuits/{record.id}/")
    assert listed.status_code == detail.status_code == 200
    assert [item["id"] for item in listed.json()] == [record.id]
    assert assert_fursuit_response(detail)["id"] == record.id


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_operator_disabled_fursuit_stays_visible_with_fresh_nonpersisted_urls() -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    type(record).objects.filter(pk=record.pk).update(is_enabled=False)
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    client = force_authenticated_client(user=user)
    first_list = client.get("/api/fursuits/")
    second_list = client.get("/api/fursuits/")
    first_detail = client.get(f"/api/fursuits/{record.id}/")
    second_detail = client.get(f"/api/fursuits/{record.id}/")
    responses = (first_list, second_list, first_detail, second_detail)
    assert all(response.status_code == 200 for response in responses)
    urls = [
        first_list.json()[0]["photo_url"],
        second_list.json()[0]["photo_url"],
        assert_fursuit_response(first_detail)["photo_url"],
        assert_fursuit_response(second_detail)["photo_url"],
    ]
    assert len(set(urls)) == 4 and storage.url_calls == 4
    record.refresh_from_db()
    assert record.is_enabled is False and all(url != record.photo_key for url in urls)


@pytest.mark.django_db
def test_create_patch_and_detail_are_closed_and_never_accept_server_fields() -> None:
    owner = create_eligible_user()
    client = force_authenticated_client(user=owner)
    created = client.post(
        "/api/fursuits/", {"name": "  New   Character ", "photo": image_upload()}
    )
    assert created.status_code == 201
    data = assert_fursuit_response(created)
    assert data["name"] == "New Character"
    record = create_fursuit_record(owner=owner)
    for body in (
        {},
        {"owner": 9},
        {"name": "New Name", "is_enabled": False},
        {"photo_key": "x"},
        {"id": 1},
        {"tailtag_id": "550e8400-e29b-41d4-a716-446655440000"},
        {"created_at": "x"},
    ):
        response = client.patch(
            f"/api/fursuits/{record.id}/", body, content_type="application/json"
        )
        assert response.status_code == 400
    updated = client.patch(
        f"/api/fursuits/{record.id}/",
        {"name": "New Name"},
        content_type="application/json",
    )
    assert (
        updated.status_code == 200
        and assert_fursuit_response(updated)["name"] == "New Name"
    )
    assert (
        client.post(
            "/api/fursuits/",
            {
                "name": "Client Chosen Identity",
                "photo": image_upload(),
                "tailtag_id": "550e8400-e29b-41d4-a716-446655440000",
            },
        ).status_code
        == 400
    )
    assert (
        client.put(
            f"/api/fursuits/{record.id}/photo/",
            {
                "photo": image_upload(),
                "tailtag_id": "550e8400-e29b-41d4-a716-446655440000",
            },
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_tailtag_id_persists_across_every_canonical_owner_response_and_mutation() -> (
    None
):
    owner = create_eligible_user()
    client = force_authenticated_client(user=owner)
    created = client.post(
        "/api/fursuits/", {"name": "Persistent Character", "photo": image_upload()}
    )
    assert created.status_code == 201
    created_data = assert_fursuit_response(created)
    created_record = Fursuit.objects.get(pk=created_data["id"])
    expected = str(created_record.tailtag_id)
    assert created_data["tailtag_id"] == expected

    listed = client.get("/api/fursuits/")
    detail = client.get(f"/api/fursuits/{created_record.id}/")
    assert listed.status_code == detail.status_code == 200
    assert assert_fursuit_data(listed.json()[0])["tailtag_id"] == expected
    assert assert_fursuit_response(detail)["tailtag_id"] == expected

    renamed = client.patch(
        f"/api/fursuits/{created_record.id}/",
        {"name": "Renamed Persistent Character"},
        content_type="application/json",
    )
    replaced_photo = client.put(
        f"/api/fursuits/{created_record.id}/photo/", {"photo": image_upload()}
    )
    assert renamed.status_code == replaced_photo.status_code == 200
    assert assert_fursuit_response(renamed)["tailtag_id"] == expected
    assert assert_fursuit_response(replaced_photo)["tailtag_id"] == expected
    created_record.refresh_from_db()
    assert str(created_record.tailtag_id) == expected


@pytest.mark.django_db
def test_successful_repeated_posts_are_non_idempotent_and_receive_distinct_ids() -> (
    None
):
    client = force_authenticated_client(user=create_eligible_user())
    first = client.post("/api/fursuits/", {"name": "Repeated", "photo": image_upload()})
    second = client.post(
        "/api/fursuits/", {"name": "Repeated", "photo": image_upload()}
    )
    assert first.status_code == second.status_code == 201
    assert assert_fursuit_response(first)["id"] != assert_fursuit_response(second)["id"]


@pytest.mark.django_db
def test_cross_owner_and_missing_detail_writes_are_indistinguishable_404_before_eligibility() -> (
    None
):
    target = create_fursuit_record(owner=create_eligible_user())
    caller = create_eligible_user()
    PlayerProfile.objects.filter(user=caller).update(is_enabled=False)
    client = force_authenticated_client(user=caller)
    for identifier in (target.id, 999999):
        for response in (
            client.get(f"/api/fursuits/{identifier}/"),
            client.patch(
                f"/api/fursuits/{identifier}/",
                b"malformed",
                content_type="application/json",
            ),
            raw_client_request(
                client,
                method="PUT",
                path=f"/api/fursuits/{identifier}/photo/",
                data=b"malformed",
                content_type="multipart/form-data",
            ),
        ):
            assert response.status_code == 404


@pytest.mark.django_db
def test_absent_and_cross_owner_ids_have_no_eligibility_normalization_media_url_or_service_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concealment precedes all request work, including GET presigning."""
    from fursuits import services
    from media import service as media_service

    owner = create_eligible_user()
    target = create_fursuit_record(owner=owner)
    caller = create_eligible_user()
    client = force_authenticated_client(user=caller)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("owner-filtered 404 must not perform this side effect")

    monkeypatch.setattr(services, "require_fursuit_write_eligible", forbidden)
    monkeypatch.setattr(services, "update_fursuit_name", forbidden)
    monkeypatch.setattr(services, "replace_fursuit_photo", forbidden)
    monkeypatch.setattr(services, "normalize_fursuit_name", forbidden)
    monkeypatch.setattr(media_service, "store_image", forbidden)
    monkeypatch.setattr(media_service, "read_image_url", forbidden)
    for identifier in (target.id, 999999):
        assert client.get(f"/api/fursuits/{identifier}/").status_code == 404
        assert (
            client.patch(
                f"/api/fursuits/{identifier}/",
                b"not json",
                content_type="application/json",
            ).status_code
            == 404
        )
        assert (
            raw_client_request(
                client,
                method="PUT",
                path=f"/api/fursuits/{identifier}/photo/",
                data=b"not multipart",
                content_type="multipart/form-data",
            ).status_code
            == 404
        )


@pytest.mark.django_db
@pytest.mark.parametrize("shape", ("missing", "incomplete", "disabled"))
def test_every_profile_ineligible_shape_forbids_all_writes(shape: str) -> None:
    user = create_eligible_user()
    client = force_authenticated_client(user=user)
    record = create_fursuit_record(owner=user)
    if shape == "missing":
        PlayerProfile.objects.filter(user=user).delete()
    elif shape == "incomplete":
        PlayerProfile.objects.filter(user=user).update(
            onboarding_completed_at=None, handle=None, display_name=None
        )
    else:
        PlayerProfile.objects.filter(user=user).update(is_enabled=False)
    assert (
        client.post(
            "/api/fursuits/", {"name": "Bad", "photo": image_upload()}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/fursuits/{record.id}/",
            {"name": "Bad"},
            content_type="application/json",
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()}
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_operator_disabled_fursuit_is_remediable() -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    type(record).objects.filter(pk=record.pk).update(is_enabled=False)
    assert (
        force_authenticated_client(user=user)
        .patch(
            f"/api/fursuits/{record.id}/",
            {"name": "Remediated"},
            content_type="application/json",
        )
        .status_code
        == 200
    )
    assert (
        force_authenticated_client(user=user)
        .put(f"/api/fursuits/{record.id}/photo/", {"photo": image_upload()})
        .status_code
        == 200
    )


@pytest.mark.django_db
@pytest.mark.parametrize("shape", ("missing", "incomplete", "disabled"))
@override_settings(STORAGES=RECORDING_STORAGES)
def test_ineligible_writes_stop_before_parsing_normalization_media_or_locking(
    shape: str,
) -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    original_key, original_updated_at = record.photo_key, record.updated_at
    storage = default_storage
    assert isinstance(storage, RecordingStorage)
    if shape == "missing":
        PlayerProfile.objects.filter(user=user).delete()
    elif shape == "incomplete":
        PlayerProfile.objects.filter(user=user).update(
            onboarding_completed_at=None, handle=None, display_name=None
        )
    else:
        PlayerProfile.objects.filter(user=user).update(is_enabled=False)

    client = force_authenticated_client(user=user)
    advisory_locks = AdvisoryLockObserver()
    with connection.execute_wrapper(advisory_locks):
        assert (
            raw_client_request(
                client,
                method="POST",
                path="/api/fursuits/",
                data=b"not multipart",
                content_type="multipart/form-data",
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/fursuits/", {"name": "bad\x00name", "photo": image_upload()}
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/fursuits/{record.id}/",
                b"not json",
                content_type="application/json",
            ).status_code
            == 403
        )
        assert (
            raw_client_request(
                client,
                method="PUT",
                path=f"/api/fursuits/{record.id}/photo/",
                data=b"not multipart",
                content_type="multipart/form-data",
            ).status_code
            == 403
        )
    assert advisory_locks.acquisitions == []
    assert storage.events == []
    record.refresh_from_db()
    assert (record.photo_key, record.updated_at) == (original_key, original_updated_at)


@pytest.mark.django_db
@pytest.mark.parametrize("bad_name", ("", " \t", "bad\x00name", "x" * 51))
def test_invalid_name_is_a_safe_name_field_error(bad_name: str) -> None:
    user = create_eligible_user()
    record = create_fursuit_record(owner=user)
    response = force_authenticated_client(user=user).patch(
        f"/api/fursuits/{record.id}/",
        {"name": bad_name},
        content_type="application/json",
    )
    assert response.status_code == 400 and set(response.json()) == {"name"}
