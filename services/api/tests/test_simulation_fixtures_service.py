"""Acceptance coverage for simulation fixture provisioning (#220, F-1 to F-11)."""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from PIL import Image, UnidentifiedImageError
from pytest_django.fixtures import SettingsWrapper

from accounts.models import User
from conventions import services as convention_services
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit
from media import service as media_service
from media.images import ImageValidationError, normalize_image
from profiles.models import PlayerProfile
from simulation_fixtures import images, services
from simulation_fixtures.models import FAILED, PROVISIONED, FixtureObject, FixtureRun
from simulation_pool.models import PoolSlot
from tests.catch_test_support import create_catch, create_catch_scenario
from tests.fursuit_test_support import create_eligible_user, create_fursuit_record
from tests.profile_test_support import (
    RECORDING_STORAGES,
    RecordingStorage,
    image_upload,
)
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

OWNERS = [2, 0]
CATCHERS = [3, 1]


def provision(**overrides: Any) -> services.ProvisionResult:
    arguments: dict[str, Any] = {
        "pool": POOL,
        "run_id": RUN_A,
        "owners": list(OWNERS),
        "catchers": list(CATCHERS),
        "fursuits_per_owner": 2,
    } | overrides
    return services.provision(**arguments)


def seed_preexisting_fursuit() -> str:
    """A fursuit outside the run with its own stored image, like a baseline one."""
    key = media_service.store_image(image_upload())
    Fursuit.objects.create(owner=create_eligible_user(), name="Baseline", photo_key=key)
    return key


def test_valid_request_creates_the_complete_run_state_and_ledger() -> None:
    """F-1/F-3/F-4/F-10/F-11: one request yields the full, ledgered, photo-bearing run."""
    users = lease_pool(POOL, RUN_A, 4)
    baseline_key = seed_preexisting_fursuit()
    baseline_fursuit_ids = set(Fursuit.objects.values_list("pk", flat=True))
    before_dates = dt.datetime.now(dt.UTC).date()

    result = provision()

    after_dates = dt.datetime.now(dt.UTC).date()
    assert result == services.ProvisionResult(
        "PASS", {"convention": 1, "enrollment": 4, "fursuit": 4, "activation": 4}
    )

    convention = Convention.objects.get()
    assert convention.status == ConventionStatus.ACTIVE
    assert convention.name == f"Sim {RUN_A[:8]}"
    assert convention.start_date in {before_dates, after_dates}
    assert convention.end_date == convention.start_date + dt.timedelta(days=1)

    pool_users = [users[index] for index in (*OWNERS, *CATCHERS)]
    enrollments = ConventionEnrollment.objects.all()
    assert {e.user for e in enrollments} == set(pool_users)
    assert enrollments.count() == 4
    assert all(e.convention == convention and e.is_active for e in enrollments)

    fursuits = Fursuit.objects.exclude(pk__in=baseline_fursuit_ids)
    owners = [users[index] for index in OWNERS]
    assert sorted(f.owner_id for f in fursuits) == sorted(
        owner.pk for owner in owners for _ in range(2)
    )
    keys = [f.photo_key for f in fursuits]
    assert len(set(keys)) == 4
    assert baseline_key not in keys
    assert set(keys) <= stored_keys()
    assert all(f.is_enabled for f in fursuits)
    assert len({f.name for f in fursuits}) == 4
    assert all(f.name.startswith("Sim Fursuit ") for f in fursuits)

    activations = FursuitActivation.objects.all()
    assert {a.fursuit_id for a in activations} == {f.pk for f in fursuits}
    assert all(a.convention == convention and a.is_active for a in activations)

    # F-3/F-11: nothing beyond the four named kinds, no avatars.
    state = world()
    assert (state["sessions"], state["credentials"], state["catches"]) == (0, 0, 0)
    assert set(PlayerProfile.objects.values_list("avatar_key", flat=True)) == {None}

    # F-4: exactly one ledger row per created object, under one provisioned run.
    run = FixtureRun.objects.get()
    assert (run.run_id, run.pool, run.status) == (RUN_A, POOL, PROVISIONED)
    expected = (
        {("convention", convention.pk): None}
        | {("enrollment", e.pk): None for e in enrollments}
        | {("fursuit", f.pk): f.photo_key for f in fursuits}
        | {("activation", a.pk): None for a in activations}
    )
    ledger = {(o.kind, o.object_id): o.media_key for o in FixtureObject.objects.all()}
    assert FixtureObject.objects.count() == len(expected) == 13
    assert ledger == expected
    assert all(o.run == run for o in FixtureObject.objects.all())

    # status() reports the same counts for the provisioned run.
    reported = services.status(RUN_A)
    assert reported == services.RunStatus(PROVISIONED, result.counts)


def test_inclusive_upper_bounds_and_minimum_lists_are_accepted() -> None:
    """F-2: the documented limits themselves are valid (no off-by-one rejection)."""
    owners, catchers, per_owner = 50, 200, 1
    users = lease_pool(POOL, RUN_A, owners + catchers)
    indexes = list(users)

    result = provision(
        owners=indexes[:owners],
        catchers=indexes[owners:],
        fursuits_per_owner=per_owner,
    )

    assert result.result == "PASS"
    assert result.counts["enrollment"] == 250
    assert result.counts["fursuit"] == 50


def test_five_fursuits_per_owner_for_single_owner_and_catcher_is_accepted() -> None:
    """F-2: the other inclusive bounds (1 owner, 1 catcher, 5 fursuits)."""
    lease_pool(POOL, RUN_A, 2)

    result = provision(owners=[0], catchers=[1], fursuits_per_owner=5)

    assert result == services.ProvisionResult(
        "PASS", {"convention": 1, "enrollment": 2, "fursuit": 5, "activation": 5}
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"owners": []},
        {"owners": list(range(10, 61))},
        {"catchers": []},
        {"catchers": list(range(10, 211))},
        {"fursuits_per_owner": 0},
        {"fursuits_per_owner": 6},
        {"catchers": [1, 2]},
        {"owners": [0, 0]},
        {"catchers": [3, 3]},
        {"run_id": RUN_A.upper()},
        {"run_id": RUN_A.replace("-", "")},
        {"run_id": "run-1"},
        {"pool": "Alpha"},
        {"pool": "a" * 13},
        {"pool": "a-b"},
        {"pool": ""},
    ),
    ids=(
        "no-owners",
        "too-many-owners",
        "no-catchers",
        "too-many-catchers",
        "no-fursuits",
        "too-many-fursuits",
        "owner-catcher-overlap",
        "duplicate-owner",
        "duplicate-catcher",
        "run-id-uppercase",
        "run-id-without-hyphens",
        "run-id-not-a-uuid",
        "pool-uppercase",
        "pool-too-long",
        "pool-with-punctuation",
        "pool-empty",
    ),
)
def test_invalid_configuration_is_rejected_before_any_write(
    overrides: dict[str, Any],
) -> None:
    """F-2: out-of-range, overlapping, or malformed requests write nothing."""
    lease_pool(POOL, RUN_A, 4)
    before = world()

    result = provision(**overrides)

    assert result.result == "FAIL_REQUEST"
    assert world() == before


def _lease_elsewhere(slot: PoolSlot) -> None:
    slot.run_id = OTHER_RUN


def _expire(slot: PoolSlot) -> None:
    slot.lease_expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)


def _unlease(slot: PoolSlot) -> None:
    slot.run_id = None
    slot.lease_expires_at = None


def _quarantine(slot: PoolSlot) -> None:
    _unlease(slot)
    slot.state = "quarantined"


@pytest.mark.parametrize(
    ("index", "break_slot"),
    (
        (2, _lease_elsewhere),
        (3, _expire),
        (0, _unlease),
        (1, _quarantine),
    ),
    ids=(
        "owner-leased-elsewhere",
        "catcher-expired",
        "owner-unleased",
        "catcher-quarantined",
    ),
)
def test_slot_not_leased_to_this_run_fails_the_lease_without_writes(
    index: int, break_slot: Callable[[PoolSlot], None]
) -> None:
    """F-5: any listed slot that is not live, available, and ours blocks the run."""
    lease_pool(POOL, RUN_A, 4)
    slot = PoolSlot.objects.get(pool=POOL, index=index)
    break_slot(slot)
    slot.save()
    before = world()

    result = provision()

    assert result.result == "FAIL_LEASE"
    assert world() == before


@pytest.mark.parametrize(
    "break_identity",
    (
        lambda: PlayerProfile.objects.filter(handle=f"sp_{POOL}_2").delete(),
        lambda: PlayerProfile.objects.filter(handle=f"sp_{POOL}_1").update(
            handle="sp_other_1"
        ),
        lambda: PoolSlot.objects.filter(pool=POOL, index=3).delete(),
    ),
    ids=(
        "owner-profile-missing",
        "catcher-handle-in-another-pool",
        "slot-unregistered",
    ),
)
def test_identity_that_does_not_resolve_fails_the_lease_without_writes(
    break_identity: Callable[[], object],
) -> None:
    """F-5: a pool index must resolve to an onboarded sp_<pool>_<index> profile."""
    lease_pool(POOL, RUN_A, 4)
    break_identity()
    before = world()

    result = provision()

    assert result.result == "FAIL_LEASE"
    assert world() == before


def _own_a_fursuit(user: User) -> None:
    create_fursuit_record(owner=user)


def _hold_an_enrollment(user: User) -> None:
    convention = Convention.objects.create(
        name="Elsewhere",
        status=ConventionStatus.ACTIVE,
        start_date=dt.date(2026, 7, 2),
        end_date=dt.date(2026, 7, 5),
    )
    ConventionEnrollment.objects.create(user=user, convention=convention)


def _set_an_avatar(user: User) -> None:
    PlayerProfile.objects.filter(user=user).update(
        avatar_key="images/0123456789abcdef0123456789abcdef.png"
    )


def _catch_then_lose_enrollment(user: User) -> None:
    # The scenario never enrolls the catcher, so the Catch outlives any enrollment.
    scenario = create_catch_scenario(
        catcher_clerk_user_id=f"catcher_{user.pk}",
        target_owner_clerk_user_id=f"target_{user.pk}",
    )
    create_catch(scenario=dataclasses.replace(scenario, catcher_user=user))


@pytest.mark.parametrize(
    "dirtying",
    (
        ((0, _own_a_fursuit),),
        ((2, _hold_an_enrollment),),
        ((0, _set_an_avatar),),
        ((3, _catch_then_lose_enrollment),),
        ((0, _own_a_fursuit), (3, _set_an_avatar)),
    ),
    ids=(
        "owner-owns-a-fursuit",
        "catcher-has-an-enrollment",
        "owner-has-an-avatar",
        "catcher-has-a-catch",
        "two-dirty-identities",
    ),
)
def test_dirty_identity_is_quarantined_and_nothing_else_is_written(
    dirtying: tuple[tuple[int, Callable[[User], None]], ...],
) -> None:
    """F-6: leftover state quarantines exactly the dirty slots and blocks the run."""
    users = lease_pool(POOL, RUN_A, 4)
    for index, make_dirty in dirtying:
        make_dirty(users[index])
    dirty_indexes = {index for index, _ in dirtying}
    before = world(slots=False)
    clean_slots = [
        slot
        for slot in PoolSlot.objects.order_by("index").values()
        if slot["index"] not in dirty_indexes
    ]

    result = provision(owners=[0, 1], catchers=[2, 3])

    assert (result.result, result.counts) == (
        "FAIL_DIRTY",
        {"quarantined": len(dirty_indexes)},
    )
    assert world(slots=False) == before
    for slot in PoolSlot.objects.order_by("index"):
        if slot.index in dirty_indexes:
            assert (slot.state, slot.run_id, slot.lease_expires_at) == (
                "quarantined",
                None,
                None,
            )
    assert [
        slot
        for slot in PoolSlot.objects.order_by("index").values()
        if slot["index"] not in dirty_indexes
    ] == clean_slots


def test_runs_with_distinct_identities_share_nothing_and_run_ids_are_single_use() -> (
    None
):
    """F-6: separate runs are disjoint, and a used run ID is never provisioned again."""
    lease_pool(POOL, RUN_A, 3)
    lease_pool(POOL, RUN_B, 3)
    first = provision(owners=[0, 1], catchers=[2], fursuits_per_owner=1)
    second = provision(run_id=RUN_B, owners=[3, 4], catchers=[5], fursuits_per_owner=1)
    assert (first.result, second.result) == ("PASS", "PASS")

    runs = {run.run_id: run for run in FixtureRun.objects.all()}
    assert set(runs) == {RUN_A, RUN_B}
    by_run = {
        run_id: {(o.kind, o.object_id) for o in FixtureObject.objects.filter(run=run)}
        for run_id, run in runs.items()
    }
    assert by_run[RUN_A].isdisjoint(by_run[RUN_B])
    media = {
        run_id: {
            o.media_key for o in FixtureObject.objects.filter(run=run) if o.media_key
        }
        for run_id, run in runs.items()
    }
    assert len(media[RUN_A]) == len(media[RUN_B]) == 2
    assert media[RUN_A].isdisjoint(media[RUN_B])
    for run_id, indexes in ((RUN_A, (0, 1, 2)), (RUN_B, (3, 4, 5))):
        convention = Convention.objects.get(name=f"Sim {run_id[:8]}")
        enrolled = ConventionEnrollment.objects.filter(convention=convention)
        handles = PlayerProfile.objects.filter(
            user__in=[e.user_id for e in enrolled]
        ).values_list("handle", flat=True)
        assert set(handles) == {f"sp_{POOL}_{index}" for index in indexes}

    # Reuse is refused ahead of every other check (the identities are now dirty).
    before = world()
    again = provision(owners=[0, 1], catchers=[2], fursuits_per_owner=1)
    assert again.result == "FAIL_RUN_EXISTS"
    assert world() == before


@pytest.mark.parametrize(
    ("fault", "expected_result"),
    (
        (RuntimeError("private diagnostic"), "FAIL_ERROR"),
        (convention_services.FursuitActivationNotEligibleError(), "FAIL_INVARIANT"),
    ),
    ids=("unexpected-error", "domain-rejection"),
)
def test_failure_after_images_are_stored_rolls_back_and_records_a_failed_run(
    monkeypatch: pytest.MonkeyPatch,
    settings: SettingsWrapper,
    fault: Exception,
    expected_result: str,
) -> None:
    """F-9: no rows or images survive a late failure, and the run ID stays used."""
    settings.STORAGES = {**settings.STORAGES, **RECORDING_STORAGES}
    lease_pool(POOL, RUN_A, 4)
    baseline_key = seed_preexisting_fursuit()
    before = world(slots=False)
    recording = cast(RecordingStorage, default_storage)
    events_before = len(recording.events)

    real = convention_services.set_fursuit_activation_state
    calls: list[int] = []

    def fail_on_the_last_activation(*args: Any, **kwargs: Any) -> FursuitActivation:
        calls.append(1)
        if len(calls) == 4:
            raise fault
        return real(*args, **kwargs)

    monkeypatch.setattr(
        convention_services, "set_fursuit_activation_state", fail_on_the_last_activation
    )

    result = provision()

    assert len(calls) == 4  # the fault was reached after every image was stored
    assert result.result == expected_result
    saved = {
        name for event, name in recording.events[events_before:] if event == "save"
    }
    assert len(saved) == 4
    assert stored_keys() == {baseline_key}

    after = world(slots=False)
    ledger_free = {k: v for k, v in after.items() if k not in {"runs", "objects"}}
    assert ledger_free == {
        k: v for k, v in before.items() if k not in {"runs", "objects"}
    }
    run = FixtureRun.objects.get()
    assert (run.run_id, run.pool, run.status) == (RUN_A, POOL, FAILED)
    assert FixtureObject.objects.count() == 0
    failed = services.status(RUN_A)
    assert failed is not None
    assert failed.status == FAILED
    assert sum(failed.counts.values()) == 0

    # The failed run ID is spent: a clean retry under it is still refused.
    monkeypatch.undo()
    assert provision().result == "FAIL_RUN_EXISTS"
    assert world(slots=False) == after


def test_status_of_an_unknown_run_is_none() -> None:
    """Callers can tell an unknown run from a provisioned or failed one."""
    assert services.status(RUN_B) is None


def test_ledger_rejects_a_reused_run_id_and_a_shared_object() -> None:
    """F-6: the database itself refuses duplicate runs and shared fixture objects."""
    first = FixtureRun.objects.create(run_id=RUN_A, pool=POOL, status=PROVISIONED)
    second = FixtureRun.objects.create(run_id=RUN_B, pool=POOL, status=PROVISIONED)
    FixtureObject.objects.create(run=first, kind="convention", object_id=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        FixtureRun.objects.create(run_id=RUN_A, pool=POOL, status=FAILED)
    with pytest.raises(IntegrityError), transaction.atomic():
        FixtureObject.objects.create(run=second, kind="convention", object_id=1)


# --- F-10: fixture images -------------------------------------------------

_METADATA_SIGNATURES = (
    b"Exif\x00\x00",
    b"http://ns.adobe.com/xap/1.0/",
    b"<x:xmpmeta",
    b"eXIf",
    b"EXIF",
    b"XMP ",
)


def image_problems(content: bytes) -> list[str]:
    """Every way an image breaks the committed-fixture limits (empty when fine)."""
    problems: list[str] = []
    if len(content) > images.MAX_FIXTURE_IMAGE_BYTES:
        problems.append("too many bytes")
    try:
        with Image.open(BytesIO(content), formats=("JPEG", "PNG", "WEBP")) as image:
            if max(image.size) > images.MAX_FIXTURE_IMAGE_SIDE:
                problems.append("too many pixels on a side")
            if len(image.getexif()) or {"exif", "xmp", "XML:com.adobe.xmp"} & set(
                image.info
            ):
                problems.append("metadata present")
    except (UnidentifiedImageError, OSError):
        problems.append("not a JPEG, PNG, or WebP image")
    if any(signature in content for signature in _METADATA_SIGNATURES):
        problems.append("metadata signature present")
    try:
        normalize_image(ContentFile(content))
    except ImageValidationError:
        problems.append("rejected by media normalization")
    return problems


def png_bytes(size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_with_exif() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "Private Camera Maker"
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def content_of(file: Any) -> bytes:
    file.seek(0)
    data: bytes = file.read()
    return data


def test_committed_fixture_images_meet_the_format_size_and_metadata_limits() -> None:
    """F-10: whatever the maintainer commits is safe to ship (vacuous while empty)."""
    committed = sorted(
        path
        for path in images.IMAGE_DIRECTORY.iterdir()
        if path.is_file() and not path.name.startswith(".")
    )

    assert {path.name: image_problems(path.read_bytes()) for path in committed} == {
        path.name: [] for path in committed
    }


@pytest.mark.parametrize(
    "content",
    (jpeg_with_exif(), png_bytes((images.MAX_FIXTURE_IMAGE_SIDE + 1, 4), (9, 9, 9))),
    ids=("exif", "oversized-side"),
)
def test_the_image_limit_check_detects_violations(content: bytes) -> None:
    """F-10: the check above is not vacuous; known-bad images are flagged."""
    assert image_problems(content) != []
    assert image_problems(png_bytes((8, 8), (1, 2, 3))) == []


def test_fixture_images_cycle_in_sorted_order_and_ignore_non_images(
    tmp_path: Path,
) -> None:
    """F-10: files are used by sorted name, cycling; .gitkeep is not an image."""
    first, second = png_bytes((8, 8), (255, 0, 0)), png_bytes((8, 8), (0, 255, 0))
    (tmp_path / "b-second.png").write_bytes(second)
    (tmp_path / "a-first.png").write_bytes(first)
    (tmp_path / ".gitkeep").write_bytes(b"")

    chosen = [content_of(images.fixture_image(i, directory=tmp_path)) for i in range(3)]

    assert chosen == [first, second, first]


def test_empty_directory_yields_a_deterministic_acceptable_generated_png(
    tmp_path: Path,
) -> None:
    """F-10: with no committed images SETUP still supplies a valid 512x512 PNG."""
    (tmp_path / ".gitkeep").write_bytes(b"")

    first = content_of(images.fixture_image(4, directory=tmp_path))
    again = content_of(images.fixture_image(4, directory=tmp_path))

    assert first == again
    assert image_problems(first) == []
    with Image.open(BytesIO(first)) as generated:
        assert (generated.format, generated.size) == ("PNG", (512, 512))
