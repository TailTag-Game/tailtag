"""Disposable acceptance coverage for the read-only #243 fixture diagnosis."""

from __future__ import annotations

import datetime
import importlib
import json
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Final, cast

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import DatabaseError, connection
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
from rehearsal import baseline
from rehearsal.models import StagingResetIdentity
from rehearsal.safety import ResetSafetyError

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_fixture_diagnose.py"
MEDIA_KEY = "images/0123456789abcdef0123456789abcdef.png"
ENVIRONMENT_ID = "5f4ab4f2-af14-4b2b-a4c3-3344d281fe5e"

PASS: Final = "PASS"
MISSING: Final = "MISSING"
UNEXPECTED_STATE: Final = "UNEXPECTED_STATE"
UNEXPECTED_COUNT: Final = "UNEXPECTED_COUNT"
RELATIONSHIP_MISMATCH: Final = "RELATIONSHIP_MISMATCH"
EXTERNAL_ASSET_UNAVAILABLE: Final = "EXTERNAL_ASSET_UNAVAILABLE"
INDETERMINATE: Final = "INDETERMINATE"
ALLOWED_STATUSES: Final = frozenset(
    {
        PASS,
        MISSING,
        UNEXPECTED_STATE,
        UNEXPECTED_COUNT,
        RELATIONSHIP_MISMATCH,
        EXTERNAL_ASSET_UNAVAILABLE,
        INDETERMINATE,
    }
)
EXPECTED_KEYS: Final = frozenset(
    {
        "registry",
        "identities",
        "media",
        "root_bindings",
        "profiles",
        "profile_state",
        "convention",
        "convention_state",
        "fursuits",
        "fursuit_state",
        "ownership",
        "enrollments",
        "activations",
        "catches",
        "sessions",
        "credentials",
        "closure",
    }
)
RESET_OWNED: Final = "RESET_OWNED"
PRESERVED_PREREQUISITE: Final = "PRESERVED_PREREQUISITE"
NOT_243_REQUIRED: Final = "NOT_243_REQUIRED"


@pytest.fixture
def diagnostic(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the dedicated fixture-only diagnostic once it exists."""
    assert SCRIPT.is_file(), "scripts/api_staging_fixture_diagnose.py must exist"
    monkeypatch.syspath_prepend(str(REPOSITORY_ROOT))  # pyright: ignore[reportUnknownMemberType]

    # The #204 Test Surface Contract permits controlled asset-read responses.
    def available_asset(media_key: str) -> None:
        del media_key

    monkeypatch.setattr("rehearsal.safety.validate_asset", available_asset)
    return importlib.import_module("scripts.api_staging_fixture_diagnose")


def _create_baseline() -> StagingResetIdentity:
    """Create the exact #204 semantic baseline in the disposable test database."""
    owner = User.objects.create_user("fixture-diagnostic-owner")
    catcher = User.objects.create_user("fixture-diagnostic-catcher")
    now = timezone.now()
    for user, handle, display_name in (
        (owner, "tt_rehearsal_owner", "TailTag Rehearsal Owner"),
        (catcher, "tt_rehearsal_catcher", "TailTag Rehearsal Catcher"),
    ):
        PlayerProfile.objects.create(
            user=user,
            handle=handle,
            display_name=display_name,
            avatar_key=MEDIA_KEY,
            onboarding_completed_at=now,
            is_enabled=True,
        )
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2036, 9, 1),
    )
    first = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Panther",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
        is_enabled=True,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Fox",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
        is_enabled=True,
    )
    for user in (owner, catcher):
        ConventionEnrollment.objects.create(
            user=user, convention=convention, is_active=True
        )
    for fursuit in (first, second):
        FursuitActivation.objects.create(
            fursuit=fursuit,
            convention=convention,
            is_active=True,
            activated_at=now,
        )
    if not default_storage.exists(MEDIA_KEY):
        default_storage.save(MEDIA_KEY, ContentFile(b"fixture-media"))
    return StagingResetIdentity.objects.create(
        id=1,
        environment_id=ENVIRONMENT_ID,
        cluster_identifier="123",
        database_name="test_tailtag",
        media_key=MEDIA_KEY,
        owner=owner,
        catcher=catcher,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )


def _diagnose(module: ModuleType) -> dict[str, str]:
    """Exercise the fixture-only public diagnostic surface."""
    payload = cast(dict[str, object], module.safe_diagnose_fixture())
    result = cast(dict[str, str], payload["invariants"])
    assert set(result) == EXPECTED_KEYS
    assert set(result.values()) <= ALLOWED_STATUSES
    return result


def _active_graph(identity: StagingResetIdentity) -> None:
    """Add an owned session/credential/catch that #204 must remove on reset."""
    assert identity.convention_id is not None
    assert identity.first_fursuit_id is not None
    activation = FursuitActivation.objects.get(
        convention_id=identity.convention_id, fursuit_id=identity.first_fursuit_id
    )
    now = timezone.now()
    session = FursuitCatchSession.objects.create(
        activation=activation,
        started_at=now,
        expires_at=now + datetime.timedelta(hours=1),
    )
    FursuitCatchCredential.objects.create(activation=activation, token="a" * 43)
    Catch.objects.create(
        catcher_user_id=identity.catcher_id,
        fursuit_id=identity.first_fursuit_id,
        convention_id=identity.convention_id,
        activation=activation,
        catch_session=session,
    )


def _remove_owner_profile(identity: StagingResetIdentity) -> object:
    return PlayerProfile.objects.filter(user_id=identity.owner_id).delete()


def _disable_owner_profile(identity: StagingResetIdentity) -> object:
    return PlayerProfile.objects.filter(user_id=identity.owner_id).update(
        is_enabled=False
    )


def _pause_convention(identity: StagingResetIdentity) -> object:
    assert identity.convention_id is not None
    return Convention.objects.filter(pk=identity.convention_id).update(
        status=ConventionStatus.PAUSED
    )


def _disable_first_fursuit(identity: StagingResetIdentity) -> object:
    assert identity.first_fursuit_id is not None
    return Fursuit.objects.filter(pk=identity.first_fursuit_id).update(is_enabled=False)


def _deactivate_owner_enrollment(identity: StagingResetIdentity) -> object:
    assert identity.convention_id is not None
    return ConventionEnrollment.objects.filter(
        convention_id=identity.convention_id, user_id=identity.owner_id
    ).update(is_active=False)


def _deactivate_first_activation(identity: StagingResetIdentity) -> object:
    assert identity.convention_id is not None
    assert identity.first_fursuit_id is not None
    return FursuitActivation.objects.filter(
        convention_id=identity.convention_id, fursuit_id=identity.first_fursuit_id
    ).update(is_active=False, deactivated_at=timezone.now())


def _registered_rows(identity: StagingResetIdentity) -> object:
    """Return a bounded fake registry result for impossible FK-corruption branches."""

    class Rows:
        def __getitem__(self, index: slice) -> list[StagingResetIdentity]:
            assert index == slice(None, 2, None)
            return [identity]

    return Rows()


@pytest.mark.django_db
def test_exact_baseline_reports_each_required_fixture_invariant_and_ownership(
    diagnostic: ModuleType,
) -> None:
    """A #204 baseline produces independent PASS facts without role inspection."""
    _create_baseline()

    observed = _diagnose(diagnostic)

    assert observed == {key: PASS for key in EXPECTED_KEYS}
    assert diagnostic.OWNERSHIP == {
        "registry": PRESERVED_PREREQUISITE,
        "identities": PRESERVED_PREREQUISITE,
        "media": PRESERVED_PREREQUISITE,
        "root_bindings": PRESERVED_PREREQUISITE,
        "profiles": RESET_OWNED,
        "profile_state": RESET_OWNED,
        "convention": RESET_OWNED,
        "convention_state": RESET_OWNED,
        "fursuits": RESET_OWNED,
        "fursuit_state": RESET_OWNED,
        "ownership": PRESERVED_PREREQUISITE,
        "enrollments": RESET_OWNED,
        "activations": RESET_OWNED,
        "catches": RESET_OWNED,
        "sessions": RESET_OWNED,
        "credentials": RESET_OWNED,
        "closure": PRESERVED_PREREQUISITE,
    }


@pytest.mark.django_db
def test_registry_structure_does_not_compare_the_reset_uuid_to_railway_identity(
    diagnostic: ModuleType,
) -> None:
    """Regression: #204's reset UUID is a separate namespace from Railway's UUID."""
    identity = _create_baseline()
    reset_uuid = uuid.UUID("d2719be4-13dd-4cd5-b55c-ed79742c52ea")
    assert reset_uuid != uuid.UUID(ENVIRONMENT_ID)
    identity.environment_id = reset_uuid
    identity.save(update_fields={"environment_id"})

    payload = cast(dict[str, object], diagnostic.safe_diagnose_fixture())
    observed = cast(dict[str, str], payload["invariants"])

    assert observed["registry"] == PASS
    assert payload["binding_equality"] == "NOT_CHECKED"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("environment_id", uuid.UUID("12345678-1234-11ee-be56-0242ac120002")),
        ("cluster_identifier", "0"),
        ("database_name", "postgres"),
    ),
)
def test_registry_structural_contract_rejects_only_invalid_registry_fields(
    diagnostic: ModuleType,
    field: str,
    value: object,
) -> None:
    """Fixture-level registry health is limited to persisted #204 structure."""
    identity = _create_baseline()
    setattr(identity, field, value)
    identity.save(update_fields={field})

    observed = _diagnose(diagnostic)

    assert observed["registry"] == UNEXPECTED_STATE


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mutate", "invariant", "expected"),
    (
        (_remove_owner_profile, "profiles", UNEXPECTED_COUNT),
        (_disable_owner_profile, "profile_state", UNEXPECTED_STATE),
        (_pause_convention, "convention_state", UNEXPECTED_STATE),
        (_disable_first_fursuit, "fursuit_state", UNEXPECTED_STATE),
        (_deactivate_owner_enrollment, "enrollments", UNEXPECTED_STATE),
        (_deactivate_first_activation, "activations", UNEXPECTED_STATE),
        (_active_graph, "catches", UNEXPECTED_COUNT),
        (_active_graph, "sessions", UNEXPECTED_COUNT),
        (_active_graph, "credentials", UNEXPECTED_COUNT),
    ),
)
def test_reset_owned_mismatches_remain_separate_sanitized_facts(
    diagnostic: ModuleType,
    mutate: Callable[[StagingResetIdentity], object],
    invariant: str,
    expected: str,
) -> None:
    """A reset candidate can name the affected owned baseline fact safely."""
    identity = _create_baseline()
    mutate(identity)

    observed = _diagnose(diagnostic)

    assert observed[invariant] == expected
    assert diagnostic.OWNERSHIP[invariant] == RESET_OWNED


@pytest.mark.django_db
def test_registry_missing_and_asset_unavailable_are_not_relabelled_as_reset_drift(
    diagnostic: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing preserved prerequisites are distinct from reset-owned data state."""
    missing = _diagnose(diagnostic)
    assert missing["registry"] == MISSING
    assert missing["profiles"] == INDETERMINATE

    identity = _create_baseline()

    def unavailable_asset(_: str) -> None:
        raise ResetSafetyError

    monkeypatch.setattr("rehearsal.safety.validate_asset", unavailable_asset)

    observed = _diagnose(diagnostic)

    assert observed["media"] == EXTERNAL_ASSET_UNAVAILABLE
    assert diagnostic.OWNERSHIP["media"] == PRESERVED_PREREQUISITE
    assert identity.pk == 1


@pytest.mark.django_db
def test_all_null_root_bindings_are_a_reset_supported_starting_state(
    diagnostic: ModuleType,
) -> None:
    """#204 may create all roots together, but never accepts a partial binding."""
    identity = _create_baseline()
    identity.convention = None
    identity.first_fursuit = None
    identity.second_fursuit = None
    identity.save(update_fields={"convention", "first_fursuit", "second_fursuit"})

    observed = _diagnose(diagnostic)

    assert observed["root_bindings"] == PASS


@pytest.mark.django_db
def test_partial_or_dangling_root_bindings_fail_closed_without_guessing(
    diagnostic: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The DB protects roots, so exercise impossible corruption as an in-memory row."""
    identity = _create_baseline()
    identity.refresh_from_db()
    assert identity.convention_id is not None
    original_convention_id = identity.convention_id

    identity.convention_id = None

    def partial_registry_rows(*arguments: object) -> object:
        del arguments
        return _registered_rows(identity)

    monkeypatch.setattr(
        StagingResetIdentity.objects,
        "select_related",
        partial_registry_rows,
    )
    partial = _diagnose(diagnostic)

    assert partial["root_bindings"] == RELATIONSHIP_MISMATCH

    identity.convention_id = original_convention_id
    identity.convention_id += 1_000_000

    def missing_convention_rows(*arguments: object) -> object:
        del arguments
        return _registered_rows(identity)

    monkeypatch.setattr(
        StagingResetIdentity.objects,
        "select_related",
        missing_convention_rows,
    )
    missing_convention = _diagnose(diagnostic)

    assert missing_convention["root_bindings"] == RELATIONSHIP_MISMATCH
    assert missing_convention["convention"] == MISSING

    identity.convention_id = original_convention_id
    assert identity.first_fursuit_id is not None
    identity.first_fursuit_id += 1_000_000

    def dangling_registry_rows(*arguments: object) -> object:
        del arguments
        return _registered_rows(identity)

    monkeypatch.setattr(
        StagingResetIdentity.objects,
        "select_related",
        dangling_registry_rows,
    )
    dangling = _diagnose(diagnostic)

    assert dangling["root_bindings"] == RELATIONSHIP_MISMATCH
    assert dangling["fursuits"] == UNEXPECTED_COUNT


@pytest.mark.django_db
def test_preserved_identity_shape_drift_is_distinct_from_reset_owned_fixture_state(
    diagnostic: ModuleType,
) -> None:
    """#204 cannot repair a reused Clerk/User binding that gained staff status."""
    identity = _create_baseline()
    User.objects.filter(pk=identity.owner_id).update(is_staff=True)

    observed = _diagnose(diagnostic)

    assert observed["identities"] == RELATIONSHIP_MISMATCH
    assert diagnostic.OWNERSHIP["identities"] == PRESERVED_PREREQUISITE


@pytest.mark.django_db
def test_preserved_fursuit_owner_mismatch_and_unowned_dependency_are_distinct(
    diagnostic: ModuleType,
) -> None:
    """#204 must deny dependencies it does not own rather than repair them."""
    identity = _create_baseline()
    foreign = User.objects.create_user("fixture-diagnostic-foreign")
    assert identity.first_fursuit_id is not None
    Fursuit.objects.filter(pk=identity.first_fursuit_id).update(owner_id=foreign.pk)

    ownership_drift = _diagnose(diagnostic)

    assert ownership_drift["ownership"] == RELATIONSHIP_MISMATCH
    assert ownership_drift["closure"] == RELATIONSHIP_MISMATCH
    assert diagnostic.OWNERSHIP["ownership"] == PRESERVED_PREREQUISITE
    assert diagnostic.OWNERSHIP["closure"] == PRESERVED_PREREQUISITE

    Fursuit.objects.filter(pk=identity.first_fursuit_id).update(
        owner_id=identity.owner_id
    )
    ConventionEnrollment.objects.create(
        user=foreign,
        convention_id=identity.convention_id,
        is_active=False,
    )

    unowned_dependency = _diagnose(diagnostic)

    assert unowned_dependency["enrollments"] == UNEXPECTED_COUNT
    assert unowned_dependency["closure"] == RELATIONSHIP_MISMATCH


@pytest.mark.django_db
def test_missing_reset_owned_enrollments_are_distinguished(
    diagnostic: ModuleType,
) -> None:
    """The reset candidate identifies absent owned rows without inspecting roles."""
    identity = _create_baseline()
    assert identity.convention_id is not None
    ConventionEnrollment.objects.filter(convention_id=identity.convention_id).delete()

    observed = _diagnose(diagnostic)

    assert observed["enrollments"] == MISSING
    assert diagnostic.OWNERSHIP["enrollments"] == RESET_OWNED


@pytest.mark.django_db
def test_missing_reset_owned_activations_are_distinguished(
    diagnostic: ModuleType,
) -> None:
    """A missing owned activation is distinct from a missing enrollment."""
    identity = _create_baseline()
    assert identity.convention_id is not None
    FursuitActivation.objects.filter(convention_id=identity.convention_id).delete()

    observed = _diagnose(diagnostic)

    assert observed["activations"] == MISSING
    assert diagnostic.OWNERSHIP["activations"] == RESET_OWNED


@pytest.mark.django_db
def test_fixture_diagnosis_is_read_only_and_does_not_touch_operator_relations(
    diagnostic: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The narrow diagnosis only observes the #204 fixture closure."""
    _create_baseline()
    before = {
        model._meta.label: model.objects.count()
        for model in (
            StagingResetIdentity,
            User,
            PlayerProfile,
            Convention,
            Fursuit,
            ConventionEnrollment,
            FursuitActivation,
            Catch,
            FursuitCatchSession,
            FursuitCatchCredential,
        )
    }

    def fail_if_operator_queryset_is_used(*_: object, **__: object) -> object:
        raise AssertionError("operator inspection is outside the fixture diagnosis")

    monkeypatch.setattr(User.objects, "filter", fail_if_operator_queryset_is_used)

    write_prefixes = frozenset(
        {"ALTER", "CREATE", "DELETE", "DROP", "INSERT", "TRUNCATE", "UPDATE"}
    )

    def reject_write(
        execute: Callable[..., object],
        sql: str,
        parameters: object,
        many: bool,
        context: object,
    ) -> object:
        assert sql.lstrip().split(maxsplit=1)[0].upper() not in write_prefixes
        return execute(sql, parameters, many, context)

    with connection.execute_wrapper(reject_write):
        observed = _diagnose(diagnostic)

    assert observed["registry"] == PASS
    assert before == {
        model._meta.label: model.objects.count()
        for model in (
            StagingResetIdentity,
            User,
            PlayerProfile,
            Convention,
            Fursuit,
            ConventionEnrollment,
            FursuitActivation,
            Catch,
            FursuitCatchSession,
            FursuitCatchCredential,
        )
    }


@pytest.mark.django_db
def test_query_failure_is_indeterminate_without_leaking_database_detail(
    diagnostic: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable fixture state cannot be interpreted as reset-owned drift."""
    _create_baseline()

    def unavailable(*_: object, **__: object) -> object:
        raise DatabaseError("private database connection detail")

    monkeypatch.setattr(StagingResetIdentity.objects, "select_related", unavailable)

    payload = cast(dict[str, object], diagnostic.safe_diagnose_fixture())
    observed = cast(dict[str, str], payload["invariants"])

    assert payload["result"] == "FAIL_EXECUTION"
    assert set(observed.values()) == {INDETERMINATE}
    assert "private" not in json.dumps(payload)


@pytest.mark.django_db
def test_serialized_diagnostic_only_contains_fixed_statuses_and_no_fixture_values(
    diagnostic: ModuleType,
) -> None:
    """The evidence projection cannot expose reusable identity or media bindings."""
    _create_baseline()

    payload = {"result": "PASS", "invariants": _diagnose(diagnostic)}
    rendered = json.dumps(payload, sort_keys=True)

    for prohibited in (
        "fixture-diagnostic-owner",
        "fixture-diagnostic-catcher",
        MEDIA_KEY,
        str(baseline.FIRST_FURSUIT_TAILTAG_ID),
        baseline.CONVENTION_NAME,
    ):
        assert prohibited not in rendered


@pytest.mark.django_db
def test_main_emits_only_the_fixed_sanitized_payload(
    diagnostic: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The streamed command retains a compact, non-identifying evidence projection."""
    _create_baseline()

    def matching_target(source_sha: str, deployment_id: str) -> bool:
        del source_sha, deployment_id
        return True

    monkeypatch.setattr(diagnostic, "_target_matches", matching_target)
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "api_staging_fixture_diagnose.py",
            "--expected-source-sha",
            "a" * 40,
            "--expected-deployment-id",
            "11111111-1111-4111-8111-111111111111",
        ],
    )

    assert diagnostic.main() == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload == {
        "result": PASS,
        "binding_equality": "NOT_CHECKED",
        "invariants": {key: PASS for key in sorted(EXPECTED_KEYS)},
    }
