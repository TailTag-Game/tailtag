"""Acceptance contract for the sole authoritative Catch confirmation service."""

from __future__ import annotations

import datetime
import inspect
from dataclasses import is_dataclass
from typing import Any, cast
from unittest.mock import patch

import pytest
from catches.services import (
    CatchActiveConventionMismatchError,
    CatchAuthenticationError,
    CatchConfirmationResult,
    CatchConfirmationStatus,
    CatchParticipationIneligibleError,
    CatchSelfCatchError,
    CatchTargetInvalidError,
    confirm_catch,
)
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import User
from catches import services as catch_services
from conventions.catch_credential_protocol import CATCH_CREDENTIAL_PAYLOAD_PREFIX
from conventions.catch_credentials import CatchCredentialPayloadInvalidError
from conventions.models import Convention, ConventionEnrollment, ConventionStatus
from tests.authentication_support import create_test_user
from tests.catch_credential_test_support import (
    TOKEN_A,
    TOKEN_B,
    create_credential,
    revoke_current_for,
)
from tests.catch_test_support import (
    catch_model,
    create_catch,
    create_catch_confirmation_scenario,
    create_catch_scenario,
)
from tests.fursuit_catch_session_test_support import catch_session_model


def _catch_count() -> int:
    return catch_model().objects.count()


def _assert_no_catch() -> None:
    assert _catch_count() == 0


def _assert_concealed(error: CatchTargetInvalidError, scenario: Any) -> None:
    """Reject accidental target, credential, and lifecycle disclosure."""
    rendered = f"{error!s} {error!r}"
    for secret in (
        scenario.payload,
        scenario.credential.token,
        scenario.target_user.clerk_user_id,
        str(scenario.target_user.pk),
        "revoked",
        "disabled",
        "session",
    ):
        assert secret not in rendered


@pytest.mark.django_db
def test_confirm_catch_creates_the_exact_server_owned_catch() -> None:
    """AC-01/11/12: reject a service that returns a preview or caller-owned record."""
    scenario = create_catch_confirmation_scenario()

    result = confirm_catch(scenario.catcher_user, payload=scenario.payload)

    assert result == CatchConfirmationResult(
        catch=result.catch,
        status=CatchConfirmationStatus.CREATED,
    )
    assert result.status.value == "created"
    assert result.catch.catcher_user_id == scenario.catcher_user.pk
    assert result.catch.fursuit_id == scenario.fursuit.pk
    assert result.catch.convention_id == scenario.convention.pk
    assert result.catch.activation_id == scenario.activation.pk
    assert result.catch.catch_session_id == scenario.catch_session.pk
    assert result.catch.caught_at is not None
    assert _catch_count() == 1


def test_confirm_catch_exposes_only_the_frozen_public_call_shape_and_results() -> None:
    """AC-01/11: reject client-supplied identity parameters or mutable result shapes."""
    signature = inspect.signature(confirm_catch)
    assert list(signature.parameters) == ["user", "payload"]
    assert signature.parameters["user"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert signature.parameters["payload"].kind is inspect.Parameter.KEYWORD_ONLY
    assert is_dataclass(CatchConfirmationResult)
    assert CatchConfirmationResult.__dataclass_params__.frozen is True
    assert set(CatchConfirmationStatus) == {
        CatchConfirmationStatus.CREATED,
        CatchConfirmationStatus.ALREADY_CAUGHT,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("caller_kind", ["anonymous", "unsaved", "deleted", "foreign"])
def test_confirm_catch_rejects_nonconcrete_callers_before_credential_discovery(
    caller_kind: str,
) -> None:
    """AC-02: reject authentication shortcuts that resolve a credential first."""
    scenario = create_catch_confirmation_scenario()
    if caller_kind == "anonymous":
        caller: object = AnonymousUser()
    elif caller_kind == "unsaved":
        caller = User(clerk_user_id="unsaved_catch_confirmation_user")
    elif caller_kind == "deleted":
        caller = create_test_user(clerk_user_id="deleted_catch_confirmation_user")
        caller.delete()
    else:
        caller = cast(Any, object())

    with pytest.raises(CatchAuthenticationError):
        confirm_catch(cast(User, caller), payload=scenario.payload)
    _assert_no_catch()


@pytest.mark.django_db
def test_confirm_catch_distinguishes_a_real_user_without_profile_from_authentication() -> None:
    """AC-02/06: reject treating an existing TailTag user as an auth failure."""
    scenario = create_catch_confirmation_scenario()
    profileless = create_test_user(clerk_user_id="profileless_catch_confirmation_user")

    with pytest.raises(CatchParticipationIneligibleError):
        confirm_catch(profileless, payload=scenario.payload)
    _assert_no_catch()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        TOKEN_A,
        f" {CATCH_CREDENTIAL_PAYLOAD_PREFIX}{TOKEN_A}",
        f"tailtag:catch:v0:{TOKEN_A}",
        f"{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{TOKEN_A[:-1]}",
        f"{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{TOKEN_A}=",
        f"{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{TOKEN_A[:-1]}é",
        f"{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{TOKEN_A[:-1]}!",
    ],
)
def test_confirm_catch_rejects_each_malformed_credential_payload_before_writes(
    payload: str,
) -> None:
    """AC-03: reject permissive payload normalization or token parsing."""
    scenario = create_catch_confirmation_scenario()

    with pytest.raises(CatchCredentialPayloadInvalidError):
        confirm_catch(scenario.catcher_user, payload=payload)
    _assert_no_catch()


@pytest.mark.django_db
def test_confirm_catch_conceals_a_well_formed_unknown_token() -> None:
    """AC-03/07: reject credential enumeration through target error details."""
    scenario = create_catch_confirmation_scenario()
    unknown = f"{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{TOKEN_B}"

    with pytest.raises(CatchTargetInvalidError) as captured:
        confirm_catch(scenario.catcher_user, payload=unknown)
    _assert_concealed(captured.value, scenario)
    assert TOKEN_B not in f"{captured.value!s} {captured.value!r}"
    _assert_no_catch()


@pytest.mark.django_db
def test_confirm_catch_requires_a_completed_catcher_profile() -> None:
    """AC-06: reject partial or pre-lock-only catcher eligibility checks."""
    scenario = create_catch_confirmation_scenario()
    # The profile model constrains onboarding fields to change as a unit.
    scenario.catcher_profile.__class__.objects.filter(pk=scenario.catcher_profile.pk).update(
        handle=None, display_name=None, onboarding_completed_at=None
    )

    with pytest.raises(CatchParticipationIneligibleError):
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    _assert_no_catch()


@pytest.mark.django_db
def test_confirm_catch_rejects_a_disabled_catcher_profile() -> None:
    """AC-06: reject creation by an operator-disabled catcher."""
    scenario = create_catch_confirmation_scenario()
    scenario.catcher_profile.is_enabled = False
    scenario.catcher_profile.save(update_fields=["is_enabled"])

    with pytest.raises(CatchParticipationIneligibleError):
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    _assert_no_catch()


@pytest.mark.django_db
def test_confirm_catch_rejects_a_catcher_without_target_convention_enrollment() -> None:
    """AC-06: reject a catcher who is eligible but not enrolled in the target convention."""
    scenario = create_catch_confirmation_scenario()
    scenario.catcher_enrollment.delete()

    with pytest.raises(CatchParticipationIneligibleError):
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    _assert_no_catch()


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["inactive", "other_active"])
def test_confirm_catch_requires_the_target_convention_to_be_catcher_active(
    state: str,
) -> None:
    """AC-06: reject use of a merely enrolled or differently active convention."""
    scenario = create_catch_confirmation_scenario()
    if state == "inactive":
        ConventionEnrollment.objects.filter(pk=scenario.catcher_enrollment.pk).update(
            is_active=False
        )
    else:
        other = Convention.objects.create(
            name="Catch Confirmation Other Convention",
            status=ConventionStatus.ACTIVE,
            start_date=datetime.date(2026, 8, 1),
            end_date=datetime.date(2026, 8, 3),
        )
        ConventionEnrollment.objects.filter(pk=scenario.catcher_enrollment.pk).update(
            is_active=False
        )
        ConventionEnrollment.objects.create(
            user=scenario.catcher_user, convention=other, is_active=True
        )

    with pytest.raises(CatchActiveConventionMismatchError):
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    _assert_no_catch()


def _invalidate_target(scenario: Any, state: str) -> None:
    if state == "revoked_credential":
        revoke_current_for(scenario.activation)
    elif state == "revoked_with_replacement":
        revoke_current_for(scenario.activation)
        create_credential(activation=scenario.activation, token=TOKEN_B)
    elif state == "target_profile_incomplete":
        scenario.target_profile.__class__.objects.filter(pk=scenario.target_profile.pk).update(
            handle=None, display_name=None, onboarding_completed_at=None
        )
    elif state == "target_profile_disabled":
        scenario.target_profile.is_enabled = False
        scenario.target_profile.save(update_fields=["is_enabled"])
    elif state == "target_enrollment_missing":
        scenario.target_enrollment.delete()
    elif state == "fursuit_disabled":
        scenario.fursuit.is_enabled = False
        scenario.fursuit.save(update_fields=["is_enabled"])
    elif state == "convention_nonplayable":
        scenario.convention.status = ConventionStatus.PAUSED
        scenario.convention.save(update_fields=["status", "updated_at"])
    elif state == "activation_inactive":
        scenario.activation.is_active = False
        scenario.activation.deactivated_at = timezone.now()
        scenario.activation.save(update_fields=["is_active", "deactivated_at", "updated_at"])
    elif state == "session_missing":
        scenario.catch_session.delete()
    elif state == "session_stopped":
        scenario.catch_session.ended_at = timezone.now()
        scenario.catch_session.end_reason = "owner"
        scenario.catch_session.save(update_fields=["ended_at", "end_reason", "updated_at"])
    elif state == "session_expired":
        scenario.catch_session.expires_at = timezone.now() - datetime.timedelta(seconds=1)
        scenario.catch_session.save(update_fields=["expires_at", "updated_at"])
    else:
        raise AssertionError(f"unknown target state: {state}")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "state",
    [
        "revoked_credential",
        "revoked_with_replacement",
        "target_profile_incomplete",
        "target_profile_disabled",
        "target_enrollment_missing",
        "fursuit_disabled",
        "convention_nonplayable",
        "activation_inactive",
        "session_missing",
        "session_stopped",
        "session_expired",
    ],
)
def test_confirm_catch_conceals_each_current_target_ineligibility(state: str) -> None:
    """AC-07/10: reject every stale target state without leaking why it failed."""
    scenario = create_catch_confirmation_scenario(
        catcher_clerk_user_id=f"target_state_catcher_{state}",
        target_owner_clerk_user_id=f"target_state_target_{state}",
    )
    _invalidate_target(scenario, state)
    before_session = catch_session_model().objects.filter(
        pk=scenario.catch_session.pk
    ).values("ended_at", "end_reason", "updated_at").first()

    with pytest.raises(CatchTargetInvalidError) as captured:
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    _assert_concealed(captured.value, scenario)
    _assert_no_catch()
    if state == "session_expired":
        after_session = catch_session_model().objects.filter(
            pk=scenario.catch_session.pk
        ).values("ended_at", "end_reason", "updated_at").first()
        assert after_session == before_session
        assert after_session is not None
        assert after_session["ended_at"] is None
        assert after_session["end_reason"] is None


@pytest.mark.django_db
def test_confirm_catch_rejects_an_otherwise_valid_self_catch_without_writing() -> None:
    """AC-08: reject omitted or client-derived self-catch validation."""
    scenario = create_catch_confirmation_scenario(self_catch=True)

    with pytest.raises(CatchSelfCatchError):
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    _assert_no_catch()


@pytest.mark.django_db
def test_confirm_catch_reraises_an_unrelated_insert_integrity_error_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-14: reject treating every IntegrityError as duplicate success."""
    scenario = create_catch_confirmation_scenario()
    original = IntegrityError("unrelated database failure")

    def fail_insert(**_: object) -> object:
        raise original

    monkeypatch.setattr(catch_services, "_insert_catch", fail_insert)
    with pytest.raises(IntegrityError) as captured:
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    assert captured.value is original
    _assert_no_catch()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "staleness",
    [
        "credential_rotation",
        "credential_revocation",
        "session_stop",
        "session_expiration",
        "activation_deactivation",
        "target_profile_disablement",
        "target_enrollment_removal",
        "fursuit_disablement",
        "convention_nonplayable",
    ],
)
def test_confirm_catch_recovers_an_unchanged_durable_catch_after_target_staleness(
    staleness: str,
) -> None:
    """AC-04/13: reject revalidation or provenance rewrites before duplicate recovery."""
    scenario = create_catch_confirmation_scenario(
        catcher_clerk_user_id=f"recovery_catcher_{staleness}",
        target_owner_clerk_user_id=f"recovery_target_{staleness}",
    )
    first = confirm_catch(scenario.catcher_user, payload=scenario.payload)
    original_row = catch_model().objects.values().get(pk=first.catch.pk)
    state = {
        "credential_rotation": "revoked_with_replacement",
        "credential_revocation": "revoked_credential",
        "session_stop": "session_stopped",
        "session_expiration": "session_expired",
        "activation_deactivation": "activation_inactive",
        "target_profile_disablement": "target_profile_disabled",
        "target_enrollment_removal": "target_enrollment_missing",
        "fursuit_disablement": "fursuit_disabled",
        "convention_nonplayable": "convention_nonplayable",
    }[staleness]
    _invalidate_target(scenario, state)

    repeated = confirm_catch(scenario.catcher_user, payload=scenario.payload)

    assert repeated.status is CatchConfirmationStatus.ALREADY_CAUGHT
    assert repeated.catch.pk == first.catch.pk
    assert catch_model().objects.values().get(pk=first.catch.pk) == original_row


@pytest.mark.django_db
def test_confirm_catch_never_recovers_another_callers_or_another_activation_catch() -> None:
    """AC-05: reject unbound historical recovery by token alone."""
    scenario = create_catch_confirmation_scenario()
    other_catcher = create_test_user(clerk_user_id="other_catch_recovery_catcher")
    create_catch(scenario=create_catch_scenario(catcher_clerk_user_id="unrelated"))
    catch_model().objects.create(
        catcher_user=other_catcher,
        fursuit=scenario.fursuit,
        convention=scenario.convention,
        activation=scenario.activation,
        catch_session=scenario.catch_session,
    )
    revoke_current_for(scenario.activation)

    with pytest.raises(CatchTargetInvalidError):
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    assert _catch_count() == 2


@pytest.mark.django_db
def test_confirm_catch_rejects_a_credential_rebound_after_historical_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-07/09: reject trusting discovery data after the locked re-read begins."""
    scenario = create_catch_confirmation_scenario()
    other = create_catch_confirmation_scenario(
        catcher_clerk_user_id="rebound_other_catcher",
        target_owner_clerk_user_id="rebound_other_target",
        token=TOKEN_B,
    )

    def rebind_credential() -> None:
        scenario.credential.__class__.objects.filter(pk=scenario.credential.pk).update(
            activation_id=other.activation.pk
        )

    monkeypatch.setattr(
        catch_services, "_after_historical_credential_discovery", rebind_credential
    )
    with pytest.raises(CatchTargetInvalidError):
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    _assert_no_catch()


@pytest.mark.django_db
def test_confirm_catch_captures_time_only_after_its_authoritative_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-09/10: reject sampling time before a lock wait or trusting stale rows."""
    scenario = create_catch_confirmation_scenario()
    captured_now = timezone.now()
    scenario.catch_session.expires_at = captured_now
    scenario.catch_session.save(update_fields=["expires_at", "updated_at"])
    entered: list[bool] = []

    def after_locks() -> None:
        entered.append(True)

    monkeypatch.setattr(catch_services, "_after_authoritative_locks", after_locks)
    with (
        patch("catches.services.timezone.now", return_value=captured_now) as now,
        pytest.raises(CatchTargetInvalidError),
    ):
        confirm_catch(scenario.catcher_user, payload=scenario.payload)
    assert entered == [True]
    assert now.call_count == 1
    _assert_no_catch()


@pytest.mark.django_db
def test_confirm_catch_accepts_a_session_strictly_after_serialized_now_with_exact_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-10/12: reject <= boundary mistakes or substituting activation/session rows."""
    scenario = create_catch_confirmation_scenario()
    captured_now = timezone.now()
    scenario.catch_session.expires_at = captured_now + datetime.timedelta(microseconds=1)
    scenario.catch_session.save(update_fields=["expires_at", "updated_at"])

    with patch("catches.services.timezone.now", return_value=captured_now):
        result = confirm_catch(scenario.catcher_user, payload=scenario.payload)

    assert result.status is CatchConfirmationStatus.CREATED
    assert result.catch.caught_at >= captured_now
    assert result.catch.activation_id == scenario.activation.pk
    assert result.catch.catch_session_id == scenario.catch_session.pk
