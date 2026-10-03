"""Acceptance coverage for the Staging-only simulation fixture remote entry point."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

import pytest

from conventions import services as convention_services
from profiles.models import PlayerProfile
from simulation_fixtures import remote
from tests.simulation_fixtures_test_support import (
    OTHER_RUN,
    POOL,
    RUN_A,
    RUN_B,
    lease_pool,
    world,
)

IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
ENVIRON = {"RAILWAY_ENVIRONMENT_NAME": "staging", "RAILWAY_SERVICE_NAME": "api"}
PROVISION_ARGUMENTS: dict[str, object] = {
    "pool": POOL,
    "run_id": RUN_A,
    "owners": [0, 1],
    "catchers": [2],
    "fursuits_per_owner": 1,
}
COUNTS = {"convention": 1, "enrollment": 3, "fursuit": 2, "activation": 2}

pytestmark = pytest.mark.django_db


def request(
    operation: str, arguments: Mapping[str, object] | None = None
) -> dict[str, object]:
    return {
        "operation": operation,
        "identity": dict(IDENTITY),
        "arguments": dict(arguments or {}),
    }


def provision_request(**overrides: object) -> dict[str, object]:
    return request("provision", PROVISION_ARGUMENTS | overrides)


def execute(
    payload: object,
    *,
    runtime_identity: Mapping[str, object] = IDENTITY,
    environ: Mapping[str, str] = ENVIRON,
) -> dict[str, object]:
    return remote.execute(payload, runtime_identity=runtime_identity, environ=environ)


def test_provision_and_status_return_fixed_shapes_without_identifying_data() -> None:
    """F-7/F-8: counts and codes only, never ids, handles, media keys, or run IDs."""
    lease_pool(POOL, RUN_A, 3)

    provisioned = execute(provision_request())
    status = execute(request("status", {"run_id": RUN_A}))

    assert provisioned == {"result": "PASS", "data": COUNTS}
    assert status == {
        "result": "PASS",
        "data": {"status": "provisioned", "counts": COUNTS},
    }
    text = json.dumps([provisioned, status])
    assert json.loads(text) == [provisioned, status]
    for private in ("sp_", "images/", RUN_A, POOL):
        assert private not in text


def test_each_failure_has_a_fixed_code_and_no_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F-8: documented failures map to fixed codes; exception text never escapes."""
    users = lease_pool(POOL, RUN_A, 4)
    lease_pool(POOL, RUN_B, 3)

    unknown = execute(request("status", {"run_id": OTHER_RUN}))
    lease = execute(provision_request(run_id=OTHER_RUN))
    invalid = execute(provision_request(owners=[]))
    profile = PlayerProfile.objects.get(user=users[0])
    profile.avatar_key = "images/0123456789abcdef0123456789abcdef.png"
    profile.save(update_fields=["avatar_key"])
    dirty = execute(provision_request())

    def explode(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(convention_services, "set_fursuit_activation_state", explode)
    errored = execute(provision_request(run_id=RUN_B, owners=[4, 5], catchers=[6]))
    monkeypatch.undo()
    reused = execute(provision_request(run_id=RUN_B, owners=[4, 5], catchers=[6]))

    assert unknown == {"result": "FAIL_RUN_UNKNOWN", "data": {}}
    assert lease == {"result": "FAIL_LEASE", "data": {}}
    assert invalid == {"result": "FAIL_REQUEST", "data": {}}
    assert dirty == {"result": "FAIL_DIRTY", "data": {"quarantined": 1}}
    assert errored == {"result": "FAIL_ERROR", "data": {}}
    assert reused == {"result": "FAIL_RUN_EXISTS", "data": {}}
    assert "private" not in json.dumps([errored, reused])


@pytest.mark.parametrize(
    ("runtime_identity", "environ"),
    (
        (IDENTITY, {**ENVIRON, "RAILWAY_ENVIRONMENT_NAME": "development"}),
        (IDENTITY, {**ENVIRON, "RAILWAY_ENVIRONMENT_NAME": "production"}),
        (IDENTITY, {"RAILWAY_SERVICE_NAME": "api"}),
        (IDENTITY, {**ENVIRON, "RAILWAY_SERVICE_NAME": "worker"}),
        (IDENTITY, {"RAILWAY_ENVIRONMENT_NAME": "staging"}),
        (IDENTITY, {}),
        ({**IDENTITY, "source_sha": "b" * 40}, ENVIRON),
        (
            {**IDENTITY, "deployment_id": "99999999-9999-4999-8999-999999999999"},
            ENVIRON,
        ),
        ({**IDENTITY, "environment": "development"}, ENVIRON),
        ({"source_sha": IDENTITY["source_sha"]}, ENVIRON),
    ),
    ids=(
        "railway-development",
        "railway-production",
        "railway-environment-missing",
        "railway-wrong-service",
        "railway-service-missing",
        "railway-empty",
        "source-sha-mismatch",
        "deployment-mismatch",
        "runtime-not-staging",
        "runtime-identity-incomplete",
    ),
)
@pytest.mark.parametrize(
    "payload",
    (
        provision_request(),
        request("status", {"run_id": RUN_A}),
        request("drop_table", {"unexpected": 1}),
    ),
    ids=("provision", "status", "malformed-operation"),
)
def test_target_mismatch_is_refused_before_validation_or_database_access(
    payload: dict[str, object],
    runtime_identity: Mapping[str, object],
    environ: Mapping[str, str],
    django_assert_num_queries: Any,
) -> None:
    """F-7: outside the exact Staging API identity nothing is validated or read."""
    with django_assert_num_queries(0):
        response = execute(payload, runtime_identity=runtime_identity, environ=environ)

    assert response == {"result": "FAIL_TARGET", "data": {}}


def test_request_identity_for_another_environment_is_refused() -> None:
    """F-7: a request naming a non-Staging identity cannot match even itself."""
    lease_pool(POOL, RUN_A, 3)
    production = {**IDENTITY, "environment": "production"}
    payload = {**provision_request(), "identity": production}
    before = world()

    response = execute(payload, runtime_identity=production)

    assert response == {"result": "FAIL_TARGET", "data": {}}
    assert world() == before


def _without(key: str) -> dict[str, object]:
    payload = request("status", {"run_id": RUN_A})
    del payload[key]
    return payload


@pytest.mark.parametrize(
    "payload",
    (
        ["provision"],
        {**request("status", {"run_id": RUN_A}), "extra": 1},
        {**provision_request(), "pool": POOL},
        _without("operation"),
        _without("arguments"),
        _without("identity"),
        request("drop_table"),
        {**request("status"), "arguments": []},
        request("status"),
        request("status", {"run_id": RUN_A, "extra": 1}),
        request("status", {"run_id": RUN_A.upper()}),
        request("status", {"run_id": 7}),
        request(
            "provision", {k: v for k, v in PROVISION_ARGUMENTS.items() if k != "pool"}
        ),
        provision_request(extra=1),
        provision_request(owners="0"),
        provision_request(owners=[True]),
        provision_request(catchers=["2"]),
        provision_request(fursuits_per_owner="1"),
        provision_request(fursuits_per_owner=True),
        provision_request(pool=7),
    ),
    ids=(
        "request-not-an-object",
        "extra-top-level-key",
        "pool-outside-arguments",
        "missing-operation",
        "missing-arguments",
        "missing-identity",
        "unknown-operation",
        "arguments-not-an-object",
        "status-without-run-id",
        "status-extra-argument",
        "status-run-id-not-canonical",
        "status-run-id-not-a-string",
        "provision-missing-pool",
        "provision-extra-argument",
        "owners-not-a-list",
        "owners-boolean-index",
        "catchers-string-index",
        "fursuits-string",
        "fursuits-boolean",
        "pool-not-a-string",
    ),
)
def test_malformed_requests_fail_closed_without_changing_state(
    payload: object,
) -> None:
    """F-7: only exact request shapes and valid values reach a fixture operation."""
    lease_pool(POOL, RUN_A, 3)
    before = world()

    response = execute(copy.deepcopy(payload))

    assert response == {"result": "FAIL_REQUEST", "data": {}}
    assert world() == before
