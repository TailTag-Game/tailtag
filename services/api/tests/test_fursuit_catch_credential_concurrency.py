"""Real PostgreSQL, lock-observed credential race acceptance tests."""

from __future__ import annotations

import datetime
import hashlib
import math
import os
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from queue import Empty, Queue
from threading import Event
from time import monotonic, sleep
from typing import Any, cast

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from conventions.catch_credential_protocol import (
    CATCH_CREDENTIAL_PAYLOAD_PREFIX,
    CATCH_CREDENTIAL_TOKEN_LENGTH,
)
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import force_authenticated_client
from tests.catch_credential_test_support import (
    NOT_FOUND_DETAIL,
    catch_credential_model,
    create_credential,
    create_credential_scenario,
    owner_credential_path,
    resolution_path,
    rotation_path,
)
from tests.fursuit_activation_test_support import (
    activation_detail_path,
    create_activation_row,
)
from tests.fursuit_catch_session_test_support import (
    catch_session_path,
    create_catch_session,
)


def _wait_seconds() -> float:
    try:
        value = float(os.environ.get("TAILTAG_TEST_LOCK_WAIT_SECONDS", "5.0"))
    except ValueError:
        return 5.0
    return value if math.isfinite(value) and value > 0 else 5.0


_WAIT_SECONDS = _wait_seconds()
_RESULT_SECONDS = 25.0


def _configured_pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', '18000ms', false)")
        cursor.execute("SELECT set_config('statement_timeout', '20000ms', false)")
        cursor.execute("SELECT pg_backend_pid()")
        row = cursor.fetchone()
    assert row is not None
    return int(row[0])


def _worker(action: Callable[[], Any], pids: Queue[int]) -> Any:
    close_old_connections()
    try:
        pids.put(_configured_pid())
        return action()
    finally:
        connection.close()


def _pid(queue: Queue[int], future: Future[Any]) -> int:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        try:
            return queue.get_nowait()
        except Empty:
            if future.done():
                pytest.fail(
                    f"worker completed before lock evidence: {future.result()!r}"
                )
            sleep(0.01)
    pytest.fail("worker did not publish a backend PID")


def _blocked(waiter: int, holder: int, future: Future[Any]) -> None:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        if future.done():
            pytest.fail(f"worker completed before lock evidence: {future.result()!r}")
        with connection.cursor() as cursor:
            cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [holder, waiter])
            row = cursor.fetchone()
        assert row is not None
        if row[0]:
            return
        sleep(0.01)
    pytest.fail(f"backend {waiter} did not block behind holder {holder}")


def _blocked_directly_or_transitively(
    *, waiter: int, holder: int, predecessor: int, future: Future[Any]
) -> None:
    deadline = monotonic() + _WAIT_SECONDS
    while monotonic() < deadline:
        if future.done():
            pytest.fail("second worker completed before lock evidence")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_blocking_pids(%s), pg_blocking_pids(%s)",
                [waiter, predecessor],
            )
            row = cursor.fetchone()
        assert row is not None
        waiter_blockers, predecessor_blockers = map(set, row)
        if holder in waiter_blockers or (
            predecessor in waiter_blockers and holder in predecessor_blockers
        ):
            return
        sleep(0.01)
    pytest.fail("second worker did not join the serialized PostgreSQL lock chain")


def _race(
    lock: Callable[[], Any], first: Callable[[], Any], second: Callable[[], Any]
) -> tuple[Any, Any]:
    """Use a held row plus pg_blocking_pids, never a sleep-selected winner."""
    first_pids: Queue[int] = Queue()
    second_pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=2) as pool:
        with transaction.atomic():
            held = lock()
            assert held.pk
            holder_pid = _configured_pid()
            one = pool.submit(_worker, first, first_pids)
            one_pid = _pid(first_pids, one)
            _blocked(one_pid, holder_pid, one)
            two = pool.submit(_worker, second, second_pids)
            two_pid = _pid(second_pids, two)
            _blocked_directly_or_transitively(
                waiter=two_pid, holder=holder_pid, predecessor=one_pid, future=two
            )
        try:
            return one.result(timeout=_RESULT_SECONDS), two.result(
                timeout=_RESULT_SECONDS
            )
        except IntegrityError as error:
            pytest.fail(f"expected credential race leaked IntegrityError: {error}")


def assert_credential_history(activation: FursuitActivation) -> list[Any]:
    rows = list(catch_credential_model().objects.filter(activation=activation))
    assert sum(row.revoked_at is None for row in rows) <= 1
    assert all(
        (row.revoked_at is None) == (row.revocation_reason is None) for row in rows
    )
    return rows


def _assert_results(*results: Any) -> None:
    for result in results:
        status = getattr(result, "status_code", None)
        assert status != 500, f"expected race leaked HTTP 500: {result!r}"


def _separate_connection(action: Callable[[], Any]) -> Any:
    """Execute a lock-free read/write participant on its own PostgreSQL connection."""
    pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_worker, action, pids)
        _pid(pids, future)
        return future.result(timeout=_RESULT_SECONDS)


def _gate_resolution_eligibility(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Event, Event]:
    """Pause a lock-free preview at its approved target-eligibility collaborator."""
    # Delayed import retains RED collection safety until the credential module exists.
    from conventions import catch_credentials

    entered = Event()
    continue_resolution = Event()
    original = catch_credentials.is_fursuit_activation_eligible

    def gated(activation: FursuitActivation) -> bool:
        result = original(activation)
        entered.set()
        assert continue_resolution.wait(_WAIT_SECONDS), (
            "resolution gate was not released"
        )
        return result

    monkeypatch.setattr(catch_credentials, "is_fursuit_activation_eligible", gated)
    return entered, continue_resolution


def _token(label: str) -> str:
    """Return a deterministic, URL-safe, globally distinct test token."""
    return hashlib.sha256(label.encode()).hexdigest()[:CATCH_CREDENTIAL_TOKEN_LENGTH]


def _payload(token: str) -> str:
    return f"{CATCH_CREDENTIAL_PAYLOAD_PREFIX}{token}"


def _setup(label: str, *, session: bool = False) -> tuple[Any, FursuitActivation, Any]:
    scenario = create_credential_scenario(clerk_user_id=f"credential_race_{label}")
    activation = create_activation_row(
        fursuit=scenario.fursuit, convention=scenario.convention, active=True
    )
    credential = create_credential(activation=activation, token=_token(label))
    if session:
        create_catch_session(activation=activation)
    return scenario, activation, credential


def _lock_fursuit(s: Any) -> Fursuit:
    return Fursuit.objects.select_for_update().get(pk=s.fursuit.pk)


def _lock_profile(s: Any) -> PlayerProfile:
    return PlayerProfile.objects.select_for_update().get(pk=s.profile.pk)


def _lock_enrollment(s: Any) -> ConventionEnrollment:
    return ConventionEnrollment.objects.select_for_update().get(pk=s.enrollment.pk)


def _lock_convention(s: Any) -> Convention:
    return Convention.objects.select_for_update().get(pk=s.convention.pk)


def _fetch(s: Any) -> Any:
    return force_authenticated_client(user=User.objects.get(pk=s.user.pk)).get(
        owner_credential_path(s.convention.pk, s.fursuit.pk)
    )


def _rotate(s: Any) -> Any:
    return force_authenticated_client(user=User.objects.get(pk=s.user.pk)).post(
        rotation_path(s.convention.pk, s.fursuit.pk),
        b"",
        content_type="application/json",
    )


def _deactivate(s: Any) -> Any:
    return force_authenticated_client(user=User.objects.get(pk=s.user.pk)).put(
        activation_detail_path(s.convention.pk, s.fursuit.pk),
        {"is_active": False},
        content_type="application/json",
    )


def _operator_revoke(operator_id: int, credential_id: int) -> Any:
    client = Client()
    client.force_login(User.objects.get(pk=operator_id))
    return client.post(
        reverse(
            "admin:conventions_fursuitcatchcredential_change", args=(credential_id,)
        ),
        {"revoke": "1"},
    )


def _resolve(s: Any, token: str) -> Any:
    return force_authenticated_client(user=User.objects.get(pk=s.user.pk)).post(
        resolution_path(s.convention.pk),
        {"payload": _payload(token)},
        content_type="application/json",
    )


def _session(s: Any, active: bool) -> Any:
    return force_authenticated_client(user=User.objects.get(pk=s.user.pk)).put(
        catch_session_path(s.convention.pk, s.fursuit.pk),
        {"is_active": active},
        content_type="application/json",
    )


def _disable_fursuit(s: Any) -> Any:
    from fursuits.services import set_fursuit_enabled

    return set_fursuit_enabled(fursuit_id=s.fursuit.pk, is_enabled=False)


def _disable_profile(s: Any) -> Any:
    from profiles.services import set_profile_enabled

    return set_profile_enabled(profile_id=s.profile.pk, is_enabled=False)


def _remove_enrollment(s: Any) -> Any:
    from conventions.services import remove_convention_enrollment

    assert s.enrollment is not None
    return remove_convention_enrollment(enrollment_id=s.enrollment.pk)


def _pause_convention(s: Any) -> Any:
    from conventions.services import set_convention_admin_state

    return set_convention_admin_state(
        convention_id=s.convention.pk,
        name=s.convention.name,
        status=ConventionStatus.PAUSED,
        start_date=s.convention.start_date,
        end_date=s.convention.end_date,
    )


@pytest.mark.django_db(transaction=True)
def test_race_1_two_first_fetches_converge_on_one_current_payload() -> None:
    """AC-05/14: two first fetches have one visible credential, not two creators."""
    # Keep this first-creation race collection-safe yet RED on the missing
    # persistence contract, rather than reporting a misleading absent-route lock wait.
    catch_credential_model()
    s = create_credential_scenario(clerk_user_id="credential_race_first_fetch")
    activation = create_activation_row(
        fursuit=s.fursuit, convention=s.convention, active=True
    )
    one, two = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        lambda: _fetch(s),
        lambda: _fetch(s),
    )
    _assert_results(one, two)
    assert one.status_code == two.status_code == 200
    assert one.json() == two.json()
    assert len(assert_credential_history(activation)) == 1


@pytest.mark.django_db(transaction=True)
def test_unrelated_credential_creation_integrity_error_propagates_without_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-05/06/14: recovery is limited to the two named credential constraints."""
    model = catch_credential_model()
    s = create_credential_scenario(clerk_user_id="credential_unrelated_integrity")
    create_activation_row(fursuit=s.fursuit, convention=s.convention, active=True)

    def unrelated_constraint(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise IntegrityError(
            'violates constraint "unrelated_credential_test_constraint"'
        )

    monkeypatch.setattr(model.objects, "create", unrelated_constraint)
    with pytest.raises(IntegrityError, match="unrelated_credential_test_constraint"):
        _fetch(s)


@pytest.mark.django_db(transaction=True)
def test_race_2_fetch_vs_rotation_has_a_legal_serial_payload_and_one_current_row() -> (
    None
):
    """AC-05/06/14: fetch may see old or replacement, never a corrupt middle state."""
    for fetch_first in (True, False):
        s, activation, old = _setup(f"fetch_rotation_{fetch_first}")
        first = lambda s=s, fetch_first=fetch_first: (
            _fetch(s) if fetch_first else _rotate(s)
        )
        second = lambda s=s, fetch_first=fetch_first: (
            _rotate(s) if fetch_first else _fetch(s)
        )
        one, two = _race(
            lambda activation=activation: (
                FursuitActivation.objects.select_for_update().get(pk=activation.pk)
            ),
            first,
            second,
        )
        _assert_results(one, two)
        fetch, rotation = (one, two) if fetch_first else (two, one)
        assert fetch.status_code == rotation.status_code == 200
        current = next(
            row
            for row in assert_credential_history(activation)
            if row.revoked_at is None
        )
        if fetch_first:
            assert fetch.json() == {"payload": _payload(old.token)}
        else:
            assert fetch.json() == {"payload": _payload(current.token)}
            assert fetch.json() != {"payload": _payload(old.token)}
        old.refresh_from_db()
        assert old.revocation_reason == "owner_rotation"


@pytest.mark.django_db(transaction=True)
def test_race_3_two_rotations_leave_successive_terminal_history_and_one_current_row() -> (
    None
):
    """AC-06/14: rotation is state-changing even when serialized concurrently."""
    s, activation, old = _setup("double_rotation")
    one, two = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        lambda: _rotate(s),
        lambda: _rotate(s),
    )
    _assert_results(one, two)
    assert one.status_code == two.status_code == 200
    rows = assert_credential_history(activation)
    assert len(rows) == 3
    assert sum(row.revocation_reason == "owner_rotation" for row in rows) == 2
    old.refresh_from_db()
    assert old.revocation_reason == "owner_rotation"


@pytest.mark.django_db(transaction=True)
def test_race_4_rotation_vs_operator_revoke_never_rewrites_terminal_history() -> None:
    """AC-06/15/14: forced order fixes exact terminal history without relabeling."""
    operator = User.objects.create_superuser("credential_race_operator", password="pw")
    for rotation_first in (True, False):
        s, activation, old = _setup(f"rotation_operator_{rotation_first}")
        first = lambda s=s, old=old, rotation_first=rotation_first: (
            _rotate(s) if rotation_first else _operator_revoke(operator.pk, old.pk)
        )
        second = lambda s=s, old=old, rotation_first=rotation_first: (
            _operator_revoke(operator.pk, old.pk) if rotation_first else _rotate(s)
        )
        one, two = _race(
            lambda activation=activation: (
                FursuitActivation.objects.select_for_update().get(pk=activation.pk)
            ),
            first,
            second,
        )
        _assert_results(one, two)
        rotation, revoke = (one, two) if rotation_first else (two, one)
        assert rotation.status_code == 200 and revoke.status_code in {200, 302, 403}
        old.refresh_from_db()
        old_terminal = (old.revoked_at, old.revocation_reason, old.updated_at)
        assert old_terminal[0] is not None
        assert old_terminal[1] == ("owner_rotation" if rotation_first else "operator")
        rows = assert_credential_history(activation)
        assert len(rows) == 2
        successor = next(row for row in rows if row.pk != old.pk)
        assert successor.revoked_at is None and successor.pk != old.pk
        old.refresh_from_db()
        assert (old.revoked_at, old.revocation_reason, old.updated_at) == old_terminal


@pytest.mark.django_db(transaction=True)
def test_race_5_operator_revoke_vs_fetch_forces_both_serial_outcomes() -> None:
    """AC-05/15/14: fetch-first is old/no-current; revoke-first creates a successor."""
    operator = User.objects.create_superuser(
        "credential_race_fetch_operator", password="pw"
    )
    for fetch_first in (True, False):
        s, activation, old = _setup(f"operator_fetch_{fetch_first}")
        first = lambda s=s, old=old, fetch_first=fetch_first: (
            _fetch(s) if fetch_first else _operator_revoke(operator.pk, old.pk)
        )
        second = lambda s=s, old=old, fetch_first=fetch_first: (
            _operator_revoke(operator.pk, old.pk) if fetch_first else _fetch(s)
        )
        one, two = _race(
            lambda activation=activation: (
                FursuitActivation.objects.select_for_update().get(pk=activation.pk)
            ),
            first,
            second,
        )
        _assert_results(one, two)
        fetch = one if fetch_first else two
        assert fetch.status_code == 200
        rows = assert_credential_history(activation)
        current = [row for row in rows if row.revoked_at is None]
        old.refresh_from_db()
        assert old.revocation_reason == "operator"
        if fetch_first:
            assert fetch.json() == {"payload": _payload(old.token)}
            assert current == []
        else:
            assert len(current) == 1 and current[0].pk != old.pk
            assert fetch.json()["payload"] != _payload(old.token)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", (_fetch, _rotate), ids=("fetch", "rotation"))
def test_races_6_and_7_operation_vs_activation_deactivation_leaves_no_current_row(
    operation: Callable[[Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-05/06/08/14: committed activation loss dominates an in-flight owner operation."""
    from conventions import services

    captured_now = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
    monkeypatch.setattr(services.timezone, "now", lambda: captured_now)
    for owner_first in (True, False):
        s, activation, initial = _setup(
            f"activation_{operation.__name__}_{owner_first}", session=True
        )
        session = cast(Any, activation).catch_sessions.get(ended_at__isnull=True)
        first = lambda s=s, owner_first=owner_first: (
            operation(s) if owner_first else _deactivate(s)
        )
        second = lambda s=s, owner_first=owner_first: (
            _deactivate(s) if owner_first else operation(s)
        )
        one, two = _race(
            lambda activation=activation: (
                FursuitActivation.objects.select_for_update().get(pk=activation.pk)
            ),
            first,
            second,
        )
        _assert_results(one, two)
        action, deactivate = (one, two) if owner_first else (two, one)
        assert action.status_code == (200 if owner_first else 400)
        assert deactivate.status_code == 200
        activation.refresh_from_db()
        initial.refresh_from_db()
        session.refresh_from_db()
        assert activation.is_active is False
        assert session.ended_at is not None and session.end_reason == "eligibility_lost"
        assert session.ended_at == captured_now
        rows = assert_credential_history(activation)
        assert not [row for row in rows if row.revoked_at is None]
        eligibility_revocations = [
            row for row in rows if row.revocation_reason == "eligibility_lost"
        ]
        assert eligibility_revocations
        assert all(row.revoked_at == captured_now for row in eligibility_revocations)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("number", "label", "lock", "loss"),
    (
        (
            8,
            "fursuit",
            _lock_fursuit,
            _disable_fursuit,
        ),
        (
            9,
            "profile",
            _lock_profile,
            _disable_profile,
        ),
        (
            10,
            "enrollment",
            _lock_enrollment,
            _remove_enrollment,
        ),
        (
            11,
            "convention",
            _lock_convention,
            _pause_convention,
        ),
    ),
)
@pytest.mark.parametrize("operation", (_fetch, _rotate), ids=("fetch", "rotation"))
def test_races_8_to_11_owner_operation_vs_each_eligibility_loss_has_no_current_row(
    number: int,
    label: str,
    lock: Callable[[Any], Any],
    loss: Callable[[Any], Any],
    operation: Callable[[Any], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-05/06/08/14: every upstream loss is atomic with credential revocation."""
    from conventions import services

    captured_now = datetime.datetime(2026, 9, 1, tzinfo=datetime.UTC)
    monkeypatch.setattr(services.timezone, "now", lambda: captured_now)
    loss_first_status = 403 if label == "profile" else 400
    for owner_first in (True, False):
        s, activation, initial = _setup(
            f"{label}_{operation.__name__}_{owner_first}", session=True
        )
        session = cast(Any, activation).catch_sessions.get(ended_at__isnull=True)
        first = lambda s=s, owner_first=owner_first: (
            operation(s) if owner_first else loss(s)
        )
        second = lambda s=s, owner_first=owner_first: (
            loss(s) if owner_first else operation(s)
        )
        action_one, transition_one = _race(lambda s=s: lock(s), first, second)
        _assert_results(action_one, transition_one)
        action = action_one if owner_first else transition_one
        assert action.status_code == (200 if owner_first else loss_first_status), (
            f"race {number} {label}"
        )
        initial.refresh_from_db()
        session.refresh_from_db()
        rows = assert_credential_history(activation)
        assert not [row for row in rows if row.revoked_at is None]
        assert session.ended_at is not None and session.end_reason == "eligibility_lost"
        assert session.ended_at == captured_now
        eligibility_revocations = [
            row for row in rows if row.revocation_reason == "eligibility_lost"
        ]
        assert eligibility_revocations
        assert all(row.revoked_at == captured_now for row in eligibility_revocations)


@pytest.mark.django_db(transaction=True)
def test_race_12_restoration_vs_fetch_never_reactivates_a_revoked_row() -> None:
    """AC-08/14: restoration creates nothing; a later fetch can create only a distinct row."""
    s, activation, old = _setup("restoration")
    old.revoked_at = timezone.now()
    old.revocation_reason = "eligibility_lost"
    old.save(update_fields=["revoked_at", "revocation_reason", "updated_at"])
    PlayerProfile.objects.filter(pk=s.profile.pk).update(is_enabled=False)
    fetch, restore = _race(
        lambda: PlayerProfile.objects.select_for_update().get(pk=s.profile.pk),
        lambda: _fetch(s),
        lambda: __import__(
            "profiles.services", fromlist=["set_profile_enabled"]
        ).set_profile_enabled(profile_id=s.profile.pk, is_enabled=True),
    )
    _assert_results(fetch, restore)
    assert fetch.status_code in {200, 403}
    old.refresh_from_db()
    assert old.revocation_reason == "eligibility_lost"
    assert all(
        row.pk != old.pk
        for row in assert_credential_history(activation)
        if row.revoked_at is None
    )
    assert _fetch(s).status_code == 200
    current = catch_credential_model().objects.get(
        activation=activation, revoked_at__isnull=True
    )
    assert current.pk != old.pk


@pytest.mark.django_db(transaction=True)
def test_race_13_resolution_vs_rotation_or_operator_revoke_is_only_a_stale_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-06/13/14: preview never locks activation and final-current proof wins."""
    operator = User.objects.create_superuser(
        "credential_race_resolution_operator", password="pw"
    )
    for mutation in ("rotation", "operator"):
        # Evaluation first is a legal stale-preview success, on a separate resolver connection.
        s, activation, old = _setup(f"resolve_before_{mutation}", session=True)
        before = _separate_connection(lambda s=s, old=old: _resolve(s, old.token))
        assert before.status_code == 200
        change = _separate_connection(
            (lambda s=s: _rotate(s))
            if mutation == "rotation"
            else lambda old=old: _operator_revoke(operator.pk, old.pk)
        )
        _assert_results(change)
        assert _separate_connection(
            lambda s=s, old=old: _resolve(s, old.token)
        ).json() == {"detail": NOT_FOUND_DETAIL}
        assert_credential_history(activation)

        # A real concurrent change after target evaluation but before final-current
        # proof yields generic 404 without forcing the resolver to lock activation.
        s, activation, old = _setup(f"resolve_after_{mutation}", session=True)
        with monkeypatch.context() as gate_patch:
            entered, release = _gate_resolution_eligibility(gate_patch)
            pids: Queue[int] = Queue()
            with ThreadPoolExecutor(max_workers=1) as pool:
                resolver = pool.submit(
                    _worker, lambda s=s, old=old: _resolve(s, old.token), pids
                )
                _pid(pids, resolver)
                assert entered.wait(_WAIT_SECONDS), (
                    "resolver did not evaluate target eligibility"
                )
                change = _separate_connection(
                    (lambda s=s: _rotate(s))
                    if mutation == "rotation"
                    else lambda old=old: _operator_revoke(operator.pk, old.pk)
                )
                release.set()
                after = resolver.result(timeout=_RESULT_SECONDS)
        _assert_results(change, after)
        assert after.status_code == 404
        assert after.json() == {"detail": NOT_FOUND_DETAIL}
        assert_credential_history(activation)


@pytest.mark.django_db(transaction=True)
def test_race_14_resolution_vs_eligibility_loss_fails_after_the_committed_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-08/13/14: target evaluation timing, not a preview lock, controls staleness."""
    s, activation, old = _setup("resolve_loss_before", session=True)
    assert (
        _separate_connection(lambda s=s, old=old: _resolve(s, old.token)).status_code
        == 200
    )
    _assert_results(_separate_connection(lambda s=s: _disable_fursuit(s)))
    assert _separate_connection(lambda s=s, old=old: _resolve(s, old.token)).json() == {
        "detail": NOT_FOUND_DETAIL
    }
    assert not [
        row for row in assert_credential_history(activation) if row.revoked_at is None
    ]

    s, activation, old = _setup("resolve_loss_after", session=True)
    entered, release = _gate_resolution_eligibility(monkeypatch)
    pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=1) as pool:
        resolver = pool.submit(
            _worker, lambda s=s, old=old: _resolve(s, old.token), pids
        )
        _pid(pids, resolver)
        assert entered.wait(_WAIT_SECONDS), (
            "resolver did not evaluate target eligibility"
        )
        _assert_results(_separate_connection(lambda s=s: _disable_fursuit(s)))
        release.set()
        after = resolver.result(timeout=_RESULT_SECONDS)
    assert after.status_code == 404
    assert after.json() == {"detail": NOT_FOUND_DETAIL}
    assert not [
        row for row in assert_credential_history(activation) if row.revoked_at is None
    ]


@pytest.mark.django_db(transaction=True)
def test_race_15_resolution_vs_session_stop_expiration_and_restart_preserves_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-07/13/14: effective-session timing controls preview, not credential history."""
    s, activation, credential = _setup("resolve_session", session=True)
    before = (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    )
    assert (
        _separate_connection(
            lambda s=s, credential=credential: _resolve(s, credential.token)
        ).status_code
        == 200
    )
    assert _separate_connection(lambda s=s: _session(s, False)).status_code == 200
    assert (
        _separate_connection(
            lambda s=s, credential=credential: _resolve(s, credential.token)
        ).status_code
        == 404
    )
    assert _separate_connection(lambda s=s: _session(s, True)).status_code == 200

    entered, release = _gate_resolution_eligibility(monkeypatch)
    pids: Queue[int] = Queue()
    with ThreadPoolExecutor(max_workers=1) as pool:
        resolver = pool.submit(
            _worker,
            lambda s=s, credential=credential: _resolve(s, credential.token),
            pids,
        )
        _pid(pids, resolver)
        assert entered.wait(_WAIT_SECONDS), (
            "resolver did not evaluate target eligibility"
        )
        assert _separate_connection(lambda s=s: _session(s, False)).status_code == 200
        release.set()
        after_stop = resolver.result(timeout=_RESULT_SECONDS)
    assert after_stop.status_code == 404
    credential.refresh_from_db()
    assert (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    ) == before
    assert _separate_connection(lambda s=s: _session(s, True)).status_code == 200
    live = cast(Any, activation).catch_sessions.get(ended_at__isnull=True)
    live.expires_at = timezone.now()
    live.save(update_fields=["expires_at", "updated_at"])
    assert (
        _separate_connection(
            lambda s=s, credential=credential: _resolve(s, credential.token)
        ).status_code
        == 404
    )
    assert _separate_connection(lambda s=s: _session(s, True)).status_code == 200
    assert (
        _separate_connection(
            lambda s=s, credential=credential: _resolve(s, credential.token)
        ).status_code
        == 200
    )
    assert_credential_history(activation)


@pytest.mark.django_db(transaction=True)
def test_race_16_session_start_stop_vs_credential_operations_keeps_histories_independent() -> (
    None
):
    """AC-05/06/07/14: independent domains serialize without cross-history writes."""
    s, activation, credential = _setup("session_operations")
    before = (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    )
    fetch, start = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        lambda: _fetch(s),
        lambda: _session(s, True),
    )
    _assert_results(fetch, start)
    assert fetch.status_code == start.status_code == 200
    credential.refresh_from_db()
    assert (
        credential.revoked_at,
        credential.revocation_reason,
        credential.updated_at,
    ) == before
    rotate, stop = _race(
        lambda: FursuitActivation.objects.select_for_update().get(pk=activation.pk),
        lambda: _rotate(s),
        lambda: _session(s, False),
    )
    _assert_results(rotate, stop)
    assert rotate.status_code == stop.status_code == 200
    assert (
        cast(Any, activation).catch_sessions.filter(ended_at__isnull=True).count() == 0
    )
    assert_credential_history(activation)
