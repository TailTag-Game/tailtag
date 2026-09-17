"""Scoped reconciliation of the explicitly registered rehearsal closure."""

from __future__ import annotations

import datetime
from typing import Final, Protocol, cast

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from accounts.models import User
from catches.models import Catch
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
    FursuitCatchCredential,
    FursuitCatchSession,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile

from . import baseline
from .models import StagingResetIdentity
from .safety import (
    ResetConfiguration,
    ResetSafetyError,
    assert_quiescent,
    validate_asset,
    validate_database,
    validate_identity,
)

_COUNTS: Final = {
    "profiles": 2,
    "conventions": 1,
    "fursuits": 2,
    "enrollments": 2,
    "activations": 2,
    "catches": 0,
    "sessions": 0,
    "credentials": 0,
}


class _UserPrivileges(Protocol):
    is_superuser: bool


def provision_identity(configuration: ResetConfiguration) -> None:
    """Register the separately provisioned reusable pool without creating roots."""
    validate_database(configuration)
    validate_asset(configuration.media_key)
    with transaction.atomic():
        if StagingResetIdentity.objects.exists():
            raise ResetSafetyError
        try:
            owner = User.objects.get(clerk_user_id=configuration.owner_clerk_id)
            catcher = User.objects.get(clerk_user_id=configuration.catcher_clerk_id)
        except User.DoesNotExist:
            raise ResetSafetyError from None
        if (
            owner.pk == catcher.pk
            or owner.is_staff
            or cast(_UserPrivileges, owner).is_superuser
            or catcher.is_staff
            or cast(_UserPrivileges, catcher).is_superuser
        ):
            raise ResetSafetyError
        identity = StagingResetIdentity.objects.create(
            id=1,
            environment_id=configuration.environment_id,
            cluster_identifier=configuration.cluster_identifier,
            database_name=configuration.database_name,
            owner=owner,
            catcher=catcher,
            media_key=configuration.media_key,
        )
        # Use the same real transport proof as reset; no Clerk or media mutation occurs.
        validate_identity(configuration)
        del identity


def _roots(identity: StagingResetIdentity) -> tuple[Convention, Fursuit, Fursuit]:
    values = (identity.convention, identity.first_fursuit, identity.second_fursuit)
    if all(value is None for value in values):
        if (
            Convention.objects.filter(name=baseline.CONVENTION_NAME).exists()
            or Fursuit.objects.filter(
                tailtag_id__in=(
                    baseline.FIRST_FURSUIT_TAILTAG_ID,
                    baseline.SECOND_FURSUIT_TAILTAG_ID,
                )
            ).exists()
        ):
            raise ResetSafetyError
        convention = Convention.objects.create(
            name=baseline.CONVENTION_NAME,
            status=ConventionStatus.ACTIVE,
            start_date=datetime.date(2026, 9, 1),
            end_date=datetime.date(2036, 9, 1),
        )
        first = Fursuit.objects.create(
            owner=identity.owner,
            name="Rehearsal Panther",
            tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
            photo_key=identity.media_key,
            is_enabled=True,
        )
        second = Fursuit.objects.create(
            owner=identity.owner,
            name="Rehearsal Fox",
            tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
            photo_key=identity.media_key,
            is_enabled=True,
        )
        identity.convention, identity.first_fursuit, identity.second_fursuit = (
            convention,
            first,
            second,
        )
        identity.save(update_fields=["convention", "first_fursuit", "second_fursuit"])
        return convention, first, second
    if any(value is None for value in values):
        raise ResetSafetyError
    if identity.first_fursuit_id == identity.second_fursuit_id:
        raise ResetSafetyError
    return values  # type: ignore[return-value]


def _assert_closure(
    identity: StagingResetIdentity,
    convention: Convention,
    fursuits: tuple[Fursuit, Fursuit],
) -> None:
    ids = (fursuits[0].pk, fursuits[1].pk)
    if any(fursuit.owner_id != identity.owner_id for fursuit in fursuits):
        raise ResetSafetyError
    if (fursuits[0].tailtag_id, fursuits[1].tailtag_id) != (
        baseline.FIRST_FURSUIT_TAILTAG_ID,
        baseline.SECOND_FURSUIT_TAILTAG_ID,
    ):
        raise ResetSafetyError
    if (
        ConventionEnrollment.objects.filter(
            Q(user__in=(identity.owner, identity.catcher)) | Q(convention=convention)
        )
        .exclude(user__in=(identity.owner, identity.catcher), convention=convention)
        .exists()
    ):
        raise ResetSafetyError
    activations = FursuitActivation.objects.filter(
        Q(fursuit_id__in=ids) | Q(convention=convention)
    )
    if activations.exclude(fursuit_id__in=ids, convention=convention).exists():
        raise ResetSafetyError
    activation_ids = tuple(activations.values_list("pk", flat=True))
    sessions = FursuitCatchSession.objects.filter(activation_id__in=activation_ids)
    session_ids = tuple(sessions.values_list("pk", flat=True))
    catches = Catch.objects.filter(
        Q(fursuit_id__in=ids)
        | Q(convention=convention)
        | Q(activation_id__in=activation_ids)
        | Q(catch_session_id__in=session_ids)
    )
    if catches.exclude(
        catcher_user__in=(identity.owner, identity.catcher),
        fursuit_id__in=ids,
        convention=convention,
        activation_id__in=activation_ids,
        catch_session_id__in=session_ids,
    ).exists():
        raise ResetSafetyError
    if catches.exclude(
        activation__fursuit_id=F("fursuit_id"),
        activation__convention_id=F("convention_id"),
        catch_session__activation_id=F("activation_id"),
    ).exists():
        raise ResetSafetyError


def _profiles(identity: StagingResetIdentity) -> None:
    wanted = (
        (identity.owner, "tt_rehearsal_owner", "TailTag Rehearsal Owner"),
        (identity.catcher, "tt_rehearsal_catcher", "TailTag Rehearsal Catcher"),
    )
    for _, handle, _ in wanted:
        if (
            PlayerProfile.objects.exclude(user__in=(identity.owner, identity.catcher))
            .filter(handle=handle)
            .exists()
        ):
            raise ResetSafetyError
    PlayerProfile.objects.filter(user__in=(identity.owner, identity.catcher)).update(
        handle=None, display_name=None, onboarding_completed_at=None
    )
    for user, handle, display_name in wanted:
        PlayerProfile.objects.update_or_create(
            user=user,
            defaults={
                "handle": handle,
                "display_name": display_name,
                "avatar_key": identity.media_key,
                "onboarding_completed_at": timezone.now(),
                "is_enabled": True,
            },
        )


def validate_baseline(identity: StagingResetIdentity) -> dict[str, int]:
    """Check the semantic final state immediately before the atomic commit."""
    if (
        identity.convention_id is None
        or identity.first_fursuit_id is None
        or identity.second_fursuit_id is None
    ):
        raise ResetSafetyError
    profiles = list(
        PlayerProfile.objects.filter(
            user__in=(identity.owner, identity.catcher)
        ).values_list(
            "user_id",
            "handle",
            "display_name",
            "avatar_key",
            "is_enabled",
            "onboarding_completed_at",
        )
    )
    expected_profiles = {
        (identity.owner_id, "tt_rehearsal_owner", "TailTag Rehearsal Owner"),
        (identity.catcher_id, "tt_rehearsal_catcher", "TailTag Rehearsal Catcher"),
    }
    if (
        len(profiles) != 2
        or {(row[0], row[1], row[2]) for row in profiles} != expected_profiles
        or any(
            row[3] != identity.media_key or not row[4] or row[5] is None
            for row in profiles
        )
    ):
        raise ResetSafetyError
    convention = Convention.objects.get(pk=identity.convention_id)
    fursuits = Fursuit.objects.in_bulk(
        (identity.first_fursuit_id, identity.second_fursuit_id)
    )
    first = fursuits.get(identity.first_fursuit_id)
    second = fursuits.get(identity.second_fursuit_id)
    if first is None or second is None:
        raise ResetSafetyError
    _assert_closure(identity, convention, (first, second))
    if (
        convention.name,
        convention.status,
        convention.start_date,
        convention.end_date,
    ) != (
        baseline.CONVENTION_NAME,
        ConventionStatus.ACTIVE,
        datetime.date(2026, 9, 1),
        datetime.date(2036, 9, 1),
    ):
        raise ResetSafetyError
    fursuits = list(
        Fursuit.objects.filter(
            pk__in=(identity.first_fursuit_id, identity.second_fursuit_id)
        ).values_list("tailtag_id", "name", "owner_id", "photo_key", "is_enabled")
    )
    if set(fursuits) != {
        (
            baseline.FIRST_FURSUIT_TAILTAG_ID,
            "Rehearsal Panther",
            identity.owner_id,
            identity.media_key,
            True,
        ),
        (
            baseline.SECOND_FURSUIT_TAILTAG_ID,
            "Rehearsal Fox",
            identity.owner_id,
            identity.media_key,
            True,
        ),
    }:
        raise ResetSafetyError
    enrollments = ConventionEnrollment.objects.filter(
        convention_id=identity.convention_id,
        user__in=(identity.owner, identity.catcher),
    )
    if enrollments.count() != 2 or not all(
        enrollment.is_active for enrollment in enrollments
    ):
        raise ResetSafetyError
    activations = FursuitActivation.objects.filter(
        convention_id=identity.convention_id,
        fursuit_id__in=(identity.first_fursuit_id, identity.second_fursuit_id),
    )
    if activations.count() != 2 or any(
        not activation.is_active or activation.deactivated_at is not None
        for activation in activations
    ):
        raise ResetSafetyError
    if (
        Catch.objects.filter(
            fursuit_id__in=(identity.first_fursuit_id, identity.second_fursuit_id)
        ).exists()
        or FursuitCatchSession.objects.filter(
            activation__fursuit_id__in=(
                identity.first_fursuit_id,
                identity.second_fursuit_id,
            )
        ).exists()
        or FursuitCatchCredential.objects.filter(
            activation__fursuit_id__in=(
                identity.first_fursuit_id,
                identity.second_fursuit_id,
            )
        ).exists()
    ):
        raise ResetSafetyError
    return dict(_COUNTS)


def reset_baseline(configuration: ResetConfiguration) -> dict[str, int]:
    """Atomically reset only the pre-registered closure after maintenance gating."""
    identity = validate_identity(configuration)
    assert_quiescent(configuration)
    with transaction.atomic():
        assert_quiescent(configuration)
        identity = StagingResetIdentity.objects.select_for_update().get(pk=identity.pk)
        identity = StagingResetIdentity.objects.select_related(
            "owner", "catcher", "convention", "first_fursuit", "second_fursuit"
        ).get(pk=identity.pk)
        validate_identity(configuration)
        if (
            identity.environment_id,
            identity.cluster_identifier,
            identity.database_name,
            identity.owner.clerk_user_id,
            identity.catcher.clerk_user_id,
            identity.media_key,
        ) != (
            configuration.environment_id,
            configuration.cluster_identifier,
            configuration.database_name,
            configuration.owner_clerk_id,
            configuration.catcher_clerk_id,
            configuration.media_key,
        ):
            raise ResetSafetyError
        convention, first, second = _roots(identity)
        _assert_closure(identity, convention, (first, second))
        activation_ids = tuple(
            FursuitActivation.objects.filter(
                fursuit__in=(first, second), convention=convention
            ).values_list("pk", flat=True)
        )
        session_ids = tuple(
            FursuitCatchSession.objects.filter(
                activation_id__in=activation_ids
            ).values_list("pk", flat=True)
        )
        Catch.objects.filter(catch_session_id__in=session_ids).delete()
        FursuitCatchCredential.objects.filter(activation_id__in=activation_ids).delete()
        FursuitCatchSession.objects.filter(pk__in=session_ids).delete()
        FursuitActivation.objects.filter(pk__in=activation_ids).delete()
        ConventionEnrollment.objects.filter(
            convention=convention, user__in=(identity.owner, identity.catcher)
        ).delete()
        _profiles(identity)
        Convention.objects.filter(pk=convention.pk).update(
            name=baseline.CONVENTION_NAME,
            status=ConventionStatus.ACTIVE,
            start_date=datetime.date(2026, 9, 1),
            end_date=datetime.date(2036, 9, 1),
        )
        Fursuit.objects.filter(pk=first.pk).update(
            owner=identity.owner,
            name="Rehearsal Panther",
            tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
            photo_key=identity.media_key,
            is_enabled=True,
        )
        Fursuit.objects.filter(pk=second.pk).update(
            owner=identity.owner,
            name="Rehearsal Fox",
            tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
            photo_key=identity.media_key,
            is_enabled=True,
        )
        ConventionEnrollment.objects.bulk_create(
            [
                ConventionEnrollment(
                    user=identity.owner, convention=convention, is_active=True
                ),
                ConventionEnrollment(
                    user=identity.catcher, convention=convention, is_active=True
                ),
            ]
        )
        now = timezone.now()
        FursuitActivation.objects.bulk_create(
            [
                FursuitActivation(
                    fursuit=first,
                    convention=convention,
                    is_active=True,
                    activated_at=now,
                ),
                FursuitActivation(
                    fursuit=second,
                    convention=convention,
                    is_active=True,
                    activated_at=now,
                ),
            ]
        )
        identity.refresh_from_db()
        return validate_baseline(identity)
