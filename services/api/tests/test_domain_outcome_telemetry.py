"""Acceptance tests for domain outcome telemetry (#213).

Real views, real database states, and the real logging and Sentry hooks. The
substitutes sit on boundaries the tests cannot drive for real: the Sentry network
(`CapturingTransport`), Clerk's `authenticate_request` result, a database outage
under user resolution, and an unexpected service failure. Outcomes are read back
through `recorded_outcomes`, which requires the stdout JSON lines and the metrics
as sent (after the privacy filter) to agree. Contract values are written literally
so a renamed enum member cannot silently pass; tests construct enums by value.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

import pytest
import sentry_sdk
from clerk_backend_api.security.types import (
    AuthErrorReason,
    AuthStatus,
    RequestState,
    TokenVerificationErrorReason,
)
from django.conf import settings
from django.db import transaction
from django.test import Client
from django.utils import timezone
from pytest import MonkeyPatch
from rest_framework.test import APIClient
from sentry_sdk.types import Metric

from accounts.resolution import ApplicationUserResolutionUnavailable
from authentication import clerk as clerk_adapter
from authentication import drf as drf_adapter
from authentication.clerk import CLERK_FAILURE_REASONS
from catches import views as catch_views
from conventions import views as convention_views
from conventions.catch_credential_protocol import CATCH_CREDENTIAL_PAYLOAD_PREFIX
from conventions.catch_sessions import (
    set_fursuit_catch_session_state,
    terminate_session_as_operator,
)
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitCatchSessionEndReason,
)
from observability.outcomes import Outcome, Reason, Signal
from observability.privacy import scrub_metric
from tests.authentication_support import (
    TEST_CLERK_CONFIGURATION,
    force_authenticated_client,
)
from tests.catch_credential_test_support import (
    TOKEN_B,
    create_credential,
    resolution_path,
    revoke_current_for,
)
from tests.catch_test_support import (
    CatchConfirmationScenario,
    catch_model,
    create_catch_confirmation_scenario,
)
from tests.fursuit_activation_test_support import (
    activation_detail_path,
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import (
    CATCH_SESSION_LIFETIME,
    catch_session_model,
    catch_session_path,
    create_catch_session,
)
from tests.observability_test_support import (
    CapturingTransport,
    JsonLogCapture,
    RecordedOutcome,
    capture_json_stdout,
    identity,
    recorded_outcomes,
    sentry_capturing,
)

CATCH_SIGNAL = "tailtag.catches.confirmation"
RESOLUTION_SIGNAL = "tailtag.conventions.credential_resolution"
SESSION_SIGNAL = "tailtag.conventions.catch_session"
AUTH_SIGNAL = "tailtag.authentication.verification"
REQUEST_METRIC = "tailtag.http.server.requests"

SENTINEL_TOKEN = "SentinelToken" + "x" * 30
CATCH_PATH = "/api/catches/confirm/"
CATCH_TARGET_UNAVAILABLE = (
    b'{"code":"catch_target_unavailable","detail":"The catch target is unavailable."}'
)
CREDENTIAL_NOT_FOUND = b'{"detail":"Catch credential not found."}'
UNKNOWN_PAYLOAD = f"{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{TOKEN_B}"
INVALID_PAYLOAD = "tailtag:catch:v0:" + "Z" * 43

# The frozen taxonomy. Values are add-only, so the code must contain at least these.
EXPECTED_SIGNALS = {CATCH_SIGNAL, RESOLUTION_SIGNAL, SESSION_SIGNAL, AUTH_SIGNAL}
EXPECTED_OUTCOMES = {
    "created",
    "already_caught",
    "rejected",
    "resolved",
    "started",
    "start_rejected",
    "ended",
}
EXPECTED_REASONS = {
    "payload_invalid",
    "catcher_ineligible",
    "convention_mismatch",
    "self_catch",
    "caller_ineligible",
    "convention_unknown",
    "credential_unknown",
    "credential_revoked",
    "convention_not_playable",
    "target_ineligible",
    "activation_inactive",
    "session_expired",
    "session_inactive",
    "owner_ineligible",
    "not_enrolled",
    "activation_ineligible",
    "owner",
    "operator",
    "eligibility_lost",
    "expired",
    "malformed_header",
    "token_expired",
    "token_not_yet_valid",
    "token_invalid",
    "claims_missing",
    "verifier_misconfigured",
    "user_resolution_unavailable",
    "other",
}


@dataclass(frozen=True)
class Telemetry:
    logs: JsonLogCapture
    transport: CapturingTransport

    def outcomes(self) -> list[RecordedOutcome]:
        return recorded_outcomes(self.logs, self.transport)

    def request_status_classes(self) -> list[str]:
        sentry_sdk.flush()
        return [
            metric["attributes"]["http.response.status_class"]["value"]
            for metric in self.transport.metrics()
            if metric["name"] == REQUEST_METRIC
        ]

    def emitted_text(self) -> str:
        sentry_sdk.flush()
        return self.logs.text + self.transport.serialized()


@pytest.fixture
def telemetry() -> Iterator[Telemetry]:
    with sentry_capturing(identity()) as transport, capture_json_stdout() as logs:
        yield Telemetry(logs, transport)


# --- AC-1, AC-2: the taxonomy and the privacy filter ---


def _kept_attributes(key: str, value: str) -> dict[str, Any]:
    metric = cast(Metric, {"name": "tailtag.test.taxonomy", "attributes": {key: value}})
    return dict(scrub_metric(metric, None)["attributes"])


def test_taxonomy_is_frozen_and_every_value_survives_the_privacy_filter() -> None:
    """AC-1, AC-2: a renamed or removed value breaks dashboards; an unlisted one is dropped.

    Every outcome and reason value is sent through `scrub_metric` (the production
    hook) and must keep its attribute, which fails if the privacy allow-lists are
    not derived from the enumerations.
    """
    assert {str(signal) for signal in Signal} >= EXPECTED_SIGNALS
    assert {str(outcome) for outcome in Outcome} >= EXPECTED_OUTCOMES
    assert {str(reason) for reason in Reason} >= EXPECTED_REASONS
    # Ending a session converts its end reason inside the transaction.
    assert {str(end) for end in FursuitCatchSessionEndReason} <= {
        str(reason) for reason in Reason
    }

    for outcome in Outcome:
        assert _kept_attributes("tailtag.outcome", outcome) == {
            "tailtag.outcome": str(outcome)
        }
    for reason in Reason:
        assert _kept_attributes("tailtag.reason", reason) == {
            "tailtag.reason": str(reason)
        }


# --- AC-3, AC-5, AC-9, and AC-2 privacy: catch confirmation ---


def _break(
    faults: tuple[str, ...],
    scenario: CatchConfirmationScenario,
    context: dict[str, Any],
) -> None:
    """Apply real database faults (or request shape changes) to an eligible graph."""
    now = timezone.now()
    for fault in faults:
        if fault == "rotated":
            revoke_current_for(scenario.activation)
            create_credential(activation=scenario.activation, token=TOKEN_B)
        elif fault == "unknown_token":
            context["payload"] = UNKNOWN_PAYLOAD
        elif fault == "fursuit_disabled":
            scenario.fursuit.__class__.objects.filter(pk=scenario.fursuit.pk).update(
                is_enabled=False
            )
        elif fault == "target_profile_disabled":
            scenario.target_profile.__class__.objects.filter(
                pk=scenario.target_profile.pk
            ).update(is_enabled=False)
        elif fault == "target_enrollment_missing":
            scenario.target_enrollment.delete()
        elif fault == "convention_paused":
            Convention.objects.filter(pk=scenario.convention.pk).update(
                status=ConventionStatus.PAUSED
            )
        elif fault == "activation_inactive":
            scenario.activation.__class__.objects.filter(
                pk=scenario.activation.pk
            ).update(is_active=False, deactivated_at=now)
        elif fault == "session_expired":
            catch_session_model().objects.filter(pk=scenario.catch_session.pk).update(
                started_at=now - datetime.timedelta(seconds=2),
                expires_at=now - datetime.timedelta(seconds=1),
            )
        elif fault == "session_stopped":
            catch_session_model().objects.filter(pk=scenario.catch_session.pk).update(
                ended_at=now, end_reason="owner"
            )
        elif fault == "session_missing":
            scenario.catch_session.delete()
        elif fault == "catcher_profile_disabled":
            scenario.catcher_profile.__class__.objects.filter(
                pk=scenario.catcher_profile.pk
            ).update(is_enabled=False)
        elif fault == "catcher_not_enrolled":
            scenario.catcher_enrollment.delete()
        elif fault == "catcher_convention_not_active":
            ConventionEnrollment.objects.filter(
                pk=scenario.catcher_enrollment.pk
            ).update(is_active=False)
        elif fault == "self_catch":
            pass  # shaped by the scenario itself
        elif fault == "existing_catch":
            catch_model().objects.create(
                catcher_user=scenario.catcher_user,
                fursuit=scenario.fursuit,
                convention=scenario.convention,
                activation=scenario.activation,
                catch_session=scenario.catch_session,
            )
        elif fault == "invalid_grammar":
            context["payload"] = INVALID_PAYLOAD
        elif fault == "malformed_json":
            context["raw_body"] = "{not json"
        elif fault == "other_convention":
            other = Convention.objects.create(
                name="Other Convention",
                status=ConventionStatus.ACTIVE,
                start_date=scenario.convention.start_date,
                end_date=scenario.convention.end_date,
            )
            ConventionEnrollment.objects.create(
                user=scenario.catcher_user, convention=other
            )
            context["convention_id"] = other.pk
        elif fault == "unknown_convention":
            context["convention_id"] = scenario.convention.pk + 10_000
        else:
            raise AssertionError(f"unknown fault: {fault}")


# Reasons whose public response must be the one frozen 404, for both views.
# Every later-check fault is stacked under `revoked-first`: a revoked credential
# wins over a non-playable Convention, a disabled fursuit, an inactive
# activation, and a stopped session.
TARGET_CASES = [
    pytest.param(("unknown_token",), "credential_unknown", id="unknown-token"),
    pytest.param(("rotated",), "credential_revoked", id="rotated-credential"),
    pytest.param(("fursuit_disabled",), "target_ineligible", id="fursuit-disabled"),
    pytest.param(("activation_inactive",), "activation_inactive", id="activation-off"),
    pytest.param(("session_expired",), "session_expired", id="session-expired"),
    pytest.param(("session_stopped",), "session_inactive", id="session-stopped"),
    pytest.param(
        (
            "rotated",
            "convention_paused",
            "fursuit_disabled",
            "activation_inactive",
            "session_stopped",
        ),
        "credential_revoked",
        id="revoked-first",
    ),
]
# Catch confirmation only. It checks the target in clauses of its own ordered
# block, so each clause and each adjacent pair of checks can be misplaced
# independently. Resolution delegates eligibility to one helper call and reads
# the session with one unended-session query, so the rows above stand for them.
CATCH_ONLY_TARGET_CASES = [
    pytest.param(
        ("target_profile_disabled",), "target_ineligible", id="target-profile-disabled"
    ),
    pytest.param(
        ("target_enrollment_missing",), "target_ineligible", id="target-not-enrolled"
    ),
    pytest.param(("session_missing",), "session_inactive", id="session-missing"),
    pytest.param(
        ("convention_paused",), "convention_not_playable", id="convention-paused"
    ),
    pytest.param(
        ("convention_paused", "fursuit_disabled"),
        "convention_not_playable",
        id="order-convention-before-target",
    ),
    pytest.param(
        ("fursuit_disabled", "activation_inactive"),
        "target_ineligible",
        id="order-target-before-activation",
    ),
    pytest.param(
        ("activation_inactive", "session_expired"),
        "activation_inactive",
        id="order-activation-before-session",
    ),
]


def _post_payload(client: APIClient, path: str, context: dict[str, Any]) -> Any:
    """Post the (possibly faulted) payload, or the raw non-JSON body when set."""
    if context["raw_body"] is not None:
        return client.post(path, context["raw_body"], content_type="application/json")
    return client.post(path, {"payload": context["payload"]}, format="json")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("faults", "status", "outcome", "reason"),
    [
        pytest.param((), 201, "created", None, id="created"),
        pytest.param(
            ("existing_catch",), 200, "already_caught", None, id="already-caught"
        ),
        pytest.param(
            ("malformed_json",), 400, "rejected", "payload_invalid", id="malformed-json"
        ),
        pytest.param(
            ("invalid_grammar",),
            400,
            "rejected",
            "payload_invalid",
            id="invalid-grammar",
        ),
        pytest.param(
            ("catcher_profile_disabled",),
            403,
            "rejected",
            "catcher_ineligible",
            id="catcher-ineligible",
        ),
        pytest.param(
            ("catcher_convention_not_active",),
            409,
            "rejected",
            "convention_mismatch",
            id="convention-mismatch",
        ),
        pytest.param(("self_catch",), 409, "rejected", "self_catch", id="self-catch"),
        *[
            pytest.param(faults, 404, "rejected", reason, id=case.id)
            for case in (*TARGET_CASES, *CATCH_ONLY_TARGET_CASES)
            for faults, reason in [case.values]
        ],
    ],
)
def test_catch_confirmation_records_one_outcome_and_the_404_body_never_varies(
    telemetry: Telemetry,
    faults: tuple[str, ...],
    status: int,
    outcome: str,
    reason: str | None,
) -> None:
    """AC-3, AC-5, AC-9, AC-2: the reason is diagnosable only internally.

    Each row is a real state; every target reason must still yield the identical
    frozen 404 response. Neither the submitted token nor a Clerk identifier may
    reach stdout or Sentry. The request metric's status class pairs with the
    outcome so a 4xx refusal is distinguishable from a server error.
    """
    scenario = create_catch_confirmation_scenario(
        catcher_clerk_user_id="outcome_sentinel_catcher",
        target_owner_clerk_user_id="outcome_sentinel_target",
        self_catch="self_catch" in faults,
        token=SENTINEL_TOKEN,
    )
    context: dict[str, Any] = {"payload": scenario.payload, "raw_body": None}
    _break(faults, scenario, context)
    client = force_authenticated_client(user=scenario.catcher_user)

    response = _post_payload(client, CATCH_PATH, context)

    assert response.status_code == status
    if status == 404:
        assert response.content == CATCH_TARGET_UNAVAILABLE
    assert telemetry.outcomes() == [(CATCH_SIGNAL, outcome, reason)]
    assert telemetry.request_status_classes() == [f"{status // 100}xx"]
    emitted = telemetry.emitted_text()
    for secret in (
        context["payload"].removeprefix(CATCH_CREDENTIAL_PAYLOAD_PREFIX),
        "outcome_sentinel_catcher",
        "outcome_sentinel_target",
    ):
        assert secret not in emitted


@pytest.mark.django_db
def test_an_unexpected_failure_and_an_anonymous_request_record_no_domain_outcome(
    telemetry: Telemetry, monkeypatch: MonkeyPatch
) -> None:
    """AC-3, AC-9: a 5xx is the request metric's job; an unauthenticated 401 has no outcome.

    The resolution view builds its response after the success decision, so a
    failing projection must not leave a `resolved` outcome behind either.
    """
    scenario = create_catch_confirmation_scenario()

    def fail(*_: object, **__: object) -> object:
        raise RuntimeError("synthetic-unexpected-failure")

    monkeypatch.setattr(catch_views, "confirm_catch", fail)
    monkeypatch.setattr(
        convention_views, "fursuit_catch_credential_resolution_response_data", fail
    )
    client = force_authenticated_client(user=scenario.catcher_user)
    client.raise_request_exception = False  # the resolution view re-raises

    failed = client.post(CATCH_PATH, {"payload": scenario.payload}, format="json")
    resolution_failed = client.post(
        resolution_path(scenario.convention.pk),
        {"payload": scenario.payload},
        format="json",
    )
    anonymous = Client().post(
        CATCH_PATH, {"payload": scenario.payload}, content_type="application/json"
    )

    assert (
        failed.status_code,
        resolution_failed.status_code,
        anonymous.status_code,
    ) == (
        500,
        500,
        401,
    )
    assert telemetry.outcomes() == []
    assert sorted(telemetry.request_status_classes()) == ["4xx", "5xx", "5xx"]


# --- AC-4, AC-5: credential resolution ---


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("faults", "status", "outcome", "reason"),
    [
        pytest.param((), 200, "resolved", None, id="resolved"),
        pytest.param(
            ("invalid_grammar",), 400, "rejected", "payload_invalid", id="invalid"
        ),
        pytest.param(
            ("malformed_json",), 400, "rejected", "payload_invalid", id="malformed-json"
        ),
        pytest.param(
            ("catcher_profile_disabled",),
            403,
            "rejected",
            "caller_ineligible",
            id="caller-profile-disabled",
        ),
        pytest.param(
            ("catcher_not_enrolled",),
            403,
            "rejected",
            "caller_ineligible",
            id="caller-not-enrolled",
        ),
        pytest.param(
            ("unknown_convention",),
            404,
            "rejected",
            "convention_unknown",
            id="convention-unknown",
        ),
        pytest.param(
            ("other_convention",),
            404,
            "rejected",
            "credential_unknown",
            id="token-from-another-convention",
        ),
        *[
            pytest.param(faults, 404, "rejected", reason, id=case.id)
            for case in TARGET_CASES
            for faults, reason in [case.values]
        ],
    ],
)
def test_credential_resolution_records_one_outcome_and_a_revoked_token_is_not_unknown(
    telemetry: Telemetry,
    faults: tuple[str, ...],
    status: int,
    outcome: str,
    reason: str | None,
) -> None:
    """AC-4, AC-5: the same real states, through the resolution view.

    `credential_revoked` must not collapse into `credential_unknown`, and every
    target reason is the one frozen `Catch credential not found.` 404.
    """
    scenario = create_catch_confirmation_scenario(token=SENTINEL_TOKEN)
    context: dict[str, Any] = {
        "payload": scenario.payload,
        "convention_id": scenario.convention.pk,
        "raw_body": None,
    }
    _break(faults, scenario, context)
    client = force_authenticated_client(user=scenario.catcher_user)

    response = _post_payload(client, resolution_path(context["convention_id"]), context)

    assert response.status_code == status
    if status == 404 and reason != "convention_unknown":
        assert response.content == CREDENTIAL_NOT_FOUND
    assert telemetry.outcomes() == [(RESOLUTION_SIGNAL, outcome, reason)]
    token = context["payload"].removeprefix(CATCH_CREDENTIAL_PAYLOAD_PREFIX)
    assert token not in telemetry.emitted_text()


# --- AC-7: catch session lifecycle ---


def _owner_with_session(*, expired: bool = False, session: bool = True) -> Any:
    scenario = create_activation_scenario(clerk_user_id="session_sentinel_owner")
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    live = None
    if session:
        now = timezone.now()
        live = create_catch_session(
            activation=activation,
            started_at=now - CATCH_SESSION_LIFETIME - datetime.timedelta(hours=1)
            if expired
            else now,
            expires_at=now - datetime.timedelta(hours=1) if expired else None,
        )
    return scenario, activation, live


def _put_session(scenario: Any, *, active: bool) -> Any:
    return scenario.client.put(
        catch_session_path(scenario.convention.pk, scenario.fursuit.pk),
        {"is_active": active},
        format="json",
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("setup", "action", "expected"),
    [
        pytest.param({}, "start", [], id="live-session-is-returned-silently"),
        pytest.param(
            {"expired": True},
            "start",
            [("ended", "expired"), ("started", None)],
            id="start-over-expired-session",
        ),
        pytest.param({}, "stop", [("ended", "owner")], id="owner-stop"),
        pytest.param({"session": False}, "stop", [], id="stop-with-no-session"),
        pytest.param(
            {}, "operator", [("ended", "operator")], id="operator-termination"
        ),
        pytest.param(
            {}, "deactivate", [("ended", "eligibility_lost")], id="eligibility-lost"
        ),
        pytest.param(
            {"profile_disabled": True},
            "start",
            [("start_rejected", "owner_ineligible")],
            id="owner-ineligible",
        ),
        pytest.param(
            {"not_enrolled": True},
            "start",
            [("start_rejected", "not_enrolled")],
            id="not-enrolled",
        ),
        pytest.param(
            {"activation_off": True},
            "start",
            [("start_rejected", "activation_ineligible")],
            id="activation-ineligible",
        ),
    ],
)
def test_catch_session_transitions_record_the_right_outcome_after_a_real_commit(
    telemetry: Telemetry,
    setup: dict[str, bool],
    action: str,
    expected: list[tuple[str, str | None]],
) -> None:
    """AC-7: a start, an end (with its `end_reason`), and each start rejection.

    Runs against real commits (`transaction=True`) so `on_commit` callbacks fire.
    Retried starts, no-op stops, and live sessions stay silent.
    """
    scenario, activation, session = _owner_with_session(
        expired=setup.get("expired", False), session=setup.get("session", True)
    )
    if setup.get("profile_disabled"):
        scenario.profile.__class__.objects.filter(pk=scenario.profile.pk).update(
            is_enabled=False
        )
    if setup.get("not_enrolled"):
        scenario.enrollment.delete()
    if setup.get("activation_off"):
        activation.__class__.objects.filter(pk=activation.pk).update(
            is_active=False, deactivated_at=timezone.now()
        )

    if action == "start":
        _put_session(scenario, active=True)
    elif action == "stop":
        _put_session(scenario, active=False)
    elif action == "operator":
        terminate_session_as_operator(session.pk)
    else:
        response = scenario.client.put(
            activation_detail_path(scenario.convention.pk, scenario.fursuit.pk),
            {"is_active": False},
            format="json",
        )
        assert response.status_code == 200

    assert telemetry.outcomes() == [(SESSION_SIGNAL, o, r) for o, r in expected]
    assert "session_sentinel_owner" not in telemetry.emitted_text()


@pytest.mark.django_db(transaction=True)
def test_a_rolled_back_session_transition_records_no_outcome(
    telemetry: Telemetry,
) -> None:
    """AC-7: a transition rolled back with its transaction was never real.

    An expired restart registers both `ended` and `started`; neither may survive
    the enclosing rollback. Real commits (above) and this real rollback need
    `transaction=True`, since the default test transaction never fires `on_commit`.
    """

    class _Abort(Exception):
        pass

    scenario, activation, _ = _owner_with_session(expired=True)

    with pytest.raises(_Abort), transaction.atomic():
        set_fursuit_catch_session_state(
            scenario.user,
            convention_id=scenario.convention.pk,
            fursuit_id=scenario.fursuit.pk,
            is_active=True,
        )
        raise _Abort

    assert telemetry.outcomes() == []
    # The expired session is still the only one: the restart really rolled back.
    assert catch_session_model().objects.filter(activation=activation).count() == 1


# --- AC-8: authentication ---

EXPECTED_CLERK_REASONS: dict[tuple[str, str], str] = {
    ("AuthErrorReason", "SESSION_TOKEN_MISSING"): "malformed_header",
    ("AuthErrorReason", "SECRET_KEY_MISSING"): "verifier_misconfigured",
    ("AuthErrorReason", "TOKEN_TYPE_NOT_SUPPORTED"): "token_invalid",
    ("TokenVerificationErrorReason", "TOKEN_EXPIRED"): "token_expired",
    ("TokenVerificationErrorReason", "TOKEN_IAT_IN_THE_FUTURE"): "token_not_yet_valid",
    ("TokenVerificationErrorReason", "TOKEN_NOT_ACTIVE_YET"): "token_not_yet_valid",
    ("TokenVerificationErrorReason", "TOKEN_INVALID"): "token_invalid",
    ("TokenVerificationErrorReason", "TOKEN_INVALID_SIGNATURE"): "token_invalid",
    (
        "TokenVerificationErrorReason",
        "TOKEN_INVALID_AUTHORIZED_PARTIES",
    ): "token_invalid",
    ("TokenVerificationErrorReason", "TOKEN_INVALID_AUDIENCE"): "token_invalid",
    ("TokenVerificationErrorReason", "JWK_KID_MISMATCH"): "token_invalid",
    ("TokenVerificationErrorReason", "INVALID_TOKEN_TYPE"): "token_invalid",
    ("TokenVerificationErrorReason", "SECRET_KEY_MISSING"): "verifier_misconfigured",
    ("TokenVerificationErrorReason", "JWK_FAILED_TO_LOAD"): "verifier_misconfigured",
    ("TokenVerificationErrorReason", "JWK_REMOTE_INVALID"): "verifier_misconfigured",
    (
        "TokenVerificationErrorReason",
        "JWK_FAILED_TO_RESOLVE",
    ): "verifier_misconfigured",
    ("TokenVerificationErrorReason", "SERVER_ERROR"): "verifier_misconfigured",
}


def test_every_clerk_failure_reason_has_the_documented_explicit_mapping() -> None:
    """AC-8: an SDK upgrade that adds a reason fails here until it is classified."""
    members = [*AuthErrorReason, *TokenVerificationErrorReason]

    assert {(type(m).__name__, m.name) for m in members} == set(
        EXPECTED_CLERK_REASONS
    ), "the Clerk SDK's reasons changed: classify the new ones in the mapping"
    assert set(CLERK_FAILURE_REASONS) == set(members)
    for member in members:
        assert (
            CLERK_FAILURE_REASONS[member]
            == EXPECTED_CLERK_REASONS[(type(member).__name__, member.name)]
        )


def _signed_in(payload: dict[str, Any] | None) -> RequestState:
    return RequestState(AuthStatus.SIGNED_IN, token="t", payload=payload)


def _signed_out(reason: Any) -> RequestState:
    return RequestState(AuthStatus.SIGNED_OUT, reason=reason)


VALID_CLAIMS = {"sub": "user_sentinel_subject", "sid": "sess_sentinel_session"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("authorization", "provider", "reason"),
    [
        pytest.param("Basic credential", None, "malformed_header", id="bad-grammar"),
        pytest.param(
            "Bearer synthetic.token.value",
            _signed_out(TokenVerificationErrorReason.TOKEN_EXPIRED),
            "token_expired",
            id="expired-token",
        ),
        pytest.param(
            "Bearer synthetic.token.value",
            _signed_out(None),
            "other",
            id="signed-out-without-reason",
        ),
        pytest.param(
            "Bearer synthetic.token.value",
            TypeError("synthetic-sdk-failure"),
            "other",
            id="sdk-type-error",
        ),
        pytest.param(
            "Bearer synthetic.token.value",
            _signed_in({"sub": VALID_CLAIMS["sub"]}),
            "claims_missing",
            id="session-claim-missing",
        ),
        pytest.param(
            "Bearer synthetic.token.value",
            _signed_in(None),
            "claims_missing",
            id="payload-missing",
        ),
        pytest.param(
            "Bearer synthetic.token.value",
            _signed_in(VALID_CLAIMS),
            "user_resolution_unavailable",
            id="user-resolution-unavailable",
        ),
    ],
)
def test_each_authentication_failure_records_one_rejected_outcome_with_its_reason(
    telemetry: Telemetry,
    monkeypatch: MonkeyPatch,
    authorization: str,
    provider: RequestState | Exception | None,
    reason: str,
) -> None:
    """AC-8: through the real `/api/me/` stack, with only Clerk's result substituted.

    `ClerkSessionVerifier` and `TailTagAuthentication` stay real. The 503 for
    unavailable user resolution is an authentication outcome too. The token,
    claims, and Clerk subject never reach telemetry.
    """
    monkeypatch.setattr(settings, "CLERK_AUTHENTICATION", TEST_CLERK_CONFIGURATION)

    def authenticate_request(*_: object, **__: object) -> RequestState:
        if isinstance(provider, Exception):
            raise provider
        assert isinstance(provider, RequestState), "header must be rejected first"
        return provider

    def resolution_unavailable(_clerk_user_id: str) -> object:
        raise ApplicationUserResolutionUnavailable("synthetic-database-detail")

    monkeypatch.setattr(clerk_adapter, "authenticate_request", authenticate_request)
    if reason == "user_resolution_unavailable":
        monkeypatch.setattr(
            drf_adapter, "resolve_application_user", resolution_unavailable
        )

    response = Client().get("/api/me/", HTTP_AUTHORIZATION=authorization)

    assert response.status_code == (
        503 if reason == "user_resolution_unavailable" else 401
    )
    assert telemetry.outcomes() == [(AUTH_SIGNAL, "rejected", reason)]
    emitted = telemetry.emitted_text()
    for secret in ("synthetic.token.value", "user_sentinel_subject", "sess_sentinel"):
        assert secret not in emitted


@pytest.mark.django_db
def test_a_request_without_an_authorization_header_is_not_an_authentication_outcome(
    telemetry: Telemetry, monkeypatch: MonkeyPatch
) -> None:
    """AC-8: anonymous traffic is not a verification failure."""
    monkeypatch.setattr(settings, "CLERK_AUTHENTICATION", TEST_CLERK_CONFIGURATION)

    response = Client().get("/api/me/")

    assert response.status_code == 401
    assert telemetry.outcomes() == []
