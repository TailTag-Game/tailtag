"""Owner and operator lifecycle for reusable fursuit tags.

Lock order follows the reusable tag contract: PlayerProfile, then Fursuit, then
the tag row. ``Fursuit.tag_version`` lives on the locked fursuit row, so that
lock serializes every tag write for one suit.
"""

# pyright: reportUnusedFunction=false

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from fursuits.models import Fursuit, FursuitTag, FursuitTagRevocationReason
from fursuits.tag_protocol import TAG_PAYLOAD_PREFIX, TAG_TOKEN_BYTES, TAG_TOKEN_PATTERN
from operator_audit.services import OperatorTransition
from profiles.eligibility import is_participation_eligible
from profiles.models import PlayerProfile

_TOKEN_PATTERN: Final = re.compile(rf"^{TAG_TOKEN_PATTERN}$", re.ASCII)
_TOKEN_UNIQUE_CONSTRAINT: Final = "fursuits_tag_token_unique"


class TagState(StrEnum):
    """The public tag states. ``NONE`` appears only in a version conflict body."""

    CURRENT = "current"
    REVOKED = "revoked"
    NONE = "none"


@dataclass(frozen=True)
class TagView:
    """The owner's projection of a suit's tag. ``token`` is set only when current."""

    fursuit_id: int
    state: TagState
    tag_version: int
    token: str | None

    @property
    def payload(self) -> str | None:
        return None if self.token is None else format_tag_payload(self.token)


class TagOwnerIneligibleError(Exception):
    """The caller has no enabled, completed player profile."""


class TagFursuitDisabledError(Exception):
    """The owned suit is disabled."""


class TagVersionConflictError(Exception):
    """The owner sent a stale version. ``current`` never carries a token."""

    def __init__(self, current: TagView) -> None:
        super().__init__()
        self.current = current


class TagPayloadInvalidError(Exception):
    """The value does not use the exact printed tag format."""


def format_tag_payload(token: str) -> str:
    """Wrap a stored token in the exact printed format."""
    if _TOKEN_PATTERN.fullmatch(token) is None:
        raise TagPayloadInvalidError()
    return f"{TAG_PAYLOAD_PREFIX}{token}"


def parse_tag_payload(payload: str) -> str:
    """Return the token only when *payload* uses the exact printed format."""
    if not payload.isascii() or not payload.startswith(TAG_PAYLOAD_PREFIX):
        raise TagPayloadInvalidError()
    token = payload.removeprefix(TAG_PAYLOAD_PREFIX)
    if _TOKEN_PATTERN.fullmatch(token) is None:
        raise TagPayloadInvalidError()
    return token


def get_or_create_owner_tag(user: User, *, fursuit_id: int) -> TagView:
    """Return the suit's tag state. Create the first tag only if none ever existed."""
    with transaction.atomic():
        fursuit = _lock_owner_fursuit(user, fursuit_id=fursuit_id)
        current = _locked_current_tag(fursuit)
        if current is not None:
            return _current_view(fursuit, current)
        if fursuit.tag_version > 0:
            return _view_without_current(fursuit)
        return _current_view(fursuit, _create_next_tag(fursuit))


def replace_owner_tag(user: User, *, fursuit_id: int, expected_version: int) -> TagView:
    """End the current tag, if any, and create a new one when the version matches."""
    with transaction.atomic():
        fursuit = _lock_owner_fursuit(user, fursuit_id=fursuit_id)
        current = _locked_current_tag(fursuit)
        if expected_version != fursuit.tag_version:
            view = (
                _current_view(fursuit, current)
                if current is not None
                else _view_without_current(fursuit)
            )
            raise TagVersionConflictError(_without_token(view))
        if current is not None:
            _revoke_locked_tag(
                current, reason=FursuitTagRevocationReason.OWNER_REPLACEMENT
            )
        return _current_view(fursuit, _create_next_tag(fursuit))


def revoke_tag_as_operator(tag_id: int) -> OperatorTransition[FursuitTag]:
    """Revoke one selected current tag without creating a replacement.

    The preliminary read keeps the lock order stable. The final check under the
    locks stops a stale admin form from changing history.
    """
    candidate = FursuitTag.objects.filter(pk=tag_id).values("pk", "fursuit_id").first()
    if candidate is None:
        raise FursuitTag.DoesNotExist()

    with transaction.atomic():
        fursuit = Fursuit.objects.select_for_update().get(pk=candidate["fursuit_id"])
        tag = (
            FursuitTag.objects.select_for_update()
            .filter(pk=candidate["pk"], fursuit=fursuit)
            .first()
        )
        if tag is None:
            raise FursuitTag.DoesNotExist()
        if not tag.is_current:
            return OperatorTransition(value=tag, changed=False)
        _revoke_locked_tag(tag, reason=FursuitTagRevocationReason.OPERATOR)
        _bump_version(fursuit)
        return OperatorTransition(value=tag, changed=True)


def _lock_owner_fursuit(user: User, *, fursuit_id: int) -> Fursuit:
    """Lock and check the owner chain in the contract lock order."""
    if not Fursuit.objects.filter(pk=fursuit_id, owner=user).exists():
        raise Fursuit.DoesNotExist()
    profile = PlayerProfile.objects.select_for_update().filter(user=user).first()
    if profile is None or not is_participation_eligible(user):
        raise TagOwnerIneligibleError()
    fursuit = (
        Fursuit.objects.select_for_update().filter(pk=fursuit_id, owner=user).first()
    )
    if fursuit is None:
        raise Fursuit.DoesNotExist()
    if not fursuit.is_enabled:
        raise TagFursuitDisabledError()
    return fursuit


def _locked_current_tag(fursuit: Fursuit) -> FursuitTag | None:
    return (
        FursuitTag.objects.select_for_update()
        .filter(fursuit=fursuit, revoked_at__isnull=True)
        .first()
    )


def _create_next_tag(fursuit: Fursuit) -> FursuitTag:
    """Raise the locked fursuit's version and create its new current tag.

    A generated-token collision gets exactly one retry. Any other integrity
    failure propagates, because the fursuit lock rules out a competing writer.
    """
    version = _bump_version(fursuit)
    for attempt in range(2):
        try:
            with transaction.atomic():
                return FursuitTag.objects.create(
                    fursuit=fursuit,
                    token=secrets.token_urlsafe(TAG_TOKEN_BYTES),
                    created_version=version,
                )
        except IntegrityError as error:
            if _constraint_name(error) == _TOKEN_UNIQUE_CONSTRAINT and attempt == 0:
                continue
            raise
    raise AssertionError("unreachable")


def _bump_version(fursuit: Fursuit) -> int:
    fursuit.tag_version += 1
    fursuit.save(update_fields=["tag_version", "updated_at"])
    return fursuit.tag_version


def _revoke_locked_tag(tag: FursuitTag, *, reason: FursuitTagRevocationReason) -> None:
    now = timezone.now()
    tag.revoked_at = now
    tag.revocation_reason = reason
    tag.updated_at = now
    tag.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])


def _current_view(fursuit: Fursuit, tag: FursuitTag) -> TagView:
    return TagView(
        fursuit_id=fursuit.pk,
        state=TagState.CURRENT,
        tag_version=fursuit.tag_version,
        token=tag.token,
    )


def _view_without_current(fursuit: Fursuit) -> TagView:
    state = TagState.REVOKED if fursuit.tag_version > 0 else TagState.NONE
    return TagView(
        fursuit_id=fursuit.pk, state=state, tag_version=fursuit.tag_version, token=None
    )


def _without_token(view: TagView) -> TagView:
    return TagView(
        fursuit_id=view.fursuit_id,
        state=view.state,
        tag_version=view.tag_version,
        token=None,
    )


def _constraint_name(error: IntegrityError) -> str | None:
    """Read psycopg structured diagnostic metadata without inspecting error text."""
    diagnostic = getattr(error.__cause__, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return constraint_name if isinstance(constraint_name, str) else None
