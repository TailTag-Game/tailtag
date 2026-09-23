"""Acceptance coverage for the #243 target-bound operator-inspection runner."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = REPOSITORY_ROOT / "scripts" / "api_staging_operator_inspect_ssh.py"
SOURCE_PATH = REPOSITORY_ROOT / "scripts" / "api_staging_operator_inspect.py"
SOURCE_SHA = "a" * 40
DEPLOYMENT_ID = "11111111-1111-4111-8111-111111111111"
INSTANCE_ID = "22222222-2222-4222-8222-222222222222"
PUBLIC_IDENTITY = {
    "source_sha": SOURCE_SHA,
    "deployment_id": DEPLOYMENT_ID,
    "environment": "staging",
}


def completed(
    output: object, *, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    """Build one local observation from the only runner subprocess seam."""
    return subprocess.CompletedProcess(
        args=("offline",),
        returncode=returncode,
        stdout=output if isinstance(output, str) else json.dumps(output),
        stderr=stderr,
    )


@pytest.fixture
def runner() -> ModuleType:
    """Load the runner only once its repository-owned implementation exists."""
    assert RUNNER_PATH.is_file(), (
        "scripts/api_staging_operator_inspect_ssh.py must exist"
    )
    return importlib.import_module("scripts.api_staging_operator_inspect_ssh")


def install_healthy_preflight(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    """Install independent no-network provider observations for one safe run."""
    calls: list[str] = []

    def github() -> None:
        calls.append("github")

    def railway() -> None:
        calls.append("railway")

    def preflight() -> dict[str, str]:
        calls.append("preflight")
        return dict(PUBLIC_IDENTITY)

    def receipt(identity: dict[str, str]) -> None:
        assert identity == PUBLIC_IDENTITY
        calls.append("receipt")

    def instance(identity: dict[str, str]) -> str:
        assert identity == PUBLIC_IDENTITY
        calls.append("instance")
        return INSTANCE_ID

    monkeypatch.setattr(runner, "_github_identity", github)
    monkeypatch.setattr(runner, "_railway_identity", railway)
    monkeypatch.setattr(runner, "_preflight", preflight)
    monkeypatch.setattr(runner, "_approved_receipt", receipt)
    monkeypatch.setattr(runner, "_active_instance", instance)
    return calls


def assert_public_result(
    result: dict[str, object], *, code: str, phase: str, verified: bool
) -> None:
    """Keep the durable runner record constrained to the approved public schema."""
    assert set(result) == {
        "result",
        "phase",
        "identity",
        "target_verified",
        "window_utc",
    }
    assert result["result"] == code
    assert result["phase"] == phase
    assert result["target_verified"] is verified
    assert result["identity"] in (PUBLIC_IDENTITY, None)
    window = result["window_utc"]
    assert isinstance(window, list)
    typed_window = cast(list[object], window)
    assert len(typed_window) == 2
    assert all(
        isinstance(value, str) and value.endswith(("+00:00", "Z"))
        for value in typed_window
    )
    rendered = json.dumps(result, sort_keys=True)
    assert "private" not in rendered
    assert INSTANCE_ID not in rendered


def test_run_executes_exactly_once_after_fresh_target_join(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2/A3: the sole SSH execution follows an unchanged target observation."""
    calls = install_healthy_preflight(runner, monkeypatch)
    executions: list[tuple[list[str], str | None]] = []

    def run_command(
        arguments: list[str], *, input: str | None = None, timeout: int = 30
    ) -> subprocess.CompletedProcess[str]:
        del timeout
        executions.append((arguments, input))
        return completed({"result": "PASS", "target_verified": True})

    monkeypatch.setattr(runner, "_run", run_command)

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result, code="PASS", phase="exact_instance_inspector", verified=True
    )
    assert calls[0:3] == ["github", "railway", "preflight"]
    assert calls.index("receipt") < calls.index("instance")
    assert calls.count("preflight") == 2
    assert calls.count("railway") >= 3
    assert len(executions) == 1
    arguments, request_text = executions[0]
    assert arguments[:2] == ["railway", "ssh"]
    assert "--deployment-instance" in arguments
    assert arguments[arguments.index("--deployment-instance") + 1] == INSTANCE_ID
    assert "-I" in arguments
    assert "-c" in arguments
    assert isinstance(request_text, str)
    request = json.loads(request_text)
    assert request == {
        "source": SOURCE_PATH.read_text(encoding="utf-8"),
        "source_sha256": hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        "identity": PUBLIC_IDENTITY,
    }


def test_run_refuses_to_execute_if_repeat_preflight_changes_target(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2: deployment drift after the join invalidates the selected instance."""
    calls = install_healthy_preflight(runner, monkeypatch)
    observations = iter(
        (
            dict(PUBLIC_IDENTITY),
            {
                **PUBLIC_IDENTITY,
                "deployment_id": "33333333-3333-4333-8333-333333333333",
            },
        )
    )
    executions: list[object] = []
    monkeypatch.setattr(runner, "_preflight", lambda: next(observations))

    def unexpected_execution(*_args: object, **_kwargs: object) -> None:
        executions.append(1)

    monkeypatch.setattr(runner, "_run", unexpected_execution)

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result, code="FAIL_TARGET_CHANGED", phase="repeat_preflight", verified=False
    )
    assert result["identity"] == PUBLIC_IDENTITY
    assert executions == []
    assert calls[0:2] == ["github", "railway"]
    assert calls.count("receipt") == 1
    assert calls.count("instance") == 1
    assert calls.count("railway") >= 2


@pytest.mark.parametrize(
    ("helper", "code", "phase"),
    (
        ("_github_identity", "FAIL_IDENTITY", "github_identity"),
        ("_railway_identity", "FAIL_IDENTITY", "railway_identity"),
        ("_preflight", "FAIL_PREFLIGHT", "public_preflight"),
        ("_approved_receipt", "FAIL_APPROVED_RECEIPT", "approved_receipt"),
        ("_active_instance", "FAIL_INSTANCE", "running_instance"),
    ),
)
def test_run_stops_before_ssh_when_an_upstream_guard_fails(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    helper: str,
    code: str,
    phase: str,
) -> None:
    """A2: every external precondition is independently fail-closed."""
    install_healthy_preflight(runner, monkeypatch)
    executions: list[object] = []

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise ValueError("private provider diagnostic")

    def unexpected_execution(*_args: object, **_kwargs: object) -> None:
        executions.append(1)

    monkeypatch.setattr(runner, helper, unavailable)
    monkeypatch.setattr(runner, "_run", unexpected_execution)

    result = cast(dict[str, object], runner.run())

    assert_public_result(result, code=code, phase=phase, verified=False)
    assert executions == []
    assert "private provider diagnostic" not in json.dumps(result)


@pytest.mark.parametrize(
    ("observation", "expected"),
    (
        (completed("private transport diagnostic", returncode=1), "FAIL_TRANSPORT"),
        (
            completed('{"result":"PASS","target_verified":true}\nnoise'),
            "FAIL_OUTPUT_CONTRACT",
        ),
        (
            completed(
                {"result": "PASS", "target_verified": True}, stderr="private stderr"
            ),
            "FAIL_OUTPUT_CONTRACT",
        ),
        (
            completed({"result": "FAIL_TARGET_IDENTITY", "target_verified": False}),
            "FAIL_TARGET_IDENTITY",
        ),
        (
            completed({"result": "UNKNOWN", "target_verified": True}),
            "FAIL_OUTPUT_CONTRACT",
        ),
    ),
)
def test_run_rejects_unsanitized_or_invalid_remote_observations(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    observation: subprocess.CompletedProcess[str],
    expected: str,
) -> None:
    """A4: raw remote output is never interpreted or copied into evidence."""
    install_healthy_preflight(runner, monkeypatch)

    def observe(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return observation

    monkeypatch.setattr(runner, "_run", observe)

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result, code=expected, phase="exact_instance_inspector", verified=False
    )
    assert "transport diagnostic" not in json.dumps(result)


def test_run_relays_a_sanitized_denied_inspector_status(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A4/A5: a genuine role failure remains evidence rather than transport noise."""
    install_healthy_preflight(runner, monkeypatch)

    def denied(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed(
            {"result": "FAIL_MANAGED_OPERATOR_PERMISSION", "target_verified": True}
        )

    monkeypatch.setattr(
        runner,
        "_run",
        denied,
    )

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result,
        code="FAIL_MANAGED_OPERATOR_PERMISSION",
        phase="exact_instance_inspector",
        verified=True,
    )


@pytest.mark.parametrize(
    "notice",
    (
        "Using SSH key from file /synthetic/key-path: synthetic-key-name\n",
        "Using SSH key from agent: synthetic-key-name\n",
    ),
)
def test_run_accepts_exactly_one_documented_railway_key_notice(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, notice: str
) -> None:
    """A4: a known Railway CLI key-selection announcement is not remote evidence."""
    install_healthy_preflight(runner, monkeypatch)

    def observed(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed({"result": "PASS", "target_verified": True}, stderr=notice)

    monkeypatch.setattr(runner, "_run", observed)

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result, code="PASS", phase="exact_instance_inspector", verified=True
    )
    assert notice not in json.dumps(result)


@pytest.mark.parametrize(
    "stderr",
    (
        "unknown SSH diagnostic\n",
        "Using SSH key from file /synthetic/key-path: synthetic-key-name\nextra\n",
        "Using SSH key from file /synthetic/key-path: synthetic-key-name\n\n",
    ),
)
def test_run_rejects_unknown_or_extended_stderr_even_when_output_is_valid(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch, stderr: str
) -> None:
    """A4: the compatibility exception cannot become an arbitrary stderr channel."""
    install_healthy_preflight(runner, monkeypatch)

    def observed(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed({"result": "PASS", "target_verified": True}, stderr=stderr)

    monkeypatch.setattr(runner, "_run", observed)

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result,
        code="FAIL_OUTPUT_CONTRACT",
        phase="exact_instance_inspector",
        verified=False,
    )
    assert stderr not in json.dumps(result)


def test_run_rejects_nonzero_ssh_even_with_documented_key_notice(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A4: a normal setup notice never converts a failed SSH command into success."""
    install_healthy_preflight(runner, monkeypatch)
    notice = "Using SSH key from file /synthetic/key-path: synthetic-key-name\n"

    def failed(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed(
            {"result": "PASS", "target_verified": True},
            returncode=1,
            stderr=notice,
        )

    monkeypatch.setattr(runner, "_run", failed)

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result,
        code="FAIL_TRANSPORT",
        phase="exact_instance_inspector",
        verified=False,
    )
    assert notice not in json.dumps(result)


def test_run_relays_valid_role_failure_with_documented_key_notice(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A4/A5: the known client notice cannot erase a valid role evidence result."""
    install_healthy_preflight(runner, monkeypatch)
    notice = "Using SSH key from agent: synthetic-key-name\n"

    def denied(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return completed(
            {"result": "FAIL_LIMITED_OPERATOR_PERMISSION", "target_verified": True},
            stderr=notice,
        )

    monkeypatch.setattr(runner, "_run", denied)

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result,
        code="FAIL_LIMITED_OPERATOR_PERMISSION",
        phase="exact_instance_inspector",
        verified=True,
    )
    assert notice not in json.dumps(result)


def test_run_converts_ssh_timeout_without_retrying(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2/A4: an interrupted transport yields one fixed result and no retry."""
    install_healthy_preflight(runner, monkeypatch)
    attempts = 0

    def timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal attempts
        attempts += 1
        raise subprocess.TimeoutExpired("railway ssh", 30, output="private timeout")

    monkeypatch.setattr(runner, "_run", timeout)

    result = cast(dict[str, object], runner.run())

    assert_public_result(
        result, code="FAIL_TIMEOUT", phase="exact_instance_inspector", verified=False
    )
    assert attempts == 1
    assert "private timeout" not in json.dumps(result)


def test_main_returns_nonzero_for_every_fail_closed_result(
    runner: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A4: the durable JSON receipt and process status must agree about failure."""
    receipt: dict[str, object] = {
        "result": "PASS",
        "phase": "exact_instance_inspector",
        "identity": PUBLIC_IDENTITY,
        "target_verified": True,
        "window_utc": ["2026-09-23T00:00:00Z", "2026-09-23T00:00:01Z"],
    }

    def fixed_run(result: dict[str, object]) -> Callable[[], dict[str, object]]:
        def render() -> dict[str, object]:
            return result

        return render

    for status in {"PASS", *runner._RUNNER_FAILURES}:
        result = {**receipt, "result": status}
        monkeypatch.setattr(runner, "run", fixed_run(result))

        assert runner.main() == (0 if status == "PASS" else 1)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert json.loads(captured.out) == result


def isolated_bootstrap(
    runner: ModuleType, request: dict[str, object]
) -> subprocess.CompletedProcess[str]:
    """Execute the real remote bootstrap locally in Python isolated mode."""
    return subprocess.run(
        [sys.executable, "-I", "-c", runner._BOOTSTRAP],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )


def bootstrap_request(source: str) -> dict[str, object]:
    """Construct the sole bootstrap request containing reviewed checkout source."""
    return {
        "source": source,
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "identity": PUBLIC_IDENTITY,
    }


def test_isolated_bootstrap_uses_fixed_module_path_and_exact_public_arguments(
    runner: ModuleType,
) -> None:
    """A1/A3: streamed code starts independently of cwd under a deterministic name."""
    source = f"""\
import sys
import types
if __file__ != "/app/api_staging_operator_inspect.py":
    raise RuntimeError("private module location")
if "/app" not in sys.path:
    raise RuntimeError("private import path")
if __name__ == "__main__":
    raise RuntimeError("private main invocation")
events = []
class Cursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, statement): events.append(statement)
class Connection:
    def cursor(self): return Cursor()
class Atomic:
    def __enter__(self): events.append("atomic")
    def __exit__(self, *args): return False
django = types.ModuleType("django")
django.setup = lambda: events.append("setup")
database = types.ModuleType("django.db")
database.connection = Connection()
database.transaction = types.SimpleNamespace(atomic=lambda: Atomic())
django.db = database
sys.modules["django"] = django
sys.modules["django.db"] = database
STATUS_CODES = {{"PASS", "FAIL_EXECUTION"}}
def _valid_expected_identity(source_sha, deployment_id):
    return source_sha == {SOURCE_SHA!r} and deployment_id == {DEPLOYMENT_ID!r}
def _target_identity_matches(source_sha, deployment_id):
    events.append("target")
    return source_sha == {SOURCE_SHA!r} and deployment_id == {DEPLOYMENT_ID!r}
def _bootstrap():
    import django
    django.setup()
def _inspect_orm_preconditions():
    if events != ["target", "setup", "atomic", "SET TRANSACTION READ ONLY"]:
        return "FAIL_EXECUTION"
    return "PASS"
"""

    result = isolated_bootstrap(runner, bootstrap_request(source))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"result": "PASS", "target_verified": True}


def test_isolated_bootstrap_rejects_target_before_django_or_orm_work(
    runner: ModuleType,
) -> None:
    """A3: an exact-instance identity mismatch prevents all ORM inspection."""
    source = """\
def _valid_expected_identity(source_sha, deployment_id):
    return True
def _target_identity_matches(source_sha, deployment_id):
    return False
def _bootstrap():
    raise RuntimeError("private django work")
def _inspect_orm_preconditions():
    raise RuntimeError("private orm work")
"""

    result = isolated_bootstrap(runner, bootstrap_request(source))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "result": "FAIL_TARGET_IDENTITY",
        "target_verified": False,
    }


def test_isolated_bootstrap_captures_inspector_noise_and_does_not_leak_it(
    runner: ModuleType,
) -> None:
    """A4: the remote process never relays inspector stdout, stderr, or exceptions."""
    secret = "private-operator-and-database-detail"
    source = f"""\
import sys
print({secret!r})
print({secret!r}, file=sys.stderr)
raise RuntimeError({secret!r})
"""

    result = isolated_bootstrap(runner, bootstrap_request(source))

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "result": "FAIL_BOOTSTRAP",
        "target_verified": False,
    }
    assert secret not in result.stdout
    assert secret not in result.stderr


def test_isolated_bootstrap_rejects_tampered_source_before_execution(
    runner: ModuleType,
) -> None:
    """A3/A4: a source checksum mismatch cannot execute a second or substituted script."""
    request = bootstrap_request("print('PASS')\n")
    request["source_sha256"] = "0" * 64

    result = isolated_bootstrap(runner, request)

    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "result": "FAIL_BOOTSTRAP",
        "target_verified": False,
    }
