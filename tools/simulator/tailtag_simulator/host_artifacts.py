"""Owner-private admission and durable recovery holds for the trusted host."""

import fcntl
import json
import math
import os
import shutil
import stat
import time
import uuid
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn, cast

from .host_protocol import validate_manifest
from .provenance import _pairs  # pyright: ignore[reportPrivateUsage]
from .reports import validate_report

TOTAL = 1_073_741_824
RESERVE = 33_554_432


def _reject() -> NoReturn:
    raise ValueError("host_artifacts_rejected")


def _uuid(value: object) -> str:
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        _reject()
    return str(value)


def _private(path: Path, *, socket_allowed: bool = False) -> None:
    info = path.lstat()
    allowed = stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)
    allowed |= socket_allowed and stat.S_ISSOCK(info.st_mode)
    mode = stat.S_IMODE(info.st_mode)
    if (
        not allowed
        or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
        or info.st_uid != os.getuid()
        or mode != (0o700 if path.is_dir() else 0o600)
    ):
        _reject()


def _tree(path: Path) -> int:
    _private(path)
    size = 0
    for item in path.rglob("*"):
        _private(item, socket_allowed=item.name in {"rpc.sock", "health.sock"})
        if item.is_file():
            size += item.stat().st_size
    return size


def _read(path: Path) -> dict[str, Any]:
    _private(path)
    if path.stat().st_size > 65536:
        _reject()
    value: object = json.loads(path.read_text(), object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        _reject()
    return cast(dict[str, Any], value)


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path: Path, value: Mapping[str, object]) -> None:
    payload = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    if len(payload) > 65536:
        _reject()
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _clear_hold(base: Path) -> None:
    _private(base / "recovery-hold.json")
    (base / "recovery-hold.json").unlink()
    _sync_directory(base)


def _receipt(value: object, manifest: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(cast(dict[str, Any], value)) != {
        "schema_version",
        "run_id",
        "backend_identity",
        "disposition",
    }:
        _reject()
    value = cast(dict[str, Any], value)
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["run_id"] != manifest["run_id"]
        or value["backend_identity"] != manifest["backend_identity"]
        or value["disposition"] not in {"released", "no_mutation"}
    ):
        _reject()
    return value


class RunArtifacts:
    """Paths and evidence owned by one admission's still-held flock."""

    def __init__(
        self, root: Path, manifest: dict[str, object], clock: Callable[[], float]
    ):
        self.root = root
        self.manifest = manifest
        self.clock = clock
        self.base = root / "runs" / str(manifest["run_id"])
        self.report_dir = self.base / "reports"
        self.stage_log_path = self.report_dir / "stages.log"
        self.companion_path = self.base / "host.json"

    def check_budget(self) -> None:
        used = _tree(self.root / "runs")
        current = _tree(self.base)
        if (
            used > TOTAL
            or current >= RESERVE
            or (
                self.stage_log_path.exists()
                and self.stage_log_path.stat().st_size > 1_048_576
            )
            or shutil.disk_usage(self.root).free < RESERVE - current
        ):
            _reject()

    def finalize(
        self, evidence: Mapping[str, object], recovery_receipt: object = None
    ) -> None:
        self.check_budget()
        if evidence.get("run_id") != self.manifest["run_id"]:
            _reject()
        report = self.report_dir / f"{self.manifest['run_id']}.json"
        if report.exists():
            _private(report)
            validated = cast(
                dict[str, Any], validate_report(json.loads(report.read_text()))
            )
            release = cast(dict[str, Any], self.manifest["release"])
            if (
                validated["run_id"] != self.manifest["run_id"]
                or validated["source"]["provenance"] != "clean"
                or validated["source"]["simulator_sha"]["value"]
                != release["simulator_sha"]
                or validated["source"]["runtime"]["dependency_lock_sha256"]["value"]
                != release["dependency_lock_sha256"]
                or validated["target"]["starting"]["value"]
                != self.manifest["backend_identity"]
                or validated["safety"]["target"]["identity"]
                != self.manifest["backend_identity"]
            ):
                _reject()
        completed = self.clock()
        if not math.isfinite(completed):
            _reject()
        # Persist completion even if the trusted settlement receipt is absent.
        _write(
            self.companion_path,
            {
                "schema_version": 1,
                "run_id": self.manifest["run_id"],
                "completed_at": completed,
                "evidence": dict(evidence),
            },
        )
        trusted = _receipt(recovery_receipt, self.manifest)
        _write(self.base / "control" / "recovery.json", trusted)
        self.check_budget()
        _clear_hold(self.base)


@contextmanager
def _lock(root: Path) -> Generator[None]:
    if not root.is_absolute() or any(
        parent.is_symlink() for parent in (root, *root.parents)
    ):
        _reject()
    _private(root)
    path = root / "host.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        _private(path)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _prune(runs: Path, now: float) -> None:
    _tree(runs)
    for base in runs.iterdir():
        _uuid(base.name)
        if not base.is_dir() or (base / "recovery-hold.json").exists():
            _reject()
        companion = base / "host.json"
        if not companion.exists():
            continue  # A prepared socket skeleton is validated during admission.
        completed = _read(companion).get("completed_at")
        if type(completed) not in {int, float} or not math.isfinite(
            cast(float, completed)
        ):
            _reject()
        age = now - cast(float, completed)
        if age >= 7 * 86400:
            (base / "reports" / "stages.log").unlink(missing_ok=True)
        if age >= 30 * 86400:
            # Delete only the fixed completed evidence classes; retain UUID marker.
            (base / "reports" / f"{base.name}.json").unlink(missing_ok=True)
            companion.unlink()


@contextmanager
def admit_run(
    root: Path,
    manifest: Mapping[str, object],
    *,
    clock: Callable[[], float] = time.time,
) -> Generator[RunArtifacts]:
    supplied = validate_manifest(dict(manifest))
    run_id = _uuid(supplied["run_id"])
    with _lock(root):
        runs = root / "runs"
        runs.mkdir(mode=0o700, exist_ok=True)
        _prune(runs, clock())
        if _tree(runs) + RESERVE > TOTAL or shutil.disk_usage(root).free < RESERVE:
            _reject()
        base = runs / run_id
        if base.exists():
            expected = {"rpc", "control"}
            if {p.name for p in base.iterdir()} != expected:
                _reject()
            rpc, control = base / "rpc", base / "control"
            for socket_path in (rpc / "rpc.sock", control / "health.sock"):
                if socket_path.exists() and not stat.S_ISSOCK(
                    socket_path.lstat().st_mode
                ):
                    _reject()
            if (
                {p.name for p in rpc.iterdir()} - {"rpc.sock"}
                or {p.name for p in control.iterdir()}
                - {"health.sock", "manifest.json"}
                or _read(control / "manifest.json") != supplied
            ):
                _reject()
        else:
            base.mkdir(mode=0o700)
            (base / "rpc").mkdir(mode=0o700)
            (base / "control").mkdir(mode=0o700)
            _write(base / "control" / "manifest.json", supplied)
        (base / "reports").mkdir(mode=0o700)
        _write(base / "recovery-hold.json", {"schema_version": 1, "run_id": run_id})
        # A prepared manifest may have arrived before this admission. Flush its
        # bytes and every containing directory, not just the hold's parent.
        manifest_fd = os.open(
            base / "control" / "manifest.json", os.O_RDONLY | os.O_NOFOLLOW
        )
        try:
            os.fsync(manifest_fd)
        finally:
            os.close(manifest_fd)
        for directory in (
            base / "reports",
            base / "rpc",
            base / "control",
            base,
            runs,
            root,
        ):
            _sync_directory(directory)
        yield RunArtifacts(root, supplied, clock)


def resolve_recovery(root: Path, run_id: str, receipt: Mapping[str, object]) -> None:
    with _lock(root):
        runs = root / "runs"
        _private(runs)
        base = runs / _uuid(run_id)
        _tree(base)
        manifest = validate_manifest(_read(base / "control" / "manifest.json"))
        if manifest["run_id"] != run_id:
            _reject()
        trusted = _receipt(dict(receipt), manifest)
        hold = _read(base / "recovery-hold.json")
        if (
            set(hold) != {"schema_version", "run_id"}
            or type(hold["schema_version"]) is not int
            or hold["schema_version"] != 1
            or hold["run_id"] != run_id
        ):
            _reject()
        companion = base / "host.json"
        if companion.exists():
            _read(companion)  # Preserve original runtime evidence verbatim.
        else:
            _write(
                companion,
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "completed_at": time.time(),
                    "evidence": {
                        "schema_version": 1,
                        "run_id": run_id,
                        "status": "manual_recovered",
                    },
                },
            )
        _write(base / "control" / "recovery.json", trusted)
        _clear_hold(base)
