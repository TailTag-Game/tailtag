"""#228 U3: real host admission, durable recovery evidence and bounded storage."""

import json
import os
import select
import shutil
import socket
import stat
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from convention_support import CONFIG
from test_host_protocol import manifest as launch_manifest
from test_reports_v3 import successful_report

from tailtag_simulator.host_artifacts import admit_run, resolve_recovery
from tailtag_simulator.reports import ReportFailed, validate_report
from tailtag_simulator.traffic_config import resolve_traffic_config

RUN = "55555555-5555-4555-8555-555555555555"
NEXT = "66666666-6666-4666-8666-666666666666"
SENTINEL = b"SENTINEL-outside-owner-root"
REJECTED = (ValueError, OSError, RuntimeError)


def manifest(run_id: str = RUN) -> dict[str, Any]:
    value = launch_manifest()
    value["run_id"] = run_id
    value["seed"] = -42
    value["configuration"] = resolve_traffic_config(CONFIG)
    return value


def receipt(run_id: str = RUN, disposition: str = "released") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "backend_identity": manifest()["backend_identity"],
        "disposition": disposition,
    }


def report_file(directory: Path, supplied: dict[str, Any], scratch: Path) -> Path:
    value = successful_report(scratch)
    value["run_id"] = supplied["run_id"]
    value["source"]["simulator_sha"]["value"] = supplied["release"]["simulator_sha"]
    value["source"]["runtime"]["dependency_lock_sha256"]["value"] = supplied["release"][
        "dependency_lock_sha256"
    ]
    for name in ("starting", "final"):
        value["target"][name]["value"] = supplied["backend_identity"]
    value["safety"]["target"]["identity"] = supplied["backend_identity"]
    value["safety"]["policy"] = supplied["safety"]
    assert validate_report(value) == value
    path = directory / f"{supplied['run_id']}.json"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    return path


def evidence(run_id: str = RUN) -> dict[str, object]:
    return {"schema_version": 1, "run_id": run_id, "status": "completed"}


@pytest.fixture
def owner_root(tmp_path: Path) -> Path:
    root = tmp_path / "owner"
    root.mkdir(mode=0o700)
    return root


@pytest.fixture
def socket_owner_root() -> Iterator[Path]:
    # macOS limits AF_UNIX paths to 104 bytes. Resolve /tmp so owner-path checks
    # still see a canonical root rather than the system's /tmp symlink.
    with TemporaryDirectory(prefix="tt228-a-", dir="/tmp") as directory:
        root = Path(directory).resolve()
        root.chmod(0o700)
        yield root


@pytest.fixture
def admission_child(
    owner_root: Path, tmp_path: Path
) -> Iterator[subprocess.Popen[str]]:
    supplied = tmp_path / "manifest.json"
    supplied.write_text(json.dumps(manifest()))
    # The child is the real competing lock owner. It never starts Docker/SSH.
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from tailtag_simulator.host_artifacts import admit_run\n"
        "with admit_run(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())) as run:\n"
        "    run.stage_log_path.write_text('stage evidence survives crash')\n"
        "    run.stage_log_path.chmod(0o600)\n"
        "    print(str(run.stage_log_path), flush=True)\n"
        "    sys.stdin.readline()\n"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code, str(owner_root), str(supplied)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        yield child
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def test_competing_process_and_crash_hold_require_explicit_manual_recovery(
    owner_root: Path, admission_child: subprocess.Popen[str]
) -> None:
    assert admission_child.stdout is not None
    assert select.select([admission_child.stdout], [], [], 5)[0], (
        "admission child stalled"
    )
    path = Path(admission_child.stdout.readline().strip())
    assert path.is_file(), "child failed to acquire admission"
    external = owner_root.parent / "external-work"
    with pytest.raises(REJECTED), admit_run(owner_root, manifest(NEXT)):
        external.write_bytes(SENTINEL)
    assert not external.exists()
    assert path.read_text() == "stage evidence survives crash"
    assert path.stat().st_mode & 0o777 == 0o600
    admission_child.kill()
    admission_child.wait(timeout=5)
    # The OS has released flock. A durable hold still refuses a new process/run;
    # neither ancient age nor an absent process authorizes automatic recovery.
    with (
        pytest.raises(REJECTED),
        admit_run(owner_root, manifest(NEXT), clock=lambda: 4_000_000_000.0),
    ):
        external.write_bytes(SENTINEL)
    assert not external.exists() and path.read_text() == "stage evidence survives crash"
    base = owner_root / "runs" / RUN
    companion = base / "host.json"
    original_manifest = base / "control" / "manifest.json"
    manifest_bytes = original_manifest.read_bytes()
    report = base / "reports" / f"{RUN}.json"
    assert not companion.exists() and not report.exists()
    # Hard crash preceded companion/report finalization. Exact trusted manual
    # recovery must still settle this hold, without inventing a successful run.
    resolve_recovery(owner_root, RUN, receipt(disposition="no_mutation"))
    assert companion.is_file() and json.loads(companion.read_text())
    assert not report.exists()
    assert original_manifest.read_bytes() == manifest_bytes
    assert path.read_text() == "stage evidence survives crash"
    with pytest.raises(REJECTED), admit_run(owner_root, manifest()):
        pytest.fail("manual recovery reopened the old immutable manifest")
    with admit_run(owner_root, manifest(NEXT)):
        assert (
            not report.exists() and path.read_text() == "stage evidence survives crash"
        )


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "held",
        "run",
        "target",
        "extra",
        "manual_root_symlink",
        "manual_runs_symlink",
        "manual_foreign_manifest",
    ],
)
def test_pass_report_cannot_clear_missing_or_untrusted_recovery_receipt(
    owner_root: Path, tmp_path: Path, fault: str
) -> None:
    supplied = manifest()
    trusted: dict[str, Any] | None = receipt()
    if fault == "missing":
        trusted = None
    elif fault == "held":
        trusted["disposition"] = "held"
    elif fault == "run":
        trusted["run_id"] = NEXT
    elif fault == "target":
        trusted["backend_identity"] = {
            **trusted["backend_identity"],
            "source_sha": "e" * 40,
        }
    elif fault == "extra":
        trusted["unexpected"] = "SENTINEL-private-control"
    else:
        trusted = None
    with admit_run(owner_root, supplied) as run:
        path = report_file(run.report_dir, supplied, tmp_path / "scratch")
        companion = run.companion_path
        if fault in {"held", "run", "target", "extra"}:
            original_bytes = path.read_bytes()
            invalid = json.loads(original_bytes)
            if fault == "held":
                invalid["source"]["simulator_sha"]["value"] = "e" * 40
            elif fault == "run":
                invalid["run_id"] = NEXT
            elif fault == "target":
                foreign = {**supplied["backend_identity"], "source_sha": "e" * 40}
                for name in ("starting", "final"):
                    invalid["target"][name]["value"] = foreign
                invalid["safety"]["target"]["identity"] = foreign
            else:
                invalid["unexpected"] = "SENTINEL-private-report"
            if fault != "extra":
                assert validate_report(invalid) == invalid
            path.write_text(json.dumps(invalid))
            with pytest.raises((*REJECTED, ReportFailed)):
                run.record_completion(evidence())
            assert not companion.exists()
            path.write_bytes(original_bytes)
        # Workload exit writes host evidence without accepting a receipt or
        # clearing recovery authority. Missing receipt exercises this seam alone.
        run.record_completion(evidence())
        assert companion.is_file() and json.loads(companion.read_text())
        assert companion.stat().st_mode & 0o777 == 0o600
        try:
            if fault != "missing":
                run.finalize(evidence(), trusted)
        except REJECTED:
            pass  # A sanitized refusal or durable held completion are both safe.
        assert path.exists()
        companion_bytes = companion.read_bytes() if companion.exists() else None
    with pytest.raises(REJECTED), admit_run(owner_root, manifest(NEXT)):
        pytest.fail("PASS report incorrectly granted fresh host admission")
    # Manual resolution is explicit and bound to the original run and tuple.
    with pytest.raises(REJECTED):
        resolve_recovery(owner_root, RUN, receipt(NEXT))
    if fault.startswith("manual_"):
        base = owner_root / "runs" / RUN
        recovery_root, recovery_receipt = owner_root, receipt()
        original_manifest = base / "control" / "manifest.json"
        outside_runs = tmp_path / "outside-runs"
        if fault == "manual_root_symlink":
            recovery_root = tmp_path / "root-alias"
            recovery_root.symlink_to(owner_root, target_is_directory=True)
        elif fault == "manual_runs_symlink":
            (owner_root / "runs").rename(outside_runs)
            (owner_root / "runs").symlink_to(outside_runs, target_is_directory=True)
        else:
            original_manifest.write_text(json.dumps(manifest(NEXT)))
            recovery_receipt = receipt(NEXT)
        before = {
            p.relative_to(base): p.read_bytes() for p in base.rglob("*") if p.is_file()
        }
        with pytest.raises(REJECTED):
            resolve_recovery(recovery_root, RUN, recovery_receipt)
        assert {
            p.relative_to(base): p.read_bytes() for p in base.rglob("*") if p.is_file()
        } == before
        if fault == "manual_runs_symlink":
            (owner_root / "runs").unlink()
            outside_runs.rename(owner_root / "runs")
        elif fault == "manual_foreign_manifest":
            original_manifest.write_text(json.dumps(manifest()))
    resolve_recovery(owner_root, RUN, receipt())
    if companion_bytes is not None:
        assert companion.read_bytes() == companion_bytes
    with admit_run(owner_root, manifest(NEXT)):
        assert path.is_file()


@pytest.mark.parametrize(
    ("prepared", "fail_root_sync"), [(False, False), (True, False), (False, True)]
)
def test_admission_syncs_full_owner_directory_chain_before_external_authority(
    owner_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    prepared: bool,
    fail_root_sync: bool,
) -> None:
    runs = owner_root / "runs"
    base = runs / RUN
    control = base / "control"
    if prepared:
        for directory in (runs, base, base / "rpc", control):
            directory.mkdir(mode=0o700)
        path = control / "manifest.json"
        path.write_text(json.dumps(manifest()))
        path.chmod(0o600)
    real_fsync = os.fsync
    synced: list[tuple[Path, set[str]]] = []

    def fsync(fd: int) -> None:
        info = os.fstat(fd)
        actual: Path | None = None
        if stat.S_ISDIR(info.st_mode):
            for directory in (owner_root, runs, base, control):
                if directory.exists():
                    candidate = directory.stat()
                    if (candidate.st_dev, candidate.st_ino) == (
                        info.st_dev,
                        info.st_ino,
                    ):
                        actual = directory
                        break
        # Forward every call to the real filesystem. The one fault models an
        # external syscall error, not an internal helper or alleged power loss.
        real_fsync(fd)
        if actual is not None:
            synced.append((actual, {p.name for p in actual.iterdir()}))
            if fail_root_sync and actual == owner_root:
                raise OSError("simulated directory fsync failure")

    monkeypatch.setattr(os, "fsync", fsync)
    if fail_root_sync:
        with pytest.raises(REJECTED), admit_run(owner_root, manifest()):
            pytest.fail("fsync failure granted external authority")
        return
    with admit_run(owner_root, manifest()):
        # Observe inode-backed directory sync only after the child entries exist
        # and before authority is yielded; no exact helper/call count required.
        for directory, children in (
            (owner_root, {"runs"}),
            (runs, {RUN}),
            (base, {"rpc", "control", "reports"}),
            (control, {"manifest.json"}),
        ):
            assert any(
                path == directory and children <= entries for path, entries in synced
            ), f"directory entry not durable before admission: {directory.name}"


@pytest.mark.parametrize("disposition", ["released", "no_mutation"])
def test_acknowledged_recovery_persists_companion_before_releasing_host(
    owner_root: Path, tmp_path: Path, disposition: str
) -> None:
    with admit_run(owner_root, manifest()) as run:
        path = report_file(run.report_dir, manifest(), tmp_path / "scratch")
        run.finalize(evidence(), receipt(disposition=disposition))
        companion = run.companion_path
        assert companion.is_file() and json.loads(companion.read_text())
        assert companion.stat().st_mode & 0o777 == 0o600
        # Finalization does not release the enclosing runtime's host lock.
        with pytest.raises(REJECTED), admit_run(owner_root, manifest(NEXT)):
            pytest.fail("lock released before owning runtime exited")
    with admit_run(owner_root, manifest(NEXT)):
        assert path.is_file() and companion.is_file()


@pytest.mark.parametrize(
    ("age", "log_exists", "report_exists"),
    [
        (604799, True, True),
        (604801, False, True),
        (2591999, False, True),
        (2592001, False, False),
    ],
)
def test_completed_artifacts_expire_by_class_and_persisted_completion_time(
    owner_root: Path, tmp_path: Path, age: int, log_exists: bool, report_exists: bool
) -> None:
    with admit_run(owner_root, manifest(), clock=lambda: 1_800_000_000.0) as run:
        path = report_file(run.report_dir, manifest(), tmp_path / "scratch")
        log = run.stage_log_path
        log.write_text("fixed stage evidence\n")
        log.chmod(0o600)
        companion = run.companion_path
        run.finalize(evidence(), receipt())
    # Misleading filesystem mtimes must not substitute for durable completion.
    for artifact in (path, log, companion):
        os.utime(artifact, (1.0, 1.0))
    with admit_run(owner_root, manifest(NEXT), clock=lambda: 1_800_000_000.0 + age):
        assert log.exists() is log_exists
        assert path.exists() is report_exists
        assert companion.exists() is report_exists


@pytest.mark.parametrize("excess", [-1, 0, 1])
def test_aggregate_budget_reserves_32_mib_before_external_work(
    owner_root: Path, tmp_path: Path, excess: int
) -> None:
    with admit_run(owner_root, manifest(), clock=lambda: 1_800_000_000.0) as run:
        path = report_file(run.report_dir, manifest(), tmp_path / "scratch")
        log = run.stage_log_path
        log.touch(mode=0o600)
        run.finalize(evidence(), receipt())
    target_bytes = 1_073_741_824 - 33_554_432 + excess
    used = sum(
        p.stat().st_size for p in (owner_root / "runs").rglob("*") if p.is_file()
    )
    with log.open("wb") as stream:
        stream.truncate(target_bytes - used)
    external = owner_root.parent / "external-work"
    if excess > 0:
        with (
            pytest.raises(REJECTED),
            admit_run(owner_root, manifest(NEXT), clock=lambda: 1_800_000_001.0),
        ):
            external.touch()
        assert not external.exists() and path.exists() and log.exists()
    else:
        with admit_run(owner_root, manifest(NEXT), clock=lambda: 1_800_000_001.0):
            external.touch()
        assert external.exists()


def test_low_filesystem_capacity_and_run_allowance_fail_without_deleting_evidence(
    owner_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_usage = shutil.disk_usage
    usage_type = type(real_usage(owner_root))

    def low_capacity(_: str | os.PathLike[str]) -> Any:
        return usage_type(2_000_000_000, 1_966_445_569, 33_554_431)

    monkeypatch.setattr(shutil, "disk_usage", low_capacity)
    with pytest.raises(REJECTED), admit_run(owner_root, manifest()):
        pytest.fail("filesystem reserve was not established")
    monkeypatch.setattr(shutil, "disk_usage", real_usage)
    with admit_run(owner_root, manifest(NEXT)) as run:
        with run.stage_log_path.open("wb") as stream:
            stream.truncate(33_554_433)
        run.stage_log_path.chmod(0o600)
        with pytest.raises(REJECTED):
            run.check_budget()
        assert run.stage_log_path.stat().st_size == 33_554_433


@pytest.mark.parametrize(
    "fault", ["root_symlink", "root_mode", "uuid", "stage_symlink"]
)
def test_unsafe_owner_paths_fail_closed_without_touching_external_files(
    owner_root: Path, tmp_path: Path, fault: str
) -> None:
    outside = tmp_path / "outside"
    outside.write_bytes(SENTINEL)
    external = tmp_path / "external-work"
    supplied = manifest()
    if fault == "root_symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(owner_root, target_is_directory=True)
        owner_root = alias
    elif fault == "root_mode":
        owner_root.chmod(0o777)
    elif fault == "uuid":
        supplied["run_id"] = "../outside"
    else:
        with admit_run(owner_root, supplied) as run:
            run.stage_log_path.unlink(missing_ok=True)
            run.stage_log_path.symlink_to(outside)
            with pytest.raises(REJECTED):
                run.check_budget()
        assert outside.read_bytes() == SENTINEL
        return
    with pytest.raises(REJECTED), admit_run(owner_root, supplied):
        external.write_bytes(b"wrong")
    assert not external.exists() and outside.read_bytes() == SENTINEL


@pytest.mark.parametrize("mismatched", [False, True])
def test_only_matching_owner_prepared_socket_skeleton_can_be_admitted(
    socket_owner_root: Path, mismatched: bool
) -> None:
    owner_root = socket_owner_root
    base = owner_root / "runs" / RUN
    rpc, control = base / "rpc", base / "control"
    for directory in (owner_root / "runs", base, rpc, control):
        directory.mkdir(mode=0o700)
    prepared = manifest()
    if mismatched:
        prepared["seed"] = -43
    path = control / "manifest.json"
    path.write_text(json.dumps(prepared))
    path.chmod(0o600)
    for path in (rpc / "rpc.sock", control / "health.sock"):
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(path))
        path.chmod(0o600)
    if mismatched:
        with pytest.raises(REJECTED), admit_run(owner_root, manifest()):
            pytest.fail("different prepared manifest admitted")
        assert not (base / "reports").exists()
    else:
        with admit_run(owner_root, manifest()) as run:
            assert run.report_dir == base / "reports"
            assert run.report_dir.stat().st_mode & 0o777 == 0o700
            assert run.stage_log_path == base / "reports" / "stages.log"
            assert run.companion_path == base / "host.json"
