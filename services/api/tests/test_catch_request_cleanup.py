"""Catch request expiry and cleanup after the review deadline (#507).

The criteria live in .refinement/507.md. The contract is
docs/specs/2026-11-09-reusable-tailtag-catch-request-contract.md.

The Sentry SDK runs for real. Only its network transport is replaced, so the
Crons check-ins and the cleanup metrics are read as sent.
"""

from __future__ import annotations

import datetime
import io
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from catches import request_cleanup
from catches.models import Catch, CatchBlock, CatchRequest, CatchRequestState
from conventions.models import Convention, ConventionEnrollment
from conventions.services import set_convention_admin_state
from tests.authentication_support import force_authenticated_client
from tests.fursuit_tag_test_support import (
    PreviewScenario,
    assert_no_token_leak,
    create_convention,
    create_player,
    create_preview_scenario,
    owner_client,
)
from tests.observability_test_support import (
    CapturingTransport,
    JsonLogCapture,
    RecordedCount,
    capture_json_stdout,
    identity,
    recorded_outcome_counts,
    sentry_capturing,
)

pytestmark = pytest.mark.django_db

SIGNAL = "tailtag.catches.request_cleanup"
REQUESTS_PATH = "/api/catches/requests/"
INCOMING_PATH = "/api/catches/incoming-requests/"


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True


@dataclass(frozen=True)
class Telemetry:
    logs: JsonLogCapture
    transport: CapturingTransport

    def cleanup_outcomes(self) -> list[RecordedCount]:
        return [
            outcome
            for outcome in recorded_outcome_counts(self.logs, self.transport)
            if outcome[0] == SIGNAL
        ]

    def check_ins(self) -> list[tuple[str, str]]:
        return [
            (check_in["monitor_slug"], check_in["status"])
            for check_in in self.transport.check_ins()
        ]


@pytest.fixture
def telemetry() -> Iterator[Telemetry]:
    with sentry_capturing(identity()) as transport, capture_json_stdout() as logs:
        yield Telemetry(logs, transport)


def _row(
    scenario: PreviewScenario, state: str, *, convention: Convention | None = None
) -> CatchRequest:
    now = timezone.now()
    times = {
        CatchRequestState.APPROVED: {"approved_at": now},
        CatchRequestState.DECLINED: {"declined_at": now, "decline_blocked": True},
        CatchRequestState.WITHDRAWN: {"withdrawn_at": now},
        CatchRequestState.INVALIDATED: {"invalidated_at": now},
    }.get(CatchRequestState(state), {})
    return CatchRequest.objects.create(
        player=scenario.catcher,
        fursuit=scenario.fursuit,
        convention=convention or scenario.convention,
        activation=scenario.activation,
        catch_session=scenario.session,
        state=state,
        requested_at=now,
        **times,
    )


def _block(scenario: PreviewScenario, convention: Convention) -> CatchBlock:
    return CatchBlock.objects.create(
        player=scenario.catcher,
        fursuit=scenario.fursuit,
        convention=convention,
        created_at=timezone.now(),
    )


def _close(convention: Convention) -> None:
    Convention.objects.filter(pk=convention.pk).update(
        review_deadline_at=timezone.now() - datetime.timedelta(seconds=1)
    )


def _cleanup() -> str:
    out = io.StringIO()
    call_command("cleanup_catch_requests", stdout=out)
    return out.getvalue()


def test_cleanup_deletes_closed_history_and_keeps_catches(
    telemetry: Telemetry,
) -> None:
    """AC21 to AC25, AC34: every state and block goes, catches stay, a rerun is a no-op."""
    scenario = create_preview_scenario("cleanup")
    for state in CatchRequestState:
        _row(scenario, state)
    _block(scenario, scenario.convention)
    caught_at = timezone.now() - datetime.timedelta(hours=1)
    catch = Catch.objects.create(
        catcher_user=scenario.catcher,
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        activation=scenario.activation,
        catch_session=scenario.session,
        caught_at=caught_at,
        approved_at=caught_at + datetime.timedelta(minutes=5),
    )
    open_window = create_convention("cleanup_open")
    unknown_zone = create_convention("cleanup_unknown", window_open=None)
    kept = [
        _row(scenario, CatchRequestState.PENDING, convention=open_window),
        _row(scenario, CatchRequestState.PENDING, convention=unknown_zone),
    ]
    kept_block = _block(scenario, open_window)
    _close(scenario.convention)

    first = _cleanup()
    second = _cleanup()

    assert first == "Deleted 5 catch requests and 1 blocks.\n"
    assert second == "Deleted 0 catch requests and 0 blocks.\n"
    assert not CatchRequest.objects.filter(convention=scenario.convention).exists()
    assert not CatchBlock.objects.filter(convention=scenario.convention).exists()
    assert sorted(CatchRequest.objects.values_list("pk", flat=True)) == sorted(
        row.pk for row in kept
    )
    assert CatchBlock.objects.filter(pk=kept_block.pk).exists()
    catch.refresh_from_db()
    assert (catch.caught_at, catch.approved_at) == (
        caught_at,
        caught_at + datetime.timedelta(minutes=5),
    )
    assert sorted(telemetry.cleanup_outcomes()) == sorted(
        [
            (SIGNAL, "deleted", "expired", 1),
            (SIGNAL, "deleted", "approved", 1),
            (SIGNAL, "deleted", "declined", 1),
            (SIGNAL, "deleted", "withdrawn", 1),
            (SIGNAL, "deleted", "invalidated", 1),
            (SIGNAL, "succeeded", None, 1),
            (SIGNAL, "succeeded", None, 1),
        ]
    )
    assert (
        telemetry.check_ins()
        == [
            ("catch-request-cleanup", "in_progress"),
            ("catch-request-cleanup", "ok"),
        ]
        * 2
    )
    config = telemetry.transport.check_ins()[0]["monitor_config"]
    assert config["schedule"] == {"type": "crontab", "value": "0 10 * * *"}
    emitted = telemetry.logs.text + telemetry.transport.serialized()
    assert_no_token_leak(emitted)
    for private in (scenario.convention.name, scenario.fursuit.name, "player"):
        assert private not in emitted


def test_a_failed_convention_keeps_its_rows_and_the_next_run_retries(
    telemetry: Telemetry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC23 to AC25: one failure keeps the others, fails the check-in, and retries."""
    scenario = create_preview_scenario("cleanup_failure")
    failing = scenario.convention
    healthy = create_convention("cleanup_healthy")
    failing_row = _row(scenario, CatchRequestState.PENDING)
    _row(scenario, CatchRequestState.PENDING, convention=healthy)
    _close(failing)
    _close(healthy)
    clean = request_cleanup._clean_convention  # pyright: ignore[reportPrivateUsage]

    def fault(convention_id: int) -> tuple[dict[str, int], int]:
        # Fault injection: a database failure for one convention only.
        if convention_id == failing.pk:
            raise RuntimeError("forced cleanup failure")
        return clean(convention_id)

    monkeypatch.setattr(request_cleanup, "_clean_convention", fault)

    with pytest.raises(CommandError, match="failed for 1 convention"):
        _cleanup()
    after_failure = (
        CatchRequest.objects.filter(pk=failing_row.pk).exists(),
        CatchRequest.objects.filter(convention=healthy).exists(),
    )
    monkeypatch.setattr(request_cleanup, "_clean_convention", clean)
    retry = _cleanup()

    assert after_failure == (True, False)
    assert retry == "Deleted 1 catch requests and 0 blocks.\n"
    assert telemetry.cleanup_outcomes() == [
        (SIGNAL, "deleted", "expired", 1),
        (SIGNAL, "failed", None, 1),
        (SIGNAL, "deleted", "expired", 1),
        (SIGNAL, "succeeded", None, 1),
    ]
    assert [status for _, status in telemetry.check_ins()] == [
        "in_progress",
        "error",
        "in_progress",
        "ok",
    ]
    failure_lines = [
        line
        for line in telemetry.logs.lines()
        if line.get("event") == SIGNAL and "error_type" in line
    ]
    assert [line["error_type"] for line in failure_lines] == ["RuntimeError"]
    assert "forced cleanup failure" not in telemetry.logs.text


def test_history_closes_at_the_deadline_and_is_gone_after_cleanup() -> None:
    """AC20: closure hides every request and refuses actions. A date change keeps
    the window closed. After cleanup, actions find nothing and catches stay."""
    scenario = create_preview_scenario("closure")
    owner = owner_client(scenario.owner)
    clients = [scenario.catcher_client()]
    for label in ("closure_two", "closure_three"):
        player, _ = create_player(label)
        ConventionEnrollment.objects.create(
            user=player, convention=scenario.convention, is_active=True
        )
        clients.append(force_authenticated_client(user=player))
    ids = [
        int(
            client.post(
                REQUESTS_PATH,
                {"payload": scenario.payload},
                content_type="application/json",
            ).json()["request"]["id"]
        )
        for client in clients
    ]
    approved = owner.post(f"{INCOMING_PATH}{ids[0]}/approve/").json()["catch"]
    owner.post(
        f"{INCOMING_PATH}{ids[1]}/decline/",
        {"block": False},
        content_type="application/json",
    )
    _close(scenario.convention)
    convention = Convention.objects.get(pk=scenario.convention.pk)
    deadline = convention.review_deadline_at
    set_convention_admin_state(
        convention_id=convention.pk,
        name=convention.name,
        status=convention.status,
        start_date=convention.start_date,
        end_date=timezone.localdate() + datetime.timedelta(days=30),
        time_zone=convention.time_zone,
    )

    def actions() -> set[tuple[int, str]]:
        responses = [
            owner.post(f"{INCOMING_PATH}{request_id}/approve/") for request_id in ids
        ] + [clients[2].post(f"{REQUESTS_PATH}{ids[2]}/withdraw/")]
        return {(r.status_code, r.json()["code"]) for r in responses}

    lists = [
        clients[0].get(REQUESTS_PATH).json()["results"],
        owner.get(INCOMING_PATH).json()["results"],
        owner.get(f"{INCOMING_PATH}summary/").json()["pending_count"],
    ]
    closed_actions = actions()
    _cleanup()
    deleted_actions = actions()

    assert Convention.objects.get(pk=convention.pk).review_deadline_at == deadline
    assert lists == [[], [], 0]
    assert closed_actions == {(409, "review_window_closed")}
    assert deleted_actions == {(404, "request_not_found")}
    catch = Catch.objects.get()
    assert catch.pk == approved["id"]
    assert catch.caught_at.isoformat().replace("+00:00", "Z") == approved["caught_at"]
    assert (
        catch.approved_at.isoformat().replace("+00:00", "Z") == approved["approved_at"]
    )
