"""#508 AC11 to AC19: load traffic on the catch request flow, end to end."""

from collections.abc import Callable
from typing import cast

import pytest
from request_support import RequestWorld, Row, request_config, run_requests


def totals(run: object, *keys: str) -> dict[str, int]:
    summaries = cast(dict[str, dict[str, int]], run.population.summaries)  # type: ignore[attr-defined]
    return {key: sum(item[key] for item in summaries.values()) for key in keys}


def test_baseline_submits_reviews_and_credits_every_request() -> None:
    config = request_config(actors=4, review={"automatic_share": 0.5})
    world = RequestWorld(config)

    run, _ = run_requests(world, config)

    assert run.population.passed, run.population.failure
    counts = totals(run, "pending", "automatic", "approved", "declined")
    assert counts["pending"] + counts["automatic"] == len(world.rows) == 4
    assert counts["approved"] + counts["declined"] == counts["pending"]
    assert all(row.state in ("approved", "declined") for row in world.rows)
    # Every catch belongs to an approved request, at the request time.
    approved = {
        (r.player, r.fursuit): r.requested_at
        for r in world.rows
        if r.state == "approved"
    }
    assert {
        (c["player"], c["fursuit"]): c["caught_at"] for c in world.catches
    } == approved
    # Owners set the seeded approval mode and read the tag, never the v1 credential.
    paths = {path for _, _, path in world.calls}
    assert not any(
        "catch-credential" in path or path.endswith("/confirm/") for path in paths
    )
    assert {"/api/catches/preview/", "/api/catches/incoming-requests/"} <= paths
    attempts = run.traffic
    assert attempts["unresolved"] == 0


def test_the_same_seed_makes_the_same_choices() -> None:
    config = request_config(actors=4)

    def choices() -> tuple[object, ...]:
        world = RequestWorld(config)
        run_requests(world, config, seed=11)
        return tuple((r.player, r.fursuit, r.state) for r in world.rows) + tuple(
            (s.id, s.mode) for s in world.suits.values()
        )

    assert choices() == choices()


def test_lost_submit_responses_converge_on_one_request() -> None:
    config = request_config(
        actors=2,
        failure={"operations": ["submit"]},
        casual_repeats=2,
        review={"automatic_share": 0},
    )
    world = RequestWorld(config)
    world.lost_submits = 3

    run, compared = run_requests(world, config, reconcile=True)

    assert run.population.passed, run.population.failure
    assert len(world.rows) == 2
    assert compared is not None and compared.passed, compared


def test_concurrent_duplicate_submissions_name_one_request() -> None:
    config = request_config(actors=1, family="hotspot", review={"automatic_share": 0})
    world = RequestWorld(config)
    world.overlap = True

    run, _ = run_requests(world, config)

    assert run.population.passed, run.population.failure
    assert len(world.rows) == 1
    assert totals(run, "pending", "already_pending") == {
        "pending": 1,
        "already_pending": 1,
    }


@pytest.mark.parametrize("case", ["stopped", "replaced"])
def test_a_session_end_or_tag_replacement_keeps_the_pending_request_approvable(
    case: str,
) -> None:
    config = request_config(
        actors=1,
        fursuits=1,
        failure={"domain_case": case, "recover_existing": True},
        review={"automatic_share": 0, "approve_rate": 1},
    )
    world = RequestWorld(config)

    run, _ = run_requests(world, config)

    assert run.population.passed, run.population.failure
    assert [r.state for r in world.rows] == ["approved"]
    assert totals(run, "already_pending")["already_pending"] == 1


@pytest.mark.parametrize("case", ["stopped", "replaced"])
def test_a_new_submission_after_the_change_is_an_expected_rejection(case: str) -> None:
    config = request_config(actors=1, fursuits=1, failure={"domain_case": case})
    world = RequestWorld(config)

    run, _ = run_requests(world, config)

    assert run.population.passed, run.population.failure
    assert world.rows == []
    assert totals(run, "expected_rejections")["expected_rejections"] == 1


def test_an_unplanned_429_fails_correctness() -> None:
    config = request_config(actors=1)
    world = RequestWorld(config)
    world.refuse_submits = 1

    run, _ = run_requests(world, config)

    assert not run.population.passed
    assert run.traffic["stop_reason"] == "correctness"


def _second_row(world: RequestWorld) -> None:
    first = world.rows[0]
    world.rows.append(
        Row(first.id + 100, first.player, first.fursuit, "pending", first.requested_at)
    )


def _uncredited(world: RequestWorld) -> None:
    world.catches.clear()


def _declined_with_credit(world: RequestWorld) -> None:
    row = next(r for r in world.rows if r.state == "approved")
    row.state = "declined"


def _state_changed(world: RequestWorld) -> None:
    world.rows[0].state = "invalidated"


@pytest.mark.parametrize(
    ("tamper", "check"),
    [
        (_second_row, "request_duplicate"),
        (_uncredited, "request_credit"),
        (_declined_with_credit, "request_credit"),
        (_state_changed, "request_state"),
    ],
    ids=(
        "two-rows-one-trio",
        "approved-without-catch",
        "catch-without-approval",
        "state-differs",
    ),
)
def test_request_reconciliation_finds_each_break(
    tamper: Callable[[RequestWorld], None], check: str
) -> None:
    """#508 AC24 to AC26: credit and state disagreements fail reconciliation."""
    config = request_config(actors=2, review={"automatic_share": 0, "approve_rate": 1})
    world = RequestWorld(config)
    world.tamper = tamper

    run, compared = run_requests(world, config, reconcile=True)

    assert run.population.passed
    assert compared is not None and not compared.passed
    assert check in {item.check for item in compared.discrepancies}
