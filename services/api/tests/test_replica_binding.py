"""Cloud Run target binding for the hybrid replica (#355 U1, AC10)."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import NoReturn

import pytest
from pytest import MonkeyPatch

from config import replica_binding
from tests import replica_contract as contract
from tests.process_support import minimal_environment

API_ROOT = Path(__file__).resolve().parents[1]

SERVICE_ENV = {
    "K_SERVICE": contract.SERVICE_NAME,
    "K_REVISION": contract.SERVICE_REVISION,
}
JOB_ENV = {
    "CLOUD_RUN_JOB": contract.JOB_NAME,
    "CLOUD_RUN_EXECUTION": contract.JOB_EXECUTION,
}


def test_non_cloud_run_process_has_no_replica_target(monkeypatch: MonkeyPatch) -> None:
    """Railway and local processes must pass through with no metadata lookup."""

    def fail_metadata(path: str) -> NoReturn:
        pytest.fail(f"unexpected metadata call: {path}")

    monkeypatch.setattr(replica_binding, "_fetch_metadata", fail_metadata)

    assert replica_binding.read_cloud_run_target({}) is None
    assert (
        replica_binding.read_cloud_run_target({"RAILWAY_SERVICE_NAME": "api"}) is None
    )


@pytest.mark.parametrize(
    "environment",
    (
        pytest.param({**SERVICE_ENV, **JOB_ENV}, id="service-and-job-markers"),
        pytest.param(
            {
                "K_SERVICE": "tailtag-api-other",
                "K_REVISION": "tailtag-api-other-00001-a",
            },
            id="unpinned-name",
        ),
        pytest.param(
            {
                "K_SERVICE": contract.JOB_NAME,
                "K_REVISION": f"{contract.JOB_NAME}-00001-a",
            },
            id="job-name-under-service-marker",
        ),
        pytest.param(
            {**SERVICE_ENV, "K_REVISION": "tailtag-other-00007-abc"},
            id="revision-without-name-prefix",
        ),
        pytest.param(
            {**SERVICE_ENV, "K_REVISION": f"{contract.SERVICE_NAME}-00007/../x"},
            id="malformed-revision",
        ),
    ),
)
def test_unbound_or_malformed_cloud_run_identity_is_rejected(
    monkeypatch: MonkeyPatch, environment: dict[str, str]
) -> None:
    """Failure modes 3, 4 and 5: only an exact, pinned Cloud Run identity binds."""
    contract.install_replica_pins(monkeypatch)

    with pytest.raises(replica_binding.ReplicaBindingError) as caught:
        replica_binding.read_cloud_run_target(environment)

    assert not any(value in str(caught.value) for value in environment.values())


def test_target_digest_must_match_metadata_project_number(
    monkeypatch: MonkeyPatch,
) -> None:
    """Failure mode 1: a valid-looking name pinned to another project is refused."""
    contract.install_replica_pins(
        monkeypatch,
        targets=contract.pinned_targets(project_number=contract.OTHER_PROJECT_NUMBER),
    )

    with pytest.raises(replica_binding.ReplicaBindingError):
        replica_binding.read_cloud_run_target(SERVICE_ENV)


def test_metadata_failure_is_retried_and_only_success_is_cached() -> None:
    """Failure mode 2: errors and a mismatched region never bind or stick.

    A fresh interpreter keeps the process-wide cache empty, so the order of
    failure, mismatch, success and repeat success is deterministic.
    """
    script = textwrap.dedent(
        """
        import json
        from config import replica_binding as rb
        from tests import replica_contract as c

        mode = ["error"]
        calls = []

        def fetch(path):
            calls.append(path)
            if mode[0] == "error":
                raise rb.ReplicaBindingError("metadata unreachable")
            if mode[0] == "mismatch" and path == "instance/region":
                return f"projects/{c.OTHER_PROJECT_NUMBER}/regions/{c.REGION}"
            return c.fake_metadata(path)

        rb._fetch_metadata = fetch
        rb._EXPECTED_TARGET_DIGESTS = c.pinned_targets()
        env = {"K_SERVICE": c.SERVICE_NAME, "K_REVISION": c.SERVICE_REVISION}

        def attempt(new_mode):
            mode[0] = new_mode
            try:
                rb.read_cloud_run_target(env)
            except rb.ReplicaBindingError:
                return "error"
            return "ok"

        outcomes = [attempt("error"), attempt("mismatch"), attempt("ok")]
        calls_after_first_success = len(calls)
        outcomes.append(attempt("error"))
        print(json.dumps({
            "outcomes": outcomes,
            "refetched_after_success": len(calls) - calls_after_first_success,
        }))
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=API_ROOT,
        env=minimal_environment(),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "outcomes": ["error", "error", "ok", "ok"],
        "refetched_after_success": 0,
    }
