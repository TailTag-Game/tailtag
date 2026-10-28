"""#359 U3a: the hybrid replica as a third, digest-pinned simulator target."""

import asyncio
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from report_support import recorder

from tailtag_simulator import baselines, clerk, targets
from tailtag_simulator.client import open_client
from tailtag_simulator.host_protocol import validate_manifest
from tailtag_simulator.safety import resolve_safety_policy, valid_identity
from tailtag_simulator.targets import (
    TargetRejected,
    bind_target,
    bound_target,
    replica_host_digest,
    resolve_target,
    verify_target,
)
from tailtag_simulator.traffic_config import resolve_traffic_config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HOST = "tailtag-api-replica-123456789012.us-east4.run.app"
ORIGIN = f"https://{HOST}"
REVISION = "tailtag-api-replica-00016-fh9"
REPLICA_IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": REVISION,
    "environment": "replica",
}
STAGING_IDENTITY: dict[str, object] = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}


@pytest.fixture(autouse=True)
def pinned(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pin a synthetic host, as the API tests do. The real host stays private."""
    monkeypatch.setattr(targets, "REPLICA_HOST_DIGEST", replica_host_digest(HOST))
    yield


def test_committed_digest_equals_the_api_pin() -> None:
    """T1: the simulator and the API pin the same private host."""
    source = (REPOSITORY_ROOT / "services/api/config/replica_binding.py").read_text()
    match = re.search(r'_EXPECTED_HOST_DIGEST: Final = \(\s*"([0-9a-f]{64})"', source)
    assert match is not None
    module_source = Path(targets.__file__).read_text()
    pinned = re.search(
        r'REPLICA_HOST_DIGEST: Final = \(\s*"([0-9a-f]{64})"', module_source
    )
    assert pinned is not None
    assert pinned.group(1) == match.group(1)


@pytest.mark.parametrize(
    "origin",
    [
        None,
        f"http://{HOST}",
        f"{ORIGIN}/",
        f"{ORIGIN}:443",
        f"https://candidate---{HOST}",
        "https://tailtag-api-replica-999999999999.us-east4.run.app",
        ORIGIN.upper(),
    ],
)
def test_replica_resolves_only_the_pinned_origin(origin: str | None) -> None:
    """T1: any other, tagged, look-alike or decorated origin is refused."""
    with pytest.raises(TargetRejected):
        resolve_target("replica", origin)


def test_replica_target_records_only_the_digest_label() -> None:
    target = resolve_target("replica", ORIGIN)
    assert (target.name, target.origin) == ("replica", ORIGIN)
    assert target.report_origin == f"sha256:{replica_host_digest(HOST)}"
    assert HOST not in target.report_origin
    staging = resolve_target("staging", None)
    assert staging.report_origin == staging.origin == targets.STAGING_ORIGIN


@pytest.mark.parametrize(
    ("name", "identity", "valid"),
    [
        ("replica", REPLICA_IDENTITY, True),
        ("replica", {**REPLICA_IDENTITY, "environment": "staging"}, False),
        ("replica", {**REPLICA_IDENTITY, "deployment_id": "tailtag-api-other"}, False),
        ("replica", {**REPLICA_IDENTITY, "source_sha": None}, False),
        ("staging", STAGING_IDENTITY, True),
        ("staging", REPLICA_IDENTITY, False),
        (
            "local",
            {"source_sha": None, "deployment_id": None, "environment": None},
            True,
        ),
        ("local", REPLICA_IDENTITY, False),
        (
            "unknown",
            {"source_sha": None, "deployment_id": None, "environment": None},
            False,
        ),
    ],
)
def test_identity_rule_follows_the_target(
    name: str, identity: dict[str, object], valid: bool
) -> None:
    """T2, T5: one rule per target, shared by targets, safety, reports and manifests."""
    assert valid_identity(name, identity) is valid


@pytest.mark.parametrize("failure", [None, "unready", "changed", "staging-shaped"])
def test_replica_verification_requires_stable_identity_around_readiness(
    failure: str | None,
) -> None:
    """T2: like Staging, the replica must be ready between two equal reads."""
    seen: list[str] = []
    reads = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        assert request.url.host == HOST
        seen.append(request.url.path)
        if request.url.path == "/health/identity":
            reads += 1
            body = dict(
                STAGING_IDENTITY if failure == "staging-shaped" else REPLICA_IDENTITY
            )
            if failure == "changed" and reads == 2:
                body["source_sha"] = "b" * 40
            return httpx.Response(200, json=body)
        return httpx.Response(
            503 if failure == "unready" else 200, json={"status": "ok"}
        )

    async def execute() -> dict[str, object]:
        async with open_client(
            ORIGIN, transport=httpx.MockTransport(respond)
        ) as client:
            return (
                await verify_target(client, resolve_target("replica", ORIGIN))
            ).identity()

    if failure is None:
        assert asyncio.run(execute()) == REPLICA_IDENTITY
        assert seen == ["/health/identity", "/health/ready", "/health/identity"]
    else:
        with pytest.raises(TargetRejected):
            asyncio.run(execute())


def test_bound_target_selects_the_clerk_application() -> None:
    """T3, T4: Staging stays the default. A bound replica switches every Clerk pin."""
    assert bound_target().name == "staging"
    assert clerk.clerk_profile().frontend_api == clerk.FRONTEND_API
    with bind_target(resolve_target("replica", ORIGIN)):
        assert bound_target().origin == ORIGIN
        profile = clerk.clerk_profile()
        assert profile == clerk.REPLICA_CLERK
        assert (
            profile.frontend_api,
            profile.tooling_origin,
            profile.primary_domain,
        ) == (
            "https://clerk.replica.tailtag.app",
            "https://simulator.replica.tailtag.app",
            "replica.tailtag.app",
        )
        assert profile.environment == "replica"
    assert bound_target().name == "staging"


def test_replica_report_records_the_digest_never_the_origin(tmp_path: Path) -> None:
    """T6: the recorded target names the replica by its pin digest."""
    report = recorder(
        tmp_path,
        "journeys",
        config={"target": "replica", "base_url": None, "pool": "replica1"},
    )
    target = resolve_target("replica", ORIGIN)
    report.record_target(target.name, target.report_origin, REPLICA_IDENTITY)
    text = next(tmp_path.glob("*.json")).read_text()
    assert HOST not in text
    assert f"sha256:{replica_host_digest(HOST)}" in text
    with pytest.raises(Exception):  # noqa: B017 - any refusal is enough here
        report.record_target(target.name, ORIGIN, REPLICA_IDENTITY)


def test_replica_attribution_records_the_final_identity_by_digest(
    tmp_path: Path,
) -> None:
    """T6: the final target check after a run records the digest label too."""
    from tailtag_simulator.smoke import attribute

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.host == HOST
        if request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json=REPLICA_IDENTITY)

    report = recorder(
        tmp_path,
        "journeys",
        config={"target": "replica", "base_url": None, "pool": "replica1"},
    )
    target = resolve_target("replica", ORIGIN)
    report.record_target(target.name, target.report_origin, REPLICA_IDENTITY)
    verified = targets.VerifiedTarget(target, "a" * 40, REVISION, "replica")
    asyncio.run(attribute(verified, report, httpx.MockTransport(respond)))
    text = next(tmp_path.glob("*.json")).read_text()
    assert '"attribution":"verified"' in text
    assert HOST not in text


def test_replica_baseline_slug_never_names_a_staging_file() -> None:
    """T7: the replica slug carries its environment. Staging slugs are unchanged."""
    key = {
        "scenario_id": "convention-baseline",
        "scenario_version": 2,
        "plan_digest": "f" * 64,
        "execution_context": "external_host:linux/amd64",
        "environment": "staging",
    }
    staging = baselines.baseline_slug(key)
    replica = baselines.baseline_slug({**key, "environment": "replica"})
    assert staging == "convention-baseline-v2-ffffffffffff-external_host-linux-amd64"
    assert replica == staging + "-replica"


def replica_manifest(**changes: object) -> dict[str, object]:
    configuration = changes.pop("configuration", None) or resolve_traffic_config(
        {"pool": "replica1", "target": "replica"}
    )
    return {
        "schema_version": 1,
        "run_id": "55555555-5555-4555-8555-555555555555",
        "scenario_id": "convention-baseline",
        "scenario_version": 2,
        "seed": 1,
        "configuration": configuration,
        "safety": resolve_safety_policy({"population": 50}),
        "backend_identity": dict(REPLICA_IDENTITY),
        "release": {
            "simulator_sha": "b" * 40,
            "dependency_lock_sha256": "c" * 64,
            "image_id": "sha256:" + "d" * 64,
            "platform": "linux/amd64",
        },
        "target": {"name": "replica", "origin": ORIGIN},
        **changes,
    }


def burst(target: str, value: int, safety: int | None = None) -> dict[str, object]:
    configuration = resolve_traffic_config(
        {
            "pool": "replica1",
            "target": target,
            "limits": {
                "active": value,
                "in_flight": value,
                "attempts": 9000,
                "generation_seconds": 360,
                "drain_seconds": 15,
            },
        }
    )
    changes: dict[str, object] = {
        "configuration": configuration,
        "safety": resolve_safety_policy(
            {"population": 50, "in_flight": value if safety is None else safety}
        ),
    }
    if target == "staging":
        changes.update(backend_identity=dict(STAGING_IDENTITY))
        launch = replica_manifest(**changes)
        del launch["target"]
        return launch
    return replica_manifest(**changes)


def test_replica_manifest_and_its_burst_tier_are_admitted() -> None:
    """T8, T9: a pinned replica manifest passes, up to the 20-request burst tier."""
    assert validate_manifest(replica_manifest())["target"] == {
        "name": "replica",
        "origin": ORIGIN,
    }
    validate_manifest(burst("replica", 20))


@pytest.mark.parametrize(
    "launch",
    [
        pytest.param(
            replica_manifest(target={"name": "staging", "origin": ORIGIN}),
            id="target-named-staging",
        ),
        pytest.param(
            replica_manifest(
                target={"name": "replica", "origin": f"https://candidate---{HOST}"}
            ),
            id="candidate-origin",
        ),
        pytest.param(replica_manifest(target={"name": "replica"}), id="no-origin"),
        pytest.param(
            replica_manifest(backend_identity=dict(STAGING_IDENTITY)),
            id="staging-identity",
        ),
        pytest.param(
            replica_manifest(
                configuration=resolve_traffic_config({"pool": "replica1"})
            ),
            id="configuration-names-staging",
        ),
        pytest.param(lambda: burst("replica", 21), id="replica-over-burst"),
        pytest.param(lambda: burst("staging", 20, safety=10), id="staging-burst"),
    ],
)
def test_manifest_refuses_a_replica_mismatch_or_a_wrong_tier(launch: object) -> None:
    """T8, T9: target, identity and configuration must agree. Staging keeps its tier."""
    value = launch() if callable(launch) else launch
    with pytest.raises(ValueError):
        validate_manifest(value)


def test_manifest_without_a_target_is_still_a_staging_manifest() -> None:
    """T8: manifests written before #359 keep their meaning."""
    launch = replica_manifest(
        configuration=resolve_traffic_config({"pool": "replica1"}),
        backend_identity=dict(STAGING_IDENTITY),
    )
    del launch["target"]
    assert "target" not in validate_manifest(launch)
    with pytest.raises(ValueError):
        validate_manifest({**launch, "backend_identity": dict(REPLICA_IDENTITY)})


@pytest.mark.parametrize(
    ("environment", "backend", "valid"),
    [
        ("replica", REPLICA_IDENTITY, True),
        ("staging", STAGING_IDENTITY, True),
        ("staging", REPLICA_IDENTITY, False),
        ("replica", STAGING_IDENTITY, False),
        ("local", REPLICA_IDENTITY, False),
    ],
)
def test_baseline_backend_must_come_from_its_key_environment(
    environment: str, backend: dict[str, object], valid: bool
) -> None:
    """T7: a replica baseline cannot pose as a Staging one, or the reverse."""
    import json

    from tailtag_simulator.evaluation import parse_baseline

    committed = next(
        (REPOSITORY_ROOT / "tools/simulator/baselines").glob("*.baseline.json")
    )
    value = json.loads(committed.read_text())
    value["key"]["environment"] = environment
    value["report"]["backend"] = dict(backend)
    if valid:
        assert parse_baseline(value)["key"]["environment"] == environment
    else:
        with pytest.raises(Exception):  # noqa: B017 - the parser's own refusal type
            parse_baseline(value)


@pytest.mark.parametrize("command", ["pool", "fixture"])
def test_bound_replica_runs_probe_only_the_replica_host(command: str) -> None:
    """T3: pool and fixture runs follow the bound target, never the Staging origin."""
    from tailtag_simulator.fixtures import run_fixture_smoke
    from tailtag_simulator.pool import run_pool_smoke

    hosts: list[str] = []

    def api(request: httpx.Request) -> httpx.Response:
        # The replica passes its target checks, so the run reaches its own
        # target stage and then stops at the Clerk secret.
        hosts.append(request.url.host)
        if request.url.host == HOST and request.url.path == "/health/identity":
            return httpx.Response(200, json=REPLICA_IDENTITY)
        if request.url.host == HOST and request.url.path == "/health/ready":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(503, json={"status": "unavailable"})

    def clerk_call(_: httpx.Request) -> httpx.Response:
        raise AssertionError("no Clerk call before the target passes")

    def no_secret() -> str:
        return ""  # Refused by the Clerk client before any Clerk call.

    lines: list[str] = []
    unused = cast(Any, None)
    with bind_target(resolve_target("replica", ORIGIN)):
        if command == "pool":
            work = run_pool_smoke(
                "replica1",
                3,
                prompt_secret=no_secret,
                channel=unused,
                emit=lines.append,
                clerk_transport=httpx.MockTransport(clerk_call),
                api_transport=httpx.MockTransport(api),
            )
        else:
            work = run_fixture_smoke(
                "replica1",
                1,
                1,
                1,
                prompt_secret=no_secret,
                lease_channel=unused,
                fixture_channel=unused,
                emit=lines.append,
                clerk_transport=httpx.MockTransport(clerk_call),
                api_transport=httpx.MockTransport(api),
            )
        code = asyncio.run(work)

    assert code == 1
    assert hosts.count(HOST) >= 6, "both the safety probe and the run's own check"
    assert set(hosts) == {HOST}
    assert all("staging" not in line for line in lines)
