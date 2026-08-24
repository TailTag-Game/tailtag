"""Black-box acceptance tests for V0 player profile lifecycle behavior."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import pytest
from django.core.files.storage import default_storage
from django.test import Client, override_settings
from rest_framework.test import APIClient

from tests.authentication_support import (
    TEST_CLERK_CONFIGURATION,
    create_test_user,
    fake_clerk_session_verification,
    force_authenticated_client,
)
from tests.profile_test_support import (
    RECORDING_STORAGES,
    RecordingStorage,
    assert_profile_response,
    image_upload,
)

DEFAULT_PROFILE = {
    "handle": None,
    "display_name": None,
    "avatar_url": None,
    "onboarding_complete": False,
    "is_enabled": True,
}
RESERVED_HANDLES = (
    "admin",
    "api",
    "me",
    "moderator",
    "staff",
    "support",
    "system",
    "tailtag",
)


def _complete(
    client: APIClient, *, handle: str = "finn_42", display_name: str = "Finn"
) -> None:
    response = client.put(
        "/api/profile/",
        {"handle": handle, "display_name": display_name},
        content_type="application/json",
    )
    assert response.status_code == 200, response.content


@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_every_profile_operation_requires_existing_bearer_authentication() -> None:
    """Rejects endpoints declared private in OpenAPI but reachable without authentication."""
    client = Client()
    responses = (
        client.get("/api/profile/"),
        client.put("/api/profile/", {}, content_type="application/json"),
        client.patch("/api/profile/", {}, content_type="application/json"),
        client.generic(
            "PUT", "/api/profile/avatar/", data=b"", content_type="multipart/form-data"
        ),
        client.delete("/api/profile/avatar/"),
    )

    for response in responses:
        assert response.status_code == 401
        assert response["WWW-Authenticate"] == "Bearer"
        assert set(response.json()) == {"detail"}


@pytest.mark.django_db
def test_profile_get_uses_the_real_bearer_resolution_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rejects profile auth that works only through force_authenticate or calls the network."""
    subject = "user_profile_bearer"
    verified = fake_clerk_session_verification(monkeypatch, subject=subject)
    response = Client().get("/api/profile/", HTTP_AUTHORIZATION="Bearer synthetic")
    assert response.status_code == 200
    assert response.json() == DEFAULT_PROFILE
    assert_profile_response(response)
    assert len(verified) == 1


@pytest.mark.django_db
def test_profile_get_exposes_the_exact_conceptual_default_not_identity_data() -> None:
    """Rejects a 404, eager Clerk copy, extra fields, or a non-enabled default."""
    user = create_test_user()

    response = force_authenticated_client(user=user).get("/api/profile/")

    assert response.status_code == 200
    assert response.json() == DEFAULT_PROFILE
    assert_profile_response(response)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "handle",
    (
        "a",  # too short
        "ab",
        "a" * 32,
        "a" * 33,  # too long
        "_abc",  # invalid first character
        "-abc",
        "ab cd",
        "café",
        "Ｆｉｎｎ",
        *RESERVED_HANDLES,
        *(reserved.upper() for reserved in RESERVED_HANDLES),
    ),
)
def test_initial_put_enforces_handle_boundaries_and_reserved_names_atomically(
    handle: str,
) -> None:
    """Rejects implementations that lowercase but skip syntax, size, or reserved checks."""
    client = force_authenticated_client(user=create_test_user())

    response = client.put(
        "/api/profile/",
        {"handle": handle, "display_name": "Valid name"},
        content_type="application/json",
    )

    if handle in {"ab", "a" * 32}:
        assert response.status_code == 200
    else:
        assert response.status_code == 400
        assert set(response.json()) == {"handle"}
        assert client.get("/api/profile/").json() == DEFAULT_PROFILE


@pytest.mark.django_db
@pytest.mark.parametrize("handle", (" finn_42", "finn_42 ", "\u00a0finn_42\u2003"))
def test_handle_whitespace_is_invalid_before_onboarding(handle: str) -> None:
    """Rejects DRF trimming that would make ASCII or Unicode handle whitespace valid."""
    client = force_authenticated_client(user=create_test_user())
    response = client.put(
        "/api/profile/",
        {"handle": handle, "display_name": "Finn"},
        content_type="application/json",
    )
    assert response.status_code == 400
    assert set(response.json()) == {"handle"}
    assert client.get("/api/profile/").json() == DEFAULT_PROFILE


@pytest.mark.django_db
@pytest.mark.parametrize(
    "display_name",
    (
        "",
        "  \t ",
        "a" * 51,
        "before\x00after",
        "before\tafter",
        "before\u2028after",
        "before\u2029after",
    ),
)
def test_initial_put_rejects_invalid_display_names_without_partial_completion(
    display_name: str,
) -> None:
    """Rejects trim-only, overlong, or non-single-line onboarding implementations."""
    client = force_authenticated_client(user=create_test_user())

    response = client.put(
        "/api/profile/",
        {"handle": "finn_42", "display_name": display_name},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert set(response.json()) == {"display_name"}
    assert client.get("/api/profile/").json() == DEFAULT_PROFILE


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("display_name", "expected"),
    (
        ("A", "A"),
        ("a" * 50, "a" * 50),
        ("  Fi\u006e\u0303   Wolf  ", "Fiñ Wolf"),
        (" Finn\u00a0\u2003 Wolf ", "Finn Wolf"),
    ),
)
def test_initial_put_normalizes_complete_text_profile(
    display_name: str, expected: str
) -> None:
    """Rejects persistence of un-normalized whitespace or decomposed Unicode."""
    client = force_authenticated_client(user=create_test_user())

    response = client.put(
        "/api/profile/",
        {"handle": "Finn_42", "display_name": display_name},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json() == {
        "handle": "finn_42",
        "display_name": expected,
        "avatar_url": None,
        "onboarding_complete": True,
        "is_enabled": True,
    }
    assert_profile_response(response)


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
def test_put_and_patch_preserve_avatar_and_the_original_completion_timestamp() -> None:
    """Rejects a PUT that replaces avatar or a mutation that resets completion time."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    _complete(client)
    uploaded = client.put("/api/profile/avatar/", {"avatar": image_upload()})
    assert uploaded.status_code == 200
    avatar_before = uploaded.json()["avatar_url"]
    storage = cast(RecordingStorage, default_storage)
    initial_profile = PlayerProfile.objects.get(user=user)
    before = initial_profile.onboarding_completed_at
    avatar_key_before = initial_profile.avatar_key
    assert isinstance(before, datetime)
    assert isinstance(avatar_key_before, str)

    avatar = client.put("/api/profile/avatar/", {"avatar": b"not-an-image"})
    assert avatar.status_code == 400  # Avatar validation must not corrupt text state.
    replaced = client.put(
        "/api/profile/",
        {"handle": "wolf_2", "display_name": "  New\u00a0Name "},
        content_type="application/json",
    )

    assert replaced.status_code == 200
    replaced_profile = assert_profile_response(replaced)
    assert replaced_profile["handle"] == "wolf_2"
    assert replaced_profile["display_name"] == "New Name"
    assert replaced_profile["onboarding_complete"] is True
    assert isinstance(replaced_profile["avatar_url"], str)
    profile_after_put = PlayerProfile.objects.get(user=user)
    assert profile_after_put.handle == "wolf_2"
    assert profile_after_put.display_name == "New Name"
    assert profile_after_put.onboarding_completed_at == before
    assert profile_after_put.avatar_key == avatar_key_before

    patched = client.patch(
        "/api/profile/", {"display_name": "Patched"}, content_type="application/json"
    )
    assert patched.status_code == 200
    profile = PlayerProfile.objects.get(user=user)
    assert profile.handle == "wolf_2"
    assert profile.display_name == "Patched"
    assert profile.onboarding_completed_at == before
    assert profile.avatar_key is not None
    assert replaced.json()["avatar_url"] != avatar_before
    assert (
        len(
            {avatar_before, replaced.json()["avatar_url"], patched.json()["avatar_url"]}
        )
        == 3
    )
    assert storage.events.count(("url", profile.avatar_key)) == 3
    assert_profile_response(patched)


@pytest.mark.django_db
@override_settings(STORAGES=RECORDING_STORAGES)
@pytest.mark.parametrize("handle", ("admin", "_invalid", "new handle", "café"))
def test_completed_patch_rejects_invalid_handles_without_changing_durable_state(
    handle: str,
) -> None:
    """Rejects post-onboarding validation that omits reserved or syntax rules."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    _complete(client)
    uploaded = client.put("/api/profile/avatar/", {"avatar": image_upload()})
    assert uploaded.status_code == 200
    before = PlayerProfile.objects.get(user=user)
    durable_state = (
        before.handle,
        before.display_name,
        before.onboarding_completed_at,
        before.avatar_key,
    )

    response = client.patch(
        "/api/profile/", {"handle": handle}, content_type="application/json"
    )

    assert response.status_code == 400
    assert set(response.json()) == {"handle"}
    after = PlayerProfile.objects.get(user=user)
    assert (
        after.handle,
        after.display_name,
        after.onboarding_completed_at,
        after.avatar_key,
    ) == durable_state


@pytest.mark.django_db
@pytest.mark.parametrize("method", ("put", "patch"))
@pytest.mark.parametrize("handle", (" wolf_2 ", "\u00a0wolf_2\u2003"))
def test_completed_handle_whitespace_is_rejected_without_state_change(
    method: str, handle: str
) -> None:
    """Rejects completed writes that normalize away prohibited handle whitespace."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    _complete(client)
    before = PlayerProfile.objects.get(user=user)
    state = (
        before.handle,
        before.display_name,
        before.onboarding_completed_at,
        before.avatar_key,
    )
    payload = (
        {"handle": handle, "display_name": "Wolf"}
        if method == "put"
        else {"handle": handle}
    )
    response = getattr(client, method)(
        "/api/profile/", payload, content_type="application/json"
    )
    assert response.status_code == 400
    assert set(response.json()) == {"handle"}
    after = PlayerProfile.objects.get(user=user)
    assert (
        after.handle,
        after.display_name,
        after.onboarding_completed_at,
        after.avatar_key,
    ) == state


@pytest.mark.django_db
def test_completed_text_writes_normalize_and_reject_incomplete_or_reserved_values() -> (
    None
):
    """Rejects weaker post-onboarding validation than initial onboarding receives."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    _complete(client)
    normalized = client.patch(
        "/api/profile/",
        {"handle": "WOLF_2", "display_name": "  New\u00a0Name "},
        content_type="application/json",
    )
    assert normalized.status_code == 200
    assert normalized.json()["handle"] == "wolf_2"
    assert normalized.json()["display_name"] == "New Name"
    profile = PlayerProfile.objects.get(user=user)
    state = (
        profile.handle,
        profile.display_name,
        profile.onboarding_completed_at,
        profile.avatar_key,
    )
    for payload in (
        {"display_name": "Missing"},
        {"handle": None, "display_name": "Null"},
        {"handle": "admin", "display_name": "Admin"},
    ):
        response = client.put("/api/profile/", payload, content_type="application/json")
        assert response.status_code == 400
        current = PlayerProfile.objects.get(user=user)
        assert (
            current.handle,
            current.display_name,
            current.onboarding_completed_at,
            current.avatar_key,
        ) == state


@pytest.mark.django_db
def test_patch_requires_completed_nonempty_text_and_ignores_player_lifecycle_flags() -> (
    None
):
    """Rejects incomplete PATCH, clearing fields, and client control of protected flags."""
    client = force_authenticated_client(user=create_test_user())

    for payload in (
        {},
        {"handle": "finn_42"},
        {"handle": "finn_42", "display_name": "Finn"},
        {"onboarding_complete": True, "is_enabled": False},
    ):
        response = client.patch(
            "/api/profile/", payload, content_type="application/json"
        )
        assert response.status_code == 400
        assert client.get("/api/profile/").json() == DEFAULT_PROFILE
    completed = client.put(
        "/api/profile/",
        {
            "handle": "finn_42",
            "display_name": "Finn",
            "onboarding_complete": False,
            "is_enabled": False,
        },
        content_type="application/json",
    )
    assert completed.status_code == 200
    assert completed.json()["onboarding_complete"] is True
    assert completed.json()["is_enabled"] is True

    for payload in ({}, {"handle": None}, {"display_name": ""}):
        response = client.patch(
            "/api/profile/", payload, content_type="application/json"
        )
        assert response.status_code == 400
    response = client.patch(
        "/api/profile/",
        {"handle": "wolf_2", "onboarding_complete": False, "is_enabled": False},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["handle"] == "wolf_2"
    assert response.json()["onboarding_complete"] is True
    assert response.json()["is_enabled"] is True
    both_fields = client.patch(
        "/api/profile/",
        {"handle": "two_fields_2", "display_name": "Two Fields"},
        content_type="application/json",
    )
    assert both_fields.status_code == 200
    assert both_fields.json()["handle"] == "two_fields_2"
    assert both_fields.json()["display_name"] == "Two Fields"


@pytest.mark.django_db
def test_serial_duplicate_handle_is_a_safe_field_validation_error() -> None:
    """Rejects duplicate checks that are omitted outside a concurrency race."""
    first = force_authenticated_client(user=create_test_user())
    second = force_authenticated_client(user=create_test_user())
    _complete(first, handle="duplicate_1")

    response = second.put(
        "/api/profile/",
        {"handle": "DUPLICATE_1", "display_name": "Second"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert set(response.json()) == {"handle"}
    assert response.data["handle"][0].code == "unique"
    assert second.get("/api/profile/").json() == DEFAULT_PROFILE


@pytest.mark.django_db
def test_profile_mutations_are_forbidden_while_disabled_and_resume_when_reenabled() -> (
    None
):
    """Rejects disabling that leaks into reads, allows writes, or loses durable profile state."""
    from profiles.models import PlayerProfile

    user = create_test_user()
    client = force_authenticated_client(user=user)
    _complete(client)
    profile = PlayerProfile.objects.get(user=user)
    profile.is_enabled = False
    profile.save(update_fields={"is_enabled"})
    before = (profile.handle, profile.display_name, profile.avatar_key)

    disabled_get = client.get("/api/profile/")
    assert disabled_get.status_code == 200
    assert_profile_response(disabled_get, is_enabled=False)
    assert client.get("/api/me/").status_code == 200
    mutations = (
        client.put(
            "/api/profile/",
            {"handle": "wolf_2", "display_name": "Wolf"},
            content_type="application/json",
        ),
        client.patch(
            "/api/profile/", {"handle": "wolf_2"}, content_type="application/json"
        ),
        client.put("/api/profile/avatar/", {"avatar": b"not-an-image"}),
        client.delete("/api/profile/avatar/"),
    )
    assert [response.status_code for response in mutations] == [403, 403, 403, 403]
    profile.refresh_from_db()
    assert (profile.handle, profile.display_name, profile.avatar_key) == before

    profile.is_enabled = True
    profile.save(update_fields={"is_enabled"})
    assert (
        client.patch(
            "/api/profile/", {"handle": "wolf_2"}, content_type="application/json"
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_profile_has_no_unsupported_creation_or_deletion_methods() -> None:
    """Rejects accidental public collection and profile deletion surfaces."""
    client = force_authenticated_client(user=create_test_user())

    assert (
        client.post("/api/profile/", {}, content_type="application/json").status_code
        == 405
    )
    assert client.delete("/api/profile/").status_code == 405
