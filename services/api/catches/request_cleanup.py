"""Delete catch request history after the review deadline (#507).

The reusable TailTag contract, section "Privacy and retention", is the source
of truth. Cleanup deletes every request row, in any state, and every block for
each convention whose stored review deadline has passed. It never changes a
catch (#507 G3).

Each convention runs in its own transaction. A failure leaves that
convention's rows in place, and the next run deletes them. Reads already hide
closed-window rows, so a late or failed run exposes nothing.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Final

from django.db import transaction
from django.db.models import Count, Exists, OuterRef

from catches.models import CatchBlock, CatchRequest, CatchRequestState
from conventions.models import Convention
from conventions.review_deadline import database_now
from observability.outcomes import Outcome, Reason, Signal, record_outcome

_logger = logging.getLogger(__name__)

# The state of each deleted row, as a cleanup reason. A pending row expired.
_STATE_REASONS: Final = {
    CatchRequestState.PENDING: Reason.EXPIRED,
    CatchRequestState.APPROVED: Reason.APPROVED,
    CatchRequestState.DECLINED: Reason.DECLINED,
    CatchRequestState.WITHDRAWN: Reason.WITHDRAWN,
    CatchRequestState.INVALIDATED: Reason.INVALIDATED,
}


@dataclass
class CleanupResult:
    """Counts from one run. It holds no convention, request, or player ID."""

    deleted_requests: Counter[str] = field(default_factory=Counter[str])
    deleted_blocks: int = 0
    failed_conventions: int = 0

    @property
    def succeeded(self) -> bool:
        return self.failed_conventions == 0


def run_cleanup() -> CleanupResult:
    """Clean every closed convention and record one outcome for the run."""
    result = CleanupResult()
    try:
        for convention_id in _closed_conventions_with_history():
            try:
                requests, blocks = _clean_convention(convention_id)
            except Exception as error:  # noqa: BLE001 - one convention never stops the run.
                result.failed_conventions += 1
                # No traceback: an exception message can carry row values.
                _logger.error(
                    "Catch request cleanup failed for one convention.",
                    extra={
                        "event": str(Signal.REQUEST_CLEANUP),
                        "error_type": type(error).__name__,
                    },
                )
                continue
            result.deleted_requests.update(requests)
            result.deleted_blocks += blocks
    except BaseException:
        record_outcome(Signal.REQUEST_CLEANUP, Outcome.FAILED)
        raise
    for state, reason in _STATE_REASONS.items():
        count = result.deleted_requests[state]
        if count:
            record_outcome(Signal.REQUEST_CLEANUP, Outcome.DELETED, reason, count=count)
    record_outcome(
        Signal.REQUEST_CLEANUP,
        Outcome.SUCCEEDED if result.succeeded else Outcome.FAILED,
    )
    return result


def _closed_conventions_with_history() -> list[int]:
    """Return conventions whose deadline passed and that still hold history.

    A null deadline never matches, so a convention without a zone is skipped.
    """
    now = database_now()
    return list(
        Convention.objects.filter(review_deadline_at__lte=now)
        .filter(
            Exists(CatchRequest.objects.filter(convention_id=OuterRef("pk")))
            | Exists(CatchBlock.objects.filter(convention_id=OuterRef("pk")))
        )
        .order_by("pk")
        .values_list("pk", flat=True)
    )


def _clean_convention(convention_id: int) -> tuple[dict[str, int], int]:
    """Delete one closed convention's requests and blocks in one transaction.

    The Convention lock waits for any request action in flight, because every
    action locks the Convention first. After the lock, no action can write,
    because the window is closed for good.
    """
    with transaction.atomic():
        convention = Convention.objects.select_for_update().get(pk=convention_id)
        deadline = convention.review_deadline_at
        if deadline is None or database_now() < deadline:
            return {}, 0
        blocks, _ = CatchBlock.objects.filter(convention_id=convention_id).delete()
        requests = CatchRequest.objects.filter(convention_id=convention_id)
        counts: dict[str, int] = dict(
            requests.order_by()
            .values_list("state")
            .annotate(rows=Count("pk"))
            .values_list("state", "rows")
        )
        requests.delete()
        return counts, blocks
