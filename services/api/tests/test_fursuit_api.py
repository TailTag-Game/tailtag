"""Black-box player API acceptance and authorization-ordering tests."""

from __future__ import annotations

import pytest
from django.test import Client, override_settings

from profiles.models import PlayerProfile
from tests.authentication_support import (
    TEST_CLERK_CONFIGURATION,
    force_authenticated_client,
)
from tests.fursuit_test_support import (
    assert_fursuit_response,
    create_eligible_user,
    create_fursuit_record,
)
from tests.profile_test_support import image_upload


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
        assert_fursuit_response(type("R", (), {"json": lambda self, d=data: d})())["id"]
        for data in response.json()
    ] == [first.id, second.id]


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
            client.generic(
                "PUT",
                f"/api/fursuits/{identifier}/photo/",
                data=b"malformed",
                content_type="multipart/form-data",
            ),
        ):
            assert response.status_code == 404


@pytest.mark.django_db
def test_every_profile_ineligible_shape_forbids_all_writes_but_disabled_fursuit_is_remediable() -> (
    None
):
    for shape in ("missing", "incomplete", "disabled"):
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
