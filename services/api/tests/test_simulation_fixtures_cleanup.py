"""Acceptance coverage for simulation run cleanup, retention, and listing (#223, C-1 to C-13).

Assumed interface (new module ``simulation_fixtures/cleanup.py``). Every function
returns a frozen dataclass with ``result: str`` and ``data: dict[str, object]``
(``data`` is empty for every failure code); the remote operation maps it 1:1.

* ``cleanup(pool, run_id)``. PASS data is ``convention, enrollment, fursuit,
  activation, catch, session, credential, image`` (counts of deleted objects, the
  image count being the distinct stored keys) plus ``readmitted`` (slots readmitted
  or cleared in the completion phase). ``FixtureRun.cleanup_counts`` stores exactly
  the eight deletion counts (not ``readmitted``), and a resumed call reports them
  again from there.
* ``retain(pool, run_id, reason)``. PASS data is ``{"quarantined": n}``.
* ``retained_counts(*, now=None)``: PASS data is exactly ``{"retained": n, "unfinished": m}``
  (no listing, no limit).
* ``retained(*, now=None)``. PASS data is ``{"runs": [{"run_id", "pool", "reason",
  "age_days"}, ...], "retained": n, "unfinished": m}`` (a list of plain dicts),
  retained runs first, then oldest first within each group.

Result codes follow the frozen plan: FAIL_RUN_UNKNOWN, FAIL_ATTRIBUTION,
FAIL_STORAGE, FAIL_LIMIT. Models: ``FixtureRun.reason`` / ``cleaned_at`` /
``cleanup_counts``, ``RETAINED`` and ``CLEANED`` status constants,
``FixtureIdentity(run, index)``, ``FixturePendingImage(run, key)``.
Storage is only touched at the ``default_storage.delete`` boundary.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from collections.abc import Callable
from typing import Any, cast

import pytest
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import User
from catches.models import Catch
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit
from media import service as media_service
from profiles.models import PlayerProfile
from rehearsal.models import StagingResetIdentity
from simulation_fixtures import cleanup, services
from simulation_fixtures.models import (
    CLEANED,
    FAILED,
    PROVISIONED,
    RETAINED,
    FixtureIdentity,
    FixtureObject,
    FixturePendingImage,
    FixtureRun,
)
from simulation_pool import services as pool_services
from simulation_pool.models import AVAILABLE, QUARANTINED, PoolSlot
from tests.authentication_support import create_test_user
from tests.catch_credential_test_support import TOKEN_A, TOKEN_B, create_credential
from tests.catch_test_support import create_catch, create_catch_scenario
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record
from tests.profile_test_support import image_upload
from tests.simulation_fixtures_test_support import (
    OTHER_RUN,
    POOL,
    RUN_A,
    RUN_B,
    lease_pool,
    stored_keys,
    world,
)

pytestmark = pytest.mark.django_db

OWNERS = [0, 1]
CATCHERS = [2, 3]
EXTRAS = [4]
DELETED = {
    "convention": 1,
    "enrollment": 4,
    "fursuit": 3,  # two provisioned plus the journey-created one
    "activation": 2,
    "catch": 1,
    "session": 1,
    "credential": 2,  # one rotated away, one current
    "image": 4,  # two ledger photos, the journey fursuit's photo, one avatar
}


@dataclasses.dataclass
class Journey:
    """A provisioned run plus the state a journey leaves behind, and a bystander world."""

    users: dict[int, User]
    ledger_keys: set[str]
    journey_photo_key: str
    avatar_key: str
    bystander_key: str
    bystander_user: User
    foreign: Convention

    @property
    def image_keys(self) -> set[str]:
        return self.ledger_keys | {self.journey_photo_key, self.avatar_key}


def start_run() -> Journey:
    """Provision RUN_A (with an extra), then add journey-like state to it."""
    users = lease_pool(POOL, RUN_A, 5)
    # State outside the run that cleanup must never touch.
    bystander_user = create_eligible_user()
    bystander_key = media_service.store_image(image_upload())
    Fursuit.objects.create(
        owner=bystander_user, name="Baseline", photo_key=bystander_key
    )
    foreign = Convention.objects.create(
        name="Elsewhere",
        status=ConventionStatus.ACTIVE,
        start_date=dt.date(2026, 7, 2),
        end_date=dt.date(2026, 7, 5),
    )
    ConventionEnrollment.objects.create(user=bystander_user, convention=foreign)

    provisioned = services.provision(
        POOL, RUN_A, OWNERS, CATCHERS, fursuits_per_owner=1, extras=EXTRAS
    )
    assert provisioned.result == "PASS"
    ledger_keys = {
        key
        for key in FixtureObject.objects.filter(run__run_id=RUN_A).values_list(
            "media_key", flat=True
        )
        if key
    }

    activation = FursuitActivation.objects.filter(fursuit__owner=users[0]).get()
    session = create_catch_session(activation=activation)
    create_credential(
        activation=activation,
        token=TOKEN_A,
        revoked_at=timezone.now(),
        revocation_reason="owner_rotation",
    )
    create_credential(activation=activation, token=TOKEN_B)
    Catch.objects.create(
        catcher_user=users[2],
        fursuit=activation.fursuit,
        convention=activation.convention,
        activation=activation,
        catch_session=session,
    )
    journey_photo_key = media_service.store_image(image_upload())
    Fursuit.objects.create(
        owner=users[1], name="Journey Fursuit", photo_key=journey_photo_key
    )
    avatar_key = media_service.store_image(image_upload())
    PlayerProfile.objects.filter(user=users[2]).update(avatar_key=avatar_key)
    return Journey(
        users,
        ledger_keys,
        journey_photo_key,
        avatar_key,
        bystander_key,
        bystander_user,
        foreign,
    )


def slot_states() -> dict[int, tuple[str, str | None]]:
    return {
        slot.index: (slot.state, slot.run_id)
        for slot in PoolSlot.objects.filter(pool=POOL)
    }


def snapshot() -> dict[str, Any]:
    return world() | {
        "identities": list(FixtureIdentity.objects.order_by("pk").values()),
        "pending": list(FixturePendingImage.objects.order_by("pk").values()),
    }


def assert_run_removed_and_bystanders_kept(journey: Journey) -> None:
    """Every deletion-set row and image is gone; everything else survives."""
    assert Convention.objects.get() == journey.foreign
    assert ConventionEnrollment.objects.get().user == journey.bystander_user
    assert Fursuit.objects.get().photo_key == journey.bystander_key
    assert FursuitActivation.objects.count() == 0
    state = world(slots=False)
    assert (state["sessions"], state["credentials"], state["catches"]) == (0, 0, 0)
    assert FixtureObject.objects.count() == 0
    assert FixturePendingImage.objects.count() == 0
    assert stored_keys() == {journey.bystander_key}
    # Pool users and profiles survive, with the avatar cleared.
    profiles = PlayerProfile.objects.filter(user__in=journey.users.values())
    assert profiles.count() == 5
    assert set(profiles.values_list("avatar_key", flat=True)) == {None}


# --- C-4/C-5/C-6/C-7/C-10: the full deletion ------------------------------


@pytest.mark.parametrize(
    ("retained_first", "readmitted", "expected_slots"),
    (
        (False, 0, (AVAILABLE, RUN_A)),  # in-run: live leases stay for RELEASE
        (True, 5, (AVAILABLE, None)),  # later maintainer cleanup readmits
    ),
    ids=("in-run-passing-run", "retained-run-cleaned-later"),
)
def test_cleanup_deletes_exactly_the_runs_state_and_evidence_remains(
    retained_first: bool, readmitted: int, expected_slots: tuple[str, str | None]
) -> None:
    """C-4/C-5/C-6/C-7/C-10: the whole run, its images, and nothing else go."""
    journey = start_run()
    if retained_first:
        assert cleanup.retain(POOL, RUN_A, "journeys").result == "PASS"
        assert {state for state, _ in slot_states().values()} == {QUARANTINED}
    before = timezone.now()

    result = cleanup.cleanup(POOL, RUN_A)

    assert (result.result, result.data) == (
        "PASS",
        DELETED | {"readmitted": readmitted},
    )
    assert_run_removed_and_bystanders_kept(journey)
    run = FixtureRun.objects.get(run_id=RUN_A)
    assert run.status == CLEANED
    assert run.reason == ("journeys" if retained_first else None)
    assert run.cleanup_counts == DELETED
    assert run.cleaned_at is not None and run.cleaned_at >= before
    assert slot_states() == {index: expected_slots for index in range(5)}


# --- C-4: refusals change nothing -----------------------------------------


def _cleaned_already(journey: Journey) -> tuple[str, str]:
    assert cleanup.cleanup(POOL, RUN_A).result == "PASS"
    return POOL, RUN_A


def _wrong_pool(journey: Journey) -> tuple[str, str]:
    return "beta", RUN_A


def _unknown_run(journey: Journey) -> tuple[str, str]:
    return POOL, OTHER_RUN


def _failed_status(journey: Journey) -> tuple[str, str]:
    FixtureRun.objects.filter(run_id=RUN_A).update(status=FAILED)
    return POOL, RUN_A


def _slot_leased_to_another_run(journey: Journey) -> tuple[str, str]:
    PoolSlot.objects.filter(pool=POOL, index=1).update(run_id=OTHER_RUN)
    return POOL, RUN_A


def _recorded_slot_missing(journey: Journey) -> tuple[str, str]:
    PoolSlot.objects.filter(pool=POOL, index=2).delete()
    return POOL, RUN_A


def _identity_enrolled_in_a_foreign_convention(journey: Journey) -> tuple[str, str]:
    ConventionEnrollment.objects.create(
        user=journey.users[0], convention=journey.foreign
    )
    return POOL, RUN_A


def _run_fursuit_caught_in_a_foreign_convention(journey: Journey) -> tuple[str, str]:
    fursuit = Fursuit.objects.get(owner=journey.users[0], name__startswith="Sim ")
    activation = create_activation_row(
        fursuit=fursuit, convention=journey.foreign, active=True
    )
    Catch.objects.create(
        catcher_user=journey.bystander_user,
        fursuit=fursuit,
        convention=journey.foreign,
        activation=activation,
        catch_session=create_catch_session(activation=activation),
    )
    return POOL, RUN_A


def _extra_owns_a_fursuit(journey: Journey) -> tuple[str, str]:
    create_fursuit_record(owner=journey.users[4])
    return POOL, RUN_A


def _extra_is_enrolled(journey: Journey) -> tuple[str, str]:
    ConventionEnrollment.objects.create(
        user=journey.users[4], convention=journey.foreign
    )
    return POOL, RUN_A


def _extra_has_an_avatar(journey: Journey) -> tuple[str, str]:
    PlayerProfile.objects.filter(user=journey.users[4]).update(
        avatar_key="images/0123456789abcdef0123456789abcdef.png"
    )
    return POOL, RUN_A


def _extra_made_a_catch(journey: Journey) -> tuple[str, str]:
    scenario = create_catch_scenario(
        catcher_clerk_user_id="extra_catcher", target_owner_clerk_user_id="extra_target"
    )
    create_catch(scenario=dataclasses.replace(scenario, catcher_user=journey.users[4]))
    return POOL, RUN_A


def _ledger_photo_shared_with_another_fursuit(journey: Journey) -> tuple[str, str]:
    Fursuit.objects.create(
        owner=journey.bystander_user, name="Twin", photo_key=min(journey.ledger_keys)
    )
    return POOL, RUN_A


def _avatar_shared_with_another_profile(journey: Journey) -> tuple[str, str]:
    PlayerProfile.objects.filter(user=journey.bystander_user).update(
        avatar_key=journey.avatar_key
    )
    return POOL, RUN_A


def _photo_is_the_staging_reset_media_key(journey: Journey) -> tuple[str, str]:
    StagingResetIdentity.objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        media_key=journey.journey_photo_key,
        owner=create_test_user(),
        catcher=create_test_user(),
    )
    return POOL, RUN_A


def _run_fursuit_is_a_reset_root(journey: Journey) -> tuple[str, str]:
    # A PROTECT reference from outside the set; its own key is not in the image set,
    # so only the foreign-reference refusal can stop it, after earlier deletes began.
    StagingResetIdentity.objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        media_key="images/ffffffffffffffffffffffffffffffff.png",
        owner=create_test_user(),
        catcher=create_test_user(),
        convention=journey.foreign,
        first_fursuit=Fursuit.objects.get(
            owner=journey.users[0], name__startswith="Sim "
        ),
        second_fursuit=Fursuit.objects.get(photo_key=journey.bystander_key),
    )
    return POOL, RUN_A


@pytest.mark.parametrize(
    ("break_run", "expected"),
    (
        (_cleaned_already, "FAIL_ATTRIBUTION"),
        (_wrong_pool, "FAIL_ATTRIBUTION"),
        (_unknown_run, "FAIL_RUN_UNKNOWN"),
        (_failed_status, "FAIL_ATTRIBUTION"),
        (_slot_leased_to_another_run, "FAIL_ATTRIBUTION"),
        (_recorded_slot_missing, "FAIL_ATTRIBUTION"),
        (_identity_enrolled_in_a_foreign_convention, "FAIL_ATTRIBUTION"),
        (_run_fursuit_caught_in_a_foreign_convention, "FAIL_ATTRIBUTION"),
        (_extra_owns_a_fursuit, "FAIL_ATTRIBUTION"),
        (_extra_is_enrolled, "FAIL_ATTRIBUTION"),
        (_extra_has_an_avatar, "FAIL_ATTRIBUTION"),
        (_extra_made_a_catch, "FAIL_ATTRIBUTION"),
        (_ledger_photo_shared_with_another_fursuit, "FAIL_ATTRIBUTION"),
        (_avatar_shared_with_another_profile, "FAIL_ATTRIBUTION"),
        (_photo_is_the_staging_reset_media_key, "FAIL_ATTRIBUTION"),
        (_run_fursuit_is_a_reset_root, "FAIL_ATTRIBUTION"),
    ),
    ids=(
        "already-cleaned",
        "wrong-pool",
        "unknown-run",
        "failed-status",
        "slot-leased-to-another-run",
        "recorded-slot-missing",
        "identity-enrolled-in-foreign-convention",
        "run-fursuit-caught-in-foreign-convention",
        "extra-owns-a-fursuit",
        "extra-is-enrolled",
        "extra-has-an-avatar",
        "extra-made-a-catch",
        "ledger-photo-shared-with-another-fursuit",
        "avatar-shared-with-another-profile",
        "photo-is-the-staging-reset-media-key",
        "run-fursuit-is-a-protected-reset-root",
    ),
)
def test_refused_cleanup_changes_no_row_and_no_storage_object(
    break_run: Callable[[Journey], tuple[str, str]], expected: str
) -> None:
    """C-4: every refusal is a fixed code and a no-op, including for the object store."""
    journey = start_run()
    pool, run_id = break_run(journey)
    before = snapshot()

    result = cleanup.cleanup(pool, run_id)

    assert (result.result, result.data) == (expected, {})
    assert snapshot() == before


# --- C-6/C-9: storage failure, then resume --------------------------------


@pytest.mark.parametrize("mode", ("delete-raises", "object-survives"))
def test_storage_failure_keeps_keys_pending_and_a_rerun_completes(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """C-6/C-9: the database phase commits once; only unconfirmed images are retried."""
    journey = start_run()
    assert cleanup.retain(POOL, RUN_A, "journeys").result == "PASS"
    stuck = (
        {journey.avatar_key} if mode == "delete-raises" else {min(journey.ledger_keys)}
    )
    real_delete = default_storage.delete

    def flaky_delete(name: str) -> None:
        if name not in stuck:
            real_delete(name)
        elif mode == "delete-raises":
            raise OSError("storage unavailable")

    monkeypatch.setattr(default_storage, "delete", flaky_delete)

    failed = cleanup.cleanup(POOL, RUN_A)

    assert (failed.result, failed.data) == ("FAIL_STORAGE", {})
    pending = set(FixturePendingImage.objects.values_list("key", flat=True))
    assert stuck <= pending
    assert pending == journey.image_keys & stored_keys()  # leaves only once gone
    run = FixtureRun.objects.get(run_id=RUN_A)
    assert (run.status, run.reason, run.cleaned_at) == (RETAINED, "journeys", None)
    assert run.cleanup_counts == DELETED  # the database phase is complete
    assert Fursuit.objects.count() == 1 and FursuitActivation.objects.count() == 0
    assert {state for state, _ in slot_states().values()} == {QUARANTINED}

    monkeypatch.undo()
    recovered = cleanup.cleanup(POOL, RUN_A)

    # A repeated database phase would find nothing and report zero deletions.
    assert (recovered.result, recovered.data) == (
        "PASS",
        DELETED | {"readmitted": 5},
    )
    assert_run_removed_and_bystanders_kept(journey)
    cleaned = FixtureRun.objects.get(run_id=RUN_A)
    assert (cleaned.status, cleaned.cleanup_counts) == (CLEANED, DELETED)
    assert cleaned.cleaned_at is not None
    assert slot_states() == {index: (AVAILABLE, None) for index in range(5)}


# --- C-12: runs from before #223 ------------------------------------------


def test_run_without_identity_rows_cleans_through_its_enrollments() -> None:
    """C-12: a pre-#223 run has no FixtureIdentity rows; enrollments resolve identities."""
    journey = start_run()
    FixtureIdentity.objects.filter(run__run_id=RUN_A).delete()

    result = cleanup.cleanup(POOL, RUN_A)

    assert (result.result, result.data) == ("PASS", DELETED | {"readmitted": 0})
    assert_run_removed_and_bystanders_kept(journey)
    assert FixtureRun.objects.get(run_id=RUN_A).status == CLEANED


# --- C-13: no contamination -----------------------------------------------


def test_a_cleaned_runs_identities_provision_cleanly_for_the_next_run() -> None:
    """C-13: nothing from run A makes run B's provision dirty or leaks into it."""
    journey = start_run()
    assert cleanup.cleanup(POOL, RUN_A).result == "PASS"
    assert pool_services.release(POOL, RUN_A) == 5
    assert pool_services.allocate(POOL, RUN_B, 5, 600) == (0, 1, 2, 3, 4)

    second = services.provision(
        POOL, RUN_B, OWNERS, CATCHERS, fursuits_per_owner=1, extras=EXTRAS
    )

    assert second.result == "PASS"
    owned = Fursuit.objects.filter(owner__in=[journey.users[i] for i in OWNERS])
    assert owned.count() == 2
    assert not Catch.objects.exists()
    assert FixtureObject.objects.exclude(run__run_id=RUN_B).count() == 0


# --- C-8/C-11: retain and retained ----------------------------------------


def test_retain_quarantines_live_recorded_slots_and_is_idempotent() -> None:
    """C-8: only live leases are quarantined; the first retained reason is kept."""
    start_run()
    PoolSlot.objects.filter(pool=POOL, index=3).update(
        lease_expires_at=timezone.now() - dt.timedelta(seconds=1)
    )

    first = cleanup.retain(POOL, RUN_A, "journeys")

    assert (first.result, first.data) == ("PASS", {"quarantined": 4})
    assert slot_states() == {
        0: (QUARANTINED, None),
        1: (QUARANTINED, None),
        2: (QUARANTINED, None),
        3: (AVAILABLE, RUN_A),  # not live, so not ours to quarantine
        4: (QUARANTINED, None),
    }
    run = FixtureRun.objects.get(run_id=RUN_A)
    assert (run.status, run.reason) == (RETAINED, "journeys")
    before = snapshot()

    again = cleanup.retain(POOL, RUN_A, "cleanup")

    assert again.result == "PASS"
    after = snapshot()
    assert after["slots"] == before["slots"]
    kept = FixtureRun.objects.get(run_id=RUN_A)
    assert (kept.status, kept.reason) == (RETAINED, "journeys")


@pytest.mark.parametrize(
    ("setup_state", "expected"),
    (
        (CLEANED, "FAIL_ATTRIBUTION"),
        (FAILED, "FAIL_ATTRIBUTION"),
        (None, "FAIL_RUN_UNKNOWN"),
    ),
    ids=("cleaned", "failed", "unknown"),
)
def test_retain_refuses_runs_that_are_not_provisioned_or_retained(
    setup_state: str | None, expected: str
) -> None:
    """C-8: a finished or unknown run is never retained, and nothing changes."""
    lease_pool(POOL, RUN_A, 2)
    if setup_state is not None:
        FixtureRun.objects.create(
            run_id=RUN_A,
            pool=POOL,
            status=setup_state,
            cleaned_at=timezone.now() if setup_state == CLEANED else None,
            cleanup_counts={} if setup_state == CLEANED else None,
        )
    before = snapshot()

    result = cleanup.retain(POOL, RUN_A, "journeys")

    assert (result.result, result.data) == (expected, {})
    assert snapshot() == before


def _run(
    run_id: str,
    status: str,
    *,
    pool: str = POOL,
    reason: str | None = None,
    age: dt.timedelta,
    indexes: tuple[int, ...] = (),
    now: dt.datetime,
) -> None:
    run = FixtureRun.objects.create(
        run_id=run_id,
        pool=pool,
        status=status,
        reason=reason,
        cleaned_at=now if status == CLEANED else None,
        cleanup_counts={} if status == CLEANED else None,
    )
    FixtureRun.objects.filter(pk=run.pk).update(created_at=now - age)
    FixtureIdentity.objects.bulk_create(
        [FixtureIdentity(run=run, index=index) for index in indexes]
    )


def test_retained_lists_retained_and_unfinished_runs_in_a_fixed_order() -> None:
    """C-11: counts and entries; live, cleaned and failed runs are not clutter."""
    now = timezone.now()
    pool_services.register(POOL, 3)
    pool_services.register("beta", 1)
    live = str(uuid.uuid4())
    pool_services.allocate(POOL, live, 1, 600)
    ids = {name: str(uuid.uuid4()) for name in ("r1", "r2", "u1", "legacy", "x", "y")}
    day = dt.timedelta(days=1)
    hours = dt.timedelta(hours=3)
    _run(
        ids["u1"], PROVISIONED, pool="beta", age=9 * day + hours, indexes=(0,), now=now
    )
    _run(ids["r2"], RETAINED, reason="interrupted", age=2 * day + hours, now=now)
    _run(ids["r1"], RETAINED, reason="journeys", age=5 * day + hours, now=now)
    _run(ids["legacy"], PROVISIONED, age=day + hours, now=now)
    _run(live, PROVISIONED, age=hours, indexes=(0,), now=now)
    _run(ids["x"], CLEANED, reason="journeys", age=day, now=now)
    _run(ids["y"], FAILED, age=day, now=now)

    result = cleanup.retained(now=now)

    assert result.result == "PASS"
    assert result.data == {
        "runs": [
            {"run_id": ids["r1"], "pool": POOL, "reason": "journeys", "age_days": 5},
            {"run_id": ids["r2"], "pool": POOL, "reason": "interrupted", "age_days": 2},
            {
                "run_id": ids["u1"],
                "pool": "beta",
                "reason": "unfinished",
                "age_days": 9,
            },
            {
                "run_id": ids["legacy"],
                "pool": POOL,
                "reason": "unfinished",
                "age_days": 1,
            },
        ],
        "retained": 2,
        "unfinished": 2,
    }


def test_retained_lists_up_to_one_hundred_runs_then_fails_the_limit() -> None:
    """C-11: the listing is bounded; a larger one is refused rather than truncated."""

    def add(count: int) -> None:
        FixtureRun.objects.bulk_create(
            [
                FixtureRun(
                    run_id=str(uuid.uuid4()),
                    pool=POOL,
                    status=RETAINED,
                    reason="journeys",
                )
                for _ in range(count)
            ]
        )

    add(100)
    full = cleanup.retained()
    assert full.result == "PASS"
    assert len(cast(list[object], full.data["runs"])) == 100
    assert full.data["retained"] == 100

    add(1)
    over = cleanup.retained()
    assert (over.result, over.data) == ("FAIL_LIMIT", {})


def test_retained_counts_answers_past_the_listing_limit_without_listing() -> None:
    """C-11: the pre-run cap check still gets true counts when `retained` is refused."""
    FixtureRun.objects.bulk_create(
        [
            FixtureRun(
                run_id=str(uuid.uuid4()),
                pool=POOL,
                status=RETAINED if index < 3 else PROVISIONED,
                reason="journeys" if index < 3 else None,
            )
            for index in range(101)
        ]
    )

    assert cleanup.retained().result == "FAIL_LIMIT"
    counts = cleanup.retained_counts()
    assert (counts.result, counts.data) == ("PASS", {"retained": 3, "unfinished": 98})


# --- C-2: ledger constraints ----------------------------------------------


_VIOLATIONS: tuple[Callable[[FixtureRun, FixtureRun], object], ...] = (
    lambda a, b: FixtureRun.objects.create(
        run_id=str(uuid.uuid4()), pool=POOL, status=RETAINED
    ),
    lambda a, b: FixtureRun.objects.create(
        run_id=str(uuid.uuid4()), pool=POOL, status=CLEANED, cleanup_counts={}
    ),
    lambda a, b: FixtureRun.objects.create(
        run_id=str(uuid.uuid4()),
        pool=POOL,
        status=PROVISIONED,
        cleaned_at=timezone.now(),
    ),
    lambda a, b: FixtureIdentity.objects.bulk_create(
        [FixtureIdentity(run=a, index=1), FixtureIdentity(run=a, index=1)]
    ),
    lambda a, b: FixturePendingImage.objects.bulk_create(
        [
            FixturePendingImage(run=a, key="images/x.png"),
            FixturePendingImage(run=b, key="images/x.png"),
        ]
    ),
)


@pytest.mark.parametrize(
    "violation",
    _VIOLATIONS,
    ids=(
        "retained-needs-a-reason",
        "cleaned-needs-cleaned-at",
        "cleaned-at-only-when-cleaned",
        "identity-unique-per-run-and-index",
        "pending-image-key-unique",
    ),
)
def test_ledger_constraints_reject_inconsistent_rows(
    violation: Callable[[FixtureRun, FixtureRun], object],
) -> None:
    """C-2: the database itself refuses rows the cleanup state machine never writes."""
    a = FixtureRun.objects.create(run_id=RUN_A, pool=POOL, status=PROVISIONED)
    b = FixtureRun.objects.create(run_id=RUN_B, pool=POOL, status=PROVISIONED)

    with pytest.raises(IntegrityError), transaction.atomic():
        violation(a, b)
