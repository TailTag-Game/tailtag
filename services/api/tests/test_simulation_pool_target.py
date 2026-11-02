"""#411 AC3: the Staging runtime check and Render instance pin for the relays."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from simulation_pool import target

STAGING_SERVICE = "srv-d0staging000000000000"
DEVELOPMENT_SERVICE = "srv-d0development00000000"
INSTANCE = f"{STAGING_SERVICE}-874b544b8-k7qws"
OTHER_INSTANCE = f"{STAGING_SERVICE}-54fcd9cd8d-wthkj"
RAILWAY_IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
RENDER_IDENTITY: dict[str, object] = {**RAILWAY_IDENTITY, "deployment_id": None}
RAILWAY = {"RAILWAY_ENVIRONMENT_NAME": "staging", "RAILWAY_SERVICE_NAME": "api"}
RENDER = {
    "RENDER": "true",
    "RENDER_SERVICE_ID": STAGING_SERVICE,
    "RENDER_INSTANCE_ID": INSTANCE,
}


@pytest.fixture(autouse=True)
def render_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import replacement_target_binding as binding

    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_DIGESTS",
        {
            environment: binding.fingerprint_render_service(environment, service)
            for environment, service in (
                ("development", DEVELOPMENT_SERVICE),
                ("staging", STAGING_SERVICE),
            )
        },
    )


def check(
    identity: Mapping[str, object],
    environ: Mapping[str, str],
    expected_instance: object = None,
    runtime_identity: Mapping[str, object] | None = None,
) -> str | None:
    return target.check(
        identity,
        identity if runtime_identity is None else runtime_identity,
        environ,
        expected_instance,
    )


@pytest.mark.parametrize("expected_instance", [None, INSTANCE])
def test_render_staging_returns_its_instance(expected_instance: object) -> None:
    assert check(RENDER_IDENTITY, RENDER, expected_instance) == INSTANCE


def test_railway_staging_keeps_its_rule_and_has_no_instance() -> None:
    assert check(RAILWAY_IDENTITY, RAILWAY) is None


@pytest.mark.parametrize(
    ("identity", "environ", "expected_instance"),
    [
        # A restart or a redeploy replaces the pinned instance.
        (RENDER_IDENTITY, RENDER, OTHER_INSTANCE),
        (RENDER_IDENTITY, {**RENDER, "RENDER_SERVICE_ID": DEVELOPMENT_SERVICE}, None),
        (RENDER_IDENTITY, {**RENDER, "RENDER": "false"}, None),
        (RENDER_IDENTITY, {**RENDER, **RAILWAY}, None),
        (
            RENDER_IDENTITY,
            {k: v for k, v in RENDER.items() if k != "RENDER_INSTANCE_ID"},
            None,
        ),
        (
            RENDER_IDENTITY,
            {
                **RENDER,
                "RENDER_INSTANCE_ID": "srv-d0other0000000000000-874b544b8-k7qws",
            },
            None,
        ),
        (
            RENDER_IDENTITY,
            {**RENDER, "RENDER_INSTANCE_ID": f"{STAGING_SERVICE}-k7qws"},
            None,
        ),
        (RAILWAY_IDENTITY, RENDER, None),
        (RAILWAY_IDENTITY, RAILWAY, INSTANCE),
        (RENDER_IDENTITY, RAILWAY, None),
        ({**RENDER_IDENTITY, "environment": "development"}, RENDER, None),
        ({**RENDER_IDENTITY, "source_sha": None}, RENDER, None),
        (RENDER_IDENTITY, {}, None),
    ],
    ids=[
        "render-instance-replaced",
        "render-development",
        "render-marker-false",
        "render-and-railway-markers",
        "render-instance-missing",
        "render-instance-other-service",
        "render-instance-without-hex",
        "render-with-deploy-id",
        "railway-with-pin",
        "railway-without-deploy-id",
        "not-staging",
        "no-source-sha",
        "no-platform",
    ],
)
def test_every_other_runtime_or_pin_is_refused(
    identity: Mapping[str, object],
    environ: Mapping[str, str],
    expected_instance: object,
) -> None:
    with pytest.raises(target.TargetRefused):
        check(identity, environ, expected_instance)


@pytest.mark.parametrize(
    "environ",
    [{"RAILWAY_ENVIRONMENT_NAME": "development", "RAILWAY_SERVICE_NAME": "api"}, {}],
    ids=["railway-development", "no-platform"],
)
def test_a_runtime_without_a_render_instance_never_loads_the_binding(
    monkeypatch: pytest.MonkeyPatch, environ: Mapping[str, str]
) -> None:
    """Loading the binding resolves the home directory, which fails on Windows."""

    def unexpected(_environ: Mapping[str, str]) -> bool:
        raise AssertionError

    monkeypatch.setattr(target, "_render_staging", unexpected)

    with pytest.raises(target.TargetRefused):
        check(RENDER_IDENTITY, environ)


def test_render_runtime_identity_must_equal_the_request() -> None:
    with pytest.raises(target.TargetRefused):
        check(
            RENDER_IDENTITY,
            RENDER,
            runtime_identity={**RENDER_IDENTITY, "source_sha": "b" * 40},
        )


REMOTE_REQUESTS: dict[str, dict[str, object]] = {
    "pool": {"operation": "status", "pool": "gamma", "arguments": {}},
    "fixtures": {"operation": "retained", "arguments": {}},
    "inspection": {
        "operation": "inspect",
        "arguments": {
            "pool": "gamma",
            "run_id": "cccccccc-3333-4333-8333-333333333333",
            "identities": {
                "owner0": 5,
                "owner1": 3,
                "catcher0": 8,
                "catcher1": 4,
                "catcher2": 9,
                "catcher3": 6,
                "outsider": 7,
            },
        },
    },
}


def _remote(name: str) -> Any:
    from simulation_fixtures import inspection_remote
    from simulation_fixtures import remote as fixture_remote
    from simulation_pool import remote as pool_remote

    return {
        "pool": pool_remote,
        "fixtures": fixture_remote,
        "inspection": inspection_remote,
    }[name]


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(REMOTE_REQUESTS))
def test_each_render_relay_reply_names_the_instance_it_ran_on(name: str) -> None:
    payload = {**REMOTE_REQUESTS[name], "identity": dict(RENDER_IDENTITY)}

    first = _remote(name).execute(
        payload, runtime_identity=RENDER_IDENTITY, environ=RENDER
    )
    pinned = _remote(name).execute(
        {**payload, "expected_instance": INSTANCE},
        runtime_identity=RENDER_IDENTITY,
        environ=RENDER,
    )

    assert first["instance"] == INSTANCE
    assert pinned["instance"] == INSTANCE
    assert pinned["result"] == first["result"] != "FAIL_REQUEST"


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(REMOTE_REQUESTS))
def test_each_relay_refuses_a_replaced_instance_before_any_query(
    name: str, django_assert_num_queries: Any
) -> None:
    payload = {
        **REMOTE_REQUESTS[name],
        "identity": dict(RENDER_IDENTITY),
        "expected_instance": OTHER_INSTANCE,
    }

    with django_assert_num_queries(0):
        response = _remote(name).execute(
            payload, runtime_identity=RENDER_IDENTITY, environ=RENDER
        )

    assert response == {"result": "FAIL_TARGET", "data": {}}
