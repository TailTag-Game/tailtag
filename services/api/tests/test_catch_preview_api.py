"""Reusable tag preview acceptance tests (#504 AC2 to AC4, AC10, AC13)."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

import pytest
from django.utils import timezone

from catches.models import Catch
from conventions.models import (
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
    FursuitCatchSession,
)
from conventions.services import remove_convention_enrollment
from fursuits.models import FursuitTag
from fursuits.services import set_fursuit_enabled
from fursuits.tags import revoke_tag_as_operator
from profiles.models import PlayerProfile
from profiles.services import set_profile_enabled
from tests.authentication_support import force_authenticated_client
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.fursuit_tag_test_support import (
    PREVIEW_PATH,
    TARGET_UNAVAILABLE,
    PreviewScenario,
    assert_logs_hold_no_token,
    assert_no_token_leak,
    create_convention,
    create_preview_scenario,
    owner_client,
    replace_path,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True


def _preview(scenario: PreviewScenario, payload: str | None = None) -> Any:
    return scenario.catcher_client().post(
        PREVIEW_PATH,
        {"payload": scenario.payload if payload is None else payload},
        content_type="application/json",
    )


def _row_counts() -> tuple[int, ...]:
    return (
        FursuitTag.objects.count(),
        Catch.objects.count(),
        FursuitCatchSession.objects.count(),
        FursuitActivation.objects.count(),
    )


def test_preview_resolves_at_the_selected_convention_and_writes_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scenario = create_preview_scenario()
    before = _row_counts()

    response = _preview(scenario)

    assert response.status_code == 200
    body = response.json()
    assert body["convention_id"] == scenario.convention.pk
    fursuit = body["fursuit"]
    assert set(fursuit) == {"id", "tailtag_id", "name", "photo_url"}
    assert fursuit["id"] == scenario.fursuit.pk
    assert fursuit["tailtag_id"] == str(scenario.fursuit.tailtag_id)
    assert fursuit["name"] == scenario.fursuit.name
    assert _row_counts() == before
    assert_no_token_leak(response.content.decode())
    assert_logs_hold_no_token(caplog)


def test_the_same_payload_resolves_at_a_later_convention() -> None:
    scenario = create_preview_scenario("later")
    later = create_convention("later_event")
    ConventionEnrollment.objects.create(user=scenario.owner, convention=later)
    scenario.catcher_enrollment.is_active = False
    scenario.catcher_enrollment.save(update_fields=["is_active", "updated_at"])
    ConventionEnrollment.objects.create(
        user=scenario.catcher, convention=later, is_active=True
    )

    not_active_there = _preview(scenario)
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=later, active=True
    )
    create_catch_session(activation=activation)
    active_there = _preview(scenario)

    assert not_active_there.status_code == 404
    assert not_active_there.json() == TARGET_UNAVAILABLE
    assert active_there.status_code == 200
    assert active_there.json()["convention_id"] == later.pk


def _replace_tag(s: PreviewScenario) -> None:
    owner_client(s.owner).post(
        replace_path(s.fursuit.pk),
        {"expected_version": 1},
        content_type="application/json",
    )


def _revoke_tag(s: PreviewScenario) -> None:
    revoke_tag_as_operator(FursuitTag.objects.get(fursuit=s.fursuit).pk)


def _deactivate(s: PreviewScenario) -> None:
    FursuitActivation.objects.filter(pk=s.activation.pk).update(
        is_active=False, deactivated_at=timezone.now()
    )


def _end_session(s: PreviewScenario) -> None:
    FursuitCatchSession.objects.filter(pk=s.session.pk).update(
        ended_at=timezone.now(), end_reason="owner"
    )


def _expire_session(s: PreviewScenario) -> None:
    past = timezone.now() - datetime.timedelta(seconds=1)
    FursuitCatchSession.objects.filter(pk=s.session.pk).update(
        started_at=past - datetime.timedelta(hours=1), expires_at=past
    )


def _disable_suit(s: PreviewScenario) -> None:
    type(s.fursuit).objects.filter(pk=s.fursuit.pk).update(is_enabled=False)


def _pause_convention(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        status=ConventionStatus.PAUSED
    )


def _disable_owner(s: PreviewScenario) -> None:
    PlayerProfile.objects.filter(pk=s.owner_profile.pk).update(is_enabled=False)


def _unenroll_owner(s: PreviewScenario) -> None:
    ConventionEnrollment.objects.filter(pk=s.owner_enrollment.pk).delete()


_NEUTRAL_CASES: dict[
    str, tuple[Callable[[PreviewScenario], None] | None, str | None]
] = {
    "unknown": (None, "https://tailtag.app/t#" + "Z" * 43),
    "malformed": (None, "https://tailtag.app/t#short"),
    "v1_code": (None, "tailtag:catch:v1:" + "A" * 43),
    "replaced": (_replace_tag, None),
    "revoked": (_revoke_tag, None),
    "activation_inactive": (_deactivate, None),
    "no_session": (_end_session, None),
    "session_expired": (_expire_session, None),
    "suit_disabled": (_disable_suit, None),
    "convention_paused": (_pause_convention, None),
    "owner_disabled": (_disable_owner, None),
    "owner_not_enrolled": (_unenroll_owner, None),
}


@pytest.mark.parametrize("case", list(_NEUTRAL_CASES))
def test_unavailable_targets_share_one_neutral_404(
    case: str, caplog: pytest.LogCaptureFixture
) -> None:
    scenario = create_preview_scenario(f"neutral_{case}")
    change, payload = _NEUTRAL_CASES[case]
    if change is not None:
        change(scenario)

    response = _preview(scenario, payload)

    assert response.status_code == 404
    assert response.json() == TARGET_UNAVAILABLE
    assert_no_token_leak(response.content.decode())
    assert_logs_hold_no_token(caplog)


def _no_selected_convention(s: PreviewScenario) -> None:
    ConventionEnrollment.objects.filter(pk=s.catcher_enrollment.pk).update(
        is_active=False
    )


def _catcher_unenrolled(s: PreviewScenario) -> None:
    ConventionEnrollment.objects.filter(pk=s.catcher_enrollment.pk).delete()


def _catcher_disabled(s: PreviewScenario) -> None:
    PlayerProfile.objects.filter(pk=s.catcher_profile.pk).update(is_enabled=False)


def _no_time_zone(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        time_zone=None, review_deadline_at=None
    )


def _window_closed(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        review_deadline_at=timezone.now() - datetime.timedelta(seconds=1)
    )


@pytest.mark.parametrize(
    ("change", "status", "code"),
    [
        (_no_selected_convention, 403, "catcher_ineligible"),
        (_catcher_unenrolled, 403, "catcher_ineligible"),
        (_catcher_disabled, 403, "catcher_ineligible"),
        (_no_time_zone, 409, "catch_requests_unavailable"),
        (_window_closed, 409, "catch_requests_unavailable"),
    ],
)
def test_catcher_and_window_refusals_use_their_contract_codes(
    change: Callable[[PreviewScenario], None], status: int, code: str
) -> None:
    scenario = create_preview_scenario(f"refusal_{change.__name__}")
    change(scenario)

    response = _preview(scenario)

    assert response.status_code == status
    assert response.json()["code"] == code
    assert_no_token_leak(response.content.decode())


def test_an_owner_scanning_their_own_tag_gets_self_catch_not_allowed() -> None:
    scenario = create_preview_scenario("self")
    ConventionEnrollment.objects.filter(pk=scenario.owner_enrollment.pk).update(
        is_active=True
    )

    response = force_authenticated_client(user=scenario.owner).post(
        PREVIEW_PATH, {"payload": scenario.payload}, content_type="application/json"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "self_catch_not_allowed"


@pytest.mark.parametrize("body", [{}, {"payload": 1}, {"payload": "x", "extra": 1}])
def test_preview_rejects_a_body_without_one_string_payload(body: object) -> None:
    scenario = create_preview_scenario("bad_body")

    response = scenario.catcher_client().post(
        PREVIEW_PATH, body, content_type="application/json"
    )

    assert response.status_code == 400
    assert set(response.json()) == {"payload"}


def _disable_suit_by_operator(s: PreviewScenario) -> Callable[[], None]:
    set_fursuit_enabled(fursuit_id=s.fursuit.pk, is_enabled=False)

    def restore() -> None:
        set_fursuit_enabled(fursuit_id=s.fursuit.pk, is_enabled=True)

    return restore


def _disable_owner_by_operator(s: PreviewScenario) -> Callable[[], None]:
    set_profile_enabled(profile_id=s.owner_profile.pk, is_enabled=False)

    def restore() -> None:
        set_profile_enabled(profile_id=s.owner_profile.pk, is_enabled=True)

    return restore


def _remove_owner_enrollment(s: PreviewScenario) -> Callable[[], None]:
    remove_convention_enrollment(enrollment_id=s.owner_enrollment.pk)

    def restore() -> None:
        ConventionEnrollment.objects.create(user=s.owner, convention=s.convention)
        FursuitActivation.objects.filter(pk=s.activation.pk).update(
            is_active=True, deactivated_at=None
        )

    return restore


@pytest.mark.parametrize(
    "lose",
    [_disable_suit_by_operator, _disable_owner_by_operator, _remove_owner_enrollment],
)
def test_eligibility_loss_never_changes_the_tag_and_preview_resolves_again(
    lose: Callable[[PreviewScenario], Callable[[], None]],
) -> None:
    scenario = create_preview_scenario(f"eligibility_{lose.__name__}")
    tag_before = FursuitTag.objects.values().get(fursuit=scenario.fursuit)
    version_before = (
        type(scenario.fursuit).objects.get(pk=scenario.fursuit.pk).tag_version
    )

    restore = lose(scenario)
    while_lost = _preview(scenario)
    restore()
    create_catch_session(
        activation=FursuitActivation.objects.get(pk=scenario.activation.pk)
    )
    after_return = _preview(scenario)

    assert while_lost.status_code == 404
    assert FursuitTag.objects.values().get(fursuit=scenario.fursuit) == tag_before
    fursuit = type(scenario.fursuit).objects.get(pk=scenario.fursuit.pk)
    assert fursuit.tag_version == version_before
    assert after_return.status_code == 200
