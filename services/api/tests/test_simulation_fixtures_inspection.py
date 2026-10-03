"""Acceptance coverage for the read-only simulation inspection (#222, R-3, R-4, R-9).

``inspect`` is the privileged read behind the simulator's reconciliation. These
tests run against real PostgreSQL: the read-only transaction, the lease guard, the
scope union, and the flag computations are all database behavior.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
from collections.abc import Callable, Mapping
from typing import Any

import pytest
from django.db import InternalError, connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from accounts.models import User
from catches.models import Catch
from catches.serializers import catch_history_entry_data
from conventions.models import (
    Convention,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from simulation_fixtures import inspection, inspection_remote, services
from simulation_fixtures.models import FAILED, FixtureRun
from simulation_pool.models import PoolSlot
from tests.authentication_support import create_test_user
from tests.catch_test_support import CatchScenario, create_catch, create_catch_scenario
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session
from tests.simulation_fixtures_test_support import (
    OTHER_RUN,
    POOL,
    RUN_A,
    RUN_B,
    create_pool_identity,
    lease_pool,
    world,
)

# The inspection opens its own transaction, so it must not nest inside the
# transaction a plain ``django_db`` test already holds open.
pytestmark = pytest.mark.django_db(transaction=True)

IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
ENVIRON = {"RAILWAY_ENVIRONMENT_NAME": "staging", "RAILWAY_SERVICE_NAME": "api"}

# Deliberately not ascending in role order, and offset from user primary keys, so a
# role-order or user-id shortcut cannot pass for a pool index.
INDEXES: dict[str, int] = {
    "owner0": 5,
    "owner1": 3,
    "catcher0": 8,
    "catcher1": 4,
    "catcher2": 9,
    "catcher3": 6,
    "outsider": 7,
}
PHOTO_KEY = "images/0123456789abcdef0123456789abcdef.png"
RELAY_LIMIT_BYTES = 65536
# Largest 64-bit ids: the widest integers a record can ever carry.
WIDE_ID = 9_000_000_000_000_000_000


@dataclasses.dataclass(frozen=True)
class Run:
    """A provisioned run: its leased identities, Convention, and ledger fursuits."""

    users: dict[str, User]
    convention: Convention
    fursuits: dict[str, list[Fursuit]]
    activations: dict[int, FursuitActivation]


def seed_run() -> Run:
    """Lease seven identities, provision as the real flow does, leave the outsider bare."""
    lease_pool(POOL, OTHER_RUN, 3)  # Offsets the run's indexes from zero.
    by_index = lease_pool(POOL, RUN_A, 7)
    assert sorted(by_index) == sorted(INDEXES.values())
    provisioned = services.provision(
        POOL,
        RUN_A,
        [INDEXES["owner0"], INDEXES["owner1"]],
        [INDEXES[f"catcher{n}"] for n in range(4)],
        2,
    )
    assert provisioned.result == "PASS"
    users = {role: by_index[index] for role, index in INDEXES.items()}
    convention = Convention.objects.get()
    return Run(
        users=users,
        convention=convention,
        fursuits={
            role: list(Fursuit.objects.filter(owner=users[role]).order_by("pk"))
            for role in ("owner0", "owner1")
        },
        activations={
            activation.fursuit_id: activation
            for activation in FursuitActivation.objects.filter(convention=convention)
        },
    )


def run_catch(run: Run, catcher: str, owner: str, position: int) -> Catch:
    """A catch with full provenance inside the run, as a real confirm would leave."""
    fursuit = run.fursuits[owner][position]
    activation = run.activations[fursuit.pk]
    return create_catch(
        scenario=CatchScenario(
            catcher_user=run.users[catcher],
            fursuit=fursuit,
            convention=run.convention,
            activation=activation,
            catch_session=create_catch_session(activation=activation),
        )
    )


def history_caught_at(catch: Catch) -> str:
    """``caught_at`` exactly as the public catch history serializer formats it."""
    request = Request(APIRequestFactory().get("/"))
    return str(catch_history_entry_data(catch, request=request)["caught_at"])


def record(
    catch: Catch,
    *,
    catcher: int | None,
    owner: int | None,
    run_convention: bool = True,
    provenance: bool = True,
    in_window: bool = True,
) -> dict[str, object]:
    catch.refresh_from_db()
    return {
        "id": catch.pk,
        "catcher": catcher,
        "fursuit": catch.fursuit_id,
        "fursuit_owner": owner,
        "run_convention": run_convention,
        "provenance": provenance,
        "in_window": in_window,
        "caught_at": history_caught_at(catch),
    }


def data(
    catches: list[dict[str, object]],
    *,
    fursuits: list[dict[str, object]] | None = None,
    photos: bool = True,
    avatars: list[int] | None = None,
) -> dict[str, object]:
    return {
        "catches": catches,
        "fursuits": fursuits or [],
        "fixture_photos_unchanged": photos,
        "avatars": avatars or [],
    }


def inspect(
    *, pool: str = POOL, run_id: str = RUN_A, identities: Mapping[str, int] = INDEXES
) -> inspection.InspectionOutcome:
    return inspection.inspect(pool, run_id, dict(identities))


def new_fursuit(owner: User, name: str) -> Fursuit:
    return Fursuit.objects.create(owner=owner, name=name, photo_key=PHOTO_KEY)


def test_clean_run_reports_every_field_for_a_legitimate_catch_set() -> None:
    """R-3/R-4: indexes (not ids), id ordering, history timestamp, extras, and no leakage."""
    run = seed_run()
    first = run_catch(run, "catcher0", "owner0", 0)  # Pool index 8, created first.
    second = run_catch(run, "catcher1", "owner0", 1)  # Pool index 4.
    created_by_owner0 = new_fursuit(run.users["owner0"], "Extra A")
    created_by_owner1 = new_fursuit(run.users["owner1"], "Extra B")
    # Neither a stranger's fursuit nor a stranger's avatar belongs in the answer.
    new_fursuit(create_test_user(), "Stranger")
    stranger = create_pool_identity("other", 1)
    PlayerProfile.objects.filter(user=stranger).update(avatar_key=PHOTO_KEY)

    outcome = inspect()

    assert outcome == inspection.InspectionOutcome(
        "PASS",
        data(
            [
                record(first, catcher=8, owner=5),
                record(second, catcher=4, owner=5),
            ],
            fursuits=[
                {"id": created_by_owner0.pk, "owner": 5},
                {"id": created_by_owner1.pk, "owner": 3},
            ],
        ),
    )
    json.dumps(outcome.data)  # Plain JSON types only.


def _foreign_catch_by_run_catcher(run: Run) -> dict[str, object]:
    """A run catcher's catch in another Convention."""
    foreign = create_catch_scenario(
        catcher_clerk_user_id="arm1_catcher", target_owner_clerk_user_id="arm1_owner"
    )
    catch = create_catch(
        scenario=dataclasses.replace(foreign, catcher_user=run.users["catcher1"])
    )
    return record(catch, catcher=4, owner=None, run_convention=False)


def _stranger_catch_in_run_convention(run: Run) -> dict[str, object]:
    """A non-run catcher, on a non-run fursuit, inside the run Convention."""
    foreign = create_catch_scenario(
        catcher_clerk_user_id="arm2_catcher", target_owner_clerk_user_id="arm2_owner"
    )
    activation = create_activation_row(
        fursuit=foreign.fursuit, convention=run.convention, active=True
    )
    catch = create_catch(
        scenario=CatchScenario(
            catcher_user=foreign.catcher_user,
            fursuit=foreign.fursuit,
            convention=run.convention,
            activation=activation,
            catch_session=create_catch_session(activation=activation),
        )
    )
    return record(catch, catcher=None, owner=None)


def _stranger_catch_of_run_fursuit_elsewhere(run: Run) -> dict[str, object]:
    """A non-run catcher of a run owner's fursuit, in another Convention."""
    foreign = create_catch_scenario(
        catcher_clerk_user_id="arm3_catcher", target_owner_clerk_user_id="arm3_owner"
    )
    fursuit = run.fursuits["owner0"][0]
    activation = create_activation_row(
        fursuit=fursuit, convention=foreign.convention, active=True
    )
    catch = create_catch(
        scenario=CatchScenario(
            catcher_user=foreign.catcher_user,
            fursuit=fursuit,
            convention=foreign.convention,
            activation=activation,
            catch_session=create_catch_session(activation=activation),
        )
    )
    return record(catch, catcher=None, owner=5, run_convention=False)


@pytest.mark.parametrize(
    "seed_leak",
    (
        _foreign_catch_by_run_catcher,
        _stranger_catch_in_run_convention,
        _stranger_catch_of_run_fursuit_elsewhere,
    ),
    ids=(
        "run-catcher-elsewhere",
        "stranger-in-run-convention",
        "run-fursuit-elsewhere",
    ),
)
def test_each_leak_direction_is_in_scope_and_unrelated_catches_are_not(
    seed_leak: Callable[[Run], dict[str, object]],
) -> None:
    """R-3: the scope is the union of all three arms; nothing else is returned."""
    run = seed_run()
    unrelated = create_catch_scenario(
        catcher_clerk_user_id="unrelated_catcher",
        target_owner_clerk_user_id="unrelated_owner",
    )
    create_catch(scenario=unrelated)
    leak = seed_leak(run)

    outcome = inspect()

    assert outcome == inspection.InspectionOutcome("PASS", data([leak]))


@dataclasses.dataclass(frozen=True)
class Break:
    """A seeded deviation and the part of the expected data it must change."""

    record: dict[str, bool] = dataclasses.field(default_factory=dict[str, bool])
    top: dict[str, object] = dataclasses.field(default_factory=dict[str, object])


def _session_of_another_activation(run: Run, catch: Catch) -> Break:
    other = run.activations[run.fursuits["owner0"][1].pk]
    session = create_catch_session(activation=other)
    Catch.objects.filter(pk=catch.pk).update(catch_session=session)
    return Break(record={"provenance": False})


def _activation_of_another_fursuit(run: Run, catch: Catch) -> Break:
    other = run.activations[run.fursuits["owner0"][1].pk]
    session = create_catch_session(activation=other)
    Catch.objects.filter(pk=catch.pk).update(activation=other, catch_session=session)
    return Break(record={"provenance": False})


def _activation_in_another_convention(run: Run, catch: Catch) -> Break:
    elsewhere = Convention.objects.create(
        name="Elsewhere",
        status=ConventionStatus.ACTIVE,
        start_date=run.convention.start_date,
        end_date=run.convention.end_date,
    )
    activation = create_activation_row(
        fursuit=catch.fursuit, convention=elsewhere, active=True
    )
    session = create_catch_session(activation=activation)
    Catch.objects.filter(pk=catch.pk).update(
        activation=activation, catch_session=session
    )
    return Break(record={"provenance": False})


def _caught_before_the_run(_run: Run, catch: Catch) -> Break:
    created_at = FixtureRun.objects.get(run_id=RUN_A).created_at
    Catch.objects.filter(pk=catch.pk).update(
        caught_at=created_at - dt.timedelta(minutes=1)
    )
    return Break(record={"in_window": False})


def _caught_in_the_future(_run: Run, catch: Catch) -> Break:
    Catch.objects.filter(pk=catch.pk).update(
        caught_at=timezone.now() + dt.timedelta(hours=1)
    )
    return Break(record={"in_window": False})


def _fixture_photo_replaced(run: Run, _catch: Catch) -> Break:
    Fursuit.objects.filter(pk=run.fursuits["owner0"][0].pk).update(
        photo_key="images/ffffffffffffffffffffffffffffffff.png"
    )
    return Break(top={"fixture_photos_unchanged": False})


def _avatars_set(run: Run, _catch: Catch) -> Break:
    # Role order is [5, 3]; the answer is the sorted indexes. A stranger's avatar is
    # not a run identity's.
    PlayerProfile.objects.filter(
        user__in=[run.users["owner0"], run.users["owner1"]]
    ).update(avatar_key=PHOTO_KEY)
    PlayerProfile.objects.filter(user=create_pool_identity("other", 0)).update(
        avatar_key=PHOTO_KEY
    )
    return Break(top={"avatars": [3, 5]})


@pytest.mark.parametrize(
    "seed_break",
    (
        _session_of_another_activation,
        _activation_of_another_fursuit,
        _activation_in_another_convention,
        _caught_before_the_run,
        _caught_in_the_future,
        _fixture_photo_replaced,
        _avatars_set,
    ),
    ids=(
        "provenance-session-of-another-activation",
        "provenance-activation-of-another-fursuit",
        "provenance-activation-in-another-convention",
        "window-before-the-run",
        "window-after-now",
        "fixture-photo-replaced",
        "avatar-set",
    ),
)
def test_each_flag_changes_only_for_its_own_break(
    seed_break: Callable[[Run, Catch], Break],
) -> None:
    """R-3/R-6: provenance, window, photo, and avatar flags are independent."""
    run = seed_run()
    catch = run_catch(run, "catcher0", "owner0", 0)
    deviation = seed_break(run, catch)

    outcome = inspect()

    expected = data([record(catch, catcher=8, owner=5, **deviation.record)])
    assert outcome == inspection.InspectionOutcome("PASS", expected | deviation.top)


def _leased_to_another_run(_run: Run) -> tuple[str, str, Mapping[str, int]]:
    PoolSlot.objects.filter(pool=POOL, index=INDEXES["outsider"]).update(run_id=RUN_B)
    return POOL, RUN_A, INDEXES


def _lease_expired(_run: Run) -> tuple[str, str, Mapping[str, int]]:
    PoolSlot.objects.filter(pool=POOL, index=INDEXES["catcher3"]).update(
        lease_expires_at=timezone.now() - dt.timedelta(seconds=1)
    )
    return POOL, RUN_A, INDEXES


def _run_never_provisioned(_run: Run) -> tuple[str, str, Mapping[str, int]]:
    unprovisioned = lease_pool(POOL, RUN_B, 7)
    return POOL, RUN_B, dict(zip(INDEXES, unprovisioned, strict=True))


def _run_leased_in_another_pool(_run: Run) -> tuple[str, str, Mapping[str, int]]:
    # RUN_A is provisioned in POOL; the same run id also holds leases in "beta",
    # where it was never provisioned.
    elsewhere = lease_pool("beta", RUN_A, 7)
    return "beta", RUN_A, dict(zip(INDEXES, elsewhere, strict=True))


def _run_failed(_run: Run) -> tuple[str, str, Mapping[str, int]]:
    FixtureRun.objects.filter(run_id=RUN_A).update(status=FAILED)
    return POOL, RUN_A, INDEXES


@pytest.mark.parametrize(
    ("seed_state", "code"),
    (
        (_leased_to_another_run, "FAIL_LEASE"),
        (_lease_expired, "FAIL_LEASE"),
        (_run_never_provisioned, "FAIL_RUN_UNKNOWN"),
        (_run_leased_in_another_pool, "FAIL_RUN_UNKNOWN"),
        (_run_failed, "FAIL_RUN_UNKNOWN"),
    ),
    ids=(
        "leased-to-another-run",
        "lease-expired",
        "never-provisioned",
        "run-from-another-pool",
        "failed-run",
    ),
)
def test_unleased_or_unprovisioned_runs_are_refused_without_data(
    seed_state: Callable[[Run], tuple[str, str, Mapping[str, int]]], code: str
) -> None:
    """R-4/G13: only a live, provisioned run's own leases can be inspected."""
    run = seed_run()
    run_catch(run, "catcher0", "owner0", 0)
    pool, run_id, identities = seed_state(run)

    assert inspect(pool=pool, run_id=run_id, identities=identities) == (
        inspection.InspectionOutcome(code, {})
    )


def test_inspection_transaction_starts_read_only() -> None:
    """R-9: the first statement inside ``inspect`` makes the transaction read-only."""
    run = seed_run()
    run_catch(run, "catcher0", "owner0", 0)

    with CaptureQueriesContext(connection) as queries:
        outcome = inspect()

    assert outcome.result == "PASS"
    statements = [
        entry["sql"].strip().rstrip(";").upper() for entry in queries.captured_queries
    ]
    # Django logs the transaction's own BEGIN; nothing may run between it and the SET.
    assert next(sql for sql in statements if sql != "BEGIN") == (
        "SET TRANSACTION READ ONLY"
    )


def test_a_write_inside_the_inspection_transaction_is_rejected_by_postgresql() -> None:
    """R-9: the read-only mode really governs the transaction ``inspect`` reads in.

    A write is injected on ``inspect``'s own connection immediately after its
    ``SET TRANSACTION READ ONLY``. If the statement were issued outside the
    transaction, or never took effect, the write would succeed.
    """
    seed_run()
    table = connection.ops.quote_name(PoolSlot._meta.db_table)  # pyright: ignore[reportPrivateUsage]
    rejected: list[BaseException] = []

    def write_after_read_only(
        execute: Callable[..., Any], sql: str, params: Any, many: bool, context: Any
    ) -> Any:
        result = execute(sql, params, many, context)
        if sql.strip().rstrip(";").upper() == "SET TRANSACTION READ ONLY":
            try:
                execute(f"UPDATE {table} SET updated_at = now()", None, False, context)
            except InternalError as error:
                rejected.append(error)
                raise
        return result

    with (
        connection.execute_wrapper(write_after_read_only),
        pytest.raises(InternalError, match="read-only"),
    ):
        inspect()

    assert len(rejected) == 1


@pytest.mark.parametrize(
    ("fursuit_count", "catch_count", "result"),
    (
        (inspection.MAX_RECORDS, inspection.MAX_RECORDS, "PASS"),
        (inspection.MAX_RECORDS, inspection.MAX_RECORDS + 1, "FAIL_LIMIT"),
        (inspection.MAX_RECORDS + 1, 0, "FAIL_LIMIT"),
    ),
    ids=("at-both-limits", "catches-over", "fursuits-over"),
)
def test_record_caps_and_the_output_fits_the_launcher_limit(
    fursuit_count: int, catch_count: int, result: str
) -> None:
    """R-4: 201 of either kind is refused; 200 of both still fits the 64 KiB launcher cap."""
    run = seed_run()
    owner = run.users["owner0"]
    Fursuit.objects.bulk_create(
        [
            Fursuit(id=WIDE_ID + n, owner=owner, name=f"Bulk {n}", photo_key=PHOTO_KEY)
            for n in range(fursuit_count)
        ]
    )
    ledger_fursuit = run.fursuits["owner0"][0]
    activation = run.activations[ledger_fursuit.pk]
    session = create_catch_session(activation=activation)
    # Distinct (catcher, fursuit) pairs: the bulk fursuits first, then one ledger fursuit.
    targets = [WIDE_ID + n for n in range(min(catch_count, fursuit_count))]
    targets += [ledger_fursuit.pk] * (catch_count - len(targets))
    Catch.objects.bulk_create(
        [
            Catch(
                id=WIDE_ID + n,
                catcher_user=run.users["catcher0"],
                fursuit_id=fursuit_id,
                convention=run.convention,
                activation=activation,
                catch_session=session,
            )
            for n, fursuit_id in enumerate(targets)
        ]
    )

    response = inspection_remote.execute(
        {
            "operation": "inspect",
            "identity": dict(IDENTITY),
            "arguments": {"pool": POOL, "run_id": RUN_A, "identities": INDEXES},
        },
        runtime_identity=IDENTITY,
        environ=ENVIRON,
    )

    if result == "FAIL_LIMIT":
        assert response == {"result": "FAIL_LIMIT", "data": {}}
        return
    payload = response["data"]
    assert response["result"] == "PASS"
    assert isinstance(payload, dict)
    assert len(payload["catches"]) == catch_count  # pyright: ignore[reportUnknownArgumentType]
    assert len(payload["fursuits"]) == fursuit_count  # pyright: ignore[reportUnknownArgumentType]
    relayed = json.dumps(response, sort_keys=True) + "\n"
    assert len(relayed.encode()) <= RELAY_LIMIT_BYTES


def request(
    operation: str, arguments: Mapping[str, object] | None = None
) -> dict[str, object]:
    return {
        "operation": operation,
        "identity": dict(IDENTITY),
        "arguments": dict(
            arguments
            if arguments is not None
            else {"pool": POOL, "run_id": RUN_A, "identities": dict(INDEXES)}
        ),
    }


def execute(
    payload: object,
    *,
    runtime_identity: Mapping[str, object] = IDENTITY,
    environ: Mapping[str, str] = ENVIRON,
) -> dict[str, object]:
    return inspection_remote.execute(
        payload, runtime_identity=runtime_identity, environ=environ
    )


@pytest.mark.parametrize(
    ("runtime_identity", "environ", "payload"),
    (
        ({**IDENTITY, "source_sha": "b" * 40}, ENVIRON, request("inspect")),
        (
            {**IDENTITY, "deployment_id": "99999999-9999-4999-8999-999999999999"},
            ENVIRON,
            request("inspect"),
        ),
        (
            IDENTITY,
            {**ENVIRON, "RAILWAY_ENVIRONMENT_NAME": "development"},
            request("inspect"),
        ),
        (IDENTITY, {**ENVIRON, "RAILWAY_SERVICE_NAME": "worker"}, request("inspect")),
        # The target is proven before the request is even validated.
        (IDENTITY, {}, request("drop_table", {"unexpected": 1})),
    ),
    ids=(
        "source-sha-mismatch",
        "deployment-mismatch",
        "not-the-staging-environment",
        "not-the-api-service",
        "mismatch-before-validation",
    ),
)
def test_target_mismatch_is_refused_before_any_database_access(
    runtime_identity: Mapping[str, object],
    environ: Mapping[str, str],
    payload: dict[str, object],
    django_assert_num_queries: Any,
) -> None:
    """R-9: outside the exact Staging API identity nothing is read."""
    with django_assert_num_queries(0):
        response = execute(payload, runtime_identity=runtime_identity, environ=environ)

    assert response == {"result": "FAIL_TARGET", "data": {}}


@pytest.mark.parametrize(
    "payload",
    (
        request(
            "provision",
            {
                "pool": POOL,
                "run_id": RUN_A,
                "owners": [0, 1],
                "catchers": [2],
                "fursuits_per_owner": 1,
            },
        ),
        request("status", {"run_id": RUN_A}),
    ),
    ids=("provision", "status"),
)
def test_this_channel_has_no_route_to_the_other_fixture_operations(
    payload: dict[str, object],
) -> None:
    """R-9: the inspection remote accepts only ``inspect``; provision cannot run here."""
    lease_pool(POOL, RUN_A, 3)
    before = world()

    response = execute(payload)

    assert response == {"result": "FAIL_REQUEST", "data": {}}
    assert world() == before


def _with_identities(**changes: object) -> dict[str, object]:
    return request(
        "inspect",
        {"pool": POOL, "run_id": RUN_A, "identities": {**INDEXES, **changes}},
    )


def _arguments(**changes: object) -> dict[str, object]:
    return request(
        "inspect",
        {"pool": POOL, "run_id": RUN_A, "identities": dict(INDEXES)} | changes,
    )


@pytest.mark.parametrize(
    "payload",
    (
        _arguments(extra=1),
        request("inspect", {"pool": POOL, "identities": dict(INDEXES)}),
        _arguments(run_id=RUN_A.upper()),
        _arguments(pool="Alpha"),
        _arguments(identities=list(INDEXES.values())),
        request(
            "inspect",
            {
                "pool": POOL,
                "run_id": RUN_A,
                "identities": {
                    role: index for role, index in INDEXES.items() if role != "catcher3"
                },
            },
        ),
        _with_identities(catcher4=10),
        _with_identities(owner0=True),
        _with_identities(owner0="5"),
        _with_identities(owner1=INDEXES["owner0"]),
        {**request("inspect"), "extra": 1},
        {**request("inspect"), "arguments": []},
    ),
    ids=(
        "extra-argument",
        "missing-run-id",
        "run-id-not-canonical",
        "pool-invalid",
        "identities-not-an-object",
        "role-missing",
        "role-extra",
        "index-boolean",
        "index-string",
        "duplicate-index",
        "extra-top-level-key",
        "arguments-not-an-object",
    ),
)
def test_only_the_exact_request_shape_reaches_inspect(payload: object) -> None:
    """R-4: any other request shape is FAIL_REQUEST."""
    seed_run()

    assert execute(payload) == {"result": "FAIL_REQUEST", "data": {}}
