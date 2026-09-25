"""One bounded, interactive #243 operator validation on the guarded Staging image."""

from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import json
import re
import sys
import warnings
from collections.abc import Mapping
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Final, cast
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from scripts import api_staging_operator_inspect as inspector

_STAGING_ORIGIN: Final = "https://staging.tailtag.app"
_MAX_BODY: Final = 131072
_CONTROL_FILES: Final = (
    "accounts/admin.py",
    "catches/admin.py",
    "conventions/admin.py",
    "fursuits/admin.py",
    "profiles/admin.py",
)
_CONTROL_HASHES: dict[str, str] = globals().get("_CONTROL_HASHES", {})
_active_identity: Mapping[str, str] | None = None
_CASE9_NAMES: Final = (
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
)
_COMBINED: Final = frozenset(
    {
        "catch_change",
        "credential_replacement",
        "credential_raw_edit",
        "activation_reactivation",
    }
)
_WINDOW_PHRASE: Final = "exclusive Railway Staging validation window; I own cleanup"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")


def _json(body: bytes) -> object:
    if len(body) > _MAX_BODY:
        raise ValueError

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    return json.loads(body, object_pairs_hook=unique)


def _http_request(
    method: str,
    path: str,
    *,
    actor: Mapping[str, Any] | None,
    body: bytes | None = None,
    csrf: str | None = None,
) -> dict[str, Any]:
    """Single bounded HTTP boundary; each actor owns its own cookie jar."""
    if (
        not path.startswith("/")
        or path.startswith("//")
        or "?" in path
        or "#" in path
        or "\\" in path
    ):
        raise ValueError
    if method not in {"GET", "POST", "PUT"}:
        raise ValueError
    if body is not None and len(body) > 4096:
        raise ValueError
    jar = actor.get("cookies") if actor is not None else None
    if jar is not None and not isinstance(jar, CookieJar):
        raise ValueError
    opener = build_opener(ProxyHandler({}), _NoRedirect(), HTTPCookieProcessor(jar))
    headers: dict[str, str] = {}
    if actor is not None and actor.get("role") == "owner":
        token = actor.get("token")
        if isinstance(token, str):
            headers["Authorization"] = f"Bearer {token}"
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif method == "PUT":
        headers["Content-Type"] = "application/json"
    if csrf is not None:
        if actor is None:
            raise ValueError
        headers["X-CSRFToken"] = csrf
    request = Request(_STAGING_ORIGIN + path, data=body, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        if response.url != _STAGING_ORIGIN + path:
            raise ValueError
        observed = response.read(_MAX_BODY + 1)
        if len(observed) > _MAX_BODY:
            raise ValueError
        return {
            "status": response.status,
            "headers": dict(response.headers),
            "body": observed,
        }


def _guard_target(expected_identity: Mapping[str, str]) -> None:
    if not inspector._target_identity_matches(  # pyright: ignore[reportPrivateUsage]
        expected_identity["source_sha"], expected_identity["deployment_id"]
    ):
        raise ValueError
    for path, expected in (
        ("/health/identity", dict(expected_identity)),
        ("/health/ready", {"status": "ok"}),
        ("/health/identity", dict(expected_identity)),
    ):
        response = _http_request("GET", path, actor=None)
        if response["status"] != 200 or _json(response["body"]) != expected:
            raise ValueError


def _confirm_window() -> None:
    if not sys.stdin.isatty():
        raise ValueError
    print(
        "Confirm exclusive Staging validation window and cleanup responsibility.",
        flush=True,
    )
    if input(f"Type exactly: {_WINDOW_PHRASE}\n> ") != _WINDOW_PHRASE:
        raise ValueError


def _reject_debug_database_logging() -> None:
    from django.conf import settings
    from django.db import connection

    if settings.DEBUG or connection.force_debug_cursor:
        raise ValueError


def _csrf_from(response: Mapping[str, Any]) -> str:
    if response["status"] != 200:
        raise ValueError
    matched = re.search(
        rb'name="csrfmiddlewaretoken" value="([A-Za-z0-9]+)"', response["body"]
    )
    if matched is None:
        raise ValueError
    return matched.group(1).decode("ascii")


def _authenticate(role: str) -> dict[str, Any]:
    from django.conf import settings
    from django.contrib.auth.hashers import check_password
    from django.contrib.auth.models import Group
    from django.contrib.sessions.models import Session
    from django.http import HttpRequest

    from accounts.management.commands.bootstrap_staging_operator import (
        OPERATOR_GROUP_NAME,
    )
    from accounts.models import User
    from authentication.clerk import ClerkSessionVerifier
    from rehearsal.models import StagingResetIdentity

    _reject_debug_database_logging()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError
    warnings.filterwarnings("error", category=getpass.GetPassWarning)
    if role == "owner":
        token = getpass.getpass("Owner ordinary Clerk session token: ")
        identity = StagingResetIdentity.objects.get(pk=1)
        configuration = settings.CLERK_AUTHENTICATION
        if configuration is None or not token:
            raise ValueError
        request = HttpRequest()
        request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        verified = ClerkSessionVerifier(configuration).verify(request)
        if verified is None or verified.subject != identity.owner.clerk_user_id:
            raise ValueError
        return {
            "role": role,
            "actor_id": identity.owner_id,
            "token": token,
            "cookies": CookieJar(),
            "csrf": None,
        }
    if role not in {"limited", "managed", "emergency"}:
        raise ValueError
    group: Group | None = None
    pinned: tuple[int, str, str] | None = None
    if role in {"managed", "limited"}:
        if role == "managed":
            if inspector._validate_managed_operator() is not None:  # pyright: ignore[reportPrivateUsage]
                raise ValueError
            group = Group.objects.get(name=OPERATOR_GROUP_NAME)
            members = list(User.objects.filter(groups=group))
        else:
            if inspector._validate_limited_operator() is not None:  # pyright: ignore[reportPrivateUsage]
                raise ValueError
            members = inspector._limited_candidates()  # pyright: ignore[reportPrivateUsage]
        if len(members) != 1:
            raise ValueError
        operator = members[0]
        pinned = (
            operator.pk,
            operator.clerk_user_id,
            cast(str, operator.password),  # pyright: ignore[reportUnknownMemberType]
        )
        identifier = operator.clerk_user_id
    else:
        identifier = getpass.getpass(f"{role} admin identifier: ")
    password = getpass.getpass(f"{role} admin password: ")
    try:
        if role in {"managed", "limited"}:
            if pinned is None:
                raise ValueError
            if role == "managed":
                if group is None or inspector._validate_managed_operator() is not None:  # pyright: ignore[reportPrivateUsage]
                    raise ValueError
                current_members = list(User.objects.filter(groups=group))
            else:
                if inspector._validate_limited_operator() is not None:  # pyright: ignore[reportPrivateUsage]
                    raise ValueError
                current_members = inspector._limited_candidates()  # pyright: ignore[reportPrivateUsage]
            if len(current_members) != 1:
                raise ValueError
            operator = current_members[0]
            if (
                operator.pk,
                operator.clerk_user_id,
                cast(str, operator.password),  # pyright: ignore[reportUnknownMemberType]
            ) != pinned:
                raise ValueError
        else:
            operator = User.objects.get(clerk_user_id=identifier)
        encoded_password = cast(str, operator.password)  # pyright: ignore[reportUnknownMemberType]
        if not operator.is_staff or not check_password(password, encoded_password):
            raise ValueError
        if role == "emergency":
            if not cast(bool, operator.is_superuser):  # pyright: ignore[reportUnknownMemberType]
                raise ValueError
            if operator.clerk_user_id.startswith("staging_emergency_"):
                from accounts.management.commands.bootstrap_staging_emergency_operator import (
                    inspect_emergency_state,
                )

                dedicated = list(
                    User.objects.filter(clerk_user_id__startswith="staging_emergency_")[
                        :2
                    ]
                )
                if (
                    inspect_emergency_state() != "READY"
                    or len(dedicated) != 1
                    or dedicated[0].pk != operator.pk
                ):
                    raise ValueError
        elif role == "limited":
            if (
                cast(bool, operator.is_superuser)  # pyright: ignore[reportUnknownMemberType]
                or inspector._validate_limited_operator() is not None  # pyright: ignore[reportPrivateUsage]
            ):
                raise ValueError
            if inspector._limited_candidates()[0].pk != operator.pk:  # pyright: ignore[reportPrivateUsage]
                raise ValueError
        elif (
            cast(bool, operator.is_superuser)  # pyright: ignore[reportUnknownMemberType]
            or inspector._validate_managed_operator() is not None  # pyright: ignore[reportPrivateUsage]
        ):
            raise ValueError
        actor: dict[str, Any] = {
            "role": role,
            "actor_id": operator.pk,
            "cookies": CookieJar(),
            "csrf": None,
        }
        csrf = _csrf_from(_http_request("GET", "/admin/login/", actor=actor))
        body = urlencode(
            {"username": identifier, "password": password, "csrfmiddlewaretoken": csrf}
        ).encode()
        actor["csrf"] = csrf
        if _active_identity is None:
            raise ValueError
        _guard_target(_active_identity)
        login = _http_request(
            "POST", "/admin/login/", actor=actor, body=body, csrf=csrf
        )
        if (
            login["status"] != 302
            or _http_request("GET", "/admin/", actor=actor)["status"] != 200
        ):
            raise ValueError
        if role == "managed":
            session_keys = [
                cookie.value
                for cookie in actor["cookies"]
                if cookie.name == settings.SESSION_COOKIE_NAME
            ]
            if len(session_keys) != 1:
                raise ValueError
            session = Session.objects.get(session_key=session_keys[0])
            if session.get_decoded().get("_auth_user_id") != str(operator.pk):
                raise ValueError
        rotated = next(
            (cookie.value for cookie in actor["cookies"] if cookie.name == "csrftoken"),
            None,
        )
        if not isinstance(rotated, str):
            raise TypeError
        actor["csrf"] = rotated
        return actor
    finally:
        identifier = ""
        password = ""


def _owner_token_still_valid(actor: Mapping[str, Any], owner_id: int) -> None:
    """Check token expiry and preserved subject immediately before player write."""
    token = actor.get("token")
    if not isinstance(token, str):
        return  # Injected test actors are verified by their approved seam.
    from django.conf import settings
    from django.http import HttpRequest

    from accounts.models import User
    from authentication.clerk import ClerkSessionVerifier

    configuration = settings.CLERK_AUTHENTICATION
    if configuration is None:
        raise ValueError
    request = HttpRequest()
    request.META["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    verified = ClerkSessionVerifier(configuration).verify(request)
    if (
        verified is None
        or verified.subject != User.objects.get(pk=owner_id).clerk_user_id
    ):
        raise ValueError


def _snapshot() -> dict[str, Any]:
    """Read the registered closure and its exact audit rows without secret fields."""
    from django.db import connection, transaction

    from catches.models import Catch
    from conventions.models import (
        Convention,
        ConventionEnrollment,
        FursuitActivation,
        FursuitCatchCredential,
        FursuitCatchSession,
    )
    from fursuits.models import Fursuit
    from operator_audit.models import OperatorAuditEvent
    from profiles.models import PlayerProfile
    from rehearsal.models import StagingResetIdentity
    from rehearsal.reset import _assert_closure  # pyright: ignore[reportPrivateUsage]
    from rehearsal.safety import ResetSafetyError

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
        identity = StagingResetIdentity.objects.get(pk=1)
        owner, catcher = identity.owner_id, identity.catcher_id
        convention = identity.convention_id
        first, second = identity.first_fursuit_id, identity.second_fursuit_id
        if convention is None or first is None or second is None or first == second:
            raise ValueError
        try:
            _assert_closure(
                identity,
                Convention.objects.get(pk=convention),
                (Fursuit.objects.get(pk=first), Fursuit.objects.get(pk=second)),
            )
        except ResetSafetyError:
            raise ValueError from None
        profiles = tuple(
            PlayerProfile.objects.filter(user_id__in=(owner, catcher))
            .order_by("user_id")
            .values_list(
                "pk",
                "user_id",
                "is_enabled",
                "onboarding_completed_at",
                "handle",
                "display_name",
                "avatar_key",
            )
        )
        fursuits = tuple(
            Fursuit.objects.filter(pk__in=(first, second))
            .order_by("pk")
            .values_list(
                "pk",
                "owner_id",
                "is_enabled",
                "updated_at",
                "tailtag_id",
                "name",
                "photo_key",
                "created_at",
            )
        )
        conventions = tuple(
            Convention.objects.filter(pk=convention).values_list(
                "pk",
                "status",
                "start_date",
                "end_date",
                "name",
                "created_at",
                "updated_at",
            )
        )
        enrollments = tuple(
            ConventionEnrollment.objects.filter(convention_id=convention)
            .order_by("pk")
            .values_list(
                "pk",
                "user_id",
                "convention_id",
                "is_active",
                "created_at",
                "updated_at",
            )
        )
        activations = tuple(
            FursuitActivation.objects.filter(convention_id=convention)
            .order_by("pk")
            .values_list(
                "pk",
                "fursuit_id",
                "convention_id",
                "is_active",
                "deactivated_at",
                "activated_at",
            )
        )
        if (
            len(profiles),
            len(fursuits),
            len(conventions),
            len(enrollments),
            len(activations),
        ) != (2, 2, 1, 2, 2):
            raise ValueError
        from django.db.models import Q

        if (
            {row[1] for row in fursuits} != {owner}
            or {row[1] for row in enrollments} != {owner, catcher}
            or {row[1] for row in activations} != {first, second}
        ):
            raise ValueError
        activation_ids = tuple(row[0] for row in activations)
        sessions = tuple(
            FursuitCatchSession.objects.filter(activation_id__in=activation_ids)
            .order_by("pk")
            .values_list(
                "pk",
                "activation_id",
                "started_at",
                "expires_at",
                "ended_at",
                "end_reason",
                "created_at",
                "updated_at",
            )
        )
        credentials = tuple(
            FursuitCatchCredential.objects.filter(activation_id__in=activation_ids)
            .order_by("pk")
            .values_list(
                "pk",
                "activation_id",
                "revoked_at",
                "revocation_reason",
                "created_at",
                "updated_at",
            )
        )
        catches = tuple(
            Catch.objects.filter(fursuit_id__in=(first, second))
            .order_by("pk")
            .values_list(
                "pk",
                "catcher_user_id",
                "fursuit_id",
                "convention_id",
                "activation_id",
                "catch_session_id",
                "caught_at",
            )
        )
        if len(sessions) > 8 or len(credentials) > 8 or len(catches) > 8:
            raise ValueError
        audit = tuple(
            OperatorAuditEvent.objects.filter(
                Q(
                    affected_record_type="profiles.playerprofile",
                    affected_record_id__in=tuple(row[0] for row in profiles),
                )
                | Q(
                    affected_record_type="fursuits.fursuit",
                    affected_record_id__in=(first, second),
                )
                | Q(
                    affected_record_type="conventions.fursuitcatchsession",
                    affected_record_id__in=tuple(row[0] for row in sessions),
                )
                | Q(
                    affected_record_type="conventions.fursuitcatchcredential",
                    affected_record_id__in=tuple(row[0] for row in credentials),
                )
                | Q(
                    affected_record_type="conventions.fursuitactivation",
                    affected_record_id__in=activation_ids,
                )
                | Q(
                    affected_record_type="conventions.conventionenrollment",
                    affected_record_id__in=tuple(row[0] for row in enrollments),
                )
                | Q(
                    affected_record_type="catches.catch",
                    affected_record_id__in=tuple(row[0] for row in catches),
                )
                | Q(
                    affected_record_type="conventions.convention",
                    affected_record_id=convention,
                )
            )
            .order_by("occurred_at", "pk")
            .values_list(
                "id",
                "actor_id",
                "action",
                "actor_class",
                "affected_record_type",
                "affected_record_id",
                "outcome",
                "occurred_at",
            )
        )
        if len(audit) > 64:
            raise ValueError
        return {
            "roots": {
                "owner": owner,
                "catcher": catcher,
                "owner_profile": next(row[0] for row in profiles if row[1] == owner),
                "convention": convention,
                "first_fursuit": first,
                "second_fursuit": second,
            },
            "state": {
                "profiles": profiles,
                "fursuits": fursuits,
                "convention": conventions,
                "enrollments": enrollments,
                "activations": activations,
                "sessions": sessions,
                "credentials": credentials,
                "catches": catches,
            },
            "audit": audit,
        }


def _review_deployed_controls() -> dict[str, str]:
    """Compare deployed control bytes with the reviewed checkout only."""
    try:
        root = Path("/app")
        if set(_CONTROL_HASHES) != set(_CONTROL_FILES):
            raise ValueError
        if any(
            hashlib.sha256((root / file).read_bytes()).hexdigest()
            != _CONTROL_HASHES[file]
            for file in _CONTROL_FILES
        ):
            raise ValueError
    except (OSError, ValueError):
        return {"deployed_control_hash_match": "FAIL"}
    return {"deployed_control_hash_match": "PASS"}


def _await_receipt(marker: str, acknowledgement: str) -> dict[str, str]:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError
    print(marker, flush=True)
    return {
        "classification": "PASS"
        if input(
            f"Acknowledge the separately observed successful command receipt: {acknowledgement}\n> "
        )
        == acknowledgement
        else "FAIL"
    }


def _await_reset_receipt() -> dict[str, str]:
    return _await_receipt(
        "TAILTAG_MATRIX_RESET_READY", "verified Railway Staging reset"
    )


def _await_decommission_receipt() -> dict[str, str]:
    return _await_receipt(
        "TAILTAG_MATRIX_DECOMMISSION_READY", "verified Railway Staging decommission"
    )


def _await_emergency_decommission_receipt() -> dict[str, str]:
    return _await_receipt(
        "TAILTAG_MATRIX_EMERGENCY_DECOMMISSION_READY",
        "verified Railway Staging emergency decommission",
    )


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError


def _event_delta(
    before: Mapping[str, Any], after: Mapping[str, Any], expected: tuple[object, ...]
) -> None:
    old = before["audit"]
    new = after["audit"]
    _require(
        len(new) == len(old) + 1 and new[: len(old)] == old and new[-1][1:7] == expected
    )


def _same_except(
    before: Mapping[str, Any], after: Mapping[str, Any], *names: str
) -> None:
    _require(before["roots"] == after["roots"])
    _require(
        all(
            before["state"][name] == after["state"][name]
            for name in before["state"]
            if name not in names
        )
    )


def _changed_row_only(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    table: str,
    target_id: int,
    changing: frozenset[int],
) -> None:
    old_rows = before["state"][table]
    new_rows = after["state"][table]
    _require(len(old_rows) == len(new_rows))
    for old, new in zip(old_rows, new_rows, strict=True):
        _require(old[0] == new[0])
        _require(
            old == new
            if old[0] != target_id
            else all(
                a == b
                for index, (a, b) in enumerate(zip(old, new, strict=True))
                if index not in changing
            )
        )


def _response_status(response: Mapping[str, Any], status: int) -> None:
    _require(response.get("status") == status)


def _guarded_request(
    expected: Mapping[str, str],
    method: str,
    path: str,
    *,
    actor: Mapping[str, Any],
    body: bytes,
    csrf: str | None = None,
) -> Mapping[str, Any]:
    _guard_target(expected)
    return _http_request(method, path, actor=actor, body=body, csrf=csrf)


def _case9_routes(
    snapshot: Mapping[str, Any],
) -> dict[str, tuple[str, str, bytes | None]]:
    roots, state = snapshot["roots"], snapshot["state"]
    activation = next(
        row[0] for row in state["activations"] if row[1] == roots["first_fursuit"]
    )
    session = state["sessions"][0][0]
    enrollment = next(
        row[0] for row in state["enrollments"] if row[1] == roots["owner"]
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
            f"/admin/conventions/fursuitcatchsession/{session}/delete/",
            None,
        ),
        "session_bulk_edit": (
            "POST",
            "/admin/conventions/fursuitcatchsession/",
            b"action=delete_selected",
        ),
        "session_history_edit": (
            "GET",
            f"/admin/conventions/fursuitcatchsession/{session}/change/",
            None,
        ),
        "activation_add": ("GET", "/admin/conventions/fursuitactivation/add/", None),
        "activation_delete": (
            "GET",
            f"/admin/conventions/fursuitactivation/{activation}/delete/",
            None,
        ),
        "activation_reactivation": (
            "GET",
            f"/admin/conventions/fursuitactivation/{activation}/change/",
            None,
        ),
        "enrollment_add": ("GET", "/admin/conventions/conventionenrollment/add/", None),
        "enrollment_selection_change": (
            "GET",
            f"/admin/conventions/conventionenrollment/{enrollment}/change/",
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
            f"/admin/conventions/convention/{roots['convention']}/delete/",
            b"post=yes",
        ),
    }


def _case9_response(name: str, response: Mapping[str, Any]) -> None:
    status, body = response["status"], response["body"]
    if name in {
        "catch_add",
        "catch_bulk_edit",
        "credential_add",
        "session_add",
        "session_delete",
        "activation_add",
        "activation_delete",
        "enrollment_add",
    }:
        _require(status == 403)
    elif name == "session_bulk_edit":
        _require(status == 200 and b'name="action"' not in body)
    elif name in {"session_history_edit", "enrollment_selection_change"}:
        _require(status == 200 and b'class="readonly"' in body)
        fields = (
            ("activation", "started_at", "expires_at", "ended_at", "end_reason")
            if name == "session_history_edit"
            else ("user", "convention", "is_active")
        )
        _require(all(f'name="{field}"'.encode() not in body for field in fields))
    elif name == "activation_reactivation":
        _require(
            status == 200
            and re.search(rb'<input[^>]*name="is_active"[^>]*checked', body) is not None
            and b'name="reactivate"' not in body
        )
    elif name == "convention_create":
        _require(status == 200 and b"Conventions cannot be created playable." in body)
    elif name == "convention_delete":
        _require(
            status == 200
            and b"Cannot delete convention" in body
            and b'name="post"' not in body
        )


def run(expected_identity: Mapping[str, str]) -> dict[str, Any]:
    """Run one guarded matrix; emit only fixed allowlisted evidence on any exit."""
    global _active_identity
    started = _now()
    result: dict[str, Any] = {
        "classification": "FAIL_PRECONDITION",
        "identity": None,
        "window_utc": [started, started],
        "cases": {str(i): "NOT_EXERCISED" for i in range(1, 10)},
        "case9": {name: "NOT_EXERCISED" for name in _CASE9_NAMES},
        "deployed_control_hash_match": "NOT_EXERCISED",
        "case9_control_review": "NOT_EXERCISED",
        "case9_deterministic_evidence": "NOT_EXERCISED",
        "case9_limitations": sorted(_COMBINED),
        "mutation_may_have_begun": False,
        "reset": "NOT_EXERCISED",
        "emergency_decommission": "NOT_EXERCISED",
        "decommission": "NOT_EXERCISED",
        "audit_events": [],
        "session_cascade": "NOT_EXERCISED",
        "credential_cascade": "NOT_EXERCISED",
    }
    phase = "precondition"
    actors: dict[str, dict[str, Any]] = {}
    try:
        _require(
            set(expected_identity) == {"source_sha", "deployment_id", "environment"}
        )
        _require(
            expected_identity["environment"] == "staging"
            and inspector._valid_expected_identity(  # pyright: ignore[reportPrivateUsage]
                expected_identity["source_sha"], expected_identity["deployment_id"]
            )
        )
        _reject_debug_database_logging()
        _active_identity = expected_identity
        result["identity"] = dict(expected_identity)
        _guard_target(expected_identity)
        before = _snapshot()
        _require(
            not before["state"]["sessions"]
            and not before["state"]["credentials"]
            and not before["state"]["catches"]
        )
        from rehearsal.models import StagingResetIdentity
        from rehearsal.reset import validate_baseline

        validate_baseline(StagingResetIdentity.objects.get(pk=1))
        review = _review_deployed_controls()
        result["deployed_control_hash_match"] = review["deployed_control_hash_match"]
        _require(review == {"deployed_control_hash_match": "PASS"})
        phase = "confirmation"
        _confirm_window()
        phase = "authentication"
        actors = {
            role: _authenticate(role)
            for role in ("limited", "managed", "emergency", "owner")
        }
        _require(len({actors[role]["actor_id"] for role in actors}) == 4)
        owner = actors["owner"]
        me = _http_request("GET", "/api/me/", actor=owner)
        me_body = _json(me["body"])
        if not isinstance(me_body, dict):
            raise TypeError
        _require(
            me["status"] == 200
            and cast(dict[str, Any], me_body).get("id") == before["roots"]["owner"]
        )
        profile_path = (
            f"/admin/profiles/playerprofile/{before['roots']['owner_profile']}/change/"
        )
        fursuit_path = (
            f"/admin/fursuits/fursuit/{before['roots']['second_fursuit']}/change/"
        )
        phase = "case1"
        for path in ("/admin/profiles/playerprofile/", profile_path):
            response = _http_request("GET", path, actor=owner)
            _require(
                response["status"] == 302
                and str(response["headers"].get("Location", "")).startswith(
                    "/admin/login/"
                )
            )
        owner_csrf = owner.get("csrf")
        if not isinstance(owner_csrf, str):
            owner_csrf = _csrf_from(_http_request("GET", "/admin/login/", actor=owner))
        owner["csrf"] = owner_csrf
        result["mutation_may_have_begun"] = True
        denied = _guarded_request(
            expected_identity,
            "POST",
            profile_path,
            actor=owner,
            body=urlencode(
                {"csrfmiddlewaretoken": owner_csrf, "is_enabled": ""}
            ).encode(),
            csrf=owner_csrf,
        )
        _require(
            denied["status"] == 302
            and str(denied["headers"].get("Location", "")).startswith("/admin/login/")
        )
        observed = _snapshot()
        _require(observed == before)
        result["cases"]["1"] = "PASS"
        phase = "case2_4_7"
        limited = actors["limited"]
        limited_csrf = limited["csrf"]
        limited["csrf"] = limited_csrf
        result["mutation_may_have_begun"] = True
        denied = _guarded_request(
            expected_identity,
            "POST",
            fursuit_path,
            actor=limited,
            body=urlencode({"csrfmiddlewaretoken": limited_csrf}).encode(),
            csrf=limited_csrf,
        )
        _response_status(denied, 403)
        observed = _snapshot()
        _same_except(before, observed)
        _event_delta(
            before,
            observed,
            (
                limited["actor_id"],
                "set_fursuit_enabled",
                "unauthorized_actor",
                "fursuits.fursuit",
                before["roots"]["second_fursuit"],
                "denied",
            ),
        )
        for key in ("2", "4", "7"):
            result["cases"][key] = "PASS"
        result["audit_events"].append(
            {
                "action": "set_fursuit_enabled",
                "actor_class": "unauthorized_actor",
                "target_type": "fursuits.fursuit",
                "outcome": "denied",
                "count": 1,
            }
        )
        before = observed
        phase = "session"
        session_path = f"/api/conventions/{before['roots']['convention']}/fursuit-activations/{before['roots']['first_fursuit']}/catch-session/"
        _owner_token_still_valid(owner, before["roots"]["owner"])
        result["mutation_may_have_begun"] = True
        session_response = _guarded_request(
            expected_identity,
            "PUT",
            session_path,
            actor=owner,
            body=b'{"is_active":true}',
        )
        _response_status(session_response, 200)
        owner.pop("token", None)
        owner.pop("cookies", None)
        observed = _snapshot()
        _same_except(before, observed, "sessions")
        first_activation = next(
            row[0]
            for row in before["state"]["activations"]
            if row[1] == before["roots"]["first_fursuit"]
        )
        _require(
            len(observed["state"]["sessions"]) == 1
            and observed["state"]["sessions"][0][1] == first_activation
            and observed["state"]["sessions"][0][4:6] == (None, None)
            and observed["audit"] == before["audit"]
        )
        before = observed
        phase = "case3_6_8"
        managed = actors["managed"]
        managed_csrf = _csrf_from(_http_request("GET", profile_path, actor=managed))
        managed["csrf"] = managed_csrf
        result["mutation_may_have_begun"] = True
        changed = _guarded_request(
            expected_identity,
            "POST",
            profile_path,
            actor=managed,
            body=urlencode({"csrfmiddlewaretoken": managed_csrf}).encode(),
            csrf=managed_csrf,
        )
        _response_status(changed, 302)
        observed = _snapshot()
        _same_except(before, observed, "profiles", "sessions")
        _changed_row_only(
            before,
            observed,
            "profiles",
            before["roots"]["owner_profile"],
            frozenset({2}),
        )
        session_id = before["state"]["sessions"][0][0]
        _changed_row_only(
            before, observed, "sessions", session_id, frozenset({4, 5, 7})
        )
        _require(
            next(
                row
                for row in observed["state"]["profiles"]
                if row[1] == before["roots"]["owner"]
            )[2]
            is False
        )
        _require(
            observed["state"]["sessions"][0][4] is not None
            and observed["state"]["sessions"][0][5] == "eligibility_lost"
        )
        _event_delta(
            before,
            observed,
            (
                managed["actor_id"],
                "set_profile_enabled",
                "operator",
                "profiles.playerprofile",
                before["roots"]["owner_profile"],
                "succeeded",
            ),
        )
        for key in ("3", "6", "8"):
            result["cases"][key] = "PASS"
        result["session_cascade"] = "PASS"
        result["audit_events"].append(
            {
                "action": "set_profile_enabled",
                "actor_class": "operator",
                "target_type": "profiles.playerprofile",
                "outcome": "succeeded",
                "count": 1,
            }
        )
        before = observed
        phase = "case5"
        emergency = actors["emergency"]
        emergency_csrf = _csrf_from(_http_request("GET", fursuit_path, actor=emergency))
        emergency["csrf"] = emergency_csrf
        result["mutation_may_have_begun"] = True
        changed = _guarded_request(
            expected_identity,
            "POST",
            fursuit_path,
            actor=emergency,
            body=urlencode({"csrfmiddlewaretoken": emergency_csrf}).encode(),
            csrf=emergency_csrf,
        )
        _response_status(changed, 302)
        observed = _snapshot()
        _same_except(before, observed, "fursuits")
        _changed_row_only(
            before,
            observed,
            "fursuits",
            before["roots"]["second_fursuit"],
            frozenset({2, 3}),
        )
        _require(
            next(
                row
                for row in observed["state"]["fursuits"]
                if row[0] == before["roots"]["second_fursuit"]
            )[2]
            is False
        )
        _event_delta(
            before,
            observed,
            (
                emergency["actor_id"],
                "set_fursuit_enabled",
                "emergency_superuser",
                "fursuits.fursuit",
                before["roots"]["second_fursuit"],
                "succeeded",
            ),
        )
        result["cases"]["5"] = "PASS"
        result["audit_events"].append(
            {
                "action": "set_fursuit_enabled",
                "actor_class": "emergency_superuser",
                "target_type": "fursuits.fursuit",
                "outcome": "succeeded",
                "count": 1,
            }
        )
        before = observed
        phase = "case9"
        for name, (method, path, body) in _case9_routes(before).items():
            if method == "POST":
                csrf = emergency["csrf"]
                body = (
                    body + b"&csrfmiddlewaretoken=" + csrf.encode()
                    if body
                    else urlencode({"csrfmiddlewaretoken": csrf}).encode()
                )
                result["mutation_may_have_begun"] = True
                response = _guarded_request(
                    expected_identity,
                    method,
                    path,
                    actor=emergency,
                    body=body,
                    csrf=csrf,
                )
            else:
                response = _http_request(method, path, actor=emergency)
            _case9_response(name, response)
            observed = _snapshot()
            _require(observed == before)
            if name not in _COMBINED:
                result["case9"][name] = "PASS"
        retained_audit = before["audit"]
        for actor in actors.values():
            actor.pop("csrf", None)
            actor.pop("cookies", None)
        phase = "reset"
        _guard_target(expected_identity)
        from django.db import connections

        connections.close_all()
        _require(_await_reset_receipt().get("classification") == "PASS")
        _guard_target(expected_identity)
        identity = StagingResetIdentity.objects.get(pk=1)
        validate_baseline(identity)
        observed = _snapshot()
        _require(
            observed["roots"] == before["roots"] and observed["audit"] == retained_audit
        )
        result["reset"] = "PASS"
        from accounts.models import User

        emergency_user = User.objects.get(pk=actors["emergency"]["actor_id"])
        if emergency_user.clerk_user_id.startswith("staging_emergency_"):
            phase = "emergency_decommission"
            _guard_target(expected_identity)
            connections.close_all()
            _require(
                _await_emergency_decommission_receipt().get("classification") == "PASS"
            )
            _guard_target(expected_identity)
            from accounts.management.commands.bootstrap_staging_emergency_operator import (
                inspect_emergency_state,
            )

            _require(inspect_emergency_state() == "DECOMMISSIONED")
            decommissioned_actor = User.objects.get(pk=actors["emergency"]["actor_id"])
            _require(
                decommissioned_actor.clerk_user_id.startswith("staging_emergency_")
                and decommissioned_actor.is_staff is False
                and not decommissioned_actor.is_superuser
                and not decommissioned_actor.has_usable_password()
                and not decommissioned_actor.groups.exists()
                and not decommissioned_actor.user_permissions.exists()
            )
            _require(_snapshot()["audit"] == retained_audit)
            result["emergency_decommission"] = "PASS"
        phase = "decommission"
        _guard_target(expected_identity)
        connections.close_all()
        _require(_await_decommission_receipt().get("classification") == "PASS")
        _guard_target(expected_identity)
        _require(inspector._validate_decommissioned_operator() is None)  # pyright: ignore[reportPrivateUsage]
        _require(
            len(inspector._limited_candidates()) == 1  # pyright: ignore[reportPrivateUsage]
            and inspector._limited_candidates()[0].pk == limited["actor_id"]  # pyright: ignore[reportPrivateUsage]
        )
        _require(User.objects.get(pk=limited["actor_id"]).is_staff is False)
        _require(inspector._validate_managed_operator() is None)  # pyright: ignore[reportPrivateUsage]
        validate_baseline(StagingResetIdentity.objects.get(pk=1))
        _require(_snapshot()["audit"] == retained_audit)
        result["decommission"] = "PASS"
        result["classification"] = "LIVE_SEQUENCE_COMPLETE_PENDING_CASE9_EVIDENCE"
    except (Exception, KeyboardInterrupt):  # noqa: BLE001
        result["classification"] = "FAIL_" + phase.upper()
        if phase in {"case1", "case2_4_7", "case3_6_8", "case5", "case9"}:
            keys = {
                "case1": ("1",),
                "case2_4_7": ("2", "4", "7"),
                "case3_6_8": ("3", "6", "8"),
                "case5": ("5",),
                "case9": ("9",),
            }[phase]
            for key in keys:
                result["cases"][key] = "FAIL"
    finally:
        for actor in actors.values():
            actor.pop("token", None)
            actor.pop("csrf", None)
            actor.pop("cookies", None)
        _active_identity = None
        result["window_utc"][1] = _now()
        print(json.dumps(result, sort_keys=True), flush=True)
    return result
