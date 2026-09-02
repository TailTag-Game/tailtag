"""Literal fixtures and public projections for catch-credential acceptance tests."""

from __future__ import annotations

from typing import Any, cast

from django.apps import apps
from django.utils import timezone

from conventions.models import FursuitActivation
from tests.fursuit_activation_test_support import (
    ActivationScenario,
    create_activation_scenario,
)

TOKEN_A = "A" * 43
TOKEN_B = "B" * 43
PAYLOAD_A = f"tailtag:catch:v1:{TOKEN_A}"
PAYLOAD_B = f"tailtag:catch:v1:{TOKEN_B}"
OWNER_INELIGIBLE_DETAIL = "The fursuit cannot currently participate in this convention."
NOT_FOUND_DETAIL = "Catch credential not found."


def owner_credential_path(convention_id: int, fursuit_id: int) -> str:
    return (
        f"/api/conventions/{convention_id}/fursuit-activations/"
        f"{fursuit_id}/catch-credential/"
    )


def rotation_path(convention_id: int, fursuit_id: int) -> str:
    return f"{owner_credential_path(convention_id, fursuit_id)}rotate/"


def resolution_path(convention_id: int) -> str:
    return f"/api/conventions/{convention_id}/catch-credentials/resolve/"


def catch_credential_model() -> type[Any]:
    """Delay the future-model lookup so collection remains safe while RED."""
    return apps.get_model("conventions", "FursuitCatchCredential")


def create_credential_scenario(**kwargs: Any) -> ActivationScenario:
    return create_activation_scenario(**kwargs)


def create_credential(
    *,
    activation: FursuitActivation,
    token: str = TOKEN_A,
    revoked_at: Any = None,
    revocation_reason: str | None = None,
) -> Any:
    return catch_credential_model().objects.create(
        activation=activation,
        token=token,
        revoked_at=revoked_at,
        revocation_reason=revocation_reason,
    )


def assert_owner_payload(response: Any, payload: str) -> None:
    assert response.status_code == 200
    assert response.json() == {"payload": payload}


def assert_not_found(response: Any, submitted_payload: str) -> None:
    assert response.status_code == 404
    assert response.json() == {"detail": NOT_FOUND_DETAIL}
    assert submitted_payload not in response.content.decode()


def assert_resolution_data(
    data: object, *, convention_id: int, tailtag_id: str, name: str, photo_url: str
) -> None:
    assert isinstance(data, dict)
    result = cast(dict[str, object], data)
    assert result == {
        "convention_id": convention_id,
        "fursuit": {
            "tailtag_id": tailtag_id,
            "name": name,
            "photo_url": photo_url,
        },
    }


def revoke_current_for(activation: FursuitActivation) -> Any:
    """Direct setup helper for terminal-history probes only."""
    credential = catch_credential_model().objects.get(
        activation=activation, revoked_at__isnull=True
    )
    now = timezone.now()
    credential.revoked_at = now
    credential.revocation_reason = "eligibility_lost"
    credential.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])
    return credential
