"""Acceptance contract for the fail-closed participation eligibility predicate."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from tests.authentication_support import create_test_user


def _assert_no_writes(queries: CaptureQueriesContext) -> None:
    assert not any(
        query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for query in queries.captured_queries
    )


@pytest.mark.django_db
def test_eligibility_is_noncreating_and_true_only_for_completed_enabled_profiles() -> (
    None
):
    """Rejects a predicate that materializes, repairs, or treats partial state as eligible."""
    from profiles.eligibility import is_participation_eligible
    from profiles.models import PlayerProfile

    missing = create_test_user()
    incomplete = create_test_user()
    completed_enabled = create_test_user()
    completed_disabled = create_test_user()
    PlayerProfile.objects.create(user=incomplete)
    PlayerProfile.objects.create(
        user=completed_enabled,
        handle="eligible_1",
        display_name="Eligible",
        onboarding_completed_at=timezone.now(),
    )
    PlayerProfile.objects.create(
        user=completed_disabled,
        handle="disabled_1",
        display_name="Disabled",
        onboarding_completed_at=timezone.now(),
        is_enabled=False,
    )

    for user, expected in (
        (AnonymousUser(), False),
        (missing, False),
        (incomplete, False),
        (completed_enabled, True),
        (completed_disabled, False),
    ):
        with CaptureQueriesContext(connection) as queries:
            eligible = is_participation_eligible(user)
        assert eligible is expected
        _assert_no_writes(queries)

    assert not PlayerProfile.objects.filter(user=missing).exists()
    # An unsaved, apparently complete object cannot make the persisted missing state eligible.
    PlayerProfile(
        user=missing,
        handle="forged_1",
        display_name="Forged",
        onboarding_completed_at=timezone.now(),
    )
    assert is_participation_eligible(missing) is False
