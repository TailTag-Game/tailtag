"""Acceptance coverage for the Staging-only simulation pool remote entry point."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

import pytest

from simulation_pool import remote, services
from simulation_pool.models import PoolSlot

IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
ENVIRON = {"RAILWAY_ENVIRONMENT_NAME": "staging", "RAILWAY_SERVICE_NAME": "api"}
RUN_A = "cccccccc-3333-4333-8333-333333333333"
RUN_B = "44444444-4444-4444-8444-444444444444"
POOL = "gamma"

pytestmark = pytest.mark.django_db


def request(
    operation: str, arguments: Mapping[str, object] | None = None
) -> dict[str, object]:
    return {
        "operation": operation,
        "pool": POOL,
        "identity": dict(IDENTITY),
        "arguments": dict(arguments or {}),
    }


def execute(
    payload: Mapping[str, object],
    *,
    runtime_identity: Mapping[str, object] = IDENTITY,
    environ: Mapping[str, str] = ENVIRON,
) -> dict[str, object]:
    return remote.execute(payload, runtime_identity=runtime_identity, environ=environ)


def snapshot() -> list[dict[str, Any]]:
    return list(PoolSlot.objects.order_by("pool", "index").values())


def test_each_operation_returns_its_fixed_pass_shape() -> None:
    """P-12: one request runs one operation and returns exactly the JSON shape."""
    steps: list[tuple[dict[str, object], dict[str, object]]] = [
        (request("register", {"size": 3}), {"created": 3}),
        (
            request("allocate", {"run_id": RUN_A, "count": 2, "ttl_seconds": 600}),
            {"indexes": [0, 1]},
        ),
        (
            request("heartbeat", {"run_id": RUN_A, "ttl_seconds": 600}),
            {"extended": 2},
        ),
        (
            request("status"),
            {"total": 3, "available": 1, "leased": 2, "quarantined": 0},
        ),
        (request("quarantine", {"index": 1, "run_id": RUN_A}), {}),
        (request("readmit", {"index": 1}), {}),
        (request("release", {"run_id": RUN_A}), {"released": 1}),
    ]

    for payload, data in steps:
        response = execute(payload)
        assert response == {"result": "PASS", "data": data}
        assert json.loads(json.dumps(response)) == response


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
def test_target_mismatch_is_refused_before_any_database_access(
    runtime_identity: Mapping[str, object],
    environ: Mapping[str, str],
    django_assert_num_queries: Any,
) -> None:
    """P-12: outside the exact Staging API identity nothing is read or written."""
    with django_assert_num_queries(0):
        response = execute(
            request("register", {"size": 2}),
            runtime_identity=runtime_identity,
            environ=environ,
        )

    assert response == {"result": "FAIL_TARGET", "data": {}}
    assert PoolSlot.objects.count() == 0


def test_request_identity_for_another_environment_is_refused() -> None:
    """P-12: a request naming a non-Staging identity cannot match even itself."""
    production = {**IDENTITY, "environment": "production"}
    payload = {**request("register", {"size": 2}), "identity": production}

    response = execute(payload, runtime_identity=production)

    assert response == {"result": "FAIL_TARGET", "data": {}}
    assert PoolSlot.objects.count() == 0


def _without(key: str) -> dict[str, object]:
    payload = request("status")
    del payload[key]
    return payload


@pytest.mark.parametrize(
    "payload",
    (
        {**request("status"), "extra": 1},
        _without("pool"),
        _without("arguments"),
        request("drop_table"),
        {**request("status"), "pool": 7},
        {**request("status"), "pool": "Not Valid"},
        {**request("status"), "arguments": []},
        request("status", {"extra": 1}),
        request("register", {}),
        request("register", {"size": 2, "extra": 1}),
        request("register", {"size": "2"}),
        request("register", {"size": True}),
        request("register", {"size": 0}),
        request("allocate", {"run_id": RUN_A.upper(), "count": 1, "ttl_seconds": 600}),
        request("allocate", {"run_id": RUN_A, "count": 1001, "ttl_seconds": 600}),
        request("allocate", {"run_id": RUN_A, "count": 1, "ttl_seconds": 59}),
        request("heartbeat", {"run_id": RUN_A}),
        request("release", {"run_id": RUN_A, "index": 0}),
        request("quarantine", {"index": -1, "run_id": RUN_A}),
        request("readmit", {"index": 0, "run_id": RUN_A}),
    ),
)
def test_malformed_requests_fail_closed_without_changing_the_pool(
    payload: dict[str, object],
) -> None:
    """P-12: only exact request shapes and valid values reach a lease operation."""
    services.register(POOL, 2)
    before = snapshot()

    response = execute(copy.deepcopy(payload))

    assert response == {"result": "FAIL_REQUEST", "data": {}}
    assert snapshot() == before


def test_domain_failures_have_fixed_codes_and_no_exception_text() -> None:
    """P-7: shortage and slot errors report counts or nothing, never details."""
    services.register(POOL, 2)
    services.allocate(POOL, RUN_A, 1, 600)
    before = snapshot()

    shortage = execute(
        request("allocate", {"run_id": RUN_B, "count": 2, "ttl_seconds": 600})
    )
    not_leased = execute(request("quarantine", {"index": 1, "run_id": RUN_B}))
    unknown = execute(request("readmit", {"index": 9}))

    assert shortage == {"result": "FAIL_INSUFFICIENT", "data": {"available": 1}}
    assert not_leased == {"result": "FAIL_SLOT", "data": {}}
    assert unknown == {"result": "FAIL_SLOT", "data": {}}
    assert snapshot() == before
