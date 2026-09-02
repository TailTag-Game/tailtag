"""Persistence and protocol primitives for Convention catch credentials."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

import datetime
import re
import secrets
from typing import Final

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from conventions.models import (
    Convention,
    ConventionEnrollment,
    FursuitActivation,
    FursuitCatchCredential,
    FursuitCatchCredentialRevocationReason,
)
from fursuits.models import Fursuit
from profiles.eligibility import is_participation_eligible
from profiles.models import PlayerProfile

from .catch_sessions import get_effective_fursuit_catch_session_for_activation
from .services import (
    ConventionParticipationIneligibleError,
    FursuitActivationNotEligibleError,
    is_fursuit_activation_eligible,
)

CATCH_CREDENTIAL_TOKEN_BYTES: Final = 32
CATCH_CREDENTIAL_TOKEN_LENGTH: Final = 43
CATCH_CREDENTIAL_PAYLOAD_PREFIX: Final = "tailtag:catch:v1:"
_TOKEN_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{43}$", re.ASCII)

_TOKEN_UNIQUE_CONSTRAINT: Final = "conventions_catch_credential_token_unique"
_ONE_CURRENT_CONSTRAINT: Final = (
    "conventions_catch_credential_one_current_per_activation"
)


class CatchCredentialPayloadInvalidError(Exception):
    """The submitted payload does not use the exact supported protocol grammar."""


class CatchCredentialNotFoundError(Exception):
    """A credential cannot currently resolve to a safe catchable preview."""


def format_catch_credential_payload(token: str) -> str:
    """Wrap a persisted opaque token in the exact V1 application envelope."""
    return f"{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{_valid_catch_credential_token(token)}"


def parse_catch_credential_payload(payload: str) -> str:
    """Return the raw token only when *payload* uses the exact V1 grammar."""
    if not payload.isascii() or not payload.startswith(CATCH_CREDENTIAL_PAYLOAD_PREFIX):
        raise CatchCredentialPayloadInvalidError()
    token = payload.removeprefix(CATCH_CREDENTIAL_PAYLOAD_PREFIX)
    return _valid_catch_credential_token(token)


def resolve_catch_credential(
    *, convention_id: int, payload: str
) -> FursuitCatchCredential:
    """Resolve a current credential to its catchable activation without locking.

    This is intentionally a preview-only read.  The final current-row query
    closes the meaningful revocation/rotation race without adding reservations.
    """
    token = parse_catch_credential_payload(payload)
    credential = (
        FursuitCatchCredential.objects.filter(
            token=token,
            activation__convention_id=convention_id,
            revoked_at__isnull=True,
        )
        .select_related(
            "activation__fursuit",
            "activation__fursuit__owner",
            "activation__convention",
        )
        .first()
    )
    if credential is None:
        raise CatchCredentialNotFoundError()

    activation = credential.activation
    if (
        not activation.is_active
        or not is_fursuit_activation_eligible(activation)
        or get_effective_fursuit_catch_session_for_activation(activation) is None
    ):
        raise CatchCredentialNotFoundError()

    if not FursuitCatchCredential.objects.filter(
        pk=credential.pk,
        activation_id=credential.activation_id,
        token=token,
        revoked_at__isnull=True,
    ).exists():
        raise CatchCredentialNotFoundError()
    return credential


def _valid_catch_credential_token(token: str) -> str:
    """Return a token only when it uses the exact persisted-token grammar."""
    if _TOKEN_PATTERN.fullmatch(token) is None:
        raise CatchCredentialPayloadInvalidError()
    return token


def _create_current_catch_credential(
    activation: FursuitActivation,
) -> FursuitCatchCredential:
    """Create a current row, recovering only known uniqueness races.

    Callers normally hold the activation lock.  The named one-current constraint
    remains the final database defense; a winner is returned if it was created
    concurrently.  A generated-token collision receives exactly one retry.
    """
    with transaction.atomic():
        for attempt in range(2):
            try:
                with transaction.atomic():
                    return FursuitCatchCredential.objects.create(
                        activation=activation,
                        token=secrets.token_urlsafe(CATCH_CREDENTIAL_TOKEN_BYTES),
                    )
            except IntegrityError as error:
                if _is_one_current_constraint_violation(error):
                    winner = _locked_current_catch_credential(activation)
                    if winner is not None:
                        return winner
                    raise
                if _is_token_unique_constraint_violation(error) and attempt == 0:
                    continue
                raise
    raise AssertionError("unreachable")


def _revoke_current_catch_credential(
    activation: FursuitActivation,
    *,
    now: datetime.datetime,
    reason: FursuitCatchCredentialRevocationReason,
) -> FursuitCatchCredential | None:
    """Terminally revoke a locked activation's current row without rewriting history."""
    credential = _locked_current_catch_credential(activation)
    if credential is None:
        return None
    _terminally_revoke_locked_credential(credential, now=now, reason=reason)
    return credential


def _terminally_revoke_locked_credential(
    credential: FursuitCatchCredential,
    *,
    now: datetime.datetime,
    reason: FursuitCatchCredentialRevocationReason,
) -> None:
    """Apply the sole allowed terminal mutation to an already-locked current row."""
    credential.revoked_at = now
    credential.revocation_reason = reason
    credential.updated_at = now
    credential.save(update_fields={"revoked_at", "revocation_reason", "updated_at"})


def _locked_current_catch_credential(
    activation: FursuitActivation,
) -> FursuitCatchCredential | None:
    """Return and lock the current credential for an already-locked activation."""
    return (
        FursuitCatchCredential.objects.select_for_update()
        .filter(activation=activation, revoked_at__isnull=True)
        .order_by("pk")
        .first()
    )


def revoke_for_activation_deactivation(
    activation: FursuitActivation, *, now: datetime.datetime
) -> FursuitActivation:
    """Revoke a locked activation's current credential for eligibility loss."""
    _revoke_current_catch_credential(
        activation,
        now=now,
        reason=FursuitCatchCredentialRevocationReason.ELIGIBILITY_LOST,
    )
    return activation


def revoke_for_profile_disable(
    profile: PlayerProfile, *, now: datetime.datetime
) -> tuple[FursuitActivation, ...]:
    """Lock a profile's activations, then revoke their current credentials."""
    activations = _locked_activations_for_profile(profile)
    _revoke_current_credentials_for_locked_activations(activations, now=now)
    return activations


def revoke_for_fursuit_disable(
    fursuit: Fursuit, *, now: datetime.datetime
) -> tuple[FursuitActivation, ...]:
    """Lock a fursuit's activations, then revoke their current credentials."""
    activations = tuple(
        FursuitActivation.objects.select_for_update()
        .filter(fursuit=fursuit)
        .order_by("pk")
    )
    _revoke_current_credentials_for_locked_activations(activations, now=now)
    return activations


def revoke_for_enrollment_removal(
    enrollment: ConventionEnrollment, *, now: datetime.datetime
) -> tuple[FursuitActivation, ...]:
    """Lock an enrollment's activations, then revoke their current credentials."""
    activations = tuple(
        FursuitActivation.objects.select_for_update(of=("self",))
        .filter(
            convention_id=enrollment.convention_id,
            fursuit__owner_id=enrollment.user_id,
        )
        .order_by("pk")
    )
    _revoke_current_credentials_for_locked_activations(activations, now=now)
    return activations


def revoke_for_convention_nonplayable(
    convention: Convention, *, now: datetime.datetime
) -> tuple[FursuitActivation, ...]:
    """Lock a Convention's activations, then revoke their current credentials."""
    activations = tuple(
        FursuitActivation.objects.select_for_update()
        .filter(convention=convention)
        .order_by("pk")
    )
    _revoke_current_credentials_for_locked_activations(activations, now=now)
    return activations


def _locked_activations_for_profile(
    profile: PlayerProfile,
) -> tuple[FursuitActivation, ...]:
    """Lock only activation rows after the already-locked profile."""
    return tuple(
        FursuitActivation.objects.select_for_update(of=("self",))
        .filter(fursuit__owner_id=profile.user_id)
        .order_by("pk")
    )


def _revoke_current_credentials_for_locked_activations(
    activations: tuple[FursuitActivation, ...], *, now: datetime.datetime
) -> None:
    """Lock current credentials after activations and apply one terminal mutation."""
    if not activations:
        return
    credentials = (
        FursuitCatchCredential.objects.select_for_update()
        .filter(
            activation__in=activations,
            revoked_at__isnull=True,
        )
        .order_by("pk")
    )
    for credential in credentials:
        _terminally_revoke_locked_credential(
            credential,
            now=now,
            reason=FursuitCatchCredentialRevocationReason.ELIGIBILITY_LOST,
        )


def _is_token_unique_constraint_violation(error: IntegrityError) -> bool:
    """Recognize only the named global-token uniqueness failure from psycopg."""
    return _constraint_name(error) == _TOKEN_UNIQUE_CONSTRAINT


def _is_one_current_constraint_violation(error: IntegrityError) -> bool:
    """Recognize only the named one-current-per-activation failure from psycopg."""
    return _constraint_name(error) == _ONE_CURRENT_CONSTRAINT


def _constraint_name(error: IntegrityError) -> str | None:
    """Read psycopg structured diagnostic metadata without inspecting error text."""
    diagnostic = getattr(error.__cause__, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return constraint_name if isinstance(constraint_name, str) else None


def get_or_create_owner_catch_credential(
    user: User, *, convention_id: int, fursuit_id: int
) -> str:
    """Return the owner's current credential, creating it lazily when absent."""
    with transaction.atomic():
        activation = _lock_owner_operational_activation(
            user, convention_id=convention_id, fursuit_id=fursuit_id
        )
        credential = _locked_current_catch_credential(activation)
        if credential is None:
            credential = _create_current_catch_credential(activation)
        return format_catch_credential_payload(credential.token)


def rotate_owner_catch_credential(
    user: User, *, convention_id: int, fursuit_id: int
) -> str:
    """Revoke the current credential and return a newly created replacement."""
    with transaction.atomic():
        now = timezone.now()
        activation = _lock_owner_operational_activation(
            user, convention_id=convention_id, fursuit_id=fursuit_id
        )
        _revoke_current_catch_credential(
            activation,
            now=now,
            reason=FursuitCatchCredentialRevocationReason.OWNER_ROTATION,
        )
        replacement = _create_current_catch_credential(activation)
        return format_catch_credential_payload(replacement.token)


def _lock_owner_operational_activation(
    user: User, *, convention_id: int, fursuit_id: int
) -> FursuitActivation:
    """Lock and revalidate the owner eligibility chain in the global lock order."""
    profile = PlayerProfile.objects.select_for_update().filter(user=user).first()
    if profile is None or not is_participation_eligible(user):
        raise ConventionParticipationIneligibleError()

    convention = Convention.objects.select_for_update().filter(pk=convention_id).first()
    if convention is None:
        raise Convention.DoesNotExist()
    enrollment = (
        ConventionEnrollment.objects.select_for_update()
        .filter(user=user, convention=convention)
        .first()
    )
    fursuit = (
        Fursuit.objects.select_for_update().filter(pk=fursuit_id, owner=user).first()
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
    if (
        enrollment is None
        or not activation.is_active
        or not convention.is_playable
        or not fursuit.is_enabled
    ):
        raise FursuitActivationNotEligibleError()
    return activation
