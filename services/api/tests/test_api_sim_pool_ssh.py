"""Acceptance coverage for the Staging simulation pool lease-channel launcher."""

from __future__ import annotations

import importlib
import io
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.process_support import minimal_environment

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

IDENTITY = {
    "source_sha": "a" * 40,
    "deployment_id": "11111111-1111-4111-8111-111111111111",
    "environment": "staging",
}
RENDER_SERVICE = "srv-d0staging000000000000"
PROJECT_ID = "a1111111-1111-4111-8111-111111111111"
ENVIRONMENT_ID = "c3333333-3333-4333-8333-333333333333"
SERVICE_ID = "d4444444-4444-4444-8444-444444444444"
POSTGRES_ID = "e5555555-5555-4555-8555-555555555555"
INSTANCE_ID = "46d09c1e-9c09-4f31-8b86-4ce9b667c70b"
SECRET_POOL = "privatepool"
SECRET_RUN_ID = "55555555-5555-4555-8555-555555555555"
FAILURE: dict[str, object] = {"result": "FAIL_LAUNCHER", "data": {}}
CALLER_REQUEST = {
    "operation": "quarantine",
    "pool": SECRET_POOL,
    "arguments": {"index": 7, "run_id": SECRET_RUN_ID},
}


@pytest.fixture
def launcher() -> ModuleType:
    return importlib.import_module("scripts.api_sim_pool_ssh")


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
    """Replace the public identity, the service pin and ssh; record each ssh call.

    A real remote names the instance it ran on, so the seam adds one when the
    stand-in answer is a JSON object without it.
    """
    del launcher
    calls: list[str] = []
    relay = importlib.import_module("scripts.api_sim_render_relay")
    monkeypatch.setattr(relay._staging_preflight, "_RENDER_STAGING_PHASE", "canonical")
    monkeypatch.setattr(relay, "_identity", lambda: dict(IDENTITY))
    monkeypatch.setattr(relay, "_service_id", lambda: RENDER_SERVICE)

    def run_seam(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append("run")
        result = run(*args, **kwargs)
        try:
            reply = json.loads(result.stdout)
        except ValueError:
            return result
        if isinstance(reply, dict) and "instance" not in reply:
            reply["instance"] = f"{RENDER_SERVICE}-874b544b8-k7qws"
            result.stdout = json.dumps(reply)
        return result

    monkeypatch.setattr(relay, "_run", run_seam)
    return calls


def invoke(launcher: ModuleType, request: object | str) -> tuple[int, str]:
    text = request if isinstance(request, str) else json.dumps(request)
    stdout = io.StringIO()
    code = launcher.main([], stdin=io.StringIO(text), stdout=stdout)
    return code, stdout.getvalue()


@pytest.mark.parametrize(
    "execution",
    (
        completed("private transport diagnostic", returncode=1),
        completed({"result": "PASS", "data": {}}, returncode=1),
        completed("not json private"),
        completed(""),
        completed('{"result":"PASS","data":{}}\n{"result":"PASS","data":{}}'),
        completed({"result": "PASS", "data": {}, "extra": "private"}),
        completed({"result": "PASS"}),
        completed({"result": "private-text", "data": {}}),
        completed({"result": "PASS", "data": "private"}),
        completed(["PASS"]),
        subprocess.TimeoutExpired(cmd="ssh", timeout=1),
        OSError("private missing ssh"),
    ),
    ids=(
        "nonzero-exit",
        "nonzero-exit-with-valid-body",
        "not-json",
        "empty",
        "two-documents",
        "extra-key",
        "missing-data",
        "unknown-result-text",
        "data-not-object",
        "not-an-object",
        "timeout",
        "ssh-missing",
    ),
)
def test_unvalidated_remote_output_is_never_relayed(
    launcher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    execution: subprocess.CompletedProcess[str] | BaseException,
) -> None:
    """P-7: only the exact result shape escapes; provider output never does."""

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
        "not json",
        "[]",
        json.dumps({"operation": "status", "pool": "p"}),
        json.dumps({**CALLER_REQUEST, "identity": dict(IDENTITY)}),
        json.dumps({**CALLER_REQUEST, "arguments": {"padding": "x" * 10_000_000}}),
    ),
    ids=("not-json", "not-object", "missing-key", "caller-identity", "oversize"),
)
def test_bad_caller_request_fails_before_any_provider_call(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, request_text: str
) -> None:
    """P-12: the caller cannot choose identity, and junk never reaches Render."""
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
        (
            json.dumps({**CALLER_REQUEST, "identity": IDENTITY}),
            "FAIL_TARGET",
        ),
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
    """P-12/P-7: the real bootstrap emits one fixed object and nothing else."""
    api_root = REPOSITORY_ROOT / "services" / "api"
    environment = {
        **minimal_environment(),
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
