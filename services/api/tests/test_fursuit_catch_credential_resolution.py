"""Privacy-safe credential resolution acceptance contract."""

from __future__ import annotations

from typing import Any, cast

import pytest
from django.apps import apps
from django.test import Client, override_settings
from django.utils import timezone

from conventions.models import Convention, ConventionEnrollment, FursuitActivation
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import TEST_CLERK_CONFIGURATION
from tests.catch_credential_test_support import (
    AUTHENTICATION_DETAIL,
    FORBIDDEN_DETAIL,
    PAYLOAD_A,
    TOKEN_A,
    assert_not_found,
    assert_resolution_data,
    catch_credential_model,
    create_credential,
    create_credential_scenario,
    resolution_path,
)
from tests.fursuit_activation_test_support import (
    ActivationScenario,
    create_activation_row,
)
from tests.fursuit_catch_session_test_support import create_catch_session

INVALID_PAYLOAD = {"payload": ["Invalid catch credential payload."]}


def _preview_state_snapshot(
    *,
    target: ActivationScenario,
    caller: ActivationScenario,
    activation: FursuitActivation,
) -> dict[str, object]:
    """Capture every currently existing state surface that preview must not mutate."""
    credential_model = catch_credential_model()
    target_fursuit = target.fursuit
    target_profile = target.profile
    target_convention = target.convention
    return {
        "credential_history": list(credential_model.objects.order_by("pk").values()),
        "activation": list(type(activation).objects.filter(pk=activation.pk).values()),
        "sessions": list(cast(Any, activation).catch_sessions.order_by("pk").values()),
        "fursuit": list(
            type(target_fursuit).objects.filter(pk=target_fursuit.pk).values()
        ),
        "profile": list(
            type(target_profile).objects.filter(pk=target_profile.pk).values()
        ),
        "enrollments": list(
            ConventionEnrollment.objects.filter(
                user_id__in=(target.user.pk, caller.user.pk),
                convention=target_convention,
            )
            .order_by("pk")
            .values()
        ),
        "convention": list(
            type(target_convention).objects.filter(pk=target_convention.pk).values()
        ),
        "existing_catch_artifacts": {
            model._meta.label: list(model.objects.order_by("pk").values())
            for model in apps.get_models()
            if any(
                marker in model.__name__.lower()
                for marker in ("catch", "reservation", "authorization")
            )
        },
    }


@pytest.mark.django_db
def test_resolution_accepts_only_closed_exact_payload_and_authorized_nonowner_caller() -> (
    None
):
    """AC-04/10: rejects normalization/open bodies and incorrect owner-scoped target checks."""
    target = create_credential_scenario(clerk_user_id="credential_target")
    activation = create_activation_row(
        fursuit=target.fursuit, convention=target.convention, active=True
    )
    create_catch_session(activation=activation)
    create_credential(activation=activation, token=TOKEN_A)
    caller = create_credential_scenario(clerk_user_id="credential_resolver")
    # The resolver's own enrollment in the target convention, not ownership, authorizes use.
    ConventionEnrollment.objects.create(user=caller.user, convention=target.convention)
    path = resolution_path(target.convention.pk)
    before = _preview_state_snapshot(
        target=target, caller=caller, activation=activation
    )
    for body in cast(
        tuple[object, ...],
        (
            {},
            {"payload": PAYLOAD_A, "extra": 1},
            {"payload": TOKEN_A},
            {"payload": None},
            {"payload": 1},
            {"payload": PAYLOAD_A + " "},
            {"payload": " " + PAYLOAD_A},
            {"payload": "tailtag:catch:v2:" + TOKEN_A},
            {"payload": "tailtag:catch:v1:" + "A" * 42},
            {"payload": "tailtag:catch:v1:" + "A" * 44},
            {"payload": "tailtag:catch:v1:" + "A" * 42 + "="},
            {"payload": "tailtag:catch:v1:" + "A" * 42 + "!"},
            {"payload": "tailtag:catch:v1:" + "A" * 42 + "é"},
            [],
            "bad",
        ),
    ):
        response = caller.client.post(path, body, content_type="application/json")
        assert response.status_code == 400
        assert response.json() == INVALID_PAYLOAD
        assert PAYLOAD_A not in response.content.decode()
    response = caller.client.post(
        path, {"payload": PAYLOAD_A}, content_type="application/json"
    )
    assert response.status_code == 200
    assert_resolution_data(
        response.json(),
        convention_id=target.convention.pk,
        tailtag_id=str(target.fursuit.tailtag_id),
        name=target.fursuit.name,
        photo_url="http://testserver/media/" + target.fursuit.photo_key,
    )
    assert (
        _preview_state_snapshot(target=target, caller=caller, activation=activation)
        == before
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "failure",
    (
        "wrong_convention",
        "random",
        "revoked",
        "revoked_with_successor",
        "inactive_activation",
        "target_profile",
        "target_fursuit",
        "target_enrollment",
        "paused_convention",
        "missing_session",
        "stopped_session",
        "expired_session",
    ),
)
def test_resolution_target_failures_are_one_generic_non_echoing_404(
    failure: str,
) -> None:
    """AC-11/12: rejects target-state disclosure or resolving a non-catchable target."""
    target = create_credential_scenario(clerk_user_id="credential_target_failure")
    activation = create_activation_row(
        fursuit=target.fursuit, convention=target.convention, active=True
    )
    session = create_catch_session(activation=activation)
    credential = create_credential(activation=activation, token=TOKEN_A)
    caller = create_credential_scenario(clerk_user_id="credential_failure_resolver")
    ConventionEnrollment.objects.create(user=caller.user, convention=target.convention)
    path = resolution_path(target.convention.pk)
    payload = PAYLOAD_A
    if failure == "wrong_convention":
        other = Convention.objects.create(
            name="Other",
            status="active",
            start_date=target.convention.start_date,
            end_date=target.convention.end_date,
        )
        ConventionEnrollment.objects.create(user=caller.user, convention=other)
        path = resolution_path(other.pk)
    elif failure == "random":
        payload = "tailtag:catch:v1:" + "Z" * 43
    elif failure in {"revoked", "revoked_with_successor"}:
        credential.revoked_at = credential.updated_at
        credential.revocation_reason = "operator"
        credential.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])
        if failure == "revoked_with_successor":
            create_credential(activation=activation, token="B" * 43)
    elif failure == "inactive_activation":
        activation.is_active = False
        activation.deactivated_at = timezone.now()
        activation.save(update_fields=["is_active", "deactivated_at", "updated_at"])
    elif failure == "target_profile":
        PlayerProfile.objects.filter(pk=target.profile.pk).update(is_enabled=False)
    elif failure == "target_fursuit":
        Fursuit.objects.filter(pk=target.fursuit.pk).update(is_enabled=False)
    elif failure == "target_enrollment":
        assert target.enrollment is not None
        target.enrollment.delete()
    elif failure == "paused_convention":
        Convention.objects.filter(pk=target.convention.pk).update(status="paused")
    elif failure == "missing_session":
        cast(Any, activation).catch_sessions.all().delete()
    elif failure == "stopped_session":
        session.ended_at = timezone.now()
        session.end_reason = "owner"
        session.save(update_fields=["ended_at", "end_reason", "updated_at"])
    else:
        session.expires_at = timezone.now()
        session.save(update_fields=["expires_at", "updated_at"])
    assert_not_found(
        caller.client.post(path, {"payload": payload}, content_type="application/json"),
        payload,
    )


@pytest.mark.django_db
def test_resolution_rechecks_current_credential_after_target_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-11/13: rejects a resolver that returns a preview after rotation/revocation wins."""
    target = create_credential_scenario(clerk_user_id="credential_final_check_target")
    activation = create_activation_row(
        fursuit=target.fursuit, convention=target.convention, active=True
    )
    create_catch_session(activation=activation)
    credential = create_credential(activation=activation, token=TOKEN_A)
    caller = create_credential_scenario(clerk_user_id="credential_final_check_caller")
    ConventionEnrollment.objects.create(user=caller.user, convention=target.convention)
    # This is the approved activation-oriented target-eligibility collaborator.
    # It leaves the credential current for lookup, then makes it terminal before
    # the resolver's required final-current check.
    from conventions import catch_credentials

    original_eligible = catch_credentials.is_fursuit_activation_eligible

    def revoke_after_target_check(checked_activation: FursuitActivation) -> bool:
        assert checked_activation == activation
        credential.revoked_at = timezone.now()
        credential.revocation_reason = "operator"
        credential.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])
        return original_eligible(checked_activation)

    monkeypatch.setattr(
        catch_credentials, "is_fursuit_activation_eligible", revoke_after_target_check
    )
    assert_not_found(
        caller.client.post(
            resolution_path(target.convention.pk),
            {"payload": PAYLOAD_A},
            content_type="application/json",
        ),
        PAYLOAD_A,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("failure", ("disabled_profile", "missing_enrollment"))
def test_resolution_rejects_an_ineligible_caller_before_target_resolution(
    failure: str,
) -> None:
    """AC-10: rejects caller authorization bypasses without target ownership as auth."""
    scenario = create_credential_scenario()
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    create_catch_session(activation=activation)
    create_credential(activation=activation, token=TOKEN_A)
    if failure == "disabled_profile":
        PlayerProfile.objects.filter(pk=scenario.profile.pk).update(is_enabled=False)
    else:
        assert scenario.enrollment is not None
        scenario.enrollment.delete()
    response = scenario.client.post(
        resolution_path(scenario.convention.pk),
        {"payload": PAYLOAD_A},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert response.json() == {"detail": FORBIDDEN_DETAIL}
    assert PAYLOAD_A not in response.content.decode()


@pytest.mark.django_db
@override_settings(CLERK_AUTHENTICATION=TEST_CLERK_CONFIGURATION)
def test_resolution_authenticates_before_validation_and_missing_path_convention_is_404() -> (
    None
):
    """AC-10/16: rejects validation-first authentication and payload-reflecting path errors."""
    bad = {"payload": "not-a-payload"}
    unauthenticated = Client().post(
        resolution_path(999999), bad, content_type="application/json"
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.json() == {"detail": AUTHENTICATION_DETAIL}
    scenario = create_credential_scenario()
    response = scenario.client.post(
        resolution_path(999999), {"payload": PAYLOAD_A}, content_type="application/json"
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}
    assert PAYLOAD_A not in response.content.decode()
