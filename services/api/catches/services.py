"""Authoritative validation and durable creation for Catch records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from catches.models import Catch
from conventions.catch_credentials import parse_catch_credential_payload
from conventions.models import (
    Convention,
    ConventionEnrollment,
    FursuitActivation,
    FursuitCatchCredential,
    FursuitCatchSession,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile

_CATCH_UNIQUE_CONSTRAINT = "catches_catcher_fursuit_convention_unique"


class CatchConfirmationStatus(StrEnum):
    CREATED = "created"
    ALREADY_CAUGHT = "already_caught"


@dataclass(frozen=True)
class CatchConfirmationResult:
    catch: Catch
    status: CatchConfirmationStatus


class CatchAuthenticationError(Exception):
    pass


class CatchParticipationIneligibleError(Exception):
    pass


class CatchActiveConventionMismatchError(Exception):
    pass


class CatchTargetInvalidError(Exception):
    pass


class CatchSelfCatchError(Exception):
    pass


def confirm_catch(user: User, *, payload: str) -> CatchConfirmationResult:
    """Create one Catch from an opaque credential, or recover its durable row."""
    catcher_id = _require_persisted_user(user)
    token = parse_catch_credential_payload(payload)
    historical = _discover_historical_credential(token)
    if historical is None:
        raise CatchTargetInvalidError()

    credential_id, activation_id, fursuit_id, convention_id, target_owner_id = (
        historical
    )
    _after_historical_credential_discovery()

    existing = _find_existing_catch(
        catcher_user_id=catcher_id,
        fursuit_id=fursuit_id,
        convention_id=convention_id,
    )
    if existing is not None:
        return CatchConfirmationResult(existing, CatchConfirmationStatus.ALREADY_CAUGHT)

    with transaction.atomic():
        profile_ids = sorted({catcher_id, target_owner_id})
        profiles: dict[int, PlayerProfile] = {}
        first_profile_locked = False
        for profile_id in profile_ids:
            profile = (
                PlayerProfile.objects.select_for_update()
                .filter(pk=profile_id)
                .order_by("pk")
                .first()
            )
            if profile is None:
                continue
            if not first_profile_locked:
                _after_first_profile_lock(profile.pk)
                first_profile_locked = True
            profiles[profile.user_id] = profile

        convention = (
            Convention.objects.select_for_update().filter(pk=convention_id).first()
        )
        enrollment_rows = list(
            ConventionEnrollment.objects.select_for_update()
            .filter(user_id__in=profile_ids, convention_id=convention_id)
            .order_by("pk")
        )
        enrollments = {enrollment.user_id: enrollment for enrollment in enrollment_rows}
        fursuit = Fursuit.objects.select_for_update().filter(pk=fursuit_id).first()
        activation = (
            FursuitActivation.objects.select_for_update()
            .filter(pk=activation_id)
            .first()
        )
        credential = (
            FursuitCatchCredential.objects.select_for_update()
            .filter(pk=credential_id)
            .first()
        )
        session = (
            FursuitCatchSession.objects.select_for_update()
            .filter(activation_id=activation_id, ended_at__isnull=True)
            .order_by("pk")
            .first()
        )

        existing = _find_existing_catch(
            catcher_user_id=catcher_id,
            fursuit_id=fursuit_id,
            convention_id=convention_id,
        )
        if existing is not None:
            return CatchConfirmationResult(
                existing, CatchConfirmationStatus.ALREADY_CAUGHT
            )

        now = timezone.now()
        catcher_profile = profiles.get(catcher_id)
        catcher_enrollment = enrollments.get(catcher_id)
        if not _profile_is_eligible(catcher_profile) or catcher_enrollment is None:
            raise CatchParticipationIneligibleError()
        if not catcher_enrollment.is_active:
            raise CatchActiveConventionMismatchError()

        target_profile = profiles.get(target_owner_id)
        target_enrollment = enrollments.get(target_owner_id)
        if (
            not _profile_is_eligible(target_profile)
            or target_enrollment is None
            or convention is None
            or not convention.is_playable
            or fursuit is None
            or not fursuit.is_enabled
            or fursuit.owner_id != target_owner_id
            or activation is None
            or activation.fursuit_id != fursuit_id
            or activation.convention_id != convention_id
            or not activation.is_active
            or credential is None
            or credential.activation_id != activation_id
            or credential.token != token
            or credential.revoked_at is not None
            or session is None
            or session.activation_id != activation_id
            or session.ended_at is not None
            or session.expires_at <= now
        ):
            raise CatchTargetInvalidError()
        if fursuit.owner_id == catcher_id:
            raise CatchSelfCatchError()

        try:
            with transaction.atomic():
                catch = _insert_catch(
                    catcher_user_id=catcher_id,
                    fursuit_id=fursuit_id,
                    convention_id=convention_id,
                    activation_id=activation_id,
                    catch_session_id=session.pk,
                )
        except IntegrityError as error:
            if _constraint_name(error) != _CATCH_UNIQUE_CONSTRAINT:
                raise
            winner = _find_existing_catch(
                catcher_user_id=catcher_id,
                fursuit_id=fursuit_id,
                convention_id=convention_id,
            )
            if winner is None:
                raise
            return CatchConfirmationResult(
                winner, CatchConfirmationStatus.ALREADY_CAUGHT
            )

        return CatchConfirmationResult(catch, CatchConfirmationStatus.CREATED)


def _require_persisted_user(user: User) -> int:
    if not isinstance(user, User):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise CatchAuthenticationError()
    user_id = getattr(user, "pk", None)
    if not isinstance(user_id, int) or not user.is_authenticated:
        raise CatchAuthenticationError()
    if not User.objects.filter(pk=user_id).exists():
        raise CatchAuthenticationError()
    return user_id


def _discover_historical_credential(
    token: str,
) -> tuple[int, int, int, int, int] | None:
    row = (
        FursuitCatchCredential.objects.filter(token=token)
        .values_list(
            "pk",
            "activation_id",
            "activation__fursuit_id",
            "activation__convention_id",
            "activation__fursuit__owner_id",
        )
        .first()
    )
    return cast(tuple[int, int, int, int, int] | None, row)


def _profile_is_eligible(profile: PlayerProfile | None) -> bool:
    return (
        profile is not None
        and profile.is_enabled
        and profile.onboarding_completed_at is not None
        and profile.handle is not None
        and profile.display_name not in (None, "")
    )


def _find_existing_catch(
    *, catcher_user_id: int, fursuit_id: int, convention_id: int
) -> Catch | None:
    return Catch.objects.filter(
        catcher_user_id=catcher_user_id,
        fursuit_id=fursuit_id,
        convention_id=convention_id,
    ).first()


def _insert_catch(
    *,
    catcher_user_id: int,
    fursuit_id: int,
    convention_id: int,
    activation_id: int,
    catch_session_id: int,
) -> Catch:
    return Catch.objects.create(
        catcher_user_id=catcher_user_id,
        fursuit_id=fursuit_id,
        convention_id=convention_id,
        activation_id=activation_id,
        catch_session_id=catch_session_id,
    )


def _constraint_name(error: IntegrityError) -> str | None:
    cause = error.__cause__
    diagnostic = getattr(cause, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    return name if isinstance(name, str) else None


def _after_historical_credential_discovery() -> None:
    """Reserved acceptance-test seam after non-authoritative discovery."""


def _after_first_profile_lock(profile_id: int) -> None:
    """Reserved acceptance-test seam after the first ordered profile lock."""
