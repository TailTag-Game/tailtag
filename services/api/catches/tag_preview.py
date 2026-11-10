"""Preview-only resolution of a reusable tag at the catcher's selected convention.

Preview reads and never writes. It runs the contract submission checks that
exist today, in contract order. #506 adds the block check. Each rejection
carries a telemetry reason that is never public.
"""

from __future__ import annotations

from dataclasses import dataclass

from accounts.models import User
from conventions.catch_sessions import unended_fursuit_catch_sessions
from conventions.models import Convention, ConventionEnrollment, FursuitActivation
from conventions.review_deadline import database_now, review_window_open
from fursuits.models import Fursuit, FursuitTag
from fursuits.tags import TagPayloadInvalidError, parse_tag_payload
from observability.outcomes import Reason
from profiles.eligibility import eligible_player_profiles, is_participation_eligible


@dataclass(frozen=True)
class TagPreview:
    fursuit: Fursuit
    convention: Convention


class TagPreviewError(Exception):
    """A preview rejection. ``reason`` is for telemetry and never public.

    The reason stays out of ``args``, ``str``, and ``repr`` so no message or log
    line can carry a target-state distinction.
    """

    def __init__(self, reason: Reason) -> None:
        super().__init__()
        self.reason = reason


class TagPreviewCatcherIneligibleError(TagPreviewError):
    """403 ``catcher_ineligible``."""


class TagPreviewUnavailableError(TagPreviewError):
    """409 ``catch_requests_unavailable``."""


class TagPreviewTargetUnavailableError(TagPreviewError):
    """404 ``catch_target_unavailable``."""


class TagPreviewSelfCatchError(TagPreviewError):
    """409 ``self_catch_not_allowed``."""


def preview_tag(user: User, *, payload: str) -> TagPreview:
    """Resolve *payload* for *user* without changing any state."""
    if not is_participation_eligible(user):
        raise TagPreviewCatcherIneligibleError(Reason.CALLER_INELIGIBLE)
    enrollment = (
        ConventionEnrollment.objects.filter(user=user, is_active=True)
        .select_related("convention")
        .first()
    )
    if enrollment is None:
        raise TagPreviewCatcherIneligibleError(Reason.CALLER_INELIGIBLE)
    convention = enrollment.convention

    now = database_now()
    if not review_window_open(convention, now):
        raise TagPreviewUnavailableError(Reason.REQUESTS_UNAVAILABLE)
    if not convention.is_playable:
        raise TagPreviewTargetUnavailableError(Reason.CONVENTION_NOT_PLAYABLE)

    try:
        token = parse_tag_payload(payload)
    except TagPayloadInvalidError:
        raise TagPreviewTargetUnavailableError(Reason.PAYLOAD_INVALID) from None
    tag = FursuitTag.objects.select_related("fursuit").filter(token=token).first()
    if tag is None:
        raise TagPreviewTargetUnavailableError(Reason.CREDENTIAL_UNKNOWN)
    if not tag.is_current:
        raise TagPreviewTargetUnavailableError(Reason.CREDENTIAL_REVOKED)
    fursuit = tag.fursuit
    owner_eligible = (
        eligible_player_profiles().filter(user_id=fursuit.owner_id).exists()
    )
    owner_enrolled = ConventionEnrollment.objects.filter(
        user_id=fursuit.owner_id, convention=convention
    ).exists()
    if not fursuit.is_enabled or not owner_eligible or not owner_enrolled:
        raise TagPreviewTargetUnavailableError(Reason.TARGET_INELIGIBLE)

    activation = FursuitActivation.objects.filter(
        fursuit=fursuit, convention=convention, is_active=True
    ).first()
    if activation is None:
        raise TagPreviewTargetUnavailableError(Reason.ACTIVATION_INACTIVE)
    session = unended_fursuit_catch_sessions(activation_id=activation.pk).first()
    if session is None:
        raise TagPreviewTargetUnavailableError(Reason.SESSION_INACTIVE)
    if session.expires_at <= now:
        raise TagPreviewTargetUnavailableError(Reason.SESSION_EXPIRED)
    if fursuit.owner_id == user.pk:
        raise TagPreviewSelfCatchError(Reason.SELF_CATCH)

    # A tag replaced after the first read must not resolve. Re-check last.
    if not FursuitTag.objects.filter(pk=tag.pk, revoked_at__isnull=True).exists():
        raise TagPreviewTargetUnavailableError(Reason.CREDENTIAL_REVOKED)
    return TagPreview(fursuit=fursuit, convention=convention)
