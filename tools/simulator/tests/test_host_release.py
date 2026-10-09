"""#228 U3: archive handoff and verified host runtime; only Docker/uv are faked."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tailtag_simulator.host_release import install_runtime, load_release, main

from tailtag_simulator.provenance import SourceRejected

IMAGE = "sha256:" + "d" * 64
SHA = "b" * 40
ARCHIVE = b"literal-docker-archive-for-external-boundary"
LOCK = b"version = 1\nrevision = 3\n"
LOCK_HASH = hashlib.sha256(LOCK).hexdigest()
REJECTED = (ValueError, OSError, RuntimeError, SourceRejected)


def metadata() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "simulator_sha": SHA,
        "dependency_lock_sha256": LOCK_HASH,
        "image_id": IMAGE,
        "platform": "linux/amd64",
        "archive_sha256": hashlib.sha256(ARCHIVE).hexdigest(),
    }


def source() -> dict[str, Any]:
    return {
        "simulator_sha": {"value": SHA, "reason": None},
        "provenance": "clean",
        "reason": None,
        "runtime": {
            "python": {"value": "3.13.11", "reason": None},
            "httpx": {"value": "0.28.1", "reason": None},
            "dependency_lock_sha256": {"value": LOCK_HASH, "reason": None},
        },
    }


def packaged(root: Path) -> Path:
    """Literal self-verifying package bytes, checked by the real source verifier."""
    files = {
        "tailtag_simulator/__init__.py": b"",
        "tailtag_simulator/host_runner.py": b"HOST_RUNTIME = 'verified'\n",
        "pyproject.toml": b'[project]\nname="tailtag-simulator"\nversion="0.1.0"\nrequires-python=">=3.13,<3.14"\ndependencies=["httpx>=0.28,<0.29"]\n',
        "uv.lock": LOCK,
        "services/api/simulation_fixtures/images/valid.png": b"fixed image fixture bytes",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "source.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "simulator_sha": SHA,
                "dependency_lock_sha256": LOCK_HASH,
                "manifest": {
                    name: hashlib.sha256(content).hexdigest()
                    for name, content in files.items()
                },
            }
        )
    )
    return root


class DockerBoundary:
    """External CLI substitute with complete image/source outputs and real copies."""

    def __init__(self, package: Path) -> None:
        self.package = package
        self.calls: list[list[str]] = []
        self.inspection: dict[str, Any] = {
            "Id": IMAGE,
            "RepoTags": [],
            "RepoDigests": [],
            "Parent": "",
            "Comment": "buildkit.dockerfile.v0",
            "Created": "2026-10-08T00:00:00Z",
            "DockerVersion": "",
            "Author": "",
            "Config": {
                "Hostname": "",
                "Domainname": "",
                "User": "10001:10001",
                "AttachStdin": False,
                "AttachStdout": False,
                "AttachStderr": False,
                "Tty": False,
                "OpenStdin": False,
                "StdinOnce": False,
                "Env": ["PATH=/usr/local/bin:/usr/bin:/bin"],
                "Cmd": ["python", "-m", "tailtag_simulator"],
                "Image": "",
                "Volumes": None,
                "WorkingDir": "/app",
                "Entrypoint": None,
                "OnBuild": None,
                "Labels": {},
            },
            "Architecture": "amd64",
            "Os": "linux",
            "Size": 100000000,
            "RootFS": {"Type": "layers", "Layers": ["sha256:" + "a" * 64]},
            "Metadata": {"LastTagTime": "0001-01-01T00:00:00Z"},
        }
        self.packaged_source = source()
        self.copy_tamper = False

    def run(
        self, arguments: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[Any]:
        assert not kwargs.get("shell", False)
        self.calls.append(list(arguments))
        output = ""
        if arguments[0] == "docker":
            if arguments[1] == "inspect" or arguments[1:3] == ["image", "inspect"]:
                assert IMAGE in arguments
                output = json.dumps([self.inspection])
            elif "load" in arguments:
                output = f"Loaded image ID: {IMAGE}\n"
            elif "save" in arguments:
                assert IMAGE in arguments
                flag = "--output" if "--output" in arguments else "-o"
                Path(arguments[arguments.index(flag) + 1]).write_bytes(ARCHIVE)
            elif arguments[1] == "run":
                assert IMAGE in arguments and "--rm" in arguments
                assert (
                    "tailtag_simulator.provenance" in arguments
                    and "inspect" in arguments
                )
                output = json.dumps(self.packaged_source)
            elif arguments[1] == "create":
                assert IMAGE in arguments
                output = "tailtag-228-runtime-copy\n"
            elif arguments[1] == "cp":
                assert arguments[-2].endswith(":/app/.") or arguments[-2].endswith(
                    ":/app"
                )
                destination = Path(arguments[-1])
                shutil.copytree(self.package, destination, dirs_exist_ok=True)
                if self.copy_tamper:
                    (destination / "tailtag_simulator/host_runner.py").write_text(
                        "SENTINEL-tampered-copy"
                    )
            elif arguments[1] == "rm":
                assert "tailtag-228-runtime-copy" in arguments
            else:
                raise AssertionError(f"Unexpected Docker operation: {arguments[1:]}")
        elif Path(arguments[0]).name == "uv":
            assert "sync" in arguments
            assert "--locked" in arguments and "--no-dev" in arguments
            assert "3.13.11" in arguments
            assert Path(arguments[0]).parent.name == "tools"
        else:
            raise AssertionError("Unexpected external process")
        return subprocess.CompletedProcess(
            arguments,
            0,
            stdout=output if kwargs.get("text") else output.encode(),
            stderr="" if kwargs.get("text") else b"",
        )


@pytest.fixture
def release_files(tmp_path: Path) -> tuple[Path, Path]:
    archive, record = tmp_path / "release.tar", tmp_path / "release.json"
    archive.write_bytes(ARCHIVE)
    record.write_text(json.dumps(metadata()))
    return archive, record


@pytest.fixture
def docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DockerBoundary:
    boundary = DockerBoundary(packaged(tmp_path / "packaged"))
    monkeypatch.setattr(subprocess, "run", boundary.run)
    return boundary


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("schema_version", True),
        ("image_id", "tailtag:latest"),
        ("platform", "linux/arm64"),
        ("archive_sha256", "invalid"),
        ("extra", "SENTINEL-private-metadata"),
    ],
)
def test_untrusted_release_metadata_is_refused_before_docker(
    release_files: tuple[Path, Path],
    docker: DockerBoundary,
    capsys: pytest.CaptureFixture[str],
    key: str,
    value: object,
) -> None:
    archive, record = release_files
    altered = metadata()
    altered[key] = value
    record.write_text(json.dumps(altered))
    assert main(["load", "--archive", str(archive), "--metadata", str(record)]) != 0
    assert docker.calls == []
    output = capsys.readouterr()
    assert "SENTINEL" not in output.out + output.err


def test_changed_archive_is_refused_before_docker_load(
    release_files: tuple[Path, Path], docker: DockerBoundary
) -> None:
    archive, record = release_files
    archive.write_bytes(ARCHIVE + b"tampered")
    assert main(["load", "--archive", str(archive), "--metadata", str(record)]) != 0
    assert docker.calls == []


@pytest.mark.parametrize("fault", ["id", "platform", "source", "lock", "unverified"])
def test_loaded_image_must_match_id_platform_and_verified_packaged_source(
    release_files: tuple[Path, Path], docker: DockerBoundary, fault: str
) -> None:
    archive, record = release_files
    if fault == "id":
        docker.inspection["Id"] = "sha256:" + "e" * 64
    elif fault == "platform":
        docker.inspection["Architecture"] = "arm64"
    elif fault == "source":
        docker.packaged_source["simulator_sha"]["value"] = "e" * 40
    elif fault == "lock":
        docker.packaged_source["runtime"]["dependency_lock_sha256"]["value"] = "e" * 64
    else:
        docker.packaged_source["provenance"] = "unknown"
        docker.packaged_source["reason"] = "not_observed"
    with pytest.raises(REJECTED):
        load_release(archive, record)
    # No result can grant the supervisor an image to execute; no broad cleanup.
    assert not any("rmi" in call or "prune" in call for call in docker.calls)


def test_export_load_uses_immutable_id_and_keeps_previous_release_and_reports(
    tmp_path: Path, docker: DockerBoundary
) -> None:
    old = tmp_path / "previous-release.json"
    old.write_text("previous approved release")
    report = tmp_path / "previous-report.json"
    report.write_text("original report bytes")
    archive, record = tmp_path / "export.tar", tmp_path / "export.json"
    assert (
        main(
            [
                "export",
                "--image",
                IMAGE,
                "--archive",
                str(archive),
                "--metadata",
                str(record),
            ]
        )
        == 0
    )
    assert archive.read_bytes() == ARCHIVE
    assert json.loads(record.read_text()) == metadata()
    assert load_release(archive, record) == IMAGE
    assert (
        old.read_text() == "previous approved release"
        and report.read_text() == "original report bytes"
    )
    assert not any("rmi" in call or "prune" in call for call in docker.calls)
    # The exact immutable image is what each Docker inspection/source run saw.
    assert any("load" in call for call in docker.calls)


@pytest.mark.parametrize("fault", ["none", "copied_bytes", "existing_bytes"])
def test_host_runtime_is_verified_before_locked_python313_sync_or_execution(
    tmp_path: Path, release_files: tuple[Path, Path], docker: DockerBoundary, fault: str
) -> None:
    archive, record = release_files
    root = tmp_path / "host"
    root.mkdir(mode=0o700)
    tools = root / "tools"
    tools.mkdir(mode=0o700)
    (tools / "uv").write_text("pinned uv boundary")
    (tools / "uv").chmod(0o700)
    if fault == "copied_bytes":
        docker.copy_tamper = True
        with pytest.raises(REJECTED):
            install_runtime(archive, record, root)
        assert not any(Path(call[0]).name == "uv" for call in docker.calls)
        return
    runtime = install_runtime(archive, record, root)
    assert runtime.is_relative_to(root) and runtime.is_dir()
    assert (
        runtime / "tailtag_simulator/host_runner.py"
    ).read_bytes() == b"HOST_RUNTIME = 'verified'\n"
    assert (runtime / "uv.lock").read_bytes() == LOCK
    assert any(Path(call[0]).name == "uv" for call in docker.calls)
    if fault == "existing_bytes":
        (runtime / "tailtag_simulator/host_runner.py").write_text(
            "SENTINEL-existing-tamper"
        )
        before = len(docker.calls)
        with pytest.raises(REJECTED):
            install_runtime(archive, record, root)
        assert not any(Path(call[0]).name == "uv" for call in docker.calls[before:])
