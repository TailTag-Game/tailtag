"""Read-only, sanitized diagnosis of the registered #204 fixture closure."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Final, NoReturn, cast

_API_ROOT = Path(__file__).resolve().parents[1] / "services" / "api"
if _API_ROOT.is_dir() and str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

PASS: Final = "PASS"
MISSING: Final = "MISSING"
UNEXPECTED_STATE: Final = "UNEXPECTED_STATE"
UNEXPECTED_COUNT: Final = "UNEXPECTED_COUNT"
RELATIONSHIP_MISMATCH: Final = "RELATIONSHIP_MISMATCH"
EXTERNAL_ASSET_UNAVAILABLE: Final = "EXTERNAL_ASSET_UNAVAILABLE"
INDETERMINATE: Final = "INDETERMINATE"
FAIL_FIXTURE_STATE_MISMATCH: Final = "FAIL_FIXTURE_STATE_MISMATCH"
FAIL_EXECUTION: Final = "FAIL_EXECUTION"
FAIL_INVALID_INPUT: Final = "FAIL_INVALID_INPUT"

OWNERSHIP: Final = {
    "registry": "PRESERVED_PREREQUISITE",
    "identities": "PRESERVED_PREREQUISITE",
    "media": "PRESERVED_PREREQUISITE",
    "root_bindings": "PRESERVED_PREREQUISITE",
    "profiles": "RESET_OWNED",
    "profile_state": "RESET_OWNED",
    "convention": "RESET_OWNED",
    "convention_state": "RESET_OWNED",
    "fursuits": "RESET_OWNED",
    "fursuit_state": "RESET_OWNED",
    "ownership": "PRESERVED_PREREQUISITE",
    "enrollments": "RESET_OWNED",
    "activations": "RESET_OWNED",
    "catches": "RESET_OWNED",
    "sessions": "RESET_OWNED",
    "credentials": "RESET_OWNED",
    "closure": "PRESERVED_PREREQUISITE",
}

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CLUSTER_IDENTIFIER = re.compile(r"[1-9][0-9]*\Z")
_DATABASE_NAME = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")


class _SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError


def _target_matches(source_sha: str, deployment_id: str) -> bool:
    from config.build_identity import get_identity

    if _SHA.fullmatch(source_sha) is None:
        return False
    try:
        if str(uuid.UUID(deployment_id)) != deployment_id:
            return False
    except ValueError:
        return False
    actual = get_identity()
    from config.replacement_target_binding import (
        TargetBindingError,
        validate_runtime_target,
    )

    try:
        if os.environ.get("RAILWAY_ENVIRONMENT_NAME") != "staging":
            return False
        validate_runtime_target(os.environ)
    except TargetBindingError:
        return False
    return (
        actual.get("source_sha") == source_sha
        and actual.get("deployment_id") == deployment_id
        and actual.get("environment") == "staging"
    )


def diagnose_fixture() -> dict[str, str]:
    """Inspect only the frozen #204 closure; never return database values."""
    from catches.models import Catch
    from conventions.models import (
        Convention,
        ConventionEnrollment,
        ConventionStatus,
        FursuitActivation,
        FursuitCatchCredential,
        FursuitCatchSession,
    )
    from django.db.models import Q
    from fursuits.models import Fursuit
    from profiles.models import PlayerProfile
    from rehearsal import baseline
    from rehearsal.models import StagingResetIdentity
    from rehearsal.reset import _assert_closure  # pyright: ignore[reportPrivateUsage]
    from rehearsal.safety import ResetSafetyError, validate_asset

    result = dict.fromkeys(OWNERSHIP, INDETERMINATE)
    identities = list(
        StagingResetIdentity.objects.select_related("owner", "catcher")[:2]
    )
    if not identities:
        result["registry"] = MISSING
        return result
    if len(identities) != 1:
        result["registry"] = UNEXPECTED_COUNT
        return result
    identity = identities[0]
    result["registry"] = (
        PASS
        if identity.pk == 1
        and identity.environment_id.version == 4
        and _CLUSTER_IDENTIFIER.fullmatch(identity.cluster_identifier) is not None
        and _DATABASE_NAME.fullmatch(identity.database_name) is not None
        and identity.database_name != "postgres"
        else UNEXPECTED_STATE
    )
    result["identities"] = (
        PASS
        if identity.owner_id != identity.catcher_id
        and not identity.owner.is_staff
        and not identity.catcher.is_staff
        and not cast(bool, identity.owner.is_superuser)  # pyright: ignore[reportUnknownMemberType]
        and not cast(bool, identity.catcher.is_superuser)  # pyright: ignore[reportUnknownMemberType]
        and bool(identity.owner.clerk_user_id)
        and bool(identity.catcher.clerk_user_id)
        else RELATIONSHIP_MISMATCH
    )
    try:
        validate_asset(identity.media_key)
    except ResetSafetyError:
        result["media"] = EXTERNAL_ASSET_UNAVAILABLE
    else:
        result["media"] = PASS

    roots = (
        identity.convention_id,
        identity.first_fursuit_id,
        identity.second_fursuit_id,
    )
    if all(root is None for root in roots):
        result["root_bindings"] = PASS
        result["convention"] = MISSING
        result["convention_state"] = MISSING
        result["fursuits"] = MISSING
        result["fursuit_state"] = MISSING
        result["ownership"] = MISSING
        result["closure"] = (
            RELATIONSHIP_MISMATCH
            if Convention.objects.filter(name=baseline.CONVENTION_NAME).exists()
            or Fursuit.objects.filter(
                tailtag_id__in=(
                    baseline.FIRST_FURSUIT_TAILTAG_ID,
                    baseline.SECOND_FURSUIT_TAILTAG_ID,
                )
            ).exists()
            else PASS
        )
    elif any(root is None for root in roots) or roots[1] == roots[2]:
        result["root_bindings"] = RELATIONSHIP_MISMATCH
    else:
        convention = Convention.objects.filter(pk=roots[0]).first()
        fursuits = Fursuit.objects.in_bulk((roots[1], roots[2]))
        result["root_bindings"] = (
            PASS
            if convention is not None and len(fursuits) == 2
            else RELATIONSHIP_MISMATCH
        )
        result["convention"] = PASS if convention is not None else MISSING
        result["fursuits"] = (
            PASS
            if len(fursuits) == 2
            else MISSING
            if not fursuits
            else UNEXPECTED_COUNT
        )
        if convention is not None:
            result["convention_state"] = (
                PASS
                if (
                    convention.name,
                    convention.status,
                    convention.start_date,
                    convention.end_date,
                    convention.is_playable,
                )
                == (
                    baseline.CONVENTION_NAME,
                    ConventionStatus.ACTIVE,
                    datetime.date(2026, 9, 1),
                    datetime.date(2036, 9, 1),
                    True,
                )
                else UNEXPECTED_STATE
            )
        if len(fursuits) == 2:
            first, second = fursuits[roots[1]], fursuits[roots[2]]
            result["ownership"] = (
                PASS
                if first.owner_id == second.owner_id == identity.owner_id
                else RELATIONSHIP_MISMATCH
            )
            result["fursuit_state"] = (
                PASS
                if (
                    first.tailtag_id,
                    first.name,
                    first.photo_key,
                    first.is_enabled,
                    second.tailtag_id,
                    second.name,
                    second.photo_key,
                    second.is_enabled,
                )
                == (
                    baseline.FIRST_FURSUIT_TAILTAG_ID,
                    "Rehearsal Panther",
                    identity.media_key,
                    True,
                    baseline.SECOND_FURSUIT_TAILTAG_ID,
                    "Rehearsal Fox",
                    identity.media_key,
                    True,
                )
                else UNEXPECTED_STATE
            )
        if convention is not None and len(fursuits) == 2:
            try:
                _assert_closure(identity, convention, (first, second))
            except ResetSafetyError:
                result["closure"] = RELATIONSHIP_MISMATCH
            else:
                result["closure"] = PASS

    profiles = list(
        PlayerProfile.objects.filter(
            user_id__in=(identity.owner_id, identity.catcher_id)
        )
    )
    result["profiles"] = (
        MISSING if not profiles else PASS if len(profiles) == 2 else UNEXPECTED_COUNT
    )
    if len(profiles) == 2:
        expected = {
            identity.owner_id: ("tt_rehearsal_owner", "TailTag Rehearsal Owner"),
            identity.catcher_id: ("tt_rehearsal_catcher", "TailTag Rehearsal Catcher"),
        }
        result["profile_state"] = (
            PASS
            if all(
                (profile.handle, profile.display_name) == expected[profile.user_id]
                and profile.avatar_key == identity.media_key
                and profile.is_enabled
                and profile.onboarding_completed_at is not None
                for profile in profiles
            )
            else UNEXPECTED_STATE
        )
    if (
        PlayerProfile.objects.exclude(
            user_id__in=(identity.owner_id, identity.catcher_id)
        )
        .filter(handle__in=("tt_rehearsal_owner", "tt_rehearsal_catcher"))
        .exists()
    ):
        result["closure"] = RELATIONSHIP_MISMATCH

    if result["root_bindings"] == PASS and roots[0] is not None:
        enrollments = list(
            ConventionEnrollment.objects.filter(
                Q(user_id__in=(identity.owner_id, identity.catcher_id))
                | Q(convention_id=roots[0])
            )
        )
        if not enrollments:
            result["enrollments"] = MISSING
        elif len(enrollments) != 2:
            result["enrollments"] = UNEXPECTED_COUNT
        elif {row.user_id for row in enrollments} != {
            identity.owner_id,
            identity.catcher_id,
        } or any(row.convention_id != roots[0] for row in enrollments):
            result["enrollments"] = RELATIONSHIP_MISMATCH
        else:
            result["enrollments"] = (
                PASS if all(row.is_active for row in enrollments) else UNEXPECTED_STATE
            )
        activations = list(
            FursuitActivation.objects.filter(
                Q(fursuit_id__in=roots[1:]) | Q(convention_id=roots[0])
            )
        )
        if not activations:
            result["activations"] = MISSING
        elif len(activations) != 2:
            result["activations"] = UNEXPECTED_COUNT
        elif {row.fursuit_id for row in activations} != set(roots[1:]) or any(
            row.convention_id != roots[0] for row in activations
        ):
            result["activations"] = RELATIONSHIP_MISMATCH
        else:
            result["activations"] = (
                PASS
                if all(
                    row.is_active and row.deactivated_at is None for row in activations
                )
                else UNEXPECTED_STATE
            )
        activation_ids = tuple(row.pk for row in activations)
        session_ids = tuple(
            FursuitCatchSession.objects.filter(
                activation_id__in=activation_ids
            ).values_list("pk", flat=True)
        )
        result["catches"] = (
            UNEXPECTED_COUNT
            if Catch.objects.filter(
                Q(fursuit_id__in=roots[1:])
                | Q(convention_id=roots[0])
                | Q(activation_id__in=activation_ids)
                | Q(catch_session_id__in=session_ids)
            ).exists()
            else PASS
        )
        result["sessions"] = (
            UNEXPECTED_COUNT
            if FursuitCatchSession.objects.filter(
                activation__fursuit_id__in=roots[1:]
            ).exists()
            else PASS
        )
        result["credentials"] = (
            UNEXPECTED_COUNT
            if FursuitCatchCredential.objects.filter(
                activation__fursuit_id__in=roots[1:]
            ).exists()
            else PASS
        )
    elif result["root_bindings"] == PASS:
        for key in ("enrollments", "activations", "catches", "sessions", "credentials"):
            result[key] = MISSING if key in ("enrollments", "activations") else PASS
    return result


def diagnostic_result(invariants: dict[str, str]) -> str:
    if any(value == INDETERMINATE for value in invariants.values()):
        return INDETERMINATE
    return (
        PASS
        if all(value == PASS for value in invariants.values())
        else FAIL_FIXTURE_STATE_MISMATCH
    )


def safe_diagnose_fixture() -> dict[str, object]:
    """Convert unexpected read failures to a fixed, value-free result."""
    try:
        invariants = diagnose_fixture()
        result = diagnostic_result(invariants)
    except Exception:  # noqa: BLE001
        invariants = dict.fromkeys(OWNERSHIP, INDETERMINATE)
        result = FAIL_EXECUTION
    return {
        "result": result,
        "invariants": invariants,
        "binding_equality": "NOT_CHECKED",
    }


def main() -> int:
    parser = _SafeParser(add_help=False)
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-deployment-id")
    try:
        args = parser.parse_args()
        if (
            args.expected_source_sha is None
            or args.expected_deployment_id is None
            or os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.production"
            or not _target_matches(
                args.expected_source_sha, args.expected_deployment_id
            )
        ):
            raise ValueError
    except Exception:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "result": FAIL_INVALID_INPUT,
                    "invariants": {},
                    "binding_equality": "NOT_CHECKED",
                }
            )
        )
        return 1
    try:
        import django

        django.setup()
        payload = safe_diagnose_fixture()
    except Exception:  # noqa: BLE001
        payload = {
            "result": FAIL_EXECUTION,
            "invariants": dict.fromkeys(OWNERSHIP, INDETERMINATE),
            "binding_equality": "NOT_CHECKED",
        }
    result = payload["result"]
    print(json.dumps(payload, sort_keys=True))
    return 0 if result == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
