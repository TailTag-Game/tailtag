"""#226 U2: real traffic engine/client/comparator; external HTTP/time only."""

from collections.abc import Mapping

import pytest
from traffic_behavior_support import (
    AT,
    CONFIRM,
    TrafficWorld,
    config_for,
    run_traffic,
)

from tailtag_simulator.reconciliation import Made
from tailtag_simulator.safety import SafetyRuntime


def confirmations(world: TrafficWorld) -> list[tuple[str, Mapping[str, object]]]:
    return [
        (actor, body)
        for actor, _method, path, body in world.requests
        if path == CONFIRM
    ]


def test_committed_transport_loss_retries_the_exact_payload_and_recovers_canonical() -> (
    None
):
    config = config_for()
    world = TrafficWorld(config)
    world.lost_first = True

    result, compared = run_traffic(world, config)

    assert result.population.passed and compared.passed
    submitted = confirmations(world)
    assert len(submitted) == 2
    assert submitted[0] == submitted[1]
    assert len(world.gameplay.catches) == 1
    assert result.population.expectations.made == {("attendee0", 100): Made(7001, AT)}
    assert result.population.expectations.pairs == {("attendee0", 100): "required"}
    assert result.traffic["retries"] == 1
    assert result.traffic["unresolved"] == 0


@pytest.mark.parametrize("effect", ["lost_response_rate", "timeout_rate"])
def test_concealed_committed_response_cannot_mark_success_or_disclose_catch(
    effect: str,
) -> None:
    config = config_for(
        failure={"operations": ["confirm"], effect: 1}, retry={"attempts": 1}
    )
    world = TrafficWorld(config)

    result, compared = run_traffic(world, config)

    assert not result.population.passed and not compared.passed
    assert len(confirmations(world)) == len(world.gameplay.catches) == 1
    assert result.population.expectations.made == {}
    assert result.population.expectations.seen.get(("attendee0", 100), []) == []
    assert result.population.expectations.pairs == {("attendee0", 100): "unresolved"}
    assert result.traffic["injected"] == 1
    assert result.traffic["exhausted"] == result.traffic["unresolved"] == 1
    assert "SENTINEL" not in str(result.traffic)
    assert "tailtag:" not in str(result.traffic)


def test_overlapping_same_actor_confirmations_join_and_keep_one_id_and_timestamp() -> (
    None
):
    config = config_for(family="hotspot", failure={"duplicate_overlap": True})
    world = TrafficWorld(config)
    world.overlap = True

    result, compared = run_traffic(world, config)

    assert result.population.passed and compared.passed
    assert world.confirm_peak == 2 and world.confirming == 0
    submitted = confirmations(world)
    assert len(submitted) == 2 and submitted[0] == submitted[1]
    assert len(world.gameplay.catches) == 1
    assert result.population.expectations.made == {("attendee0", 100): Made(7001, AT)}
    observed = [
        body["catch"]
        for _actor, path, status, body in world.responses
        if path == CONFIRM and status in {200, 201}
    ]
    assert [(row["id"], row["caught_at"]) for row in observed] == [(7001, AT)] * 2


def test_confirmation_send_and_response_delivery_respect_distinct_client_delays() -> (
    None
):
    config = config_for(
        failure={
            "operations": ["confirm"],
            "pre_send_delay_seconds": 0.3,
            "response_delay_seconds": 0.4,
        }
    )
    world = TrafficWorld(config)

    result, compared = run_traffic(world, config)

    assert result.population.passed and compared.passed
    resolve_at = next(
        at
        for _a, _m, path, at in world.times
        if path.endswith("/catch-credentials/resolve/")
    )
    confirm_at = next(at for _a, _m, path, at in world.times if path == CONFIRM)
    history_at = next(
        at
        for a, _m, path, at in world.times
        if a == "attendee0" and path == "/api/catches/" and at >= confirm_at
    )
    assert confirm_at - resolve_at >= 0.3 - 1e-9
    assert history_at - confirm_at >= 0.4 - 1e-9
    assert len(confirmations(world)) == len(world.gameplay.catches) == 1


@pytest.mark.parametrize("case", ["stale", "stopped"])
@pytest.mark.parametrize(
    "recover", [False, True], ids=["reject-new", "recover-existing"]
)
def test_public_owner_transition_distinguishes_negative_creation_and_existing_recovery(
    case: str, recover: bool
) -> None:
    config = config_for(
        failure={
            "domain_case": case,
            "recover_existing": recover,
            "confirmation_delay_seconds": 0.2,
        }
    )
    world = TrafficWorld(config)

    result, compared = run_traffic(world, config)

    assert result.population.passed and compared.passed
    pair = ("attendee0", 100)
    assert result.population.expectations.pairs == {
        pair: "required" if recover else "forbidden"
    }
    assert len(world.gameplay.catches) == int(recover)
    if recover:
        assert result.population.expectations.made == {pair: Made(7001, AT)}
        submitted = confirmations(world)
        assert len(submitted) == 2 and submitted[0] == submitted[1]
    else:
        assert result.population.expectations.made == {}
        assert result.traffic["expected_rejections"] == 1
    transition = "/catch-credential/rotate/" if case == "stale" else "/catch-session/"
    last_confirm = max(
        n for n, (_a, _m, p, _b) in enumerate(world.requests) if p == CONFIRM
    )
    controls = [
        n
        for n, (actor, method, path, body) in enumerate(world.requests[:last_confirm])
        if actor == "owner0"
        and path.endswith(transition)
        and method == ("POST" if case == "stale" else "PUT")
        and (case == "stale" or body == {"is_active": False})
    ]
    assert len(controls) == 1
    resolved = max(
        n
        for n, (_a, _m, p, _b) in enumerate(world.requests[: controls[0]])
        if p.endswith("/catch-credentials/resolve/")
    )
    assert resolved < controls[0] < last_confirm
    assert world.times[last_confirm][3] - world.times[controls[0]][3] >= 0.2 - 1e-9


@pytest.mark.parametrize(
    "recover", [False, True], ids=["reject-new", "recover-existing"]
)
def test_natural_expiration_uses_public_deadline_without_refresh_or_stop(
    recover: bool,
) -> None:
    config = config_for(
        failure={"domain_case": "expired", "recover_existing": recover},
        traffic={
            "segments": [{"duration_seconds": 43202, "start": 0, "end": 0}],
            "bursts": [{"at_seconds": 0.01, "count": 1}],
            "think_seconds": 0,
            "max_entries": 1,
            "bucket_seconds": 100,
        },
        limits={"generation_seconds": 43210},
    )
    world = TrafficWorld(config)

    result, compared = run_traffic(world, config)

    assert result.population.passed and compared.passed
    first_confirm = next(
        n for n, (_a, _m, p, _b) in enumerate(world.requests) if p == CONFIRM
    )
    last_confirm = max(
        n for n, (_a, _m, p, _b) in enumerate(world.requests) if p == CONFIRM
    )
    arms = [
        n
        for n, (_a, method, path, body) in enumerate(world.requests[:last_confirm])
        if method == "PUT"
        and path.endswith("/catch-session/")
        and body == {"is_active": True}
    ]
    assert len(arms) == 1
    assert not any(
        path.endswith(("/catch-session/", "/catch-credential/rotate/"))
        for _a, _m, path, _body in world.requests[arms[0] + 1 : last_confirm]
    )
    at = max(at for _a, _m, path, at in world.times if path == CONFIRM)
    assert world.time.epoch + at >= world.expires[100]
    assert world.expires[100] - world.time.epoch >= 43200
    assert len(world.gameplay.catches) == int(recover)
    assert result.population.expectations.pairs == {
        ("attendee0", 100): "required" if recover else "forbidden"
    }
    if recover:
        assert first_confirm < last_confirm
        assert confirmations(world)[0] == confirmations(world)[-1]


def test_presend_confirm_failure_never_sends_and_leaves_owner_bootstrap_uninjected() -> (
    None
):
    config = config_for(
        failure={"operations": ["confirm"], "pre_send_failure_rate": 1},
        retry={"attempts": 2},
    )
    world = TrafficWorld(config)

    result, _compared = run_traffic(world, config)

    assert not result.population.passed
    assert confirmations(world) == [] and world.gameplay.catches == []
    assert {a for a, _m, p, _b in world.requests if p == "/api/me/"} == set(
        world.indexes
    )
    assert any(
        path.endswith("/catch-credential/") for _a, _m, path, _b in world.requests
    )
    assert any(
        path.endswith("/catch-credentials/resolve/")
        for _a, _m, path, _b in world.requests
    )
    assert result.traffic["injected"] == 2 and result.traffic["retries"] == 1
    assert isinstance(result.traffic["sent"], int) and result.traffic["sent"] > 0
    assert not result.population.expectations.made


@pytest.mark.parametrize("guarded", [False, True])
@pytest.mark.parametrize("fault", ["malformed", "wrong-target", "redirect", "oversize"])
def test_correctness_and_client_protection_errors_stop_without_retry(
    fault: str,
    guarded: bool,
) -> None:
    config = config_for(
        actors=2,
        traffic={
            "segments": [{"duration_seconds": 2, "start": 0, "end": 0}],
            "bursts": [{"at_seconds": 0.01, "count": 1}, {"at_seconds": 1, "count": 1}],
            "think_seconds": 0,
            "max_entries": 2,
        },
    )
    world = TrafficWorld(config)
    if fault == "wrong-target":
        world.fault = fault
    else:
        world.protected_fault = fault

    runtime = SafetyRuntime({}) if guarded else None
    result, _compared = run_traffic(world, config, safety=runtime)
    if runtime is not None:
        assert runtime.abort_reason == "correctness"

    assert not result.population.passed
    assert result.traffic["stop_reason"] is not None
    assert result.traffic["retries"] == 0
    assert len(confirmations(world)) == (0 if fault == "wrong-target" else 1)
    assert not result.population.expectations.made
    assert "SENTINEL" not in str(result.population.failure)
    assert "evil.test" not in str(result.traffic)


def test_retry_exhaustion_keeps_uncertainty_and_allows_other_actors_to_finish() -> None:
    config = config_for(actors=2)
    world = TrafficWorld(config)
    world.exhaust_actor = "attendee0"

    result, _compared = run_traffic(world, config)

    assert not result.population.passed
    assert result.traffic["exhausted"] == 1
    assert result.traffic["retries"] == 2
    assert len([a for a, _b in confirmations(world) if a == "attendee0"]) == 3
    assert len([a for a, _b in confirmations(world) if a == "attendee1"]) == 1
    assert result.population.expectations.made == {("attendee1", 100): Made(7001, AT)}
    assert len(world.gameplay.catches) == 1


def test_shared_target_expiration_allows_each_actor_to_establish_then_recover() -> None:
    """A target lock held for twelve hours must not block another admitted actor."""
    config = config_for(
        actors=2,
        failure={"domain_case": "expired", "recover_existing": True},
        traffic={
            "segments": [{"duration_seconds": 43202, "start": 0, "end": 0}],
            "bursts": [{"at_seconds": 0.01, "count": 2}],
            "think_seconds": 0,
            "max_entries": 2,
            "bucket_seconds": 100,
        },
        limits={"generation_seconds": 43210},
    )
    world = TrafficWorld(config)

    result, compared = run_traffic(world, config)

    created = {
        actor: body["catch"]["id"]
        for actor, path, status, body in world.responses
        if path == CONFIRM and status == 201
    }
    assert set(created) == {"attendee0", "attendee1"}
    assert result.population.passed and compared.passed
    assert set(created.values()) == {7001, 7002}
    assert len(world.gameplay.catches) == 2
    for actor in ("attendee0", "attendee1"):
        observed = [
            (status, body["catch"]["id"], body["catch"]["caught_at"])
            for label, path, status, body in world.responses
            if label == actor and path == CONFIRM
        ]
        assert observed == [(201, created[actor], AT), (200, created[actor], AT)]
        at = [
            time
            for label, _m, path, time in world.times
            if label == actor and path == CONFIRM
        ]
        assert world.time.epoch + at[0] < world.expires[100]
        assert world.time.epoch + at[1] >= world.expires[100]
        submitted = [body for label, body in confirmations(world) if label == actor]
        assert len(submitted) == 2 and submitted[0] == submitted[1]
        assert result.population.expectations.made[(actor, 100)] == Made(
            created[actor], AT
        )
    assert [
        body
        for _a, _m, path, body in world.requests
        if path.endswith("/catch-session/")
    ] == [{"is_active": True}]
    assert not any(
        path.endswith("/catch-credential/rotate/")
        for _a, _m, path, _b in world.requests
    )


def test_history_retry_exhaustion_fails_one_actor_and_admits_later_actor() -> None:
    """Shared history parsing must preserve actor-local transient exhaustion."""
    config = config_for(
        actors=2,
        failure={"operations": ["read"]},
        traffic={
            "segments": [{"duration_seconds": 2, "start": 0, "end": 0}],
            "bursts": [{"at_seconds": 0.01, "count": 1}, {"at_seconds": 1, "count": 1}],
            "think_seconds": 0,
            "max_entries": 2,
        },
    )
    world = TrafficWorld(config)
    # The first actor's ordinary history sees three real 503 replies. Later
    # authoritative/public reconciliation sees the recovered provider normally.
    world.history_transients = 3

    result, compared = run_traffic(world, config)

    assert result.traffic["exhausted"] == 1 and result.traffic["retries"] == 2
    assert result.traffic["admitted"] == 2 and result.traffic["completed"] == 1
    assert result.traffic["stop_reason"] is None
    assert not result.population.passed and compared.passed
    assert len(world.gameplay.catches) == 2
    assert set(result.population.expectations.made) == {
        ("attendee0", 100),
        ("attendee1", 100),
    }
    assert set(result.population.expectations.made.values()) == {
        Made(7001, AT),
        Made(7002, AT),
    }
    assert (
        len(
            [
                1
                for actor, path, status, _body in world.responses
                if actor == world.failed_history_actor
                and path == "/api/catches/"
                and status == 503
            ]
        )
        == 3
    )
    assert {a for a, _b in confirmations(world)} == {"attendee0", "attendee1"}


def test_expiration_establishes_all_planned_targets_before_waiting_then_recovers() -> (
    None
):
    """Waiting during the first visit must not expire the actor's other targets."""
    config = config_for(
        fursuits=2,
        casual_budget=2,
        failure={"domain_case": "expired", "recover_existing": True},
        traffic={
            "segments": [{"duration_seconds": 43202, "start": 0, "end": 0}],
            "bursts": [{"at_seconds": 0.01, "count": 1}],
            "think_seconds": 0,
            "max_entries": 1,
            "bucket_seconds": 100,
        },
        limits={"generation_seconds": 43210},
    )
    world = TrafficWorld(config)

    result, compared = run_traffic(world, config, check_joined=True)

    replies = [
        (status, body["catch"]["id"], body["catch"]["caught_at"])
        for _actor, path, status, body in world.responses
        if path == CONFIRM and status in {200, 201}
    ]
    assert [status for status, _id, _at in replies] == [201, 201, 200, 200]
    assert result.population.passed and compared.passed
    assert {catch_id for _status, catch_id, _at in replies[:2]} == {7001, 7002}
    assert {at for _status, _id, at in replies} == {AT}
    submitted = confirmations(world)
    assert len(submitted) == 4
    for target in (100, 101):
        positions = [
            n
            for n, (actor, body) in enumerate(submitted)
            if actor == "attendee0"
            and world.gameplay.fursuit_of[str(body["payload"])] == target
        ]
        assert len(positions) == 2
        first, recovered = positions
        assert submitted[first] == submitted[recovered]
        assert replies[first][1:] == replies[recovered][1:]
        assert result.population.expectations.made[("attendee0", target)] == Made(
            replies[first][1], AT
        )
    times = [at for _a, _m, path, at in world.times if path == CONFIRM]
    assert all(world.time.epoch + at < min(world.expires.values()) for at in times[:2])
    assert all(world.time.epoch + at >= max(world.expires.values()) for at in times[2:])
    assert result.population.expectations.pairs == {
        ("attendee0", 100): "required",
        ("attendee0", 101): "required",
    }
    assert result.traffic["unresolved"] == 0
    assert len(world.gameplay.catches) == 2
    assert [
        body
        for _a, _m, path, body in world.requests
        if path.endswith("/catch-session/")
    ] == [{"is_active": True}] * 2
    assert not any(
        path.endswith("/catch-credential/rotate/")
        for _a, _m, path, _body in world.requests
    )


def test_failed_public_preparation_retains_seeded_digest_and_partial_observations() -> (
    None
):
    """Preparation failure must not erase seed attribution before scheduling starts."""
    config = config_for()
    digests: list[object] = []
    for seed in (17, 18, 17):
        world = TrafficWorld(config)
        world.context_failure = True

        result, _compared = run_traffic(world, config, seed=seed, check_joined=True)

        assert not result.population.passed
        assert result.population.failure is not None
        assert result.traffic["attempts"] == result.traffic["sent"] == 2
        assert result.traffic["admitted"] == result.traffic["completed"] == 0
        assert result.population.summaries["normal_owner"]["actions"] == 2
        assert [
            (actor, path, status) for actor, path, status, _body in world.responses
        ] == [
            ("owner0", "/api/me/", 200),
            ("owner0", "/api/conventions/active/", 503),
        ]
        assert result.population.expectations.made == {}
        assert world.gameplay.catches == []
        assert "SENTINEL" not in str(result.traffic)
        digests.append(result.traffic["plan_digest"])

    assert digests[0] != digests[1]
    assert digests[0] == digests[2]
