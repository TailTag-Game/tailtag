"""Catch request submission and the shared catch-from-request write (#505).

The reusable TailTag contract is the source of truth: sections "Submission
checks", "Transaction rule", and "Approval preference". #505 added checks 1 to 9.
#506 added check 10 (blocks) and check 11 (cooldowns and the per-player limit).

Two implementation choices from the #505 refinement apply here:

- The existing-result check runs after checks 1, 2, and 4 and a lookup of any
  known tag row, before target checks 5 to 8. A retry after a lost response
  gets its own request or catch back even when the target changed since.
- The PlayerProfile tier comes first and locks the catcher and owner profiles
  in pk order. Two players who catch each other's suits cannot deadlock.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum

from django.db import IntegrityError, transaction

from accounts.models import User
from catches.models import Catch, CatchRequest, CatchRequestState
from catches.request_protections import (
    SubmissionRefusedError,
    check_submission_allowed,
    is_blocked,
)
from catches.tag_preview import (
    TagPreviewCatcherIneligibleError,
    TagPreviewSelfCatchError,
    TagPreviewTargetUnavailableError,
    TagPreviewUnavailableError,
)
from conventions.models import (
    Convention,
    ConventionEnrollment,
    FursuitActivation,
    FursuitCatchSession,
)
from conventions.review_deadline import database_now, review_window_open
from fursuits.models import CatchApprovalMode, Fursuit, FursuitTag
from fursuits.tags import TagPayloadInvalidError, parse_tag_payload
from observability.outcomes import Reason
from profiles.eligibility import is_participation_eligible
from profiles.models import PlayerProfile

_UNIQUE_CONSTRAINTS = frozenset(
    {
        "catches_request_one_pending_per_trio",
        "catches_catcher_fursuit_convention_unique",
    }
)

# The submission refusals share the preview errors, because both map to the same
# contract codes. Each carries a telemetry reason that is never public.
CatchRequestCatcherIneligibleError = TagPreviewCatcherIneligibleError
CatchRequestsUnavailableError = TagPreviewUnavailableError
CatchRequestTargetUnavailableError = TagPreviewTargetUnavailableError
CatchRequestSelfCatchError = TagPreviewSelfCatchError
CatchRequestRefusedError = SubmissionRefusedError


class SubmissionOutcome(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    ALREADY_PENDING = "already_pending"
    ALREADY_CAUGHT = "already_caught"


@dataclass(frozen=True)
class SubmissionResult:
    outcome: SubmissionOutcome
    request: CatchRequest | None
    catch: Catch | None

    @property
    def created(self) -> bool:
        return self.outcome in (SubmissionOutcome.PENDING, SubmissionOutcome.APPROVED)


@dataclass(frozen=True)
class _Discovery:
    convention_id: int
    tag_id: int
    fursuit_id: int
    owner_id: int


def submit_catch_request(user: User, *, payload: str) -> SubmissionResult:
    """Create one request, or one immediate catch, or return the trio's result."""
    discovery = _discover(user, payload)
    try:
        return _submit(user, discovery)
    except IntegrityError as error:
        # The profile lock serializes one player's submissions, so this path only
        # covers a writer that does not take that lock, such as a later approval.
        if _constraint_name(error) not in _UNIQUE_CONSTRAINTS:
            raise
        existing = _existing_result(
            player_id=user.pk,
            fursuit_id=discovery.fursuit_id,
            convention_id=discovery.convention_id,
        )
        if existing is None:
            raise
        return existing


def approve_request_in_transaction(
    request: CatchRequest, *, approved_at: datetime.datetime
) -> Catch:
    """Approve a locked pending *request* and create its catch.

    The caller holds the contract locks and passes the database time read after
    them. The catch time is the request time. Automatic approval uses this now,
    and the #506 owner approval reuses it.
    """
    request.state = CatchRequestState.APPROVED
    request.approved_at = approved_at
    request.save(update_fields=["state", "approved_at"])
    return Catch.objects.create(
        catcher_user_id=request.player_id,
        fursuit_id=request.fursuit_id,
        convention_id=request.convention_id,
        activation_id=request.activation_id,
        catch_session_id=request.catch_session_id,
        caught_at=request.requested_at,
        approved_at=approved_at,
    )


def _discover(user: User, payload: str) -> _Discovery:
    """Find the selected convention and the tag's suit without any lock."""
    if not is_participation_eligible(user):
        raise CatchRequestCatcherIneligibleError(Reason.CATCHER_INELIGIBLE)
    enrollment = (
        ConventionEnrollment.objects.filter(user=user, is_active=True)
        .select_related("convention")
        .first()
    )
    if enrollment is None:
        raise CatchRequestCatcherIneligibleError(Reason.CATCHER_INELIGIBLE)
    # Contract check 2 precedes the tag checks, as in preview. This read only
    # picks the refusal code. The locked check in _submit stays authoritative.
    if not review_window_open(enrollment.convention, database_now()):
        raise CatchRequestsUnavailableError(Reason.REQUESTS_UNAVAILABLE)
    try:
        token = parse_tag_payload(payload)
    except TagPayloadInvalidError:
        raise CatchRequestTargetUnavailableError(Reason.PAYLOAD_INVALID) from None
    row = (
        FursuitTag.objects.filter(token=token)
        .values_list("pk", "fursuit_id", "fursuit__owner_id")
        .first()
    )
    if row is None:
        raise CatchRequestTargetUnavailableError(Reason.CREDENTIAL_UNKNOWN)
    tag_id, fursuit_id, owner_id = row
    return _Discovery(
        convention_id=enrollment.convention_id,
        tag_id=tag_id,
        fursuit_id=fursuit_id,
        owner_id=owner_id,
    )


def _submit(user: User, found: _Discovery) -> SubmissionResult:
    player_id = user.pk
    with transaction.atomic():
        # Contract lock order. Only the rows that this action needs.
        profiles = {
            profile.user_id: profile
            for profile in PlayerProfile.objects.select_for_update()
            .filter(user_id__in={player_id, found.owner_id})
            .order_by("pk")
        }
        convention = (
            Convention.objects.select_for_update()
            .filter(pk=found.convention_id)
            .first()
        )
        enrollments = {
            enrollment.user_id: enrollment
            for enrollment in ConventionEnrollment.objects.select_for_update()
            .filter(
                user_id__in={player_id, found.owner_id},
                convention_id=found.convention_id,
            )
            .order_by("pk")
        }
        fursuit = (
            Fursuit.objects.select_for_update().filter(pk=found.fursuit_id).first()
        )
        activation = (
            FursuitActivation.objects.select_for_update()
            .filter(
                fursuit_id=found.fursuit_id,
                convention_id=found.convention_id,
                is_active=True,
            )
            .order_by("pk")
            .first()
        )
        tag = FursuitTag.objects.select_for_update().filter(pk=found.tag_id).first()
        session = (
            None
            if activation is None
            else FursuitCatchSession.objects.select_for_update()
            .filter(activation_id=activation.pk, ended_at__isnull=True)
            .order_by("pk")
            .first()
        )
        existing = _existing_result(
            player_id=player_id,
            fursuit_id=found.fursuit_id,
            convention_id=found.convention_id,
            lock=True,
        )
        now = database_now()

        # Checks 1 and 4: the caller and the selected convention.
        catcher_enrollment = enrollments.get(player_id)
        if (
            not _profile_is_eligible(profiles.get(player_id))
            or convention is None
            or catcher_enrollment is None
            or not catcher_enrollment.is_active
        ):
            raise CatchRequestCatcherIneligibleError(Reason.CATCHER_INELIGIBLE)
        # Check 2: a known zone and an open window.
        if not review_window_open(convention, now):
            raise CatchRequestsUnavailableError(Reason.REQUESTS_UNAVAILABLE)
        # Check 9 runs early, so a retry recovers its own result (#505 G2).
        if existing is not None:
            return existing

        # Checks 3 and 5 to 8. The first failing check only picks the reason.
        if fursuit is None or tag is None:
            # Fixture cleanup deleted the suit after discovery.
            raise CatchRequestTargetUnavailableError(Reason.CREDENTIAL_UNKNOWN)
        if not convention.is_playable:
            raise CatchRequestTargetUnavailableError(Reason.CONVENTION_NOT_PLAYABLE)
        if not tag.is_current:
            raise CatchRequestTargetUnavailableError(Reason.CREDENTIAL_REVOKED)
        if (
            not fursuit.is_enabled
            or not _profile_is_eligible(profiles.get(found.owner_id))
            or found.owner_id not in enrollments
        ):
            raise CatchRequestTargetUnavailableError(Reason.TARGET_INELIGIBLE)
        if activation is None:
            raise CatchRequestTargetUnavailableError(Reason.ACTIVATION_INACTIVE)
        if session is None:
            raise CatchRequestTargetUnavailableError(Reason.SESSION_INACTIVE)
        if session.expires_at <= now:
            raise CatchRequestTargetUnavailableError(Reason.SESSION_EXPIRED)
        if found.owner_id == player_id:
            raise CatchRequestSelfCatchError(Reason.SELF_CATCH)
        # Check 10: a block shares the neutral target response.
        trio = {
            "player_id": player_id,
            "fursuit_id": found.fursuit_id,
            "convention_id": found.convention_id,
        }
        if is_blocked(**trio):
            raise CatchRequestTargetUnavailableError(Reason.BLOCKED)
        # Check 11: the trio cooldown and the per-player limit (#506).
        check_submission_allowed(**trio, now=now)

        request = CatchRequest.objects.create(
            player_id=player_id,
            fursuit_id=found.fursuit_id,
            convention_id=found.convention_id,
            activation_id=activation.pk,
            catch_session_id=session.pk,
            state=CatchRequestState.PENDING,
            requested_at=now,
        )
        request.fursuit = fursuit
        request.convention = convention
        if fursuit.catch_approval_mode != CatchApprovalMode.AUTOMATIC.value:
            return SubmissionResult(SubmissionOutcome.PENDING, request, None)
        catch = approve_request_in_transaction(request, approved_at=now)
        catch.fursuit = fursuit
        return SubmissionResult(SubmissionOutcome.APPROVED, request, catch)


def _existing_result(
    *, player_id: int, fursuit_id: int, convention_id: int, lock: bool = False
) -> SubmissionResult | None:
    """Return the trio's catch, else its pending request. A catch wins (G9b)."""
    catches = Catch.objects.filter(
        catcher_user_id=player_id, fursuit_id=fursuit_id, convention_id=convention_id
    ).select_related("fursuit")
    pending = CatchRequest.objects.filter(
        player_id=player_id,
        fursuit_id=fursuit_id,
        convention_id=convention_id,
        state=CatchRequestState.PENDING,
    ).select_related("fursuit", "convention")
    if lock:
        pending = pending.select_for_update(of=("self",))
        catches = catches.select_for_update(of=("self",))
    request = pending.first()
    catch = catches.first()
    if catch is not None:
        return SubmissionResult(SubmissionOutcome.ALREADY_CAUGHT, None, catch)
    if request is not None:
        return SubmissionResult(SubmissionOutcome.ALREADY_PENDING, request, None)
    return None


def _profile_is_eligible(profile: PlayerProfile | None) -> bool:
    return (
        profile is not None
        and profile.is_enabled
        and profile.onboarding_completed_at is not None
        and profile.handle is not None
        and profile.display_name not in (None, "")
    )


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.__cause__, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    return name if isinstance(name, str) else None
