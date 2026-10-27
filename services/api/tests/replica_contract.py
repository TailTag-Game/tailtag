"""Synthetic pins and runtime environment shared by the replica identity tests.

Every value here is invented for tests. Digests follow the formulas in the #355 U1
contract and are computed with hashlib, so a wrong formula in
`config.replica_binding` fails against these tests instead of hiding behind them.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pytest import MonkeyPatch

PROJECT_NUMBER: Final = "424242424242"
OTHER_PROJECT_NUMBER: Final = "737373737373"
REGION: Final = "us-east4"
OTHER_REGION: Final = "europe-west2"

SERVICE_NAME: Final = "tailtag-api-replica"
JOB_NAMES: Final = (
    "tailtag-replica-migrate",
    "tailtag-replica-reset",
    "tailtag-replica-fixture",
    "tailtag-replica-pool",
    "tailtag-replica-inspect",
    "tailtag-replica-registry-reconcile",
)
SERVICE_REVISION: Final = f"{SERVICE_NAME}-00007-abc"
JOB_NAME: Final = "tailtag-replica-migrate"
JOB_EXECUTION: Final = f"{JOB_NAME}-x9k2p"

RUN_APP_HOST: Final = "tailtag-api-replica-synthetic.a.run.app"
OTHER_RUN_APP_HOST: Final = "tailtag-api-replica-other.a.run.app"
DATABASE_HOST: Final = "db.replica-synthetic.example.test"
DATABASE_NAME: Final = "tailtag_replica_synthetic"
MEDIA_ENDPOINT: Final = "https://storage.replica-synthetic.example.test"
MEDIA_BUCKET: Final = "tailtag-replica-synthetic-media"
CLERK_PARTIES: Final = (
    "https://accounts.replica.tailtag.app",
    "https://simulator.replica.tailtag.app",
)
SSL_ROOT_CERT: Final = "/etc/ssl/certs/synthetic-root.pem"


def _sha256(*parts: str, tag: str) -> str:
    return hashlib.sha256("\0".join([tag, *parts]).encode()).hexdigest()


def target_digest(project_number: str, region: str, name: str) -> str:
    return _sha256(project_number, region, name, tag="tailtag-replica-v1")


def host_digest(host: str) -> str:
    return _sha256(host, tag="tailtag-replica-host-v1")


def database_digest(host: str, name: str) -> str:
    return _sha256(host, name, tag="tailtag-replica-database-v1")


def media_digest(endpoint_url: str, bucket_name: str) -> str:
    return _sha256(endpoint_url, bucket_name, tag="tailtag-replica-media-v1")


def pinned_targets(
    project_number: str = PROJECT_NUMBER, region: str = REGION
) -> dict[str, str]:
    return {
        name: target_digest(project_number, region, name)
        for name in (SERVICE_NAME, *JOB_NAMES)
    }


def fake_metadata(path: str) -> str:
    """Stand in for the one network seam, `replica_binding._fetch_metadata`."""
    if path == "project/numeric-project-id":
        return PROJECT_NUMBER
    if path == "instance/region":
        return f"projects/{PROJECT_NUMBER}/regions/{REGION}"
    raise AssertionError(f"unexpected metadata path: {path}")


def install_replica_pins(
    monkeypatch: MonkeyPatch,
    *,
    targets: dict[str, str] | None = None,
) -> None:
    """Replace the network seam and pin constants with the synthetic values above."""
    from config import replica_binding

    monkeypatch.setattr(replica_binding, "_fetch_metadata", fake_metadata)
    monkeypatch.setattr(
        replica_binding,
        "_EXPECTED_TARGET_DIGESTS",
        pinned_targets() if targets is None else targets,
    )
    monkeypatch.setattr(
        replica_binding, "_EXPECTED_HOST_DIGEST", host_digest(RUN_APP_HOST)
    )
    monkeypatch.setattr(
        replica_binding,
        "_EXPECTED_DATABASE_DIGEST",
        database_digest(DATABASE_HOST, DATABASE_NAME),
    )
    monkeypatch.setattr(
        replica_binding,
        "_EXPECTED_MEDIA_DIGEST",
        media_digest(MEDIA_ENDPOINT, MEDIA_BUCKET),
    )
    monkeypatch.setattr(replica_binding, "_PROBE_HOSTS", frozenset[str]())


def set_cloud_run_environment(
    monkeypatch: MonkeyPatch,
    *,
    kind: str = "service",
    **overrides: str,
) -> None:
    """Clear every runtime marker, then set one Cloud Run identity."""
    for name in (
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_DEPLOYMENT_ID",
        "RAILWAY_SERVICE_NAME",
        "K_SERVICE",
        "K_REVISION",
        "CLOUD_RUN_JOB",
        "CLOUD_RUN_EXECUTION",
    ):
        monkeypatch.delenv(name, raising=False)
    values = (
        {"K_SERVICE": SERVICE_NAME, "K_REVISION": SERVICE_REVISION}
        if kind == "service"
        else {"CLOUD_RUN_JOB": JOB_NAME, "CLOUD_RUN_EXECUTION": JOB_EXECUTION}
    )
    for name, value in {**values, **overrides}.items():
        monkeypatch.setenv(name, value)
