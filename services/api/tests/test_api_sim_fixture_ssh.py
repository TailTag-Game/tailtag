"""Acceptance coverage for the Staging simulation fixture-channel launcher.

The launcher is a copy of the pool launcher, so only what differs is covered here:
the caller request shape, the wider result and data vocabulary, and a bootstrap
that must import the fixture entry point.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
PROJECT_ID = "a1111111-1111-4111-8111-111111111111"
ENVIRONMENT_ID = "c3333333-3333-4333-8333-333333333333"
SERVICE_ID = "d4444444-4444-4444-8444-444444444444"
POSTGRES_ID = "e5555555-5555-4555-8555-555555555555"
INSTANCE_ID = "46d09c1e-9c09-4f31-8b86-4ce9b667c70b"
SECRET_POOL = "privatepool"
SECRET_RUN_ID = "55555555-5555-4555-8555-555555555555"
FAILURE: dict[str, object] = {"result": "FAIL_LAUNCHER", "data": {}}
CALLER_REQUEST = {
    "operation": "provision",
    "arguments": {
        "pool": SECRET_POOL,
        "run_id": SECRET_RUN_ID,
        "owners": [0, 1],
        "catchers": [2],
        "fursuits_per_owner": 1,
    },
}
COUNTS = {"convention": 1, "enrollment": 3, "fursuit": 2, "activation": 2}
CLEANUP_COUNTS = {
    **COUNTS,
    "catch": 1,
    "session": 1,
    "credential": 2,
    "image": 4,
    "readmitted": 5,
}
LISTED_RUN = {
    "run_id": SECRET_RUN_ID,
    "pool": "alpha",
    "reason": "journeys",
    "age_days": 3,
}


@pytest.fixture
def launcher() -> ModuleType:
    return importlib.import_module("scripts.api_sim_fixture_ssh")


def completed(
    output: object, *, returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=("offline",),
        returncode=returncode,
        stdout=output if isinstance(output, str) else json.dumps(output),
        stderr="",
    )


def install_seams(
    launcher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., subprocess.CompletedProcess[str]],
) -> list[str]:
    """Substitute every provider seam; the returned list records call order."""
    calls: list[str] = []

    def record(name: str, value: object = None) -> Callable[..., object]:
        def seam(*_args: object, **_kwargs: object) -> object:
            calls.append(name)
            return value

        return seam

    monkeypatch.setattr(launcher, "_railway_identity", record("railway"))
    monkeypatch.setattr(launcher, "_preflight", record("preflight", dict(IDENTITY)))
    monkeypatch.setattr(
        launcher,
        "_target_ids",
        record("target", (PROJECT_ID, ENVIRONMENT_ID, SERVICE_ID, POSTGRES_ID)),
    )
    monkeypatch.setattr(launcher, "_active_instance", record("instance", INSTANCE_ID))

    def run_seam(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append("run")
        return run(*args, **kwargs)

    monkeypatch.setattr(launcher, "_run", run_seam)
    return calls


def invoke(launcher: ModuleType, request: object | str) -> tuple[int, str]:
    text = request if isinstance(request, str) else json.dumps(request)
    stdout = io.StringIO()
    code = launcher.main([], stdin=io.StringIO(text), stdout=stdout)
    return code, stdout.getvalue()


@pytest.mark.parametrize(
    ("remote", "exit_code"),
    (
        ({"result": "PASS", "data": COUNTS}, 0),
        (
            {"result": "PASS", "data": {"status": "provisioned", "counts": COUNTS}},
            0,
        ),
        ({"result": "FAIL_DIRTY", "data": {"quarantined": 2}}, 1),
        ({"result": "PASS", "data": CLEANUP_COUNTS}, 0),
        ({"result": "PASS", "data": {"quarantined": 4}}, 0),
        (
            {
                "result": "PASS",
                "data": {
                    "runs": [LISTED_RUN, {**LISTED_RUN, "reason": "unfinished"}],
                    "retained": 1,
                    "unfinished": 1,
                },
            },
            0,
        ),
        ({"result": "PASS", "data": {"runs": [], "retained": 0, "unfinished": 0}}, 0),
        *(
            ({"result": code, "data": {}}, 1)
            for code in (
                "FAIL_REQUEST",
                "FAIL_TARGET",
                "FAIL_RUN_EXISTS",
                "FAIL_LEASE",
                "FAIL_INVARIANT",
                "FAIL_ERROR",
                "FAIL_RUN_UNKNOWN",
                "FAIL_BOOTSTRAP",
                "FAIL_ATTRIBUTION",
                "FAIL_STORAGE",
                "FAIL_VERIFY",
                "FAIL_LIMIT",
            )
        ),
    ),
)
def test_one_pinned_ssh_call_carries_the_request_on_stdin_only(
    launcher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    remote: dict[str, object],
    exit_code: int,
) -> None:
    """F-7/F-8: every fixture result is relayed once; no private data in argv."""
    executions: list[tuple[list[str], str | None, int | None]] = []

    def run(
        arguments: list[str], *, input: str | None = None, timeout: int | None = None
    ) -> subprocess.CompletedProcess[str]:
        executions.append((arguments, input, timeout))
        return completed(remote)

    calls = install_seams(launcher, monkeypatch, run)

    code, output = invoke(launcher, CALLER_REQUEST)

    assert code == exit_code
    assert json.loads(output) == remote
    assert calls == ["railway", "preflight", "target", "instance", "run"]
    ((arguments, stdin_text, timeout),) = executions
    # Long enough for a provision at the bounds, within the simulator's 180 s cap.
    assert timeout == 150
    assert arguments[:-1] == [
        "railway",
        "ssh",
        "--project",
        PROJECT_ID,
        "--service",
        SERVICE_ID,
        "--environment",
        ENVIRONMENT_ID,
        "--deployment-instance",
        INSTANCE_ID,
        "--",
        "/app/.venv/bin/python",
        "-I",
        "-c",
    ]
    compile(arguments[-1], "<bootstrap>", "exec")
    assert all(
        sensitive not in part
        for part in arguments
        for sensitive in (SECRET_POOL, SECRET_RUN_ID)
    )
    assert stdin_text is not None
    assert json.loads(stdin_text) == {**CALLER_REQUEST, "identity": IDENTITY}


@pytest.mark.parametrize(
    "failing",
    ("_railway_identity", "_preflight", "_target_ids", "_active_instance"),
)
def test_failed_guard_stops_before_ssh_with_only_the_fixed_failure(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    """F-7: every account, target, and instance guard is independently fail-closed."""
    calls = install_seams(
        launcher, monkeypatch, lambda *_a, **_k: pytest.fail("ssh must not run")
    )

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise ValueError("private provider diagnostic")

    monkeypatch.setattr(launcher, failing, unavailable)

    code, output = invoke(launcher, CALLER_REQUEST)

    assert code != 0
    assert json.loads(output) == FAILURE
    assert "private" not in output
    assert "run" not in calls


@pytest.mark.parametrize(
    "execution",
    (
        completed({"result": "PASS", "data": COUNTS}, returncode=1),
        completed({"result": "PASS", "data": {}, "extra": "private"}),
        completed({"result": "PASS"}),
        completed({"result": "FAIL_INSUFFICIENT", "data": {"available": 1}}),
        completed({"result": "FAIL_SLOT", "data": {}}),
        completed({"result": "private-text", "data": {}}),
        completed({"result": "PASS", "data": {"handle": "sp_private_1"}}),
        completed({"result": "FAIL_DIRTY", "data": {"quarantined": "private"}}),
        completed(
            {
                "result": "PASS",
                "data": {"status": "provisioned", "counts": {"fursuit": "private"}},
            }
        ),
        completed(
            {"result": "PASS", "data": {"status": "provisioned", "counts": "private"}}
        ),
        completed({"result": "FAIL_RETAINED_LIMIT", "data": {}}),
        *(
            completed(
                {
                    "result": "PASS",
                    "data": {"runs": runs, "retained": 1, "unfinished": 0},
                }
            )
            for runs in (
                "private",
                [{**LISTED_RUN, "handle": "private"}],
                [{k: v for k, v in LISTED_RUN.items() if k != "pool"}],
                [{**LISTED_RUN, "run_id": "private"}],
                [{**LISTED_RUN, "pool": "Private-Pool"}],
                [{**LISTED_RUN, "reason": "private"}],
                [{**LISTED_RUN, "age_days": -1}],
                [{**LISTED_RUN, "age_days": True}],
                [{**LISTED_RUN, "age_days": "private"}],
                ["private"],
            )
        ),
        completed(
            {
                "result": "PASS",
                "data": {"runs": [], "retained": "private", "unfinished": 0},
            }
        ),
        subprocess.TimeoutExpired(cmd="railway", timeout=1),
    ),
    ids=(
        "nonzero-exit-with-valid-body",
        "extra-key",
        "missing-data",
        "pool-only-result-code",
        "pool-only-slot-code",
        "unknown-result-text",
        "string-handle-in-data",
        "string-count",
        "string-in-nested-counts",
        "counts-not-an-object",
        "simulator-only-result-code",
        "runs-not-a-list",
        "run-entry-extra-key",
        "run-entry-missing-key",
        "run-id-not-a-uuid",
        "run-pool-malformed",
        "run-reason-unknown",
        "run-age-negative",
        "run-age-boolean",
        "run-age-string",
        "run-entry-not-an-object",
        "retained-count-string",
        "timeout",
    ),
)
def test_unvalidated_remote_output_is_never_relayed(
    launcher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    execution: subprocess.CompletedProcess[str] | BaseException,
) -> None:
    """F-8: only the fixture result vocabulary with counts escapes; nothing else."""

    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if isinstance(execution, BaseException):
            raise execution
        return execution

    install_seams(launcher, monkeypatch, run)

    code, output = invoke(launcher, CALLER_REQUEST)

    assert code != 0
    assert json.loads(output) == FAILURE
    assert "private" not in output


@pytest.mark.parametrize(
    "request_text",
    (
        "[]",
        json.dumps({"operation": "status"}),
        json.dumps({"arguments": {"run_id": SECRET_RUN_ID}}),
        json.dumps({**CALLER_REQUEST, "pool": SECRET_POOL}),
        json.dumps({**CALLER_REQUEST, "identity": dict(IDENTITY)}),
        json.dumps({**CALLER_REQUEST, "arguments": {"padding": "x" * 10_000_000}}),
    ),
    ids=(
        "not-object",
        "missing-arguments",
        "missing-operation",
        "pool-launcher-shape",
        "caller-identity",
        "oversize",
    ),
)
def test_bad_caller_request_fails_before_any_provider_call(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, request_text: str
) -> None:
    """F-7: the caller cannot choose identity, and junk never reaches Railway."""
    calls = install_seams(
        launcher, monkeypatch, lambda *_a, **_k: pytest.fail("ssh must not run")
    )

    code, output = invoke(launcher, request_text)

    assert code != 0
    assert json.loads(output) == FAILURE
    assert calls == []


@pytest.mark.parametrize(
    ("stdin_text", "expected_result"),
    (
        (json.dumps({**CALLER_REQUEST, "identity": IDENTITY}), "FAIL_TARGET"),
        ("x" * 65_537, "FAIL_BOOTSTRAP"),
    ),
    ids=("well-formed-outside-staging", "oversize-stdin"),
)
def test_remote_bootstrap_prints_exactly_one_fixed_json_line(
    launcher: ModuleType,
    tmp_path: Path,
    stdin_text: str,
    expected_result: str,
) -> None:
    """F-7/F-8: the real bootstrap reaches the fixture entry point and prints one line."""
    api_root = REPOSITORY_ROOT / "services" / "api"
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "DATABASE_URL": "postgresql://tailtag:tailtag@localhost:5432/tailtag",
        "DJANGO_SECRET_KEY": "not-a-real-secret",
        "DJANGO_ALLOWED_HOSTS": "localhost",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "http://localhost",
        "MEDIA_STORAGE_ENDPOINT_URL": "https://media.example.test",
        "MEDIA_STORAGE_BUCKET_NAME": "ci-media-bucket",
        "MEDIA_STORAGE_REGION": "auto",
        "MEDIA_STORAGE_ACCESS_KEY_ID": "ci-not-a-real-access-key",
        "MEDIA_STORAGE_SECRET_ACCESS_KEY": "ci-not-a-real-secret-key",
        "RAILWAY_ENVIRONMENT_NAME": "development",
        "RAILWAY_SERVICE_NAME": "api",
    }

    completed_process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            launcher._BOOTSTRAP.replace('"/app"', repr(str(api_root))),  # pyright: ignore[reportPrivateUsage]
        ],
        input=stdin_text,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed_process.returncode == 0
    assert completed_process.stdout.count("\n") == 1
    assert json.loads(completed_process.stdout) == {
        "result": expected_result,
        "data": {},
    }
    assert completed_process.stderr == ""


@pytest.mark.parametrize(
    "pin", ["matching", "changed-sha", "changed-deployment", "malformed"]
)
def test_expected_run_identity_is_checked_before_ssh_and_stripped_from_remote_wire(
    launcher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    pin: str,
) -> None:
    """#227 AC11: a valid new Staging deployment cannot silently replace the run target."""
    expected: dict[str, object] = dict(IDENTITY)
    if pin == "changed-sha":
        expected["source_sha"] = "b" * 40
    elif pin == "changed-deployment":
        expected["deployment_id"] = "22222222-2222-4222-8222-222222222222"
    elif pin == "malformed":
        expected["SENTINEL-secret"] = "private"
    sent: list[object] = []

    def run(
        arguments: list[str],
        *,
        input: str | None = None,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        assert input is not None
        sent.append(json.loads(input))
        return completed(
            {
                "result": "PASS",
                "data": {"status": "provisioned", "counts": {"convention": 1}},
            }
        )

    calls = install_seams(launcher, monkeypatch, run)
    code, output = invoke(launcher, {**CALLER_REQUEST, "expected_identity": expected})
    if pin == "matching":
        assert code == 0
        assert json.loads(output) == {
            "result": "PASS",
            "data": {"status": "provisioned", "counts": {"convention": 1}},
        }
        assert sent == [{**CALLER_REQUEST, "identity": IDENTITY}]
    else:
        assert code != 0
        assert sent == []
        assert json.loads(output) == {
            "result": "FAIL_LAUNCHER" if pin == "malformed" else "FAIL_TARGET",
            "data": {},
        }
        if pin == "malformed":
            assert calls == []
    assert "SENTINEL" not in output
