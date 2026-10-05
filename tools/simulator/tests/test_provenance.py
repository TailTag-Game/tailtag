"""#224 real Git/build/runtime byte attribution (AC14, AC4 shallow history).

Git and files are real. Only Docker's external launch is substituted; no Docker
service starts. Disposable commits verify Finn author and committer identities.
"""

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path
from typing import Any

import pytest
from report_support import DATA, commit, git, literal_report, repository

from tailtag_simulator.provenance import SourceRejected, load_source, main


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    scenario = literal_report()["scenario"]
    descriptor = {
        **scenario["descriptor"],
        "descriptor_digest": scenario["descriptor_digest"],
    }
    return repository(
        tmp_path / "source",
        {
            "tools/simulator/tailtag_simulator/__init__.py": "",
            "tools/simulator/tailtag_simulator/__main__.py": "print('packaged simulation boundary')\n",
            "tools/simulator/tailtag_simulator/smoke.py": "WORKLOAD = 'fixed'\n",
            "tools/simulator/tailtag_simulator/scenarios/smoke-v1.json": json.dumps(
                descriptor
            ),
            "tools/simulator/pyproject.toml": '[project]\nname="tailtag-simulator"\nversion="0.1.0"\nrequires-python=">=3.13,<3.14"\ndependencies=["httpx>=0.28,<0.29"]\n',
            "tools/simulator/uv.lock": "version = 1\nrevision = 3\n",
            "tools/simulator/Dockerfile": "FROM scratch\nCOPY . /app\n",
            "services/api/simulation_fixtures/images/valid-a.png": b"committed-workload-bytes",
            "Makefile": "sim-image:\n\tdocker build tools/simulator\n",
            "scripts/api_sim_pool_ssh.py": "# committed host launcher\n",
            "scripts/api_sim_fixture_ssh.py": "# committed host launcher\n",
            "scripts/api_sim_inspect_ssh.py": "# committed host launcher\n",
            "scripts/api_staging_reset_ssh.py": "# committed shared host launcher\n",
            "scripts/api_staging_preflight.py": "# committed host target preflight\n",
            "services/api/pyproject.toml": "# committed host dependency declaration\n",
            "services/api/uv.lock": "# committed host dependency lock\n",
            "README.md": "Human documentation\n",
            "tools/simulator/tests/test_fixture.py": "def test_fixture(): pass\n",
            ".gitignore": "__pycache__/\nreports/\nignored_input.py\n",
        },
    )


def test_clean_git_source_reports_full_sha_and_locked_dependency_identity(
    source_repo: Path,
) -> None:
    source = load_source(source_repo)
    assert source["simulator_sha"] == {
        "value": git(source_repo, "rev-parse", "HEAD"),
        "reason": None,
    }
    assert source["provenance"] == "clean" and source["reason"] is None
    runtime: Any = source["runtime"]
    assert runtime["python"] == {"value": platform.python_version(), "reason": None}
    assert runtime["httpx"] == {
        "value": importlib.metadata.version("httpx"),
        "reason": None,
    }
    expected_lock = hashlib.sha256(
        (source_repo / "tools/simulator/uv.lock").read_bytes()
    ).hexdigest()
    assert runtime["dependency_lock_sha256"] == {"value": expected_lock, "reason": None}


@pytest.mark.parametrize(
    "change",
    [
        "unstaged",
        "staged",
        "dependency",
        "fixture_deleted",
        "wiring",
        "untracked",
        "ignored",
        "symlink",
        "host_launcher",
        "shared_preflight",
        "host_dependency",
        "missing_launcher",
        "untracked_init",
        "namespace_module",
        "namespace_bytecode",
        "package_bytecode",
        "host_sourceless_package",
        "host_extension",
        "host_dangling_package",
        "namespace_extension",
        "initializer_extension",
    ],
)
def test_changed_or_untracked_runtime_inputs_cannot_claim_a_clean_git_identity(
    source_repo: Path, tmp_path: Path, change: str
) -> None:
    package = source_repo / "tools/simulator/tailtag_simulator"
    if change in {"unstaged", "staged"}:
        (package / "smoke.py").write_text("SENTINEL_changed_workload = True\n")
        if change == "staged":
            git(source_repo, "add", "tools/simulator/tailtag_simulator/smoke.py")
    elif change == "dependency":
        (source_repo / "tools/simulator/uv.lock").write_text(
            "SENTINEL_changed_dependency"
        )
    elif change == "fixture_deleted":
        (source_repo / "services/api/simulation_fixtures/images/valid-a.png").unlink()
    elif change == "wiring":
        (source_repo / "Makefile").write_text("SENTINEL_changed_build_wiring")
    elif change in {"untracked", "ignored"}:
        (
            package
            / ("ignored_input.py" if change == "ignored" else "extra_workload.py")
        ).write_text("SENTINEL = 1\n")
    elif change in {"host_launcher", "shared_preflight", "host_dependency"}:
        relative = {
            "host_launcher": "scripts/api_sim_pool_ssh.py",
            "shared_preflight": "scripts/api_staging_preflight.py",
            "host_dependency": "services/api/uv.lock",
        }[change]
        (source_repo / relative).write_text("SENTINEL_changed_host_input")
    elif change == "missing_launcher":
        (source_repo / "scripts/api_sim_fixture_ssh.py").unlink()
    elif change == "untracked_init":
        (source_repo / "scripts/__init__.py").write_text("SENTINEL = 1\n")
    elif change in {"namespace_module", "namespace_bytecode", "package_bytecode"}:
        relative = {
            "namespace_module": "scripts.py",
            "namespace_bytecode": "scripts.pyc",
            "package_bytecode": "scripts/__init__.pyc",
        }[change]
        (source_repo / relative).write_bytes(b"SENTINEL_namespace_loader_input")
    elif change == "host_sourceless_package":
        shadow = source_repo / "scripts/api_staging_preflight"
        shadow.mkdir()
        (shadow / "__init__.pyc").write_bytes(b"SENTINEL_package_loader_input")
    elif change == "host_extension":
        shadow = source_repo / f"scripts/api_sim_fixture_ssh{EXTENSION_SUFFIXES[0]}"
        shadow.write_bytes(b"SENTINEL_native_loader_input")
    elif change == "host_dangling_package":
        (source_repo / "scripts/api_staging_reset_ssh").symlink_to(
            tmp_path / "SENTINEL-missing-package", target_is_directory=True
        )
    elif change in {"namespace_extension", "initializer_extension"}:
        stem = "scripts" if change == "namespace_extension" else "scripts/__init__"
        (source_repo / f"{stem}{EXTENSION_SUFFIXES[0]}").write_bytes(
            b"SENTINEL_namespace_native_loader_input"
        )
    else:
        secret = tmp_path / "SENTINEL-private-source"
        secret.write_text("private bytes")
        (package / "smoke.py").unlink()
        (package / "smoke.py").symlink_to(secret)
    with pytest.raises(SourceRejected) as failure:
        load_source(source_repo)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def test_docs_tests_caches_and_output_changes_do_not_dirty_execution_inputs(
    source_repo: Path,
) -> None:
    (source_repo / "README.md").write_text("Edited documentation")
    (source_repo / "tools/simulator/tests/test_fixture.py").write_text("Edited tests")
    (source_repo / "scripts/api_sim_inspect_ssh.md").write_text(
        "Host launcher documentation is not an import loader."
    )
    cache = source_repo / "tools/simulator/tailtag_simulator/__pycache__"
    cache.mkdir()
    (cache / "smoke.cpython-313.pyc").write_bytes(b"cache")
    reports = source_repo / "tools/simulator/reports"
    reports.mkdir()
    (reports / "run.json").write_text("output")
    # Finder metadata is neither an importable module nor a supported fixture
    # image input; its ignored presence must not relabel otherwise clean source.
    for directory in (
        source_repo / "tools/simulator/tailtag_simulator",
        source_repo / "services/api/simulation_fixtures/images",
    ):
        (directory / ".DS_Store").write_bytes(b"Finder metadata")
    assert load_source(source_repo)["provenance"] == "clean"


@pytest.mark.parametrize("missing", ["no_git", "unborn"])
def test_missing_source_identity_is_rejected_with_sanitized_failure(
    tmp_path: Path, missing: str
) -> None:
    root = tmp_path / "SENTINEL-unknown-source"
    root.mkdir()
    if missing == "unborn":
        git(root, "init", "--initial-branch=main")
    with pytest.raises(SourceRejected) as failure:
        load_source(root)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def docker_recorder(
    monkeypatch: pytest.MonkeyPatch, captured: Path, *, fail: bool = False
) -> list[Path]:
    """Keep Git subprocesses real; capture only Docker's temporary context."""
    original: Callable[..., Any] = subprocess.run
    contexts: list[Path] = []

    def run(arguments: list[str], **kwargs: Any) -> Any:
        if arguments[0] != "docker":
            return original(arguments, **kwargs)
        assert arguments[1] == "build"
        assert kwargs.get("shell", False) is False
        assert (
            "-t" in arguments
            and arguments[arguments.index("-t") + 1] == "tailtag-test:224"
        )
        context = Path(arguments[-1])
        contexts.append(context)
        shutil.copytree(context, captured)
        if fail:
            raise subprocess.CalledProcessError(
                1, arguments, stderr="SENTINEL-private-docker-stderr"
            )
        return subprocess.CompletedProcess[str](arguments, 0)

    monkeypatch.setattr(subprocess, "run", run)
    return contexts


@pytest.mark.parametrize("dirty", [False, True])
def test_build_validates_git_before_docker_and_copies_a_self_verifying_runtime_context(
    source_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    dirty: bool,
) -> None:
    captured = tmp_path / "packaged"
    contexts = docker_recorder(monkeypatch, captured)
    if dirty:
        (source_repo / "tools/simulator/tailtag_simulator/smoke.py").write_text("dirty")
    code = main(["build", "--root", str(source_repo), "--tag", "tailtag-test:224"])
    if dirty:
        assert code != 0
        assert contexts == [] and not captured.exists()
        assert "dirty" not in capsys.readouterr().out
        return
    assert code == 0 and len(contexts) == 1
    assert not contexts[0].exists()  # Task-created context cleanup is observable.
    metadata = json.loads((captured / "source.json").read_text())
    assert metadata["simulator_sha"] == git(source_repo, "rev-parse", "HEAD")
    assert metadata["schema_version"] == 1
    assert metadata["manifest"]
    assert not any(
        name.startswith("scripts/")
        or name in {"services/api/pyproject.toml", "services/api/uv.lock"}
        for name in metadata["manifest"]
    )
    for name, digest in metadata["manifest"].items():
        relative = Path(name)
        assert not relative.is_absolute() and ".." not in relative.parts
        assert hashlib.sha256((captured / relative).read_bytes()).hexdigest() == digest
    assert (captured / "tailtag_simulator/smoke.py").read_bytes() == (
        source_repo / "tools/simulator/tailtag_simulator/smoke.py"
    ).read_bytes()
    monkeypatch.setenv("TAILTAG_SIMULATOR_SOURCE_SHA", "e" * 40)
    packaged = load_source(captured)
    assert packaged["simulator_sha"] == {
        "value": metadata["simulator_sha"],
        "reason": None,
    }
    assert packaged["provenance"] == "clean"


@pytest.mark.parametrize("tamper", ["package", "lock", "manifest_path"])
def test_packaged_provenance_rejects_changed_bytes_and_escaping_manifests(
    source_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    captured = tmp_path / "packaged"
    docker_recorder(monkeypatch, captured)
    assert main(["build", "--root", str(source_repo), "--tag", "tailtag-test:224"]) == 0
    if tamper == "package":
        (captured / "tailtag_simulator/smoke.py").write_text(
            "SENTINEL_dirty_packaged_code"
        )
    elif tamper == "lock":
        (captured / "uv.lock").write_text("SENTINEL_dirty_lock")
    else:
        metadata_path = captured / "source.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["manifest"]["../SENTINEL-secret"] = "0" * 64
        metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(SourceRejected) as failure:
        load_source(captured)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def test_failed_docker_build_cleans_its_context_and_sanitizes_stderr(
    source_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    contexts = docker_recorder(monkeypatch, tmp_path / "packaged", fail=True)
    assert main(["build", "--root", str(source_repo), "--tag", "tailtag-test:224"]) != 0
    assert len(contexts) == 1 and not contexts[0].exists()
    output = capsys.readouterr()
    assert "SENTINEL" not in output.out + output.err


def test_packaged_layout_resolves_source_and_runs_offline_cli_without_host_checkout(
    source_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    simulator = Path(__file__).parents[1]
    shutil.copytree(
        simulator / "tailtag_simulator",
        source_repo / "tools/simulator/tailtag_simulator",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("pyproject.toml", "uv.lock", "Dockerfile"):
        shutil.copyfile(simulator / name, source_repo / "tools/simulator" / name)
    commit(source_repo, "Actual simulator package layout fixture")
    captured = tmp_path / "packaged"
    docker_recorder(monkeypatch, captured)
    assert main(["build", "--root", str(source_repo), "--tag", "tailtag-test:224"]) == 0
    # A fresh process imports the real packaged code; package/root discovery is
    # exercised without a host checkout, a Docker daemon, provider or Git process.
    code = (
        "import socket, subprocess\n"
        "def trip(*args, **kwargs):\n"
        "    raise AssertionError('packaged offline command touched external boundary')\n"
        "socket.socket.connect = trip\n"
        "subprocess.Popen = trip\n"
        "from tailtag_simulator.provenance import load_source\n"
        f"assert load_source()['simulator_sha']['value'] == {git(source_repo, 'rev-parse', 'HEAD')!r}\n"
        "from tailtag_simulator.__main__ import main\n"
        f"raise SystemExit(main(['report', 'validate', {str(DATA)!r}]))\n"
    )
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    outcome = subprocess.run(
        [sys.executable, "-c", code],
        cwd=captured,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert outcome.returncode == 0, outcome.stderr
    assert outcome.stdout == "PASS report\n"
