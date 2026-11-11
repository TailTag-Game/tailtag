"""Contract cooldown examples A to F and the refusal tie rule (#506 AC22, AC26).

The table copies the contract section "Worked examples". Each row gives the
trio history after its events and the earliest next submission, in seconds
after the first submission.
"""

from __future__ import annotations

import datetime

import pytest

from catches.request_protections import (
    TrioHistory,
    earliest_next_submission,
    pick_refusal,
)
from observability.outcomes import Reason

_ZERO = datetime.datetime(2027, 1, 16, 12, 0, tzinfo=datetime.UTC)


def _at(seconds: int | None) -> datetime.datetime | None:
    return None if seconds is None else _ZERO + datetime.timedelta(seconds=seconds)


@pytest.mark.parametrize(
    ("last_requested", "declines", "last_declined", "earliest"),
    [
        pytest.param(0, 1, 30, 40, id="A-first-decline"),
        pytest.param(40, 2, 50, 650, id="B-second-decline"),
        pytest.param(40, 1, 30, 50, id="C-undo-second-decline"),
        pytest.param(40, 2, 400, 1000, id="D-restore-then-decline-again"),
        pytest.param(12, 1, 2, 22, id="E-submission-floor-wins"),
        pytest.param(0, 0, None, 10, id="F-withdrawal"),
    ],
)
def test_contract_cooldown_examples(
    last_requested: int, declines: int, last_declined: int | None, earliest: int
) -> None:
    history = TrioHistory(
        last_requested_at=_at(last_requested),
        counted_declines=declines,
        last_declined_at=_at(last_declined),
    )

    assert earliest_next_submission(history) == _at(earliest)


@pytest.mark.parametrize(
    ("refusals", "expected"),
    [
        pytest.param(
            [(10, Reason.COOLDOWN_ACTIVE), (10, Reason.RATE_LIMITED)],
            (10, "cooldown_active"),
            id="tie-gives-cooldown",
        ),
        pytest.param(
            [(10, Reason.RATE_LIMITED), (10, Reason.COOLDOWN_ACTIVE)],
            (10, "cooldown_active"),
            id="tie-in-any-order",
        ),
        pytest.param(
            [(9, Reason.COOLDOWN_ACTIVE), (10, Reason.RATE_LIMITED)],
            (10, "rate_limited"),
            id="larger-wins",
        ),
    ],
)
def test_the_larger_rounded_wait_wins_and_a_tie_gives_the_cooldown(
    refusals: list[tuple[int, Reason]], expected: tuple[int, str]
) -> None:
    """AC26: the comparison uses the seconds that the client sees."""
    refusal = pick_refusal(refusals)

    assert refusal is not None
    assert (refusal.retry_after_seconds, refusal.code) == expected
