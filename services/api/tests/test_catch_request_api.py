"""Catch request submission, approval preference, and player list (#505).

The criteria live in .refinement/505.md. The contract is
docs/specs/2026-11-09-reusable-tailtag-catch-request-contract.md.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

import pytest
import yaml
from django.test import Client
from django.utils import timezone

from catches.catch_requests import approve_request_in_transaction
from catches.models import Catch, CatchRequest, CatchRequestState
from catches.services import remove_catch_as_operator
from conventions.models import (
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
    FursuitCatchSession,
)
from conventions.review_deadline import database_now
from fursuits.models import Fursuit, FursuitTag
from fursuits.tags import revoke_tag_as_operator
from profiles.models import PlayerProfile
from tests.authentication_support import force_authenticated_client
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.fursuit_tag_test_support import (
    GENERIC_NOT_FOUND,
    TARGET_UNAVAILABLE,
    PreviewScenario,
    assert_no_token_leak,
    create_convention,
    create_player,
    create_preview_scenario,
    create_suit,
    owner_client,
    replace_path,
)

pytestmark = pytest.mark.django_db

REQUESTS_PATH = "/api/catches/requests/"


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True


def _submit(scenario: PreviewScenario, payload: str | None = None) -> Any:
    return scenario.catcher_client().post(
        REQUESTS_PATH,
        {"payload": scenario.payload if payload is None else payload},
        content_type="application/json",
    )


def _patch(scenario: PreviewScenario, body: object) -> Any:
    return owner_client(scenario.owner).patch(
        f"/api/fursuits/{scenario.fursuit.pk}/", body, content_type="application/json"
    )


def _set_mode(scenario: PreviewScenario, mode: str) -> None:
    response = _patch(scenario, {"catch_approval_mode": mode})
    assert response.status_code == 200, response.content


def _utc(value: datetime.datetime | None) -> str:
    assert value is not None
    return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


# --- Submission ---------------------------------------------------------------


def test_manual_submission_creates_one_pending_request_and_no_catch() -> None:
    """AC5, AC27: a pending request is not a completed catch."""
    scenario = create_preview_scenario("manual")

    response = _submit(scenario)

    assert response.status_code == 201
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert body["outcome"] == "pending"
    assert body["catch"] is None
    row = CatchRequest.objects.get()
    assert body["request"] == {
        "id": row.pk,
        "fursuit": {
            "id": scenario.fursuit.pk,
            "tailtag_id": str(scenario.fursuit.tailtag_id),
            "name": scenario.fursuit.name,
            "photo_url": body["request"]["fursuit"]["photo_url"],
        },
        "convention_id": scenario.convention.pk,
        "state": "pending",
        "requested_at": _utc(row.requested_at),
        "review_deadline_at": _utc(scenario.convention.review_deadline_at),
    }
    assert (row.activation_id, row.catch_session_id) == (
        scenario.activation.pk,
        scenario.session.pk,
    )
    assert not Catch.objects.exists()
    history = scenario.catcher_client().get("/api/catches/")
    assert history.status_code == 200
    assert history.json()["results"] == []
    assert_no_token_leak(response.content.decode())


def test_automatic_submission_creates_the_request_and_catch_with_one_time() -> None:
    """AC6: the catch time, request time, and approval time are one value."""
    scenario = create_preview_scenario("automatic")
    _set_mode(scenario, "automatic")

    response = _submit(scenario)

    assert response.status_code == 201
    body = response.json()
    assert body["outcome"] == "approved"
    row = CatchRequest.objects.get()
    catch = Catch.objects.get()
    assert row.state == CatchRequestState.APPROVED
    assert catch.caught_at == row.requested_at == row.approved_at == catch.approved_at
    assert (catch.activation_id, catch.catch_session_id) == (
        scenario.activation.pk,
        scenario.session.pk,
    )
    assert body["request"]["state"] == "approved"
    assert body["catch"]["id"] == catch.pk
    assert body["catch"]["caught_at"] == body["catch"]["approved_at"]
    assert body["catch"]["caught_at"] == _utc(row.requested_at)


def test_a_mode_change_applies_only_to_new_submissions() -> None:
    """AC4: existing pending requests stay pending after automatic is enabled."""
    scenario = create_preview_scenario("mode_change")
    first = _submit(scenario)
    _set_mode(scenario, "automatic")
    other, _ = create_player("mode_change_second")
    ConventionEnrollment.objects.create(
        user=other, convention=scenario.convention, is_active=True
    )

    retry = _submit(scenario)
    newcomer = force_authenticated_client(user=other).post(
        REQUESTS_PATH, {"payload": scenario.payload}, content_type="application/json"
    )

    assert first.json()["outcome"] == "pending"
    assert retry.status_code == 200
    assert retry.json()["outcome"] == "already_pending"
    assert retry.json()["request"]["id"] == first.json()["request"]["id"]
    assert newcomer.json()["outcome"] == "approved"
    assert CatchRequest.objects.get(player=scenario.catcher).state == "pending"
    assert list(Catch.objects.values_list("catcher_user_id", flat=True)) == [other.pk]


def _end_session(s: PreviewScenario) -> None:
    FursuitCatchSession.objects.filter(pk=s.session.pk).update(
        ended_at=timezone.now(), end_reason="owner"
    )


def _complete_convention(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        status=ConventionStatus.COMPLETED
    )


def _replace_tag(s: PreviewScenario) -> None:
    response = owner_client(s.owner).post(
        replace_path(s.fursuit.pk),
        {"expected_version": 1},
        content_type="application/json",
    )
    assert response.status_code == 200


def _revoke_tag(s: PreviewScenario) -> None:
    revoke_tag_as_operator(FursuitTag.objects.get(fursuit=s.fursuit).pk)


@pytest.mark.parametrize(
    ("change", "mode"),
    [
        (_end_session, "manual"),
        (_complete_convention, "manual"),
        (_replace_tag, "manual"),
        (_replace_tag, "automatic"),
    ],
)
def test_a_retry_after_a_target_change_returns_the_unchanged_result(
    change: Callable[[PreviewScenario], None], mode: str
) -> None:
    """AC8, AC9, AC21: the existing-result check runs before target checks 5 to 8."""
    scenario = create_preview_scenario(f"retry_{change.__name__}_{mode}")
    _set_mode(scenario, mode)
    first = _submit(scenario)
    rows_before = list(CatchRequest.objects.values())
    catches_before = list(Catch.objects.values())

    change(scenario)
    retry = _submit(scenario)

    assert retry.status_code == 200
    assert list(CatchRequest.objects.values()) == rows_before
    assert list(Catch.objects.values()) == catches_before
    if mode == "manual":
        assert retry.json()["outcome"] == "already_pending"
        assert retry.json()["request"] == first.json()["request"]
        assert retry.json()["catch"] is None
    else:
        assert retry.json()["outcome"] == "already_caught"
        assert retry.json()["request"] is None
        assert retry.json()["catch"] == first.json()["catch"]


def test_a_catch_wins_over_a_pending_request_for_the_same_trio() -> None:
    """AC10: a v1 catch made while the gate was off beats the pending request."""
    scenario = create_preview_scenario("catch_wins")
    _submit(scenario)
    catch = Catch.objects.create(
        catcher_user=scenario.catcher,
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        activation=scenario.activation,
        catch_session=scenario.session,
    )

    retry = _submit(scenario)

    assert retry.status_code == 200
    assert retry.json()["outcome"] == "already_caught"
    assert retry.json()["request"] is None
    assert retry.json()["catch"]["id"] == catch.pk


def test_a_closed_window_refuses_a_retry_too() -> None:
    """AC7: the window check runs before the existing-result check."""
    scenario = create_preview_scenario("closed_retry")
    _submit(scenario)
    type(scenario.convention).objects.filter(pk=scenario.convention.pk).update(
        review_deadline_at=timezone.now() - datetime.timedelta(seconds=1)
    )

    retry = _submit(scenario)

    assert retry.status_code == 409
    assert retry.json()["code"] == "catch_requests_unavailable"


def _deactivate(s: PreviewScenario) -> None:
    FursuitActivation.objects.filter(pk=s.activation.pk).update(
        is_active=False, deactivated_at=timezone.now()
    )


def _expire_session(s: PreviewScenario) -> None:
    past = timezone.now() - datetime.timedelta(seconds=1)
    FursuitCatchSession.objects.filter(pk=s.session.pk).update(
        started_at=past - datetime.timedelta(hours=1), expires_at=past
    )


def _disable_suit(s: PreviewScenario) -> None:
    Fursuit.objects.filter(pk=s.fursuit.pk).update(is_enabled=False)


def _pause_convention(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        status=ConventionStatus.PAUSED
    )


def _disable_owner(s: PreviewScenario) -> None:
    PlayerProfile.objects.filter(pk=s.owner_profile.pk).update(is_enabled=False)


def _unenroll_owner(s: PreviewScenario) -> None:
    ConventionEnrollment.objects.filter(pk=s.owner_enrollment.pk).delete()


def _no_selected_convention(s: PreviewScenario) -> None:
    ConventionEnrollment.objects.filter(pk=s.catcher_enrollment.pk).update(
        is_active=False
    )


def _disable_catcher(s: PreviewScenario) -> None:
    PlayerProfile.objects.filter(pk=s.catcher_profile.pk).update(is_enabled=False)


def _no_time_zone(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        time_zone=None, review_deadline_at=None
    )


def _close_window(s: PreviewScenario) -> None:
    type(s.convention).objects.filter(pk=s.convention.pk).update(
        review_deadline_at=timezone.now() - datetime.timedelta(seconds=1)
    )


_UNKNOWN = "https://tailtag.app/t#" + "Z" * 43
_REFUSALS: dict[
    str, tuple[Callable[[PreviewScenario], None] | None, str | None, int, str]
] = {
    "unknown": (None, _UNKNOWN, 404, "catch_target_unavailable"),
    "malformed": (None, "https://tailtag.app/t#short", 404, "catch_target_unavailable"),
    "revoked": (_revoke_tag, None, 404, "catch_target_unavailable"),
    "activation_inactive": (_deactivate, None, 404, "catch_target_unavailable"),
    "no_session": (_end_session, None, 404, "catch_target_unavailable"),
    "session_expired": (_expire_session, None, 404, "catch_target_unavailable"),
    "suit_disabled": (_disable_suit, None, 404, "catch_target_unavailable"),
    "convention_paused": (_pause_convention, None, 404, "catch_target_unavailable"),
    "owner_disabled": (_disable_owner, None, 404, "catch_target_unavailable"),
    "owner_not_enrolled": (_unenroll_owner, None, 404, "catch_target_unavailable"),
    "no_selected_convention": (
        _no_selected_convention,
        None,
        403,
        "catcher_ineligible",
    ),
    "catcher_disabled": (_disable_catcher, None, 403, "catcher_ineligible"),
    "no_time_zone": (_no_time_zone, None, 409, "catch_requests_unavailable"),
    "window_closed": (_close_window, None, 409, "catch_requests_unavailable"),
    "window_closed_unknown_tag": (
        _close_window,
        _UNKNOWN,
        409,
        "catch_requests_unavailable",
    ),
}


@pytest.mark.parametrize("case", list(_REFUSALS))
def test_refusals_use_the_contract_codes_and_write_nothing(case: str) -> None:
    """AC7, AC27: neutral 404s and contract codes. No row on any refusal."""
    scenario = create_preview_scenario(f"refuse_{case}")
    change, payload, status, code = _REFUSALS[case]
    if change is not None:
        change(scenario)

    response = _submit(scenario, payload)

    assert response.status_code == status
    if status == 404:
        assert response.json() == TARGET_UNAVAILABLE
    else:
        assert response.json()["code"] == code
    assert not CatchRequest.objects.exists()
    assert not Catch.objects.exists()
    assert_no_token_leak(response.content.decode())


def test_an_owner_submitting_their_own_tag_gets_self_catch_not_allowed() -> None:
    scenario = create_preview_scenario("self")
    ConventionEnrollment.objects.filter(pk=scenario.owner_enrollment.pk).update(
        is_active=True
    )

    response = owner_client(scenario.owner).post(
        REQUESTS_PATH, {"payload": scenario.payload}, content_type="application/json"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "self_catch_not_allowed"
    assert not CatchRequest.objects.exists()


@pytest.mark.parametrize("body", [{}, {"payload": 1}, {"payload": "x", "extra": 1}])
def test_submission_rejects_a_body_without_one_string_payload(body: object) -> None:
    scenario = create_preview_scenario("bad_body")

    response = scenario.catcher_client().post(
        REQUESTS_PATH, body, content_type="application/json"
    )

    assert response.status_code == 400
    assert set(response.json()) == {"payload"}


def test_the_gate_off_hides_both_request_operations(settings: Any) -> None:
    """AC29: both operations return the generic not-found shape."""
    scenario = create_preview_scenario("gate_off")
    settings.CATCH_REQUESTS_ENABLED = False

    submit = _submit(scenario)
    listing = scenario.catcher_client().get(REQUESTS_PATH)

    assert (submit.status_code, submit.json()) == (404, GENERIC_NOT_FOUND)
    assert (listing.status_code, listing.json()) == (404, GENERIC_NOT_FOUND)
    assert not CatchRequest.objects.exists()


# --- Player request list ------------------------------------------------------


def _request_row(
    scenario: PreviewScenario,
    *,
    player: Any = None,
    convention: Any = None,
    fursuit: Any = None,
    state: str = CatchRequestState.PENDING,
    requested_at: datetime.datetime | None = None,
) -> CatchRequest:
    values: dict[str, object] = {}
    if state == CatchRequestState.INVALIDATED.value:
        values["invalidated_at"] = timezone.now()
    return CatchRequest.objects.create(
        player=player or scenario.catcher,
        fursuit=fursuit or scenario.fursuit,
        convention=convention or scenario.convention,
        activation=scenario.activation,
        catch_session=scenario.session,
        state=state,
        requested_at=requested_at or timezone.now(),
        **values,
    )


def test_the_player_list_shows_only_the_callers_open_window_requests() -> None:
    """AC11, AC12: own rows, open windows, newest first, and the filter."""
    scenario = create_preview_scenario("list")
    second_suit = create_suit(scenario.owner)
    closed = create_convention("list_closed", window_open=False)
    other, _ = create_player("list_other")
    now = timezone.now()
    older = _request_row(scenario, requested_at=now - datetime.timedelta(minutes=5))
    newer = _request_row(
        scenario,
        fursuit=second_suit,
        state=CatchRequestState.INVALIDATED,
        requested_at=now,
    )
    _request_row(scenario, convention=closed)
    _request_row(scenario, player=other)

    listing = scenario.catcher_client().get(REQUESTS_PATH)
    filtered = scenario.catcher_client().get(
        REQUESTS_PATH, {"convention_id": closed.pk}
    )

    assert listing.status_code == 200
    assert listing["Cache-Control"] == "no-store"
    results = listing.json()["results"]
    assert [row["id"] for row in results] == [newer.pk, older.pk]
    assert [row["state"] for row in results] == ["unavailable", "pending"]
    assert results[0]["review_deadline_at"] == _utc(
        scenario.convention.review_deadline_at
    )
    assert filtered.json() == {"results": []}


@pytest.mark.parametrize("value", ["abc", "0", "\u00b2"])
def test_the_player_list_rejects_an_invalid_convention_filter(value: str) -> None:
    """A non-ASCII digit such as superscript two must not reach int()."""
    scenario = create_preview_scenario(f"list_filter_{value.encode().hex()}")

    response = scenario.catcher_client().get(REQUESTS_PATH, {"convention_id": value})

    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid_query",
        "detail": "The convention filter is invalid.",
    }


def test_an_ineligible_player_cannot_read_the_list() -> None:
    scenario = create_preview_scenario("list_ineligible")
    _disable_catcher(scenario)

    response = scenario.catcher_client().get(REQUESTS_PATH)

    assert response.status_code == 403
    assert response.json()["code"] == "catcher_ineligible"


# --- Approval preference ------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "status", "keys"),
    [
        ({}, 400, {"non_field_errors"}),
        ({"color": "red"}, 400, {"non_field_errors"}),
        ({"catch_approval_mode": "sometimes"}, 400, {"catch_approval_mode"}),
    ],
)
def test_the_patch_validates_its_fields(
    body: object, status: int, keys: set[str]
) -> None:
    """AC2: a body needs name, catch_approval_mode, or both, with known values."""
    scenario = create_preview_scenario("patch_invalid")

    response = _patch(scenario, body)

    assert response.status_code == status
    assert set(response.json()) == keys
    assert Fursuit.objects.get(pk=scenario.fursuit.pk).catch_approval_mode == "manual"


def test_the_patch_changes_both_fields_with_the_gate_off_on_a_disabled_suit(
    settings: Any,
) -> None:
    """AC1 to AC3: manual by default, stored with the gate off, rename unchanged."""
    settings.CATCH_REQUESTS_ENABLED = False
    owner, _ = create_player("patch_both")
    fursuit = create_suit(owner, enabled=False)
    before = owner_client(owner).get(f"/api/fursuits/{fursuit.pk}/").json()

    response = owner_client(owner).patch(
        f"/api/fursuits/{fursuit.pk}/",
        {"name": "Renamed Suit", "catch_approval_mode": "automatic"},
        content_type="application/json",
    )

    assert before["catch_approval_mode"] == "manual"
    assert response.status_code == 200
    assert response.json()["catch_approval_mode"] == "automatic"
    assert response.json()["name"] == "Renamed Suit"
    stored = Fursuit.objects.get(pk=fursuit.pk)
    assert (stored.name, stored.catch_approval_mode) == ("Renamed Suit", "automatic")


# --- Request record -----------------------------------------------------------


def test_the_shared_approval_uses_the_request_time_as_the_catch_time() -> None:
    """AC22: a later approval keeps caught_at at the request time."""
    scenario = create_preview_scenario("later_approval")
    _submit(scenario)
    row = CatchRequest.objects.get()
    later = database_now()

    catch = approve_request_in_transaction(row, approved_at=later)

    row.refresh_from_db()
    catch.refresh_from_db()
    assert later > row.requested_at
    assert catch.caught_at == row.requested_at
    assert catch.approved_at == row.approved_at == later
    assert row.state == CatchRequestState.APPROVED


def test_operator_catch_removal_works_while_its_request_exists() -> None:
    """AC17: no foreign key ties a request to its catch."""
    scenario = create_preview_scenario("operator_removal")
    _set_mode(scenario, "automatic")
    _submit(scenario)

    result = remove_catch_as_operator(catch_id=Catch.objects.get().pk)

    assert result.changed is True
    assert not Catch.objects.exists()
    assert CatchRequest.objects.get().state == CatchRequestState.APPROVED


def test_a_later_convention_activation_creates_a_separate_trio() -> None:
    """One request per trio. The same suit at a later convention is a new trio."""
    scenario = create_preview_scenario("later_trio")
    _submit(scenario)
    later = create_convention("later_trio_event")
    ConventionEnrollment.objects.create(user=scenario.owner, convention=later)
    ConventionEnrollment.objects.filter(pk=scenario.catcher_enrollment.pk).update(
        is_active=False
    )
    ConventionEnrollment.objects.create(
        user=scenario.catcher, convention=later, is_active=True
    )
    create_catch_session(
        activation=create_activation_row(
            fursuit=scenario.fursuit, convention=later, active=True
        )
    )

    response = _submit(scenario)

    assert response.status_code == 201
    assert CatchRequest.objects.filter(state="pending").count() == 2


def test_the_schema_documents_the_bodies_that_the_operations_return() -> None:
    """The documented shapes match the runtime bodies, so the client can decode them."""
    schema = yaml.safe_load(Client().get("/api/schema/").content)
    components = schema["components"]["schemas"]
    operations = schema["paths"][REQUESTS_PATH]

    def body(operation: str, status: str) -> dict[str, Any]:
        content = operations[operation]["responses"][status]["content"]
        return content["application/json"]["schema"]

    def component(name: str) -> dict[str, Any]:
        return components[name]

    assert operations["post"]["requestBody"]["required"] is True
    assert body("get", "400") == {"$ref": "#/components/schemas/CatchRequestError"}
    assert body("get", "404") == {"$ref": "#/components/schemas/DetailError"}
    assert component("DetailError")["required"] == ["detail"]
    assert body("post", "404") == {"$ref": "#/components/schemas/CatchRequestNotFound"}
    assert component("CatchRequestNotFound")["required"] == ["detail"]
    assert body("post", "200") == body("post", "201")
    assert set(component("CatchRequestState")["enum"]) == {
        "pending",
        "approved",
        "declined",
        "withdrawn",
        "unavailable",
    }
