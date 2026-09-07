"""Domain services for convention enrollment and active-convention selection."""

from __future__ import annotations

import datetime

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from accounts.models import User
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit
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


class FursuitActivationNotEligibleError(Exception):
    """The requested fursuit activation is blocked by current upstream state."""


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


def list_owned_fursuit_activations(
    user: User, *, convention: Convention
) -> QuerySet[FursuitActivation]:
    """Return the user's durable fursuit selections for a convention."""
    return (
        FursuitActivation.objects.filter(fursuit__owner=user, convention=convention)
        .select_related("fursuit", "convention")
        .order_by("fursuit_id", "id")
    )


def is_fursuit_activation_eligible(activation: FursuitActivation) -> bool:
    """Return whether all current upstream activation prerequisites hold."""
    return (
        is_participation_eligible(activation.fursuit.owner)
        and ConventionEnrollment.objects.filter(
            user_id=activation.fursuit.owner_id,
            convention_id=activation.convention_id,
        ).exists()
        and activation.convention.is_playable
        and activation.fursuit.is_enabled
    )


def get_operational_fursuit_activation(
    user: User, *, convention_id: int, fursuit_id: int
) -> FursuitActivation | None:
    """Resolve an owned fursuit's active, currently eligible participation."""
    activation = (
        FursuitActivation.objects.filter(
            fursuit_id=fursuit_id,
            convention_id=convention_id,
            fursuit__owner=user,
        )
        .select_related("fursuit", "convention", "fursuit__owner")
        .first()
    )
    if activation is None or not activation.is_active:
        return None
    return activation if is_fursuit_activation_eligible(activation) else None


def set_fursuit_activation_state(
    user: User,
    *,
    convention_id: int,
    fursuit_id: int,
    is_active: bool,
) -> FursuitActivation:
    """Atomically set a durable fursuit participation selection."""
    if is_active:
        return _activate_fursuit(
            user, convention_id=convention_id, fursuit_id=fursuit_id
        )
    return _deactivate_fursuit(user, convention_id=convention_id, fursuit_id=fursuit_id)


def _activate_fursuit(
    user: User, *, convention_id: int, fursuit_id: int
) -> FursuitActivation:
    with transaction.atomic():
        _locked_eligible_profile(user)
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
        if not convention.is_playable or not fursuit.is_enabled:
            raise FursuitActivationNotEligibleError()
        if activation is not None and activation.is_active:
            return activation
        now = timezone.now()
        if activation is None:
            try:
                with transaction.atomic():
                    return FursuitActivation.objects.create(
                        fursuit=fursuit,
                        convention=convention,
                        is_active=True,
                        activated_at=now,
                    )
            except IntegrityError as error:
                if not _is_fursuit_activation_unique_violation(error):
                    raise
                activation = (
                    FursuitActivation.objects.select_for_update()
                    .filter(fursuit=fursuit, convention=convention)
                    .first()
                )
                if activation is None:
                    raise
        activation.is_active = True
        activation.activated_at = now
        activation.deactivated_at = None
        activation.save(
            update_fields=["is_active", "activated_at", "deactivated_at", "updated_at"]
        )
        return activation


def _deactivate_fursuit(
    user: User, *, convention_id: int, fursuit_id: int
) -> FursuitActivation:
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
        if not activation.is_active:
            return activation
        now = timezone.now()
        from conventions.catch_credentials import revoke_for_activation_deactivation
        from conventions.catch_sessions import terminate_for_activation_deactivation

        revoke_for_activation_deactivation(activation, now=now)
        terminate_for_activation_deactivation(activation, now=now)
        activation.is_active = False
        activation.deactivated_at = now
        activation.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        return activation


def deactivate_fursuit_activation_as_operator(
    *, activation_id: int
) -> FursuitActivation:
    """Deactivate one durable activation through the operator lifecycle seam."""
    with transaction.atomic():
        candidate = FursuitActivation.objects.filter(pk=activation_id).first()
        if candidate is None:
            raise FursuitActivation.DoesNotExist()
        fursuit = Fursuit.objects.select_for_update().get(pk=candidate.fursuit_id)
        activation = FursuitActivation.objects.select_for_update().get(pk=candidate.pk)
        if not activation.is_active:
            return activation
        now = timezone.now()
        from conventions.catch_credentials import revoke_for_activation_deactivation
        from conventions.catch_sessions import terminate_for_activation_deactivation

        revoke_for_activation_deactivation(activation, now=now)
        terminate_for_activation_deactivation(activation, now=now)
        activation.is_active = False
        activation.deactivated_at = now
        activation.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        # Keep the fursuit lock until the state transition commits.
        del fursuit
        return activation


def remove_convention_enrollment(*, enrollment_id: int) -> None:
    """Delete an enrollment and terminally end its affected catch sessions."""
    candidate = (
        ConventionEnrollment.objects.filter(pk=enrollment_id)
        .values("user_id", "convention_id")
        .first()
    )
    if candidate is None:
        return
    with transaction.atomic():
        # Profile is optional for legacy/incomplete users but, when present, is first.
        profile = (
            PlayerProfile.objects.select_for_update()
            .filter(user_id=candidate["user_id"])
            .first()
        )
        convention = Convention.objects.select_for_update().get(
            pk=candidate["convention_id"]
        )
        enrollment = (
            ConventionEnrollment.objects.select_for_update()
            .filter(
                pk=enrollment_id, user_id=candidate["user_id"], convention=convention
            )
            .first()
        )
        if enrollment is None:
            return
        now = timezone.now()
        from conventions.catch_credentials import revoke_for_enrollment_removal
        from conventions.catch_sessions import terminate_for_locked_activations

        activations = revoke_for_enrollment_removal(enrollment, now=now)
        terminate_for_locked_activations(activations, now=now)
        enrollment.delete()
        # Keep optional upstream locks until commit.
        del profile


def set_convention_admin_state(
    *,
    convention_id: int,
    name: str,
    status: str,
    start_date: datetime.date,
    end_date: datetime.date,
) -> Convention:
    """Persist an admin Convention edit and end sessions on loss of playability."""
    with transaction.atomic():
        convention = Convention.objects.select_for_update().get(pk=convention_id)
        became_nonplayable = (
            convention.is_playable and status != ConventionStatus.ACTIVE.value
        )
        now = timezone.now()
        if became_nonplayable:
            from conventions.catch_credentials import revoke_for_convention_nonplayable
            from conventions.catch_sessions import terminate_for_locked_activations

            activations = revoke_for_convention_nonplayable(convention, now=now)
            terminate_for_locked_activations(activations, now=now)
        convention.name = name
        convention.status = status
        convention.start_date = start_date
        convention.end_date = end_date
        convention.save(
            update_fields=["name", "status", "start_date", "end_date", "updated_at"]
        )
        return convention


def _is_fursuit_activation_unique_violation(error: IntegrityError) -> bool:
    """Return whether an integrity error is the activation identity constraint."""
    cause = error.__cause__
    diagnostic = getattr(cause, "diag", None)
    return (
        getattr(diagnostic, "constraint_name", None)
        == "conventions_activation_fursuit_convention_unique"
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
