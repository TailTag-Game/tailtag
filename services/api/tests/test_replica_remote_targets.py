"""Replica target rules of the remote modules and the moved registry reconciler.

#355 U2a, A3 and A5. The Railway rules stay covered by their existing tests.
Nothing here touches the database: a request that passes the target guard is
rejected by request validation afterwards, which is how acceptance is observed.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest
from pytest import MonkeyPatch

from simulation_fixtures import inspection_remote
from simulation_fixtures import remote as fixture_remote
from simulation_pool import remote as pool_remote
from tests import replica_contract
from tests import replica_job_support as support
from tests.process_support import minimal_environment
from tests.test_staging_registry_reconciliation import request as legacy_request

API_ROOT: Final = Path(__file__).resolve().parents[1]
REGISTRY_MODULE: Final = API_ROOT / "rehearsal" / "registry_reconciliation.py"

# Every module rejects this operation, but only after its target guard has passed.
POOL_PAYLOAD: Final[dict[str, object]] = {
    "operation": "drop_table",
    "pool": "gamma",
    "arguments": {},
}
FIXTURE_PAYLOAD: Final[dict[str, object]] = {"operation": "drop_table", "arguments": {}}

MODULES: Final[dict[str, tuple[ModuleType, str, str, dict[str, object]]]] = {
    "pool": (pool_remote, support.POOL_JOB, support.FIXTURE_JOB, POOL_PAYLOAD),
    "fixture": (
        fixture_remote,
        support.FIXTURE_JOB,
        support.INSPECT_JOB,
        FIXTURE_PAYLOAD,
    ),
    "inspect": (
        inspection_remote,
        support.INSPECT_JOB,
        support.FIXTURE_JOB,
        FIXTURE_PAYLOAD,
    ),
}


def _execute(
    module: ModuleType,
    payload: Mapping[str, object],
    identity: Mapping[str, str],
    runtime: Mapping[str, str],
    environ: Mapping[str, str],
) -> object:
    result: object = module.execute(
        {**payload, "identity": dict(identity)},
        runtime_identity=runtime,
        environ=environ,
    )
    return result


@pytest.mark.parametrize("name", MODULES)
def test_each_remote_module_accepts_its_own_replica_job(
    monkeypatch: MonkeyPatch, name: str
) -> None:
    """A3: the replica rule lets each module past its target guard in its own job."""
    replica_contract.install_replica_pins(monkeypatch)
    module, job, _, payload = MODULES[name]
    identity = support.runtime_identity(job)

    response = _execute(module, payload, identity, identity, support.job_environ(job))

    assert response == {"result": "FAIL_REQUEST", "data": {}}


@pytest.mark.parametrize(
    ("name", "scenario"),
    (
        pytest.param("pool", "other-job", id="pool-in-fixture-job"),
        pytest.param("fixture", "other-job", id="fixture-in-inspect-job"),
        pytest.param("inspect", "other-job", id="inspect-in-fixture-job"),
        pytest.param("fixture", "service", id="fixture-in-replica-api-service"),
        pytest.param("pool", "railway", id="pool-in-railway-process"),
        pytest.param("inspect", "runtime-mismatch", id="inspect-with-other-runtime"),
    ),
)
def test_replica_rule_refuses_other_processes_and_unproven_identities(
    monkeypatch: MonkeyPatch, name: str, scenario: str
) -> None:
    """Failure mode 5: only the module's own job passes, and only with its own identity."""
    replica_contract.install_replica_pins(monkeypatch)
    module, job, other_job, payload = MODULES[name]
    identity = support.runtime_identity(job)
    runtime = identity
    environ = support.job_environ(job)
    if scenario == "other-job":
        identity = runtime = support.runtime_identity(other_job)
        environ = support.job_environ(other_job)
    elif scenario == "service":
        environ = support.service_environ()
        identity = runtime = {
            **identity,
            "deployment_id": replica_contract.SERVICE_REVISION,
        }
    elif scenario == "railway":
        environ = support.railway_environ()
    else:
        runtime = {**identity, "source_sha": "d" * 40}

    response = _execute(module, payload, identity, runtime, environ)

    assert response == {"result": "FAIL_TARGET", "data": {}}


def _registry_request(changes: Mapping[str, object]) -> dict[str, object]:
    return {
        "identity": support.runtime_identity(support.REGISTRY_JOB),
        "configuration": legacy_request()["configuration"],
        **changes,
    }


@pytest.mark.parametrize(
    ("process", "job", "request_changes", "expected"),
    (
        pytest.param("job", support.REGISTRY_JOB, {}, True, id="own-job"),
        pytest.param("service", support.REGISTRY_JOB, {}, False, id="api-service"),
        pytest.param("job", support.POOL_JOB, {}, False, id="another-job"),
        pytest.param(
            "job",
            support.REGISTRY_JOB,
            {"identity": support.runtime_identity(support.REGISTRY_JOB, "d" * 40)},
            False,
            id="other-source-sha",
        ),
        pytest.param(
            "job",
            support.REGISTRY_JOB,
            {"database_url_fingerprint": "b" * 64},
            False,
            id="railway-fingerprint-key-on-replica",
        ),
    ),
)
def test_registry_reconciler_replica_branch_accepts_only_its_own_job(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    process: support.Process,
    job: str,
    request_changes: Mapping[str, object],
    expected: bool,
) -> None:
    """A5: replica keys are identity and configuration; the job and identity must match."""
    support.configure_process(monkeypatch, tmp_path, process=process, job=job)
    reconciliation = importlib.import_module("rehearsal.registry_reconciliation")
    request = _registry_request(request_changes)

    assert reconciliation.target_matches(request) is expected


def test_moved_registry_module_still_runs_as_relay_source_text(
    tmp_path: Path,
) -> None:
    """Failure mode 8: the Railway relay `exec`s the file with no repository on the path.

    No module-level import may need Django, the repository, or `replica_binding`.
    """
    assert REGISTRY_MODULE.is_file()
    program = (
        "import sys\n"
        "namespace = {'__name__': 'relay'}\n"
        "exec(compile(open(sys.argv[1]).read(), 'relay', 'exec'), namespace)\n"
        "assert callable(namespace['run_request'])\n"
        "assert callable(namespace['target_matches'])\n"
        "assert not any(\n"
        "    name.split('.')[0] in ('django', 'config', 'rehearsal')\n"
        "    for name in sys.modules\n"
        ")\n"
    )

    completed = subprocess.run(
        [sys.executable, "-I", "-c", program, str(REGISTRY_MODULE)],
        cwd=tmp_path,
        env=minimal_environment(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stderr
