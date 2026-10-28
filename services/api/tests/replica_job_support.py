"""Process, identity and request setup shared by the replica job command tests.

Builds on `tests/replica_contract.py` (#355 U1). Only the metadata server is faked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, Literal

from pytest import MonkeyPatch

from config import build_identity
from tests import replica_contract

SOURCE_SHA: Final = "c070f413eec1518459f1fef21b471642765a54e9"
RAILWAY_DEPLOYMENT_ID: Final = "93de11d6-714f-405a-b931-a9b567d5ec1e"

POOL_JOB: Final = "tailtag-replica-pool"
FIXTURE_JOB: Final = "tailtag-replica-fixture"
INSPECT_JOB: Final = "tailtag-replica-inspect"
MIGRATE_JOB: Final = "tailtag-replica-migrate"
REGISTRY_JOB: Final = "tailtag-replica-registry-reconcile"

Process = Literal["job", "service", "railway", "local"]


def execution_id(job: str) -> str:
    """Return the synthetic Cloud Run execution name of one job."""
    return f"{job}-x9k2p"


def runtime_identity(job: str, source_sha: str | None = SOURCE_SHA) -> dict[str, str]:
    """Return the identity a replica job process reports for itself."""
    assert source_sha is not None
    return {
        "source_sha": source_sha,
        "deployment_id": execution_id(job),
        "environment": "replica",
    }


def job_environ(job: str) -> dict[str, str]:
    """Return the Cloud Run job markers that `read_cloud_run_target` reads."""
    return {
        "CLOUD_RUN_JOB": job,
        "CLOUD_RUN_EXECUTION": execution_id(job),
        "CLOUD_RUN_TASK_COUNT": "1",
        "CLOUD_RUN_TASK_INDEX": "0",
    }


def service_environ() -> dict[str, str]:
    """Return the Cloud Run service markers of the replica API."""
    return {
        "K_SERVICE": replica_contract.SERVICE_NAME,
        "K_REVISION": replica_contract.SERVICE_REVISION,
    }


def railway_environ() -> dict[str, str]:
    """Return the markers of the Railway Staging API."""
    return {
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "RAILWAY_SERVICE_NAME": "api",
        "RAILWAY_DEPLOYMENT_ID": RAILWAY_DEPLOYMENT_ID,
    }


def configure_process(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    *,
    process: Process = "job",
    job: str = POOL_JOB,
    source_sha: str | None = SOURCE_SHA,
) -> None:
    """Pin synthetic replica values and make this process look like `process`."""
    replica_contract.install_replica_pins(monkeypatch)
    replica_contract.set_cloud_run_environment(monkeypatch, kind="job")
    for name in ("CLOUD_RUN_JOB", "CLOUD_RUN_EXECUTION"):
        monkeypatch.delenv(name)
    for name in ("CLOUD_RUN_TASK_COUNT", "CLOUD_RUN_TASK_INDEX"):
        monkeypatch.delenv(name, raising=False)
    markers = {
        "job": job_environ(job),
        "service": service_environ(),
        "railway": railway_environ(),
        "local": {},
    }[process]
    for name, value in markers.items():
        monkeypatch.setenv(name, value)
    metadata = tmp_path / "build-identity.json"
    metadata.write_text(json.dumps({"source_sha": source_sha}))
    monkeypatch.setattr(build_identity, "_METADATA_PATH", metadata)
