"""PostgreSQL race acceptance test for globally unique normalized handles."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from django.db import close_old_connections, connection

from accounts.models import User
from tests.authentication_support import create_test_user, force_authenticated_client


@pytest.mark.django_db(transaction=True)
def test_simultaneous_normalized_handle_claims_have_one_owner_and_one_safe_loser() -> (
    None
):
    """Rejects check-then-save races and database errors leaked as 500 responses."""
    first_user = create_test_user()
    second_user = create_test_user()
    start = Barrier(2)

    def claim(user_id: int, handle: str) -> Any:
        close_old_connections()
        try:
            user = User.objects.get(pk=user_id)
            client = force_authenticated_client(user=user)
            start.wait(timeout=10)
            return client.put(
                "/api/profile/",
                {"handle": handle, "display_name": "Shared claimant"},
                content_type="application/json",
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = (
            executor.submit(claim, first_user.pk, "Shared_1"),
            executor.submit(claim, second_user.pk, "shared_1"),
        )
        first_response = first.result(timeout=15)
        second_response = second.result(timeout=15)

    statuses = sorted((first_response.status_code, second_response.status_code))
    assert statuses == [200, 400]
    loser = first_response if first_response.status_code == 400 else second_response
    assert set(loser.json()) == {"handle"}
    assert loser.data["handle"][0].code == "unique"

    from profiles.models import PlayerProfile

    assert PlayerProfile.objects.filter(handle="shared_1").count() == 1
    losing_user = second_user if loser is second_response else first_user
    assert not PlayerProfile.objects.filter(
        user=losing_user, onboarding_completed_at__isnull=False
    ).exists()
