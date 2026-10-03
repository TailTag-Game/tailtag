"""Acceptance coverage for the Staging simulation inspection-channel launcher (#222).

The launcher is a copy of the fixture launcher, so only what differs is covered
here: the exact inspection result and data schema, and a bootstrap that must reach
the read-only inspection entry point and nothing else.
"""

from __future__ import annotations

import ast
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
    "operation": "inspect",
    "arguments": {
        "pool": SECRET_POOL,
        "run_id": SECRET_RUN_ID,
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
}
CATCH: dict[str, object] = {
    "id": 11,
    "catcher": 8,
    "fursuit": 34,
    "fursuit_owner": 5,
    "run_convention": True,
    "provenance": True,
    "in_window": True,
    "caught_at": "2026-10-03T19:41:53.769123Z",
}
# A stranger's catch carries ``null`` people; a whole-second timestamp has no fraction.
FOREIGN_CATCH: dict[str, object] = {
    **CATCH,
    "id": 12,
    "catcher": None,
    "fursuit_owner": None,
    "run_convention": False,
    "provenance": False,
    "in_window": False,
    "caught_at": "2026-10-03T19:41:53Z",
}
DATA: dict[str, object] = {
    "catches": [CATCH, FOREIGN_CATCH],
    "fursuits": [{"id": 35, "owner": 5}],
    "fixture_photos_unchanged": True,
    "avatars": [3, 5],
}
EMPTY_DATA: dict[str, object] = {
    "catches": [],
    "fursuits": [],
    "fixture_photos_unchanged": False,
    "avatars": [],
}


@pytest.fixture
def launcher() -> ModuleType:
    return importlib.import_module("scripts.api_sim_inspect_ssh")


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
        ({"result": "PASS", "data": DATA}, 0),
        ({"result": "PASS", "data": EMPTY_DATA}, 0),
        *(
            ({"result": code, "data": {}}, 1)
            for code in (
                "FAIL_REQUEST",
                "FAIL_TARGET",
                "FAIL_LEASE",
                "FAIL_RUN_UNKNOWN",
                "FAIL_LIMIT",
                "FAIL_BOOTSTRAP",
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
    """R-4: every valid inspection result is relayed once; no private data in argv."""
    executions: list[tuple[list[str], str | None]] = []

    def run(
        arguments: list[str], *, input: str | None = None, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        executions.append((arguments, input))
        return completed(remote)

    calls = install_seams(launcher, monkeypatch, run)

    code, output = invoke(launcher, CALLER_REQUEST)

    assert code == exit_code
    assert json.loads(output) == remote
    assert calls == ["railway", "preflight", "target", "instance", "run"]
    ((arguments, stdin_text),) = executions
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


def _with_data(**changes: object) -> dict[str, object]:
    return {"result": "PASS", "data": {**DATA, **changes}}


def _with_catch(**changes: object) -> dict[str, object]:
    return _with_data(catches=[{**CATCH, **changes}])


def _without_catch_key(key: str) -> dict[str, object]:
    return _with_data(catches=[{k: v for k, v in CATCH.items() if k != key}])


@pytest.mark.parametrize(
    "execution",
    (
        completed({"result": "PASS", "data": DATA}, returncode=1),
        completed({**_with_data(), "extra": "private"}),
        completed({"result": "PASS"}),
        completed({"result": "private-text", "data": {}}),
        completed({"result": "FAIL_DIRTY", "data": {}}),
        completed({"result": "FAIL_LEASE", "data": {"handle": "private"}}),
        completed(_with_data(extra="private")),
        completed({"result": "PASS", "data": {}}),
        completed(_with_data(catches=[{**CATCH, "extra": "private"}])),
        completed(_without_catch_key("provenance")),
        completed(_with_catch(id="private")),
        completed(_with_catch(id=True)),
        completed(_with_catch(id=None)),
        completed(_with_catch(fursuit=None)),
        completed(_with_catch(catcher="private")),
        completed(_with_catch(run_convention=1)),
        completed(_with_catch(caught_at="private")),
        completed(_with_catch(caught_at="2026-10-03T19:41:53.769123+00:00")),
        completed(_with_catch(caught_at="2026-10-03 19:41:53Z")),
        completed(_with_data(catches={"id": 1})),
        completed(_with_data(fursuits=[{"id": 35, "owner": None}])),
        completed(_with_data(fursuits=[{"id": 35, "owner": 5, "name": "private"}])),
        completed(_with_data(fixture_photos_unchanged="private")),
        completed(_with_data(avatars=["private"])),
        subprocess.TimeoutExpired(cmd="railway", timeout=1),
    ),
    ids=(
        "nonzero-exit-with-valid-body",
        "extra-top-level-key",
        "missing-data",
        "unknown-result-text",
        "fixture-only-result-code",
        "failure-with-data",
        "extra-data-key",
        "pass-with-empty-data",
        "extra-catch-key",
        "missing-catch-key",
        "string-catch-id",
        "boolean-catch-id",
        "null-catch-id",
        "null-fursuit",
        "string-catcher",
        "integer-for-boolean-flag",
        "free-text-caught-at",
        "caught-at-with-offset",
        "caught-at-with-space",
        "catches-not-a-list",
        "null-fursuit-owner-in-fursuits",
        "extra-fursuit-key",
        "string-photo-flag",
        "string-avatar",
        "timeout",
    ),
)
def test_unvalidated_remote_output_is_never_relayed(
    launcher: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    execution: subprocess.CompletedProcess[str] | BaseException,
) -> None:
    """R-4: only the exact inspection schema escapes; nothing else is relayed."""

    def run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        if isinstance(execution, BaseException):
            raise execution
        return execution

    install_seams(launcher, monkeypatch, run)

    code, output = invoke(launcher, CALLER_REQUEST)

    assert code != 0
    assert json.loads(output) == FAILURE
    assert "private" not in output


def test_bootstrap_imports_only_the_inspection_entry_point(
    launcher: ModuleType,
) -> None:
    """R-9: this channel has no import route to provision or status."""
    imported: set[str] = set()
    for node in ast.walk(ast.parse(launcher._BOOTSTRAP)):  # pyright: ignore[reportPrivateUsage]
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    allowed = "simulation_fixtures.inspection_remote"

    simulation = {name for name in imported if "simulation" in name}
    assert simulation
    assert all(name == allowed or name.startswith(f"{allowed}.") for name in simulation)


def test_real_bootstrap_reaches_the_inspection_entry_point_and_prints_one_line(
    launcher: ModuleType, tmp_path: Path
) -> None:
    """R-9: outside Staging, the real bootstrap answers FAIL_TARGET through the remote."""
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
        input=json.dumps({**CALLER_REQUEST, "identity": IDENTITY}),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed_process.returncode == 0
    assert completed_process.stdout.count("\n") == 1
    assert json.loads(completed_process.stdout) == {"result": "FAIL_TARGET", "data": {}}
    assert completed_process.stderr == ""


@pytest.mark.parametrize(
    "request_text",
    (
        json.dumps({**CALLER_REQUEST, "identity": dict(IDENTITY)}),
        json.dumps({**CALLER_REQUEST, "pool": SECRET_POOL}),
        json.dumps({"operation": "inspect"}),
        "[]",
        json.dumps({**CALLER_REQUEST, "arguments": {"padding": "x" * 70_000}}),
    ),
    ids=(
        "caller-supplied-identity",
        "extra-top-level-key",
        "missing-arguments",
        "not-a-json-object",
        "oversize",
    ),
)
def test_bad_caller_request_fails_before_any_provider_call(
    launcher: ModuleType, monkeypatch: pytest.MonkeyPatch, request_text: str
) -> None:
    """Security: the caller cannot choose the target identity, and junk never reaches ssh."""
    calls = install_seams(
        launcher, monkeypatch, lambda *_a, **_k: pytest.fail("ssh must not run")
    )

    code, output = invoke(launcher, request_text)

    assert code != 0
    assert json.loads(output) == FAILURE
    assert calls == []
