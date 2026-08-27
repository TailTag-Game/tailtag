"""Domain services for convention enrollment and active-convention selection."""

from __future__ import annotations

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from accounts.models import User
from conventions.models import Convention, ConventionEnrollment
from profiles.eligibility import is_participation_eligible
from profiles.models import PlayerProfile


class ConventionParticipationIneligibleError(Exception):
    """The user does not currently meet player participation eligibility requirements."""


class ConventionNotEligibleForEnrollmentError(Exception):
    """The target convention is not in an active playable state for enrollment."""


class ConventionNotEnrolledError(Exception):
    """The player is not enrolled in the requested convention."""


class ConventionNotActiveError(Exception):
    """The enrolled convention is not currently in an active lifecycle state."""


def require_convention_participation_eligible(user: User) -> None:
    """Verify the user has completed onboarding and has an enabled profile."""
    if not is_participation_eligible(user):
        raise ConventionParticipationIneligibleError()


def list_user_enrollments(user: User) -> QuerySet[ConventionEnrollment]:
    """Return all convention enrollments for the given user."""
    return (
        ConventionEnrollment.objects.filter(user=user)
        .select_related("convention")
        .order_by("-created_at", "id")
    )


def get_active_enrollment(user: User) -> ConventionEnrollment | None:
    """Return the user's currently selected active convention enrollment, if any."""
    return (
        ConventionEnrollment.objects.filter(user=user, is_active=True)
        .select_related("convention")
        .first()
    )


def enroll_in_convention(
    user: User, *, convention_id: int, set_active: bool = False
) -> tuple[ConventionEnrollment, bool]:
    """Enroll the player in an active convention idempotently."""
    require_convention_participation_eligible(user)

    with transaction.atomic():
        _locked_eligible_profile(user)
        convention = (
            Convention.objects.select_for_update().filter(pk=convention_id).first()
        )
        if convention is None:
            raise Convention.DoesNotExist()
        if not convention.is_playable:
            raise ConventionNotEligibleForEnrollmentError()

        now = timezone.now()
        if set_active:
            ConventionEnrollment.objects.filter(user=user, is_active=True).update(
                is_active=False, updated_at=now
            )

        enrollment, created = ConventionEnrollment.objects.get_or_create(
            user=user,
            convention=convention,
            defaults={"is_active": set_active},
        )

        if not created and set_active and not enrollment.is_active:
            enrollment.is_active = True
            enrollment.save(update_fields=["is_active", "updated_at"])

        return enrollment, created


def set_active_convention(user: User, *, convention_id: int) -> ConventionEnrollment:
    """Explicitly select an enrolled active convention as the player's active convention."""
    require_convention_participation_eligible(user)

    with transaction.atomic():
        _locked_eligible_profile(user)
        convention = (
            Convention.objects.select_for_update().filter(pk=convention_id).first()
        )
        if convention is None:
            raise ConventionNotEnrolledError()

        enrollment = (
            ConventionEnrollment.objects.select_for_update()
            .filter(user=user, convention=convention)
            .select_related("convention")
            .first()
        )
        if enrollment is None:
            raise ConventionNotEnrolledError()
        if not convention.is_playable:
            raise ConventionNotActiveError()

        if not enrollment.is_active:
            now = timezone.now()
            ConventionEnrollment.objects.filter(user=user, is_active=True).exclude(
                pk=enrollment.pk
            ).update(is_active=False, updated_at=now)
            enrollment.is_active = True
            enrollment.save(update_fields=["is_active", "updated_at"])

        return enrollment


def clear_active_convention(user: User) -> None:
    """Clear the player's active convention selection."""
    require_convention_participation_eligible(user)

    with transaction.atomic():
        _locked_eligible_profile(user)
        now = timezone.now()
        ConventionEnrollment.objects.filter(user=user, is_active=True).update(
            is_active=False, updated_at=now
        )


def _locked_eligible_profile(user: User) -> PlayerProfile:
    """Lock an already-complete enabled profile, ensuring atomic serialization."""
    profile = (
        PlayerProfile.objects.select_for_update()
        .filter(
            user=user,
            onboarding_completed_at__isnull=False,
            handle__isnull=False,
            display_name__isnull=False,
            is_enabled=True,
        )
        .exclude(display_name="")
        .first()
    )
    if profile is None:
        raise ConventionParticipationIneligibleError()
    return profile
