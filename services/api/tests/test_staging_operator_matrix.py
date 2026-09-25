"""Independent acceptance tests for the bounded #243 matrix executor.

Test surface contract for this file (approved by the ADW parent):

* ``run(expected_identity)`` is the public entry. Its private return value is a
  mapping with a fixed ``classification``, a ``cases`` mapping keyed ``"1"``
  through ``"9"``, a ``case9`` mapping of finite subcheck statuses, and
  ``mutation_may_have_begun``. No private value in the returned evidence may
  appear in rendered stdout or stderr.
* ``_snapshot()`` is the bounded real-ORM seam. It returns ``roots`` with the
  registered owner, catcher, owner profile, convention and two fursuit IDs;
  ``state`` with immutable rows for profiles, fursuits, convention, enrollments,
  activations, sessions, credentials and Catches; and ``audit`` as immutable
  eight-field rows ``(id, actor_id, action, actor_class, affected_record_type,
  affected_record_id, outcome, occurred_at)``. Audit scope includes the exact
  profile/second-fursuit targets and any owned dependent target so an illicit
  cascade row cannot disappear. The projection stays in memory and includes
  no credential token or provider identifier.
* ``_http_request(method, path, *, actor, body=None, csrf=None)`` is the sole
  HTTP seam. It returns a bounded mapping with integer ``status``, ``headers``
  and byte ``body``. ``actor`` is an opaque private session returned by
  ``_authenticate(role)`` or ``None`` for a public request. Tests may use a
  controlled response at this seam;
  live code must use actual HTTPS and isolated per-actor sessions.
  ``_STAGING_ORIGIN`` is fixed in production and may be monkeypatched only by
  tests to point at a disposable local HTTP server.
* ``_confirm_window()`` performs the exact nonsecret real-TTY coordination
  confirmation after target/fixture guards and before authentication. Sequence
  tests substitute this seam; separate tests exercise the original function.
* ``run`` emits its final sanitized evidence mapping as JSON on stdout, so the
  inherited-TTY launcher never has to capture credentials to receive a result.
* ``_review_deployed_controls()`` returns only ``deployed_control_hash_match``
  PASS/FAIL. Matching source bytes establish no control review or test result.
  ``case9`` retains four approved object/state subchecks as NOT_EXERCISED;
  ``case9_control_review`` and ``case9_deterministic_evidence`` also remain
  NOT_EXERCISED for separately established external evidence. Runtime success
  is ``LIVE_SEQUENCE_COMPLETE_PENDING_CASE9_EVIDENCE``, with case 9 still
  NOT_EXERCISED and its fixed-name ``case9_limitations`` preserved.
* ``_await_decommission_receipt()`` is a separate external lifecycle handoff
  returning the fixed ``{"classification": "PASS"}`` receipt only on success.
  Completed live sequence status requires a fresh exact target guard, exact inactive
  limited role, valid managed role/baseline, and unchanged retained audit rows.
* A synthetic ``staging_emergency_...`` Case-5 actor additionally requires a
  separate ``_await_emergency_decommission_receipt()`` handoff and direct proof
  that staff, superuser, and usable-password access are gone before limited-role
  cleanup. An existing non-synthetic break-glass actor skips that lifecycle.
* ``_guard_target(expected_identity)`` checks the exact running tuple before
  each mutation. ``_await_reset_receipt()`` is the single external reset
  handoff; it never performs the reset itself. Tests substitute these bounded
  external interfaces, and never contact Staging or Clerk.

Reset may replace enrollment/activation IDs while preserving the registered
roots. The post-reset proof uses ``validate_baseline`` plus byte-for-byte
equality of retained audit rows, not equality to the pre-reset domain snapshot.

The real ORM and existing domain tests, not a proposed implementation, define
the state and audit evidence that the executor must verify.
"""

from __future__ import annotations

import builtins
import getpass
import hashlib
import importlib
import io
import json
import re
import sys
import warnings
from collections.abc import Callable, Mapping
from http.cookiejar import CookieJar
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn, cast
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.utils import timezone
from pytest_django.fixtures import SettingsWrapper

from accounts.models import User
from authentication.clerk import ClerkSessionVerifier, VerifiedClerkIdentity
from conventions.models import (
    Convention,
    ConventionEnrollment,
    FursuitActivation,
    FursuitCatchSession,
)
from fursuits.models import Fursuit
from fursuits.services import set_fursuit_enabled
from operator_audit.models import (
    OperatorAction,
    OperatorActorClass,
    OperatorAuditEvent,
    OperatorAuditOutcome,
    OperatorTargetType,
)
from profiles.models import PlayerProfile
from profiles.services import set_profile_enabled
from rehearsal.reset import validate_baseline
from tests.authentication_support import TEST_CLERK_CONFIGURATION
from tests.catch_credential_test_support import create_credential
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.test_staging_operator_inspector import create_owned_baseline
from tests.test_staging_validation_operator import (
    INITIAL_PASSWORD,
    create_exact_limited_operator,
    create_exact_managed_operator,
)


@pytest.fixture(autouse=True)
def local_http_cookie_transport(settings: SettingsWrapper) -> None:
    """The disposable HTTP server needs cookies that work without production TLS."""
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "api_staging_operator_matrix.py"
WINDOW_CONFIRMATION = "exclusive Railway Staging validation window; I own cleanup"
LIVE_SEQUENCE_COMPLETE = "LIVE_SEQUENCE_COMPLETE_PENDING_CASE9_EVIDENCE"
IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
CASE9_SUBCHECKS = frozenset(
    {
        "catch_add",
        "catch_change",
        "catch_bulk_edit",
        "credential_add",
        "credential_replacement",
        "credential_raw_edit",
        "session_add",
        "session_delete",
        "session_bulk_edit",
        "session_history_edit",
        "activation_add",
        "activation_delete",
        "activation_reactivation",
        "enrollment_add",
        "enrollment_selection_change",
        "convention_create",
        "convention_delete",
    }
)
ABSENT_OBJECT_SUBCHECKS = frozenset(
    {"catch_change", "credential_replacement", "credential_raw_edit"}
)
COMBINED_EVIDENCE_SUBCHECKS = ABSENT_OBJECT_SUBCHECKS | {"activation_reactivation"}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def unconfirmed_matrix() -> ModuleType:
    assert SCRIPT.is_file(), "the reviewed #243 matrix entry point must exist"
    return importlib.import_module("scripts.api_staging_operator_matrix")


@pytest.fixture
def matrix(
    unconfirmed_matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsWrapper,
) -> ModuleType:
    # Sequence tests isolate the interactive boundary. Its original behavior is
    # independently exercised below through the unpatched module fixture.
    settings.DEBUG = False
    monkeypatch.setattr(unconfirmed_matrix, "_confirm_window", lambda: None)
    monkeypatch.setattr(
        unconfirmed_matrix,
        "_review_deployed_controls",
        lambda: {"deployed_control_hash_match": "PASS"},
    )
    return unconfirmed_matrix


def snapshot(matrix: ModuleType) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], matrix._snapshot())


def role_sessions(identity: Any) -> dict[str, dict[str, Any]]:
    """Return private stand-ins for separately verified actor sessions."""
    limited = create_exact_limited_operator()
    managed = create_exact_managed_operator()
    emergency = User.objects.create_superuser(
        "emergency-matrix", password="local-only-emergency-test-password"
    )
    return {
        role: {
            "role": role,
            "actor_id": user.pk,
            "csrf": f"local-csrf-{role}",
            "cookies": {},
        }
        for role, user in (
            ("owner", identity.owner),
            ("limited", limited),
            ("managed", managed),
            ("emergency", emergency),
        )
    }


def accept_target(_: object) -> None:
    """Substitute a successful external target guard in local tests."""


def denied_response() -> dict[str, object]:
    return {"status": 403, "headers": {}, "body": b""}


def owner_login_redirect(path: str) -> dict[str, object]:
    return {
        "status": 302,
        "headers": {"Location": f"/admin/login/?next={path}"},
        "body": b"",
    }


class HiddenInputTerminal(io.StringIO):
    def isatty(self) -> bool:
        return True


@pytest.mark.parametrize(
    "answer", (WINDOW_CONFIRMATION, "wrong", WINDOW_CONFIRMATION + " ", "eof")
)
def test_window_confirmation_requires_exact_nonsecret_phrase(
    unconfirmed_matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    answer: str,
) -> None:
    """The exclusive window and cleanup acknowledgement is an exact TTY event."""
    prompts: list[str] = []
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())

    def ordinary_input(prompt: str = "") -> str:
        prompts.append(prompt)
        if answer == "eof":
            raise EOFError("local input closed")
        return answer

    def forbidden_secret(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("nonsecret coordination confirmation requested a credential")

    monkeypatch.setattr(builtins, "input", ordinary_input)
    monkeypatch.setattr(getpass, "getpass", forbidden_secret)
    if answer == WINDOW_CONFIRMATION:
        assert unconfirmed_matrix._confirm_window() is None
    else:
        with pytest.raises((ValueError, EOFError)):
            unconfirmed_matrix._confirm_window()
    assert len(prompts) == 1
    assert WINDOW_CONFIRMATION in prompts[0]


def test_window_confirmation_rejects_non_tty_without_reading_input(
    unconfirmed_matrix: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(WINDOW_CONFIRMATION))

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("noninteractive confirmation attempted an input fallback")

    monkeypatch.setattr(builtins, "input", forbidden)
    monkeypatch.setattr(getpass, "getpass", forbidden)
    with pytest.raises(ValueError):
        unconfirmed_matrix._confirm_window()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("failure_kind", ("wrong_phrase", "eof"))
def test_confirmation_failure_is_after_guards_and_before_authentication(
    matrix: ModuleType,
    failure_kind: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identity = create_owned_baseline()
    role_sessions(identity)
    observations: list[str] = []
    original_snapshot = matrix._snapshot
    private_failure = "confirmation-only-private-error-marker"

    def guard(_: object) -> None:
        observations.append("target")

    def guarded_snapshot() -> Any:
        result = original_snapshot()
        observations.append("fixture")
        return result

    def reject_confirmation() -> NoReturn:
        assert observations[0] == "target"
        assert "fixture" in observations
        observations.append("confirmation")
        if failure_kind == "eof":
            raise EOFError(private_failure)
        raise ValueError(private_failure)

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("unconfirmed validation window reached credentials or HTTP")

    monkeypatch.setattr(matrix, "_guard_target", guard)
    monkeypatch.setattr(matrix, "_snapshot", guarded_snapshot)
    monkeypatch.setattr(matrix, "_confirm_window", reject_confirmation)
    monkeypatch.setattr(matrix, "_authenticate", forbidden)
    monkeypatch.setattr(matrix, "_http_request", forbidden)
    result = matrix.run(IDENTITY)
    rendered = capsys.readouterr()
    assert observations[-1] == "confirmation"
    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is False
    assert all(value == "NOT_EXERCISED" for value in result["cases"].values())
    assert json.loads(rendered.out) == result
    assert rendered.err == ""
    assert private_failure not in rendered.out + repr(result)


@pytest.mark.django_db(transaction=True)
def test_snapshot_is_exactly_the_registered_real_orm_closure(
    matrix: ModuleType,
) -> None:
    """#243 F/data integrity: unrelated records cannot become validation targets."""
    identity = create_owned_baseline()
    before = snapshot(matrix)

    unrelated = User.objects.create_user("unrelated-matrix-player")
    PlayerProfile.objects.create(user=unrelated)
    after = snapshot(matrix)

    assert before == after
    assert before["roots"] == {
        "owner": identity.owner_id,
        "catcher": identity.catcher_id,
        "owner_profile": PlayerProfile.objects.get(user_id=identity.owner_id).pk,
        "convention": identity.convention_id,
        "first_fursuit": identity.first_fursuit_id,
        "second_fursuit": identity.second_fursuit_id,
    }
    assert {name: len(rows) for name, rows in before["state"].items()} == {
        "profiles": 2,
        "fursuits": 2,
        "convention": 1,
        "enrollments": 2,
        "activations": 2,
        "sessions": 0,
        "credentials": 0,
        "catches": 0,
    }
    assert before["audit"] == ()


@pytest.mark.django_db(transaction=True)
def test_snapshot_rejects_foreign_dependency_on_an_owned_root(
    matrix: ModuleType,
) -> None:
    """#243 precondition: a foreign dependent row stops before any HTTP write."""
    identity = create_owned_baseline()
    outsider = User.objects.create_user("foreign-matrix-enrollment")
    ConventionEnrollment.objects.create(
        user=outsider, convention=identity.convention, is_active=False
    )

    with pytest.raises(ValueError):
        snapshot(matrix)


@pytest.mark.django_db(transaction=True)
def test_snapshot_retains_exact_private_audit_record_fields(matrix: ModuleType) -> None:
    """#243 F: retained evidence detects actor, target and row replacement."""
    identity = create_owned_baseline()
    actor = User.objects.create_user("audit-actor-matrix")
    event = OperatorAuditEvent.objects.create(
        action=OperatorAction.SET_FURSUIT_ENABLED,
        actor=actor,
        actor_class=OperatorActorClass.UNAUTHORIZED_ACTOR,
        affected_record_type=OperatorTargetType.FURSUIT,
        affected_record_id=cast(int, identity.second_fursuit_id),
        outcome=OperatorAuditOutcome.DENIED,
    )

    assert snapshot(matrix)["audit"] == (
        (
            event.pk,
            actor.pk,
            OperatorAction.SET_FURSUIT_ENABLED,
            OperatorActorClass.UNAUTHORIZED_ACTOR,
            OperatorTargetType.FURSUIT,
            identity.second_fursuit_id,
            OperatorAuditOutcome.DENIED,
            event.occurred_at,
        ),
    )


@pytest.mark.django_db(transaction=True)
def test_snapshot_detects_credential_without_copying_its_token(
    matrix: ModuleType,
) -> None:
    """#243 session prerequisite/privacy: unexpected credential existence is visible."""
    identity = create_owned_baseline()
    activation = FursuitActivation.objects.get(
        fursuit_id=identity.first_fursuit_id,
        convention_id=identity.convention_id,
    )
    secret = "X" * 43
    create_credential(activation=activation, token=secret)

    observed = snapshot(matrix)

    assert len(observed["state"]["credentials"]) == 1
    assert secret not in repr(observed)
    assert identity.owner.clerk_user_id not in repr(observed)


@pytest.mark.django_db(transaction=True)
def test_snapshot_includes_unexpected_child_cascade_audit_row(
    matrix: ModuleType,
) -> None:
    """#243 case 8: a child event is not hidden by top-level target filtering."""
    identity = create_owned_baseline()
    activation = FursuitActivation.objects.get(
        fursuit_id=identity.first_fursuit_id,
        convention_id=identity.convention_id,
    )
    session = create_catch_session(activation=activation)
    actor = User.objects.create_user("unexpected-cascade-audit-actor")
    event = OperatorAuditEvent.objects.create(
        action=OperatorAction.TERMINATE_CATCH_SESSION,
        actor=actor,
        actor_class=OperatorActorClass.OPERATOR,
        affected_record_type=OperatorTargetType.FURSUIT_CATCH_SESSION,
        affected_record_id=session.pk,
        outcome=OperatorAuditOutcome.SUCCEEDED,
    )

    assert any(row[0] == event.pk for row in snapshot(matrix)["audit"])


@pytest.mark.parametrize(
    "expected_identity",
    (
        {},
        {**IDENTITY, "source_sha": "unreviewed"},
        {**IDENTITY, "environment": "production"},
        {**IDENTITY, "deployment_id": "not-a-deployment-id"},
    ),
)
def test_invalid_public_identity_stops_before_authentication_or_http(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    expected_identity: dict[str, str],
) -> None:
    """#243 precondition/security: an invalid tuple cannot solicit credentials."""

    def forbidden(*_: object, **__: object) -> None:
        pytest.fail("invalid target reached a private or network seam")

    monkeypatch.setattr(matrix, "_confirm_window", forbidden)
    monkeypatch.setattr(matrix, "_authenticate", forbidden)
    monkeypatch.setattr(matrix, "_http_request", forbidden)
    monkeypatch.setattr(matrix, "_snapshot", forbidden)
    result = cast(Mapping[str, Any], matrix.run(expected_identity))

    assert result["classification"] != "PASS"
    assert result["deployed_control_hash_match"] == "NOT_EXERCISED"
    assert result["case9_control_review"] == "NOT_EXERCISED"
    assert result["case9_deterministic_evidence"] == "NOT_EXERCISED"
    assert result["mutation_may_have_begun"] is False
    assert all(value == "NOT_EXERCISED" for value in result["cases"].values())


@pytest.mark.parametrize("debug_surface", ("settings", "cursor"))
def test_debug_logging_stops_before_private_reads_or_prompts(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsWrapper,
    debug_surface: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sensitive SQL must never run where debug logging can retain values."""
    if debug_surface == "settings":
        settings.DEBUG = True
    else:
        monkeypatch.setattr(connection, "force_debug_cursor", True)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("debug-enabled executor reached private state or a prompt")

    monkeypatch.setattr(matrix, "_snapshot", forbidden)
    monkeypatch.setattr(matrix, "_confirm_window", forbidden)
    monkeypatch.setattr(matrix, "_authenticate", forbidden)
    monkeypatch.setattr(matrix, "_http_request", forbidden)
    result = matrix.run(IDENTITY)
    rendered = capsys.readouterr()
    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is False
    assert all(value == "NOT_EXERCISED" for value in result["cases"].values())
    assert json.loads(rendered.out) == result
    assert rendered.err == ""


@pytest.mark.django_db(transaction=True)
def test_foreign_owned_dependency_stops_before_private_authentication(
    matrix: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#243 precondition: no network attempt can follow ambiguous closure state."""
    identity = create_owned_baseline()
    outsider = User.objects.create_user("foreign-matrix-run")
    ConventionEnrollment.objects.create(
        user=outsider, convention=identity.convention, is_active=False
    )
    monkeypatch.setattr(matrix, "_guard_target", accept_target)

    def forbidden(*_: object, **__: object) -> NoReturn:
        pytest.fail("unsafe closure reached authentication or HTTP")

    monkeypatch.setattr(matrix, "_authenticate", forbidden)
    monkeypatch.setattr(matrix, "_http_request", forbidden)

    result = cast(Mapping[str, Any], matrix.run(IDENTITY))

    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is False
    assert all(value == "NOT_EXERCISED" for value in result["cases"].values())


@pytest.mark.django_db(transaction=True)
def test_exact_target_guard_failure_stops_before_credentials(
    matrix: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#243 security: current instance drift cannot be overridden by fixture state."""
    create_owned_baseline()

    def drift(_: object) -> NoReturn:
        raise RuntimeError("private target marker must be redacted")

    def forbidden(*_: object, **__: object) -> NoReturn:
        pytest.fail("target drift reached authentication or HTTP")

    monkeypatch.setattr(matrix, "_guard_target", drift)
    monkeypatch.setattr(matrix, "_authenticate", forbidden)
    monkeypatch.setattr(matrix, "_http_request", forbidden)

    result = cast(Mapping[str, Any], matrix.run(IDENTITY))

    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is False
    assert all(value == "NOT_EXERCISED" for value in result["cases"].values())
    assert "private target marker" not in repr(result)


@pytest.mark.django_db(transaction=True)
def test_authentication_failure_is_sanitized_and_never_retried(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#243 authentication/reliability: a failed actor session is a terminal event."""
    create_owned_baseline()
    calls: list[str] = []
    secret = "synthetic-hidden-password-never-in-evidence"
    monkeypatch.setattr(matrix, "_guard_target", accept_target)

    def failed_authentication(role: str) -> NoReturn:
        calls.append(role)
        raise RuntimeError(secret)

    def forbidden(*_: object, **__: object) -> NoReturn:
        pytest.fail("failed authentication made an HTTP request")

    monkeypatch.setattr(matrix, "_authenticate", failed_authentication)
    monkeypatch.setattr(matrix, "_http_request", forbidden)

    result = cast(Mapping[str, Any], matrix.run(IDENTITY))
    rendered = capsys.readouterr()

    assert calls == ["limited"]
    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is False
    assert all(value == "NOT_EXERCISED" for value in result["cases"].values())
    assert secret not in repr(result) + rendered.out + rendered.err


@pytest.mark.django_db(transaction=True)
def test_verified_wrong_clerk_subject_stops_before_api_resolution(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsWrapper,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#243 owner guard: a valid token for another subject creates no app user."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    before_users = User.objects.count()
    secret = "valid-shaped-but-wrong-owner-test-token"
    verified: list[str] = []
    settings.CLERK_AUTHENTICATION = TEST_CLERK_CONFIGURATION
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    terminal_output = HiddenInputTerminal()

    def hidden_token(*_args: object, **_kwargs: object) -> str:
        return secret

    monkeypatch.setattr(getpass, "getpass", hidden_token)
    original_authenticate = matrix._authenticate
    authenticated: list[str] = []

    def authenticate(role: str) -> Any:
        authenticated.append(role)
        if role == "owner":
            return original_authenticate(role)
        return sessions[role]

    def wrong_subject(
        _verifier: ClerkSessionVerifier, request: Any
    ) -> VerifiedClerkIdentity:
        verified.append(request.headers["Authorization"])
        return VerifiedClerkIdentity(subject="a-valid-but-foreign-clerk-subject")

    def forbidden_http(*_: object, **__: object) -> NoReturn:
        pytest.fail("foreign Clerk identity reached /api/me/")

    monkeypatch.setattr(ClerkSessionVerifier, "verify", wrong_subject)
    monkeypatch.setattr(matrix, "_authenticate", authenticate)
    monkeypatch.setattr(matrix, "_http_request", forbidden_http)

    with monkeypatch.context() as terminal_patch:
        terminal_patch.setattr(sys, "stdout", terminal_output)
        result = cast(Mapping[str, Any], matrix.run(IDENTITY))
    rendered = capsys.readouterr()

    assert verified == [f"Bearer {secret}"]
    assert authenticated == ["limited", "managed", "emergency", "owner"]
    assert User.objects.count() == before_users
    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is False
    assert all(value == "NOT_EXERCISED" for value in result["cases"].values())
    assert (
        secret
        not in repr(result) + rendered.out + rendered.err + terminal_output.getvalue()
    )


@pytest.mark.django_db(transaction=True)
def test_missing_emergency_identity_is_found_before_first_mutation(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#243 precondition: later actor absence cannot strand an altered baseline."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    authenticated: list[str] = []
    monkeypatch.setattr(matrix, "_guard_target", accept_target)

    def authenticate(role: str) -> Mapping[str, Any]:
        authenticated.append(role)
        if role == "emergency":
            raise ValueError("missing verified emergency session")
        return sessions[role]

    def read_only_http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: object = None,
        csrf: object = None,
    ) -> Mapping[str, object]:
        del body, csrf, actor
        assert method == "GET", f"mutation before emergency proof: {path}"
        if path == "/api/me/":
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"id": identity.owner_id}).encode(),
            }
        return owner_login_redirect(path)

    monkeypatch.setattr(matrix, "_authenticate", authenticate)
    monkeypatch.setattr(matrix, "_http_request", read_only_http)

    result = cast(Mapping[str, Any], matrix.run(IDENTITY))

    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is False
    assert authenticated == ["limited", "managed", "emergency"]
    assert OperatorAuditEvent.objects.count() == 0
    assert PlayerProfile.objects.get(user_id=identity.owner_id).is_enabled is True


@pytest.mark.django_db(transaction=True)
def test_http_seam_uses_local_server_without_following_admin_redirect(
    matrix: ModuleType,
    live_server: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#243 HTTP boundary: real requests retain redirect and path isolation."""
    monkeypatch.setattr(matrix, "_STAGING_ORIGIN", live_server.url)

    live = cast(
        Mapping[str, Any], matrix._http_request("GET", "/health/live", actor=None)
    )
    admin = cast(Mapping[str, Any], matrix._http_request("GET", "/admin/", actor=None))

    assert live["status"] == 200
    assert admin["status"] == 302
    assert cast(Mapping[str, str], admin["headers"])["Location"].startswith(
        "/admin/login/"
    )
    with pytest.raises(ValueError):
        matrix._http_request("GET", "https://staging.tailtag.app/admin/", actor=None)
    with pytest.raises(ValueError):
        matrix._http_request("GET", "//staging.tailtag.app/admin/", actor=None)


@pytest.mark.django_db(transaction=True)
def test_http_seam_exercises_real_local_login_csrf_and_isolated_cookies(
    matrix: ModuleType,
    live_server: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#243 auth/CSRF: one staff cookie jar cannot authorize another actor."""
    monkeypatch.setattr(matrix, "_STAGING_ORIGIN", live_server.url)
    staff = create_exact_managed_operator()
    owner = User.objects.create_user("local-http-matrix-owner")
    profile = PlayerProfile.objects.create(user=owner)
    staff_actor: dict[str, object] = {
        "role": "managed",
        "actor_id": staff.pk,
        "cookies": CookieJar(),
        "csrf": None,
    }
    unrelated_actor: dict[str, object] = {
        "role": "unrelated",
        "actor_id": owner.pk,
        "cookies": CookieJar(),
        "csrf": None,
    }

    login_form = cast(
        Mapping[str, Any],
        matrix._http_request("GET", "/admin/login/", actor=staff_actor),
    )
    assert login_form["status"] == 200
    match = re.search(
        rb'name="csrfmiddlewaretoken" value="([^"]+)"', login_form["body"]
    )
    assert match is not None
    csrf = match.group(1).decode("ascii")
    login_body = urlencode(
        {
            "username": staff.clerk_user_id,
            "password": INITIAL_PASSWORD,
            "csrfmiddlewaretoken": csrf,
        }
    ).encode()
    login = cast(
        Mapping[str, Any],
        matrix._http_request(
            "POST", "/admin/login/", actor=staff_actor, body=login_body, csrf=csrf
        ),
    )
    assert login["status"] == 302
    assert matrix._http_request("GET", "/admin/", actor=staff_actor)["status"] == 200
    assert (
        matrix._http_request("GET", "/admin/", actor=unrelated_actor)["status"] == 302
    )

    change_path = f"/admin/profiles/playerprofile/{profile.pk}/change/"
    owner_login = matrix._http_request("GET", "/admin/login/", actor=unrelated_actor)
    owner_csrf_match = re.search(
        rb'name="csrfmiddlewaretoken" value="([^"]+)"', owner_login["body"]
    )
    assert owner_csrf_match is not None
    owner_csrf = owner_csrf_match.group(1).decode("ascii")
    owner_denial = matrix._http_request(
        "POST",
        change_path,
        actor=unrelated_actor,
        body=urlencode({"csrfmiddlewaretoken": owner_csrf}).encode(),
        csrf=owner_csrf,
    )
    assert owner_denial["status"] == 302
    assert owner_denial["headers"]["Location"].startswith("/admin/login/")
    profile.refresh_from_db()
    assert profile.is_enabled is True
    assert OperatorAuditEvent.objects.count() == 0
    change_form = cast(
        Mapping[str, Any],
        matrix._http_request("GET", change_path, actor=staff_actor),
    )
    assert change_form["status"] == 200
    change_match = re.search(
        rb'name="csrfmiddlewaretoken" value="([^"]+)"', change_form["body"]
    )
    assert change_match is not None
    change_csrf = change_match.group(1).decode("ascii")
    rejected = cast(
        Mapping[str, Any],
        matrix._http_request("POST", change_path, actor=staff_actor, body=b""),
    )
    profile.refresh_from_db()
    assert rejected["status"] == 403
    assert profile.is_enabled is True
    assert OperatorAuditEvent.objects.count() == 0
    submitted = cast(
        Mapping[str, Any],
        matrix._http_request(
            "POST",
            change_path,
            actor=staff_actor,
            body=urlencode({"csrfmiddlewaretoken": change_csrf}).encode(),
            csrf=change_csrf,
        ),
    )
    profile.refresh_from_db()
    assert submitted["status"] == 302
    assert profile.is_enabled is False
    assert (
        OperatorAuditEvent.objects.filter(
            actor=staff,
            action=OperatorAction.SET_PROFILE_ENABLED,
            affected_record_type=OperatorTargetType.PLAYER_PROFILE,
            affected_record_id=profile.pk,
            outcome=OperatorAuditOutcome.SUCCEEDED,
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_managed_authentication_uses_pinned_actor_and_real_admin_http_login(
    matrix: ModuleType,
    live_server: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: one hidden password logs in the exact managed User over CSRF HTTP."""
    create_owned_baseline()
    managed = create_exact_managed_operator()
    create_exact_limited_operator()
    unrelated = User(clerk_user_id="unrelated-managed-password-owner", is_staff=True)
    unrelated.set_password("unrelated-distinct-password")
    unrelated.save()
    output = HiddenInputTerminal()
    prompts: list[str] = []
    requests: list[tuple[str, str, bytes | None]] = []
    original_http = matrix._http_request
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(matrix, "_STAGING_ORIGIN", live_server.url)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    monkeypatch.setattr(matrix, "_active_identity", IDENTITY)

    def hidden_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return INITIAL_PASSWORD

    def observe_http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: bytes | None = None,
        csrf: str | None = None,
    ) -> Mapping[str, Any]:
        requests.append((method, path, body))
        return cast(
            Mapping[str, Any],
            original_http(method, path, actor=actor, body=body, csrf=csrf),
        )

    monkeypatch.setattr(getpass, "getpass", hidden_input)
    monkeypatch.setattr(matrix, "_http_request", observe_http)

    actor = cast(Mapping[str, Any], matrix._authenticate("managed"))

    assert len(prompts) == 1
    assert "password" in prompts[0].lower()
    assert "identifier" not in prompts[0].lower()
    assert actor["actor_id"] == managed.pk
    assert [(method, path) for method, path, _ in requests] == [
        ("GET", "/admin/login/"),
        ("POST", "/admin/login/"),
        ("GET", "/admin/"),
    ]
    submitted = dict(parse_qsl(cast(bytes, requests[1][2]).decode()))
    assert submitted["username"] == managed.clerk_user_id
    assert submitted["password"] == INITIAL_PASSWORD
    assert submitted["csrfmiddlewaretoken"]
    assert "username" not in repr(actor)
    assert INITIAL_PASSWORD not in repr(actor) + output.getvalue()
    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_wrong_managed_password_stops_before_case_submission(
    matrix: ModuleType,
    live_server: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: a wrong password cannot reach a sensitive case POST."""
    create_owned_baseline()
    create_exact_managed_operator()
    create_exact_limited_operator()
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", HiddenInputTerminal())
    monkeypatch.setattr(matrix, "_STAGING_ORIGIN", live_server.url)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    monkeypatch.setattr(matrix, "_active_identity", IDENTITY)
    monkeypatch.setattr(getpass, "getpass", lambda _prompt="": "wrong-managed-password")
    original_http = matrix._http_request
    requests: list[tuple[str, str]] = []

    def observe_http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: bytes | None = None,
        csrf: str | None = None,
    ) -> Mapping[str, Any]:
        requests.append((method, path))
        return cast(
            Mapping[str, Any],
            original_http(method, path, actor=actor, body=body, csrf=csrf),
        )

    monkeypatch.setattr(matrix, "_http_request", observe_http)
    with pytest.raises(ValueError):
        matrix._authenticate("managed")
    assert all(path == "/admin/login/" for _, path in requests)
    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "drift", ("group", "direct_permission", "second_retained_actor")
)
def test_synthetic_emergency_authentication_refuses_inexact_singleton_before_http(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    """A valid password cannot bypass the synthetic emergency role boundary."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    actor = User.objects.get(pk=sessions["emergency"]["actor_id"])
    actor.clerk_user_id = "staging_emergency_matrix_243"
    actor.save(update_fields={"clerk_user_id"})
    if drift == "group":
        actor.groups.add(Group.objects.create(name="unexpected matrix emergency group"))  # pyright: ignore[reportUnknownMemberType]
    elif drift == "direct_permission":
        actor.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
            Permission.objects.get(
                content_type__app_label="accounts", codename="view_user"
            )
        )
    else:
        User.objects.create_user("staging_emergency_retained_matrix_243")

    def account_states() -> dict[int, tuple[str, bool, bool, str]]:
        return {
            user.pk: (
                user.clerk_user_id,
                user.is_staff,
                cast(bool, user.is_superuser),  # pyright: ignore[reportUnknownMemberType]
                cast(str, user.password),  # pyright: ignore[reportUnknownMemberType]
            )
            for user in User.objects.all()
        }

    before = account_states()
    output = HiddenInputTerminal()
    prompts: list[str] = []
    answers = iter((actor.clerk_user_id, "local-only-emergency-test-password"))
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    monkeypatch.setattr(matrix, "_active_identity", IDENTITY)

    def hidden_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return next(answers)

    def forbidden_http(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("inexact synthetic emergency actor reached HTTP")

    monkeypatch.setattr(getpass, "getpass", hidden_input)
    monkeypatch.setattr(matrix, "_http_request", forbidden_http)

    with pytest.raises(ValueError):
        matrix._authenticate("emergency")

    assert len(prompts) == 2
    assert account_states() == before
    assert OperatorAuditEvent.objects.count() == 0
    assert actor.clerk_user_id not in output.getvalue()
    assert "local-only-emergency-test-password" not in output.getvalue()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "identifier", ("staging_emergency_matrix_243", "existing_breakglass_matrix_243")
)
def test_exact_emergency_actor_can_reach_admin_login_http(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    identifier: str,
) -> None:
    """A valid synthetic actor and existing break-glass actor retain Case-5 access."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    actor = User.objects.get(pk=sessions["emergency"]["actor_id"])
    actor.clerk_user_id = identifier
    actor.save(update_fields={"clerk_user_id"})
    answers = iter((identifier, "local-only-emergency-test-password"))
    requests: list[tuple[str, str]] = []
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", HiddenInputTerminal())
    monkeypatch.setattr(getpass, "getpass", lambda _prompt="": next(answers))
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    monkeypatch.setattr(matrix, "_active_identity", IDENTITY)

    class LoginReached(Exception):
        pass

    def observe_http(method: str, path: str, **_kwargs: object) -> NoReturn:
        requests.append((method, path))
        raise LoginReached

    monkeypatch.setattr(matrix, "_http_request", observe_http)

    with pytest.raises(LoginReached):
        matrix._authenticate("emergency")

    assert requests == [("GET", "/admin/login/")]
    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_managed_actor_drift_during_hidden_password_fails_before_post(
    matrix: ModuleType,
    live_server: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-4: a newly selected member with the same password cannot replace the pin."""
    create_owned_baseline()
    managed = create_exact_managed_operator()
    create_exact_limited_operator()
    group = managed.groups.get()  # pyright: ignore[reportUnknownMemberType]
    prompts: list[str] = []
    requests: list[tuple[str, str]] = []
    original_http = matrix._http_request
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", HiddenInputTerminal())
    monkeypatch.setattr(matrix, "_STAGING_ORIGIN", live_server.url)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    monkeypatch.setattr(matrix, "_active_identity", IDENTITY)

    def hidden_input(prompt: str = "") -> str:
        prompts.append(prompt)
        managed.groups.clear()  # pyright: ignore[reportUnknownMemberType]
        replacement = User(
            clerk_user_id="new-managed-after-hidden-prompt", is_staff=True
        )
        replacement.set_password(INITIAL_PASSWORD)
        replacement.save()
        replacement.groups.add(group)  # pyright: ignore[reportUnknownMemberType]
        return INITIAL_PASSWORD

    def observe_http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: bytes | None = None,
        csrf: str | None = None,
    ) -> Mapping[str, Any]:
        requests.append((method, path))
        if method == "POST":
            pytest.fail("changed managed actor reached admin or case submission")
        return cast(
            Mapping[str, Any],
            original_http(method, path, actor=actor, body=body, csrf=csrf),
        )

    monkeypatch.setattr(getpass, "getpass", hidden_input)
    monkeypatch.setattr(matrix, "_http_request", observe_http)
    with pytest.raises(ValueError):
        matrix._authenticate("managed")
    assert len(prompts) == 1
    assert "identifier" not in prompts[0].lower()
    assert all(method != "POST" for method, _ in requests)
    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_managed_login_rejects_admin_session_bound_to_different_actor(
    matrix: ModuleType,
    live_server: Any,
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsWrapper,
) -> None:
    """AC-4: admin HTTP success for another User cannot authorize managed cases."""
    from django.contrib.sessions.backends.db import SessionStore

    create_owned_baseline()
    managed = create_exact_managed_operator()
    create_exact_limited_operator()
    other = User(clerk_user_id="different-staff-session-actor", is_staff=True)
    other.set_password("different-staff-password")
    other.save()
    requests: list[tuple[str, str, int]] = []
    original_http = matrix._http_request
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", HiddenInputTerminal())
    monkeypatch.setattr(matrix, "_STAGING_ORIGIN", live_server.url)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    monkeypatch.setattr(matrix, "_active_identity", IDENTITY)
    monkeypatch.setattr(getpass, "getpass", lambda _prompt="": INITIAL_PASSWORD)

    def swapped_session_http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: bytes | None = None,
        csrf: str | None = None,
    ) -> Mapping[str, Any]:
        response = cast(
            Mapping[str, Any],
            original_http(method, path, actor=actor, body=body, csrf=csrf),
        )
        requests.append((method, path, cast(int, response["status"])))
        if method == "POST" and path == "/admin/login/" and response["status"] == 302:
            session_key = next(
                cookie.value
                for cookie in actor["cookies"]
                if cookie.name == settings.SESSION_COOKIE_NAME
            )
            session = SessionStore(session_key=session_key)
            session["_auth_user_id"] = str(other.pk)
            session["_auth_user_hash"] = other.get_session_auth_hash()
            session.save()
        return response

    monkeypatch.setattr(matrix, "_http_request", swapped_session_http)
    with pytest.raises(ValueError):
        matrix._authenticate("managed")

    assert managed.pk != other.pk
    assert ("POST", "/admin/login/", 302) in requests
    assert ("GET", "/admin/", 200) in requests
    assert all(path in {"/admin/login/", "/admin/"} for _, path, _ in requests)
    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_limited_login_rotates_csrf_for_real_audited_denial(
    matrix: ModuleType,
    live_server: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The next POST must reach permission auditing, not fail CSRF middleware."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    limited_user = User.objects.get(pk=sessions["limited"]["actor_id"])
    # A legacy hash would make User.check_password() save an upgrade directly.
    # Only the actual HTTP login may perform the normal authentication writes.
    legacy_hash = PBKDF2PasswordHasher().encode(
        INITIAL_PASSWORD, "local-test-upgrade", iterations=1
    )
    limited_user.password = legacy_hash
    limited_user.save()
    direct_auth_sql: list[str] = []
    inputs = iter((INITIAL_PASSWORD,))
    prompts: list[str] = []
    terminal_output = HiddenInputTerminal()
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", terminal_output)
    monkeypatch.setattr(matrix, "_STAGING_ORIGIN", live_server.url)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    original_authenticate = matrix._authenticate
    original_http = matrix._http_request
    authenticated: list[Mapping[str, Any]] = []

    def hidden_input(prompt: str = "") -> str:
        prompts.append(prompt)
        return next(inputs)

    def record_queries(
        execute: Callable[..., Any],
        sql: str,
        params: object,
        many: bool,
        context: object,
    ) -> Any:
        direct_auth_sql.append(sql)
        return execute(sql, params, many, context)

    def authenticate(role: str) -> Mapping[str, Any]:
        if role == "limited":
            with connection.execute_wrapper(record_queries):
                actor = original_authenticate(role)
            authenticated.append(actor)
            return actor
        return sessions[role]

    def http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: object = None,
        csrf: object = None,
    ) -> Mapping[str, Any]:
        if actor["role"] == "limited":
            return original_http(method, path, actor=actor, body=body, csrf=csrf)
        assert actor["role"] == "owner"
        if path == "/api/me/":
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"id": identity.owner_id}).encode(),
            }
        if method == "PUT":
            return {"status": 503, "headers": {}, "body": b""}
        return owner_login_redirect(path)

    monkeypatch.setattr(getpass, "getpass", hidden_input)
    monkeypatch.setattr(matrix, "_authenticate", authenticate)
    monkeypatch.setattr(matrix, "_http_request", http)
    with warnings.catch_warnings():
        result = matrix.run(IDENTITY)

    assert prompts == ["limited admin password: "]
    assert len(authenticated) == 1
    assert all(result["cases"][case] == "PASS" for case in ("1", "2", "4", "7"))
    assert result["classification"] != "PASS"
    event = OperatorAuditEvent.objects.get()
    assert event.actor.pk == limited_user.pk
    assert event.affected_record_id == identity.second_fursuit_id
    assert event.affected_record_type == OperatorTargetType.FURSUIT
    assert event.action == OperatorAction.SET_FURSUIT_ENABLED
    assert event.actor_class == OperatorActorClass.UNAUTHORIZED_ACTOR
    assert event.outcome == OperatorAuditOutcome.DENIED
    assert Fursuit.objects.get(pk=identity.second_fursuit_id).is_enabled is True
    assert direct_auth_sql
    assert all(
        sql.lstrip()
        .upper()
        .startswith(("SELECT", "BEGIN", "COMMIT", "SET", "ROLLBACK"))
        for sql in direct_auth_sql
    )
    limited_user.refresh_from_db()
    # The actual HTTP login upgraded the legacy hash.
    assert limited_user.password != legacy_hash  # pyright: ignore[reportUnknownMemberType]
    assert limited_user.clerk_user_id not in repr(authenticated[0])
    assert limited_user.clerk_user_id not in terminal_output.getvalue()
    assert INITIAL_PASSWORD not in repr(authenticated[0]) + terminal_output.getvalue()


@pytest.mark.django_db(transaction=True)
def test_wrong_limited_password_stops_before_case_submission(
    matrix: ModuleType,
    live_server: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A derived limited identity still requires its own valid hidden password."""
    create_owned_baseline()
    limited = create_exact_limited_operator()
    create_exact_managed_operator()
    terminal_output = HiddenInputTerminal()
    prompts: list[str] = []
    requests: list[tuple[str, str]] = []
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", terminal_output)
    monkeypatch.setattr(matrix, "_STAGING_ORIGIN", live_server.url)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    monkeypatch.setattr(matrix, "_active_identity", IDENTITY)

    def hidden(prompt: str = "") -> str:
        prompts.append(prompt)
        return "wrong-limited-password"

    original_http = matrix._http_request

    def observe_http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: bytes | None = None,
        csrf: str | None = None,
    ) -> Mapping[str, Any]:
        requests.append((method, path))
        return cast(
            Mapping[str, Any],
            original_http(method, path, actor=actor, body=body, csrf=csrf),
        )

    monkeypatch.setattr(getpass, "getpass", hidden)
    monkeypatch.setattr(matrix, "_http_request", observe_http)
    with pytest.raises(ValueError):
        matrix._authenticate("limited")

    assert prompts == ["limited admin password: "]
    assert all(path == "/admin/login/" for _, path in requests)
    assert limited.clerk_user_id not in terminal_output.getvalue()
    assert "wrong-limited-password" not in terminal_output.getvalue()
    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_getpass_warning_refuses_echoed_fallback_without_retry_or_leak(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """getpass's warning must abort before an echoed fallback can read a secret."""
    identity = create_owned_baseline()
    role_sessions(identity)
    terminal_output = HiddenInputTerminal()
    monkeypatch.setattr(sys, "stdin", HiddenInputTerminal())
    monkeypatch.setattr(sys, "stdout", terminal_output)
    monkeypatch.setattr(matrix, "_guard_target", accept_target)
    calls: list[str] = []
    private_warning = "local-getpass-private-warning-marker"

    def unsafe_getpass(prompt: str = "") -> str:
        calls.append("hidden_prompt")
        warnings.warn(private_warning, getpass.GetPassWarning, stacklevel=1)
        calls.append("echoed_fallback")
        return "must-never-read-a-fallback-secret"

    def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
        pytest.fail("failed hidden input reached plain input or HTTP")

    monkeypatch.setattr(getpass, "getpass", unsafe_getpass)
    monkeypatch.setattr(builtins, "input", forbidden)
    monkeypatch.setattr(matrix, "_http_request", forbidden)
    with warnings.catch_warnings():
        result = matrix.run(IDENTITY)

    assert calls == ["hidden_prompt"]
    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is False
    assert all(value == "NOT_EXERCISED" for value in result["cases"].values())
    assert private_warning not in repr(result) + terminal_output.getvalue()
    assert json.loads(terminal_output.getvalue()) == result
    assert OperatorAuditEvent.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_ambiguous_owner_mutation_stops_without_retry_or_next_actor(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#243 A/reliability: a timed-out submitted attempt is indeterminate."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    authenticated: list[str] = []
    requests: list[tuple[str, str, str]] = []
    secret = "private-owner-token-must-be-redacted"
    monkeypatch.setattr(matrix, "_guard_target", accept_target)

    def authenticate(role: str) -> Mapping[str, Any]:
        authenticated.append(role)
        return sessions[role]

    def http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: object = None,
        csrf: object = None,
    ) -> Mapping[str, object]:
        del body
        role = cast(str, actor["role"])
        requests.append((role, method, path))
        if path == "/api/me/":
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": f'{{"id": {identity.owner_id}}}'.encode(),
            }
        if method == "POST":
            assert role == "owner"
            assert csrf is not None
            raise TimeoutError(secret)
        return owner_login_redirect(path) if role == "owner" else denied_response()

    monkeypatch.setattr(matrix, "_authenticate", authenticate)
    monkeypatch.setattr(matrix, "_http_request", http)

    result = cast(Mapping[str, Any], matrix.run(IDENTITY))
    rendered = capsys.readouterr()

    assert result["classification"] != "PASS"
    assert result["mutation_may_have_begun"] is True
    assert result["cases"]["1"] != "PASS"
    assert authenticated == ["limited", "managed", "emergency", "owner"]
    assert len([request for request in requests if request[1] == "POST"]) == 1
    assert OperatorAuditEvent.objects.count() == 0
    assert secret not in repr(result) + rendered.out + rendered.err


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "audit_defect", ("missing", "wrong_actor", "wrong_target", "duplicate")
)
def test_limited_denial_requires_one_exact_actor_target_audit_row(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    audit_defect: str,
) -> None:
    """#243 cases 2/4/7: HTTP denial alone cannot establish audit evidence."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    authenticated: list[str] = []
    requests: list[tuple[str, str, str]] = []
    monkeypatch.setattr(matrix, "_guard_target", accept_target)

    def authenticate(role: str) -> Mapping[str, Any]:
        authenticated.append(role)
        return sessions[role]

    def http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: object = None,
        csrf: object = None,
    ) -> Mapping[str, object]:
        del body
        role = cast(str, actor["role"])
        requests.append((role, method, path))
        if path == "/api/me/":
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": f'{{"id": {identity.owner_id}}}'.encode(),
            }
        if role == "limited" and method == "POST":
            assert csrf is not None
            assert f"/{identity.second_fursuit_id}/" in path
            if audit_defect != "missing":
                OperatorAuditEvent.objects.create(
                    action=OperatorAction.SET_FURSUIT_ENABLED,
                    actor_id=(
                        sessions["managed"]["actor_id"]
                        if audit_defect == "wrong_actor"
                        else sessions["limited"]["actor_id"]
                    ),
                    actor_class=OperatorActorClass.UNAUTHORIZED_ACTOR,
                    affected_record_type=OperatorTargetType.FURSUIT,
                    affected_record_id=(
                        identity.first_fursuit_id
                        if audit_defect == "wrong_target"
                        else identity.second_fursuit_id
                    ),
                    outcome=OperatorAuditOutcome.DENIED,
                )
                if audit_defect == "duplicate":
                    OperatorAuditEvent.objects.create(
                        action=OperatorAction.SET_FURSUIT_ENABLED,
                        actor_id=sessions["limited"]["actor_id"],
                        actor_class=OperatorActorClass.UNAUTHORIZED_ACTOR,
                        affected_record_type=OperatorTargetType.FURSUIT,
                        affected_record_id=identity.second_fursuit_id,
                        outcome=OperatorAuditOutcome.DENIED,
                    )
        return owner_login_redirect(path) if role == "owner" else denied_response()

    monkeypatch.setattr(matrix, "_authenticate", authenticate)
    monkeypatch.setattr(matrix, "_http_request", http)

    result = cast(Mapping[str, Any], matrix.run(IDENTITY))

    assert result["classification"] != "PASS"
    assert all(result["cases"][case] != "PASS" for case in ("2", "4", "7"))
    assert authenticated == ["limited", "managed", "emergency", "owner"]
    assert (
        len(
            [
                request
                for request in requests
                if request[0] == "limited" and request[1] == "POST"
            ]
        )
        == 1
    )
    assert not any(role in {"managed", "emergency"} for role, _, _ in requests)


@pytest.mark.django_db(transaction=True)
def test_exact_denial_advances_only_its_cases_before_owner_session_failure(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#243 B/session prerequisite: cases 2/4/7 share one evidenced denial."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    authenticated: list[str] = []
    posts: list[tuple[str, str]] = []
    monkeypatch.setattr(matrix, "_guard_target", accept_target)

    def authenticate(role: str) -> Mapping[str, Any]:
        authenticated.append(role)
        return sessions[role]

    def http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: object = None,
        csrf: object = None,
    ) -> Mapping[str, object]:
        del body
        role = cast(str, actor["role"])
        if path == "/api/me/":
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": f'{{"id": {identity.owner_id}}}'.encode(),
            }
        if method in {"POST", "PUT"}:
            posts.append((role, path))
            if role == "limited":
                assert method == "POST" and csrf is not None
                assert f"/{identity.second_fursuit_id}/" in path
                OperatorAuditEvent.objects.create(
                    action=OperatorAction.SET_FURSUIT_ENABLED,
                    actor_id=sessions["limited"]["actor_id"],
                    actor_class=OperatorActorClass.UNAUTHORIZED_ACTOR,
                    affected_record_type=OperatorTargetType.FURSUIT,
                    affected_record_id=identity.second_fursuit_id,
                    outcome=OperatorAuditOutcome.DENIED,
                )
                return denied_response()
            if method == "PUT":
                assert role == "owner"
                assert f"/{identity.convention_id}/" in path
                assert f"/{identity.first_fursuit_id}/" in path
                return {"status": 503, "headers": {}, "body": b""}
        return owner_login_redirect(path) if role == "owner" else denied_response()

    monkeypatch.setattr(matrix, "_authenticate", authenticate)
    monkeypatch.setattr(matrix, "_http_request", http)

    result = cast(Mapping[str, Any], matrix.run(IDENTITY))

    assert result["classification"] != "PASS"
    assert all(result["cases"][case] == "PASS" for case in ("1", "2", "4", "7"))
    assert all(result["cases"][case] != "PASS" for case in ("3", "5", "6", "8", "9"))
    assert sum(role == "limited" for role, _ in posts) == 1
    assert posts[-1][0] == "owner" and "catch-session" in posts[-1][1]
    assert authenticated == ["limited", "managed", "emergency", "owner"]


@pytest.mark.parametrize("file_state", ("matching", "mismatched", "missing"))
def test_deployed_source_hashes_never_claim_control_review_or_test_execution(
    unconfirmed_matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    file_state: str,
) -> None:
    """Matching deployed bytes prove correlation only, never external evidence."""
    control_files = cast(tuple[str, ...], tuple(unconfirmed_matrix._CONTROL_FILES))
    assert control_files
    payload = b"local synthetic deployed control source"
    hashes = {path: hashlib.sha256(payload).hexdigest() for path in control_files}
    for relative in control_files:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    first = tmp_path / control_files[0]
    if file_state == "mismatched":
        first.write_bytes(b"changed local control source")
    elif file_state == "missing":
        first.unlink()

    def deployed_root(root: str) -> Path:
        assert root == "/app"
        return tmp_path

    monkeypatch.setattr(unconfirmed_matrix, "Path", deployed_root)
    monkeypatch.setattr(unconfirmed_matrix, "_CONTROL_HASHES", hashes)
    result = unconfirmed_matrix._review_deployed_controls()

    assert result == {
        "deployed_control_hash_match": "PASS" if file_state == "matching" else "FAIL"
    }
    assert "control_review" not in result
    assert "deterministic_evidence" not in result


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("review_mode", "reset_mode", "decommission_mode"),
    (
        ("hash_failure", "not_called", "not_called"),
        ("complete", "receipt_failure", "not_called"),
        ("complete", "changed_audit", "not_called"),
        ("complete", "clean_reset", "receipt_failure"),
        ("complete", "clean_reset", "still_active"),
        ("complete", "clean_reset", "direct_permission_retained"),
        ("complete", "clean_reset", "swapped_actor"),
        ("complete", "clean_reset", "changed_audit"),
        ("complete", "clean_reset", "managed_drift"),
        ("complete", "clean_reset", "fixture_drift"),
        ("complete", "clean_reset", "complete"),
        ("complete", "clean_reset", "synthetic_still_active"),
        ("complete", "clean_reset", "synthetic_complete"),
    ),
)
def test_two_successes_case9_review_and_reset_audit_retention(
    matrix: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    review_mode: str,
    reset_mode: str,
    decommission_mode: str,
    live_server: Any,
) -> None:
    """#243 C–F: live success needs cleanup and still awaits external case-9 proof."""
    review_ok = review_mode == "complete"
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    synthetic_emergency = decommission_mode.startswith("synthetic_")
    if synthetic_emergency:
        emergency_actor = User.objects.get(pk=sessions["emergency"]["actor_id"])
        emergency_actor.clerk_user_id = "staging_emergency_matrix_243"
        emergency_actor.save(update_fields={"clerk_user_id"})
    authenticated: list[str] = []
    mutations: list[tuple[str, str, str]] = []
    reviews: list[str] = []
    reset_calls: list[str] = []
    decommission_calls: list[str] = []
    emergency_decommission_calls: list[str] = []
    observations: list[str] = []
    case9_visits: set[tuple[str, str]] = set()
    expected_case9: set[tuple[str, str]] = set()
    real_http = local_admin_transport(
        live_server, User.objects.get(pk=sessions["emergency"]["actor_id"])
    )

    def record_guard(_: object) -> None:
        observations.append("guard")

    monkeypatch.setattr(matrix, "_guard_target", record_guard)

    def authenticate(role: str) -> Mapping[str, Any]:
        authenticated.append(role)
        return sessions[role]

    def http(
        method: str,
        path: str,
        *,
        actor: Mapping[str, Any],
        body: object = None,
        csrf: object = None,
    ) -> Mapping[str, object]:
        role = cast(str, actor["role"])
        if path == "/api/me/":
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"id": identity.owner_id}).encode(),
            }
        if method not in {"POST", "PUT"}:
            if role == "owner":
                return owner_login_redirect(path)
            if OperatorAuditEvent.objects.count() == 3:
                case9_visits.add((method, path))
            return real_http(method, path, body)
        assert "guard" in observations
        observations.clear()
        mutations.append((role, method, path))
        if role == "owner" and method == "POST":
            assert csrf is not None
            return owner_login_redirect(path)
        if role == "limited" and method == "POST":
            assert csrf is not None
            assert f"/{identity.second_fursuit_id}/" in path
            OperatorAuditEvent.objects.create(
                action=OperatorAction.SET_FURSUIT_ENABLED,
                actor_id=sessions["limited"]["actor_id"],
                actor_class=OperatorActorClass.UNAUTHORIZED_ACTOR,
                affected_record_type=OperatorTargetType.FURSUIT,
                affected_record_id=identity.second_fursuit_id,
                outcome=OperatorAuditOutcome.DENIED,
            )
            return denied_response()
        if role == "owner" and method == "PUT":
            assert f"/{identity.first_fursuit_id}/" in path
            activation = FursuitActivation.objects.get(
                fursuit_id=identity.first_fursuit_id,
                convention_id=identity.convention_id,
            )
            session = create_catch_session(activation=activation)
            expected_case9.update(
                (method, path) for method, path, _ in case9_routes(identity).values()
            )
            response = {
                "fursuit_id": identity.first_fursuit_id,
                "convention_id": identity.convention_id,
                "is_active": True,
                "started_at": session.started_at.isoformat().replace("+00:00", "Z"),
                "expires_at": session.expires_at.isoformat().replace("+00:00", "Z"),
                "ended_at": None,
                "end_reason": None,
            }
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(response).encode(),
            }
        if (
            role == "managed"
            and method == "POST"
            and "/profiles/playerprofile/" in path
        ):
            assert csrf is not None
            assert (
                f"/{PlayerProfile.objects.get(user_id=identity.owner_id).pk}/" in path
            )
            changed = set_profile_enabled(
                profile_id=PlayerProfile.objects.get(user_id=identity.owner_id).pk,
                is_enabled=False,
            )
            assert changed.changed
            OperatorAuditEvent.objects.create(
                action=OperatorAction.SET_PROFILE_ENABLED,
                actor_id=sessions["managed"]["actor_id"],
                actor_class=OperatorActorClass.OPERATOR,
                affected_record_type=OperatorTargetType.PLAYER_PROFILE,
                affected_record_id=changed.value.pk,
                outcome=OperatorAuditOutcome.SUCCEEDED,
            )
            return {"status": 302, "headers": {"Location": path}, "body": b""}
        if role == "emergency" and method == "POST" and "/fursuits/fursuit/" in path:
            assert csrf is not None
            assert f"/{identity.second_fursuit_id}/" in path
            changed = set_fursuit_enabled(
                fursuit_id=cast(int, identity.second_fursuit_id), is_enabled=False
            )
            assert changed.changed
            OperatorAuditEvent.objects.create(
                action=OperatorAction.SET_FURSUIT_ENABLED,
                actor_id=sessions["emergency"]["actor_id"],
                actor_class=OperatorActorClass.EMERGENCY_SUPERUSER,
                affected_record_type=OperatorTargetType.FURSUIT,
                affected_record_id=identity.second_fursuit_id,
                outcome=OperatorAuditOutcome.SUCCEEDED,
            )
            return {"status": 302, "headers": {"Location": path}, "body": b""}
        assert role in {"managed", "emergency"}
        case9_visits.add((method, path))
        return real_http(method, path, body)

    def review_controls() -> Mapping[str, str]:
        reviews.append("exact-deployment-controls")
        assert mutations == []
        assert OperatorAuditEvent.objects.count() == 0
        assert FursuitCatchSession.objects.count() == 0
        return {"deployed_control_hash_match": "PASS" if review_ok else "FAIL"}

    def reset_receipt() -> Mapping[str, str]:
        assert connection.connection is None
        reset_calls.append("handoff")
        observations.clear()
        if reset_mode == "not_called":
            pytest.fail("case 9 failed review but reset handoff began")
        if reset_mode == "receipt_failure":
            return {"classification": "FAIL_RESET"}
        FursuitCatchSession.objects.all().delete()
        old_activation_ids = set(FursuitActivation.objects.values_list("pk", flat=True))
        old_enrollment_ids = set(
            ConventionEnrollment.objects.values_list("pk", flat=True)
        )
        FursuitActivation.objects.all().delete()
        ConventionEnrollment.objects.all().delete()
        for user_id in (identity.owner_id, identity.catcher_id):
            ConventionEnrollment.objects.create(
                user_id=user_id, convention=identity.convention, is_active=True
            )
        for fursuit_id in (identity.first_fursuit_id, identity.second_fursuit_id):
            FursuitActivation.objects.create(
                fursuit_id=fursuit_id,
                convention=identity.convention,
                is_active=True,
                activated_at=timezone.now(),
            )
        assert not old_activation_ids.intersection(
            FursuitActivation.objects.values_list("pk", flat=True)
        )
        assert not old_enrollment_ids.intersection(
            ConventionEnrollment.objects.values_list("pk", flat=True)
        )
        PlayerProfile.objects.filter(user_id=identity.owner_id).update(is_enabled=True)
        Fursuit.objects.filter(pk=identity.second_fursuit_id).update(is_enabled=True)
        assert validate_baseline(identity)["sessions"] == 0
        if reset_mode == "changed_audit":
            OperatorAuditEvent.objects.filter(
                action=OperatorAction.SET_PROFILE_ENABLED
            ).update(outcome=OperatorAuditOutcome.REJECTED)
        return {"classification": "PASS"}

    def decommission_receipt() -> Mapping[str, str]:
        assert connection.connection is None
        assert "guard" in observations  # Fresh guard after reset.
        observations.clear()
        if synthetic_emergency:
            assert emergency_decommission_calls == ["handoff"]
            if decommission_mode == "synthetic_still_active":
                pytest.fail("limited cleanup began before synthetic emergency proof")
        decommission_calls.append("handoff")
        if decommission_mode == "not_called":
            pytest.fail("decommission started before reset/audit proof")
        if decommission_mode == "receipt_failure":
            return {"classification": "FAIL_DECOMMISSION"}
        limited = User.objects.get(pk=sessions["limited"]["actor_id"])
        if decommission_mode != "still_active":
            limited.is_staff = False
            limited.set_unusable_password()
            limited.save()
            limited.groups.get().permissions.clear()  # pyright: ignore[reportUnknownMemberType]
        if decommission_mode == "direct_permission_retained":
            limited.user_permissions.add(  # pyright: ignore[reportUnknownMemberType]
                Permission.objects.get(
                    content_type__app_label="profiles", codename="view_playerprofile"
                )
            )
        if decommission_mode == "swapped_actor":
            group = limited.groups.get()  # pyright: ignore[reportUnknownMemberType]
            limited.groups.clear()  # pyright: ignore[reportUnknownMemberType]
            replacement = User.objects.create_user("replacement-inactive-operator")
            replacement.set_unusable_password()
            replacement.save()
            replacement.groups.add(group)  # pyright: ignore[reportUnknownMemberType]
        if decommission_mode == "changed_audit":
            OperatorAuditEvent.objects.filter(
                action=OperatorAction.SET_PROFILE_ENABLED
            ).update(outcome=OperatorAuditOutcome.REJECTED)
        if decommission_mode == "managed_drift":
            managed = User.objects.get(pk=sessions["managed"]["actor_id"])
            managed.is_staff = False
            managed.save()
        if decommission_mode == "fixture_drift":
            PlayerProfile.objects.filter(user_id=identity.owner_id).update(
                is_enabled=False
            )
        return {"classification": "PASS"}

    def emergency_decommission_receipt() -> Mapping[str, str]:
        assert connection.connection is None
        assert reset_calls == ["handoff"]
        assert decommission_calls == []  # Emergency cleanup precedes limited cleanup.
        emergency_decommission_calls.append("handoff")
        if decommission_mode == "synthetic_complete":
            emergency_actor = User.objects.get(pk=sessions["emergency"]["actor_id"])
            emergency_actor.is_staff = False
            emergency_actor.is_superuser = False
            emergency_actor.set_unusable_password()
            emergency_actor.save(update_fields={"is_staff", "is_superuser", "password"})
        return {"classification": "PASS"}

    monkeypatch.setattr(
        matrix,
        "_await_emergency_decommission_receipt",
        emergency_decommission_receipt,
        raising=False,
    )
    monkeypatch.setattr(matrix, "_await_decommission_receipt", decommission_receipt)
    monkeypatch.setattr(matrix, "_authenticate", authenticate)
    monkeypatch.setattr(matrix, "_http_request", http)
    monkeypatch.setattr(matrix, "_review_deployed_controls", review_controls)
    monkeypatch.setattr(matrix, "_await_reset_receipt", reset_receipt)

    result = cast(Mapping[str, Any], matrix.run(IDENTITY))

    assert result["classification"] != "PASS"
    assert result["case9_control_review"] == "NOT_EXERCISED"
    assert result["case9_deterministic_evidence"] == "NOT_EXERCISED"
    assert reviews == ["exact-deployment-controls"]
    if not review_ok:
        assert result["classification"].startswith("FAIL_")
        assert result["deployed_control_hash_match"] == "FAIL"
        assert result["mutation_may_have_begun"] is False
        assert all(value == "NOT_EXERCISED" for value in result["cases"].values())
        assert result["audit_events"] == []
        assert result["reset"] == "NOT_EXERCISED"
        assert result["decommission"] == "NOT_EXERCISED"
        assert mutations == []
        assert OperatorAuditEvent.objects.count() == 0
        assert reset_calls == []
        assert decommission_calls == []
        return
    if reset_mode == "clean_reset" and decommission_mode in {
        "complete",
        "synthetic_complete",
    }:
        assert result["classification"] == LIVE_SEQUENCE_COMPLETE
        assert "guard" in observations  # Fresh guard after decommission.
    else:
        assert result["classification"] != LIVE_SEQUENCE_COMPLETE
    if reset_mode == "clean_reset":
        assert decommission_calls == (
            [] if decommission_mode == "synthetic_still_active" else ["handoff"]
        )
    else:
        assert decommission_calls == []
    if synthetic_emergency:
        assert emergency_decommission_calls == ["handoff"]
        assert result["emergency_decommission"] == (
            "PASS" if decommission_mode == "synthetic_complete" else "NOT_EXERCISED"
        )
        if decommission_mode == "synthetic_still_active":
            assert result["classification"] == "FAIL_EMERGENCY_DECOMMISSION"
            emergency_actor = User.objects.get(pk=sessions["emergency"]["actor_id"])
            assert emergency_actor.is_staff is True
            assert cast(bool, emergency_actor.is_superuser) is True  # pyright: ignore[reportUnknownMemberType]
            assert emergency_actor.has_usable_password() is True
    else:
        assert emergency_decommission_calls == []
        assert result["emergency_decommission"] == "NOT_EXERCISED"
    if review_ok:
        assert expected_case9
        assert expected_case9 <= case9_visits
    assert all(result["cases"][case] == "PASS" for case in map(str, range(1, 9)))
    if review_ok:
        assert result["cases"]["9"] == "NOT_EXERCISED"
        assert result["deployed_control_hash_match"] == "PASS"
        subchecks = cast(Mapping[str, str], result["case9"])
        assert set(subchecks) == CASE9_SUBCHECKS
        assert set(result["case9_limitations"]) == COMBINED_EVIDENCE_SUBCHECKS
        assert all(
            subchecks[name] == "NOT_EXERCISED" for name in COMBINED_EVIDENCE_SUBCHECKS
        )
        assert all(
            subchecks[name] == "PASS"
            for name in CASE9_SUBCHECKS - COMBINED_EVIDENCE_SUBCHECKS
        )
        assert reset_calls == ["handoff"]
    else:
        assert result["cases"]["9"] != "PASS"
        assert result["deployed_control_hash_match"] == "FAIL"
        assert reset_calls == []
    assert authenticated == ["limited", "managed", "emergency", "owner"]
    assert (
        sum(
            role == "limited" and "/admin/fursuits/fursuit/" in path
            for role, _, path in mutations
        )
        == 1
    )
    assert (
        sum(
            role == "managed" and "/admin/profiles/playerprofile/" in path
            for role, _, path in mutations
        )
        == 1
    )
    assert (
        sum(
            role == "emergency" and "/admin/fursuits/fursuit/" in path
            for role, _, path in mutations
        )
        == 1
    )
    assert (
        sum(role == "owner" and method == "PUT" for role, method, _ in mutations) == 1
    )
    if (
        reset_mode in {"changed_audit", "clean_reset"}
        and decommission_mode != "fixture_drift"
    ):
        assert validate_baseline(identity)["sessions"] == 0
    elif reset_mode not in {"changed_audit", "clean_reset"}:
        assert PlayerProfile.objects.get(user_id=identity.owner_id).is_enabled is False
        assert FursuitCatchSession.objects.get().end_reason is not None


def local_admin_transport(
    live_server: Any, operator: User
) -> Callable[..., Mapping[str, Any]]:
    """Real local HTTP evidence, with a real login and valid rotated CSRF token."""
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))

    def request(method: str, path: str, body: object = None) -> Mapping[str, Any]:
        data = cast(bytes | None, body)
        if method == "POST":
            fields = dict(parse_qsl((data or b"").decode()))
            token = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
            assert token is not None
            fields["csrfmiddlewaretoken"] = token
            data = urlencode(fields).encode()
        req = Request(
            f"{live_server.url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with opener.open(req) as response:
                return {
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": response.read(131072),
                }
        except HTTPError as error:
            return {
                "status": error.code,
                "headers": dict(error.headers),
                "body": error.read(131072),
            }

    assert request("GET", "/admin/login/")["status"] == 200
    assert (
        request(
            "POST",
            "/admin/login/",
            urlencode(
                {
                    "next": "/admin/",
                    "username": operator.clerk_user_id,
                    "password": "local-only-emergency-test-password",
                }
            ).encode(),
        )["status"]
        == 200
    )
    return request


def case9_routes(identity: Any) -> dict[str, tuple[str, str, bytes | None]]:
    activation = FursuitActivation.objects.get(fursuit_id=identity.first_fursuit_id)
    session = FursuitCatchSession.objects.get(activation=activation)
    enrollment = ConventionEnrollment.objects.get(
        user_id=identity.owner_id, convention_id=identity.convention_id
    )
    return {
        "catch_add": ("GET", "/admin/catches/catch/add/", None),
        "catch_bulk_edit": ("POST", "/admin/catches/catch/", b"action=delete_selected"),
        "credential_add": (
            "GET",
            "/admin/conventions/fursuitcatchcredential/add/",
            None,
        ),
        "session_add": ("GET", "/admin/conventions/fursuitcatchsession/add/", None),
        "session_delete": (
            "GET",
            f"/admin/conventions/fursuitcatchsession/{session.pk}/delete/",
            None,
        ),
        "session_bulk_edit": (
            "POST",
            "/admin/conventions/fursuitcatchsession/",
            b"action=delete_selected",
        ),
        "session_history_edit": (
            "GET",
            f"/admin/conventions/fursuitcatchsession/{session.pk}/change/",
            None,
        ),
        "activation_add": ("GET", "/admin/conventions/fursuitactivation/add/", None),
        "activation_delete": (
            "GET",
            f"/admin/conventions/fursuitactivation/{activation.pk}/delete/",
            None,
        ),
        "activation_reactivation": (
            "GET",
            f"/admin/conventions/fursuitactivation/{activation.pk}/change/",
            None,
        ),
        "enrollment_add": ("GET", "/admin/conventions/conventionenrollment/add/", None),
        "enrollment_selection_change": (
            "GET",
            f"/admin/conventions/conventionenrollment/{enrollment.pk}/change/",
            None,
        ),
        "convention_create": (
            "POST",
            "/admin/conventions/convention/add/",
            urlencode(
                {
                    "name": "Blocked playable",
                    "status": "active",
                    "start_date": "2026-09-01",
                    "end_date": "2036-09-01",
                }
            ).encode(),
        ),
        "convention_delete": (
            "POST",
            f"/admin/conventions/convention/{identity.convention_id}/delete/",
            b"post=yes",
        ),
    }


@pytest.mark.django_db(transaction=True)
def test_local_owned_baseline_case9_route_responses(live_server: Any) -> None:
    """#243 case 9: characterize safe routes over real local HTTP and owned roots."""
    identity = create_owned_baseline()
    sessions = role_sessions(identity)
    emergency = User.objects.get(pk=sessions["emergency"]["actor_id"])
    request = local_admin_transport(live_server, emergency)
    activation = FursuitActivation.objects.get(fursuit_id=identity.first_fursuit_id)
    create_catch_session(activation=activation)
    routes = case9_routes(identity)
    responses = {name: request(*route) for name, route in routes.items()}
    assert set(responses) == CASE9_SUBCHECKS - ABSENT_OBJECT_SUBCHECKS
    assert {name: response["status"] for name, response in responses.items()} == {
        "catch_add": 403,
        "catch_bulk_edit": 403,
        "credential_add": 403,
        "session_add": 403,
        "session_delete": 403,
        "session_bulk_edit": 200,
        "session_history_edit": 200,
        "activation_add": 403,
        "activation_delete": 403,
        "activation_reactivation": 200,
        "enrollment_add": 403,
        "enrollment_selection_change": 200,
        "convention_create": 200,
        "convention_delete": 200,
    }
    assert (
        b"Conventions cannot be created playable."
        in responses["convention_create"]["body"]
    )
    assert b"Cannot delete convention" in responses["convention_delete"]["body"]
    assert b'name="post"' not in responses["convention_delete"]["body"]
    assert b'name="action"' not in responses["session_bulk_edit"]["body"]
    for name, fields in {
        "session_history_edit": (
            "activation",
            "started_at",
            "expires_at",
            "ended_at",
            "end_reason",
        ),
        "enrollment_selection_change": ("user", "convention", "is_active"),
    }.items():
        page = responses[name]["body"]
        assert b'class="readonly"' in page
        for field in fields:
            assert f'name="{field}"'.encode() not in page
    page = responses["activation_reactivation"]["body"]
    assert re.search(rb'<input[^>]*name="is_active"[^>]*checked', page)
    assert b'name="reactivate"' not in page
    assert Convention.objects.count() == 1
    assert OperatorAuditEvent.objects.count() == 0
    assert FursuitCatchSession.objects.count() == 1
    assert FursuitActivation.objects.filter(is_active=True).count() == 2
