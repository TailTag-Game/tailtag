"""Transactional lifecycle operations for bounded fursuit catch sessions."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Final

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from conventions.models import (
    Convention,
    ConventionEnrollment,
    FursuitActivation,
    FursuitCatchSession,
    FursuitCatchSessionEndReason,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile

FURSUIT_CATCH_SESSION_LIFETIME: Final = datetime.timedelta(hours=12)


@dataclass(frozen=True)
class FursuitCatchSessionState:
    """The canonical domain result for a desired catchability transition."""

    activation: FursuitActivation
    session: FursuitCatchSession | None
    is_active: bool


def set_fursuit_catch_session_state(
    user: User,
    *,
    convention_id: int,
    fursuit_id: int,
    is_active: bool,
) -> FursuitCatchSessionState:
    """Atomically set an owned activation's desired current catchability."""
    now = timezone.now()
    if is_active:
        return _start_fursuit_catch_session(
            user,
            convention_id=convention_id,
            fursuit_id=fursuit_id,
            now=now,
        )
    return _stop_fursuit_catch_session(
        user,
        convention_id=convention_id,
        fursuit_id=fursuit_id,
        now=now,
    )


def get_effective_fursuit_catch_session(
    user: User, *, convention_id: int, fursuit_id: int
) -> FursuitCatchSession | None:
    """Return a currently catchable session without performing lazy cleanup."""
    # Import locally to keep the services -> catch_sessions integration in Task 4 acyclic.
    from conventions.services import get_operational_fursuit_activation

    activation = get_operational_fursuit_activation(
        user, convention_id=convention_id, fursuit_id=fursuit_id
    )
    if activation is None:
        return None
    return get_effective_fursuit_catch_session_for_activation(activation)


def get_effective_fursuit_catch_session_for_activation(
    activation: FursuitActivation,
) -> FursuitCatchSession | None:
    """Return an activation's effective session without owner-scoped resolution."""
    # Keep this import local so services can continue to depend on this module.
    from conventions.services import is_fursuit_activation_eligible

    if not activation.is_active or not is_fursuit_activation_eligible(activation):
        return None
    return (
        FursuitCatchSession.objects.filter(
            activation=activation,
            ended_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .order_by("-started_at", "-id")
        .first()
    )


def terminate_for_activation_deactivation(
    activation: FursuitActivation, *, now: datetime.datetime
) -> FursuitCatchSession | None:
    """End the active session for a locked activation due to deactivation."""
    session = _locked_unended_session(activation)
    if session is None:
        return None
    _terminate_locked_session(
        session, now=now, live_reason=FursuitCatchSessionEndReason.ELIGIBILITY_LOST
    )
    return session


def terminate_for_locked_activations(
    activations: tuple[FursuitActivation, ...], *, now: datetime.datetime
) -> int:
    """Terminate sessions after callers have locked activations and credentials."""
    return _terminate_sessions_for_activations(activations, now=now)


def terminate_for_profile_disable(
    profile: PlayerProfile, *, now: datetime.datetime
) -> int:
    """End sessions affected by a locked profile becoming disabled."""
    activations = list(
        FursuitActivation.objects.select_for_update(of=("self",))
        .filter(fursuit__owner_id=profile.user_id)
        .order_by("pk")
    )
    return _terminate_sessions_for_activations(activations, now=now)


def terminate_for_fursuit_disable(fursuit: Fursuit, *, now: datetime.datetime) -> int:
    """End sessions affected by a locked fursuit becoming disabled."""
    activations = list(
        FursuitActivation.objects.select_for_update()
        .filter(fursuit=fursuit)
        .order_by("pk")
    )
    return _terminate_sessions_for_activations(activations, now=now)


def terminate_for_enrollment_removal(
    enrollment: ConventionEnrollment, *, now: datetime.datetime
) -> int:
    """End sessions affected by a locked enrollment being removed."""
    activations = list(
        FursuitActivation.objects.select_for_update(of=("self",))
        .filter(
            convention_id=enrollment.convention_id,
            fursuit__owner_id=enrollment.user_id,
        )
        .order_by("pk")
    )
    return _terminate_sessions_for_activations(activations, now=now)


def terminate_for_convention_nonplayable(
    convention: Convention, *, now: datetime.datetime
) -> int:
    """End sessions affected by a locked Convention becoming non-playable."""
    activations = list(
        FursuitActivation.objects.select_for_update()
        .filter(convention=convention)
        .order_by("pk")
    )
    return _terminate_sessions_for_activations(activations, now=now)


def terminate_session_as_operator(session_id: int) -> FursuitCatchSession:
    """Terminally end one session from the restricted operator entry point."""
    now = timezone.now()
    with transaction.atomic():
        candidate = FursuitCatchSession.objects.filter(pk=session_id).first()
        if candidate is None:
            raise FursuitCatchSession.DoesNotExist()
        activation = FursuitActivation.objects.select_for_update().get(
            pk=candidate.activation_id
        )
        session = (
            FursuitCatchSession.objects.select_for_update()
            .filter(pk=candidate.pk)
            .first()
        )
        if session is None:
            raise FursuitCatchSession.DoesNotExist()
        if session.ended_at is None:
            _terminate_locked_session(
                session,
                now=now,
                live_reason=FursuitCatchSessionEndReason.OPERATOR,
            )
        # Keep the activation lock until the transaction commits.
        del activation
        return session


def _start_fursuit_catch_session(
    user: User,
    *,
    convention_id: int,
    fursuit_id: int,
    now: datetime.datetime,
) -> FursuitCatchSessionState:
    """Lock the complete eligibility chain then create or retain a live session."""
    from conventions.services import (
        ConventionNotEnrolledError,
        ConventionParticipationIneligibleError,
        FursuitActivationNotEligibleError,
    )

    with transaction.atomic():
        profile = PlayerProfile.objects.select_for_update().filter(user=user).first()
        if (
            profile is None
            or profile.onboarding_completed_at is None
            or profile.handle is None
            or profile.display_name in (None, "")
            or not profile.is_enabled
        ):
            raise ConventionParticipationIneligibleError()
        convention = (
            Convention.objects.select_for_update().filter(pk=convention_id).first()
        )
        if convention is None:
            raise Convention.DoesNotExist()
        enrollment = (
            ConventionEnrollment.objects.select_for_update()
            .filter(user=user, convention=convention)
            .first()
        )
        if enrollment is None:
            raise ConventionNotEnrolledError()
        fursuit = (
            Fursuit.objects.select_for_update()
            .filter(pk=fursuit_id, owner=user)
            .first()
        )
        if fursuit is None:
            raise Fursuit.DoesNotExist()
        activation = (
            FursuitActivation.objects.select_for_update()
            .filter(fursuit=fursuit, convention=convention)
            .first()
        )
        if activation is None:
            raise FursuitActivation.DoesNotExist()
        if not (activation.is_active and convention.is_playable and fursuit.is_enabled):
            raise FursuitActivationNotEligibleError()
        session = _locked_unended_session(activation)
        if session is not None:
            if session.expires_at > now:
                return FursuitCatchSessionState(
                    activation=activation, session=session, is_active=True
                )
            _terminate_locked_session(
                session,
                now=now,
                live_reason=FursuitCatchSessionEndReason.OWNER,
            )
        session = FursuitCatchSession.objects.create(
            activation=activation,
            started_at=now,
            expires_at=now + FURSUIT_CATCH_SESSION_LIFETIME,
        )
        return FursuitCatchSessionState(
            activation=activation, session=session, is_active=True
        )


def _stop_fursuit_catch_session(
    user: User,
    *,
    convention_id: int,
    fursuit_id: int,
    now: datetime.datetime,
) -> FursuitCatchSessionState:
    """Stop without requiring present operational eligibility."""
    with transaction.atomic():
        fursuit = (
            Fursuit.objects.select_for_update()
            .filter(pk=fursuit_id, owner=user)
            .first()
        )
        if fursuit is None:
            raise Fursuit.DoesNotExist()
        activation = (
            FursuitActivation.objects.select_for_update()
            .filter(fursuit=fursuit, convention_id=convention_id)
            .first()
        )
        if activation is None:
            raise FursuitActivation.DoesNotExist()
        session = _locked_unended_session(activation)
        if session is not None:
            _terminate_locked_session(
                session,
                now=now,
                live_reason=FursuitCatchSessionEndReason.OWNER,
            )
        else:
            session = _latest_session(activation)
        return FursuitCatchSessionState(
            activation=activation, session=session, is_active=False
        )


def _locked_unended_session(
    activation: FursuitActivation,
) -> FursuitCatchSession | None:
    return (
        FursuitCatchSession.objects.select_for_update()
        .filter(activation=activation, ended_at__isnull=True)
        .order_by("pk")
        .first()
    )


def _latest_session(activation: FursuitActivation) -> FursuitCatchSession | None:
    return (
        FursuitCatchSession.objects.filter(activation=activation)
        .order_by("-started_at", "-id")
        .first()
    )


def _terminate_sessions_for_activations(
    activations: tuple[FursuitActivation, ...] | list[FursuitActivation],
    *,
    now: datetime.datetime,
) -> int:
    """Lock sessions after all activations, then apply expiration-first termination."""
    if not activations:
        return 0
    sessions = list(
        FursuitCatchSession.objects.select_for_update()
        .filter(activation__in=activations, ended_at__isnull=True)
        .order_by("pk")
    )
    return sum(
        _terminate_locked_session(
            session,
            now=now,
            live_reason=FursuitCatchSessionEndReason.ELIGIBILITY_LOST,
        )
        for session in sessions
    )


def _terminate_locked_session(
    session: FursuitCatchSession,
    *,
    now: datetime.datetime,
    live_reason: FursuitCatchSessionEndReason,
) -> bool:
    """End a locked unended session, always giving expiry precedence."""
    if session.ended_at is not None:
        return False
    if now >= session.expires_at:
        session.ended_at = session.expires_at
        session.end_reason = FursuitCatchSessionEndReason.EXPIRED
    else:
        session.ended_at = now
        session.end_reason = live_reason
    session.save(update_fields=("ended_at", "end_reason", "updated_at"))
    return True
