"""#230 U3: read-only host inventory and verified operator evidence collection.

The inventory tests run the real `host_runner inventory` against real temporary host
directories. The collect tests run the real operator against those same directories;
only the `ssh`/`scp` executables are fakes at the process boundary, and they delegate to
the real inventory command and to a local file copy. Tampering is injected there.
"""

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from evaluation_support import companion_file
from report_support import RUN_ID
from test_host_runtime import executable, records
from test_reports_v3 import successful_report

from tailtag_simulator.host_operator import SSH_OPTIONS
from tailtag_simulator.host_operator import main as operator_main
from tailtag_simulator.reports import validate_report

SIMULATOR = Path(__file__).parents[1]
DATA = Path(__file__).parent / "data"
SETTLED = RUN_ID
PRUNED = "aaaaaaaa-0000-4000-8000-000000000004"
HELD = "aaaaaaaa-0000-4000-8000-000000000001"
INCOMPLETE = "aaaaaaaa-0000-4000-8000-000000000002"
JOURNEYS = "aaaaaaaa-0000-4000-8000-000000000003"
GOOD = "aaaaaaaa-0000-4000-8000-000000000005"
SHA = "b" * 40
SENTINEL = b"SENTINEL-outside-the-run"


def digest(data: bytes) -> dict[str, object]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def convention_report(run_id: str, scratch: Path) -> dict[str, Any]:
    (scratch / run_id).mkdir(mode=0o700, parents=True)
    value = successful_report(scratch / run_id)
    value["run_id"] = run_id
    return value


def journeys_report(run_id: str) -> dict[str, Any]:
    value: dict[str, Any] = json.loads((DATA / "report-v1-journeys.json").read_text())
    value["run_id"] = run_id
    assert validate_report(value) == value
    return value


def put(path: Path, data: bytes | str | dict[str, Any]) -> bytes:
    raw = (
        data
        if isinstance(data, bytes)
        else (data if isinstance(data, str) else json.dumps(data)).encode()
    )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o600)
    return raw


def host_run(
    root: Path,
    run_id: str,
    state: str,
    *,
    report: dict[str, Any] | None = None,
    stages: bytes | None = b"stage log evidence\n",
    completed_at: float | None = None,
) -> dict[str, bytes]:
    """Lay out one run like the real host; returns the bytes written by file kind."""
    base = root / "runs" / run_id
    (base / "control").mkdir(mode=0o700, parents=True, exist_ok=True)
    (base / "rpc").mkdir(mode=0o700, exist_ok=True)
    written: dict[str, bytes] = {}
    if state == "incomplete":
        put(base / "control/manifest.json", {"run_id": run_id})
        return written
    companion = companion_file()
    companion["run_id"] = run_id
    companion["evidence"]["run_id"] = run_id
    if completed_at is not None:
        companion["completed_at"] = completed_at
    written["host"] = put(base / "host.json", companion)
    written["report"] = put(
        base / "reports" / f"{run_id}.json",
        report if report is not None else {"schema_version": 5},
    )
    if stages is not None:
        written["stages"] = put(base / "reports/stages.log", stages)
    put(
        base / "control/recovery.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "backend_identity": {},
            "disposition": "released",
        },
    )
    if state == "held":
        put(base / "recovery-hold.json", {"schema_version": 1, "run_id": run_id})
    return written


def snapshot(root: Path) -> dict[str, tuple[object, ...]]:
    """Everything observable about a tree: type, mode, link target, bytes, mtime."""
    seen: dict[str, tuple[object, ...]] = {}
    for current, directories, names in os.walk(root):
        for name in [*directories, *names]:
            path = Path(current) / name
            info = path.lstat()
            content: object = None
            if stat.S_ISLNK(info.st_mode):
                content = os.readlink(path)
            elif stat.S_ISREG(info.st_mode):
                content = path.read_bytes()
            seen[str(path.relative_to(root))] = (
                stat.S_IFMT(info.st_mode),
                stat.S_IMODE(info.st_mode),
                content,
                info.st_mtime_ns,
            )
    return seen


def operator_evidence(
    root: Path, run_id: str, kinds: tuple[str, ...] = ("used", "bridge")
) -> dict[str, bytes]:
    """Host-side operator state for one run (#316), as `run-local` leaves it."""
    return {
        kind: put(
            root / "operator-state" / f"{run_id}.{kind}.json",
            {"schema_version": 1, "run_id": run_id, "kind": kind},
        )
        for kind in kinds
    }


def inventory(
    root: Path, timeout: float = 15
) -> tuple[int, str, dict[str, dict[str, Any]]]:
    # A FIFO or similar must be refused, never waited on: the timeout is the failure.
    result = subprocess.run(
        [sys.executable, "-m", "tailtag_simulator.host_runner", "inventory"]
        + ["--root", str(root)],
        env={**os.environ, "PYTHONPATH": str(SIMULATOR)},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    runs: dict[str, dict[str, Any]] = {}
    if result.returncode == 0:
        runs = {item["run_id"]: item for item in json.loads(result.stdout)["runs"]}
    return result.returncode, result.stdout, runs


@pytest.fixture
def host(tmp_path: Path) -> Path:
    root = tmp_path / "host"
    root.mkdir(mode=0o700)
    (root / "runs").mkdir(mode=0o700)
    return root


def test_inventory_classifies_runs_with_exact_hashes_and_writes_nothing(
    host: Path,
) -> None:
    settled = host_run(host, SETTLED, "settled")
    pruned = host_run(host, PRUNED, "settled", stages=None)
    host_run(host, HELD, "held")
    host_run(host, INCOMPLETE, "incomplete")
    for ignored in (SETTLED.replace("-", ""), "not-a-uuid", "..hidden"):
        (host / "runs" / ignored).mkdir(mode=0o700)
    (host / "runs" / "stray-file").write_text("not a run")
    before = snapshot(host)

    code, stdout, runs = inventory(host)

    assert code == 0
    assert stdout.endswith("\n") and stdout.count("\n") == 1 and len(stdout) <= 65536
    assert json.loads(stdout)["schema_version"] == 1
    assert {run_id: item["state"] for run_id, item in runs.items()} == {
        SETTLED: "settled",
        PRUNED: "settled",
        HELD: "held",
        INCOMPLETE: "incomplete",
    }
    assert runs[SETTLED]["files"] == {
        kind: digest(settled[kind]) for kind in ("report", "stages", "host")
    }
    assert runs[PRUNED]["files"] == {
        "report": digest(pruned["report"]),
        "stages": None,
        "host": digest(pruned["host"]),
    }
    assert runs[HELD]["files"] is None and runs[INCOMPLETE]["files"] is None
    assert snapshot(host) == before


def test_inventory_reports_operator_evidence_only_for_runs_that_have_it(
    host: Path,
) -> None:
    settled = host_run(host, SETTLED, "settled")
    both = operator_evidence(host, SETTLED)
    partial = host_run(host, PRUNED, "settled", stages=None)
    only_used = operator_evidence(host, PRUNED, ("used",))
    plain = host_run(host, GOOD, "settled")
    before = snapshot(host)

    code, _, runs = inventory(host)

    assert code == 0
    ordinary = ("report", "stages", "host")
    assert runs[SETTLED]["files"] == {
        **{kind: digest(settled[kind]) for kind in ordinary},
        "used": digest(both["used"]),
        "bridge": digest(both["bridge"]),
    }
    assert runs[PRUNED]["files"] == {
        "report": digest(partial["report"]),
        "stages": None,
        "host": digest(partial["host"]),
        "used": digest(only_used["used"]),
    }
    assert runs[GOOD]["files"] == {kind: digest(plain[kind]) for kind in ordinary}
    assert snapshot(host) == before


def test_inventory_never_reads_operator_evidence_through_a_symlink(
    host: Path, tmp_path: Path
) -> None:
    host_run(host, SETTLED, "settled")
    outside = tmp_path / "outside.json"
    outside.write_bytes(SENTINEL)
    link = host / "operator-state" / f"{SETTLED}.used.json"
    link.parent.mkdir(mode=0o700)
    link.symlink_to(outside)

    code, stdout, _ = inventory(host)

    assert code in (0, 1)  # a usage error would pass this test vacuously
    assert hashlib.sha256(SENTINEL).hexdigest() not in stdout


@pytest.mark.parametrize("unsafe", ["report", "host", "stages", "fifo-report"])
def test_inventory_never_reads_through_symlinks_or_special_files(
    host: Path, tmp_path: Path, unsafe: str
) -> None:
    host_run(host, SETTLED, "settled")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(SENTINEL)
    path = host / "runs" / SETTLED
    path = {
        "report": path / f"reports/{SETTLED}.json",
        "host": path / "host.json",
        "stages": path / "reports/stages.log",
        "fifo-report": path / f"reports/{SETTLED}.json",
    }[unsafe]
    path.unlink()
    if unsafe == "fifo-report":
        os.mkfifo(path, 0o600)
    else:
        path.symlink_to(outside)
    before = snapshot(host)

    code, stdout, runs = inventory(host)

    assert code in (0, 1)  # a usage error would pass this test vacuously
    assert hashlib.sha256(SENTINEL).hexdigest() not in stdout
    # The contract says "refused"; whether that is a failed command or a run that
    # is not settled is unstated. Either is safe. A pruned (null) stages log is the
    # only way a run may still be settled.
    if code == 0:
        entry = runs[SETTLED]
        assert entry["state"] != "settled" or (
            unsafe == "stages" and entry["files"]["stages"] is None
        )
    assert snapshot(host) == before


def test_inventory_omits_pruned_runs_without_listing_or_counting_them(
    host: Path,
) -> None:
    # Pruned: recovery.json survives, host.json and the report are gone, no hold.
    for number in range(70):
        pruned = host / "runs" / f"bbbbbbbb-0000-4000-8000-{number:012d}"
        put(pruned / "control/recovery.json", {"schema_version": 1})
    host_run(host, SETTLED, "settled")

    code, stdout, runs = inventory(host)

    assert code == 0
    assert list(runs) == [SETTLED]
    assert json.loads(stdout)["omitted"] == 0


def test_inventory_lists_the_newest_64_settled_runs_and_counts_the_rest(
    host: Path,
) -> None:
    ids = [f"aaaaaaaa-0000-4000-8000-{number:012d}" for number in range(65)]
    # Directory order must not decide: the oldest completion is in the middle.
    oldest = ids[17]
    for number, run_id in enumerate(ids):
        host_run(
            host,
            run_id,
            "settled",
            completed_at=1_000.0 if run_id == oldest else 2_000.0 + number,
        )

    code, stdout, runs = inventory(host)

    assert code == 0 and len(stdout) <= 65536
    assert set(runs) == set(ids) - {oldest}
    assert json.loads(stdout)["omitted"] == 1


@pytest.mark.parametrize(("count", "accepted"), [(64, True), (65, False)])
def test_inventory_fails_when_held_and_incomplete_runs_alone_exceed_64(
    host: Path, count: int, accepted: bool
) -> None:
    for number in range(count):
        run = host / "runs" / f"aaaaaaaa-0000-4000-8000-{number:012d}"
        run.mkdir(mode=0o700)
        if number % 2:
            put(run / "recovery-hold.json", {"schema_version": 1})

    code, stdout, runs = inventory(host)

    assert (code, len(runs)) == ((0, 64) if accepted else (1, 0))
    assert accepted or "aaaaaaaa" not in stdout


class Rig:
    """One operator-visible host plus fake ssh/scp executables and an archive."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.host = root / "host"
        (self.host / "runs").mkdir(mode=0o700, parents=True)
        self.archive = root / "archive"
        self.archive.mkdir(mode=0o700)
        self.baselines = root / "baselines"
        self.baselines.mkdir()
        (self.baselines / "sentinel.txt").write_text("untouched")
        self.release = root / "release.json"
        self.release.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "simulator_sha": SHA,
                    "dependency_lock_sha256": "c" * 64,
                    "image_id": "sha256:" + "d" * 64,
                    "platform": "linux/amd64",
                    "archive_sha256": "e" * 64,
                }
            )
        )
        self.tamper: dict[str, dict[str, str]] = {}
        binary = root / "bin"
        binary.mkdir()
        executable(
            binary / "ssh",
            f"""
import json, os, shlex, subprocess, sys
from pathlib import Path
root = Path({str(root)!r})
argv = sys.argv[1:]
with (root / "ssh.jsonl").open("a") as out:
    out.write(json.dumps({{"argv": argv}}) + "\\n")
canned = root / "inventory-stdout"
if (root / "ssh-fails").exists():
    raise SystemExit(255)
if canned.exists():
    sys.stdout.buffer.write(canned.read_bytes())
    raise SystemExit(0)
words = shlex.split(argv[-1])
at = words.index("inventory")
environment = dict(os.environ, PYTHONPATH={str(SIMULATOR)!r})
raise SystemExit(subprocess.run(
    [sys.executable, "-m", "tailtag_simulator.host_runner", "inventory",
     "--root", words[at + 2]], env=environment, check=False).returncode)
""",
        )
        executable(
            binary / "scp",
            f"""
import json, shutil, sys
from pathlib import Path
root = Path({str(root)!r})
words = [a for a in sys.argv[1:] if not a.startswith("-")]
with (root / "scp.jsonl").open("a") as out:
    out.write(json.dumps({{"argv": sys.argv[1:]}}) + "\\n")
tamper = json.loads((root / "tamper.json").read_text()) if (root / "tamper.json").exists() else {{}}
destination = Path(words[-1])
for source in words[:-1]:
    path = Path(source.split(":", 1)[1])
    target = destination / path.name if destination.is_dir() else destination
    kind = ("host" if path.name == "host.json"
            else "stages" if path.name == "stages.log"
            else "used" if path.name.endswith(".used.json")
            else "bridge" if path.name.endswith(".bridge.json") else "report")
    owner = (path.name.split(".")[0] if kind in ("used", "bridge")
             else path.parent.name if kind == "host" else path.parent.parent.name)
    fault = tamper.get(owner, {{}}).get(kind)
    if fault == "fail":
        raise SystemExit(1)
    data = path.read_bytes()
    if fault == "flip":
        data = bytes([data[0] ^ 1]) + data[1:]
    if fault == "truncate":
        data = data[:-1]
    target.write_bytes(data)
    target.chmod(path.stat().st_mode & 0o777)  # as real scp creates the file
""",
        )
        monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])

    def tampering(self, run_id: str, kind: str, fault: str) -> None:
        self.tamper.setdefault(run_id, {})[kind] = fault
        (self.root / "tamper.json").write_text(json.dumps(self.tamper))

    def collect(
        self, capsys: pytest.CaptureFixture[str], *, baselines: bool = True
    ) -> tuple[int, dict[str, str], str]:
        capsys.readouterr()
        code = operator_main(
            [
                "collect",
                "--host",
                "tailtag-test",
                "--host-root",
                str(self.host),
                "--release",
                str(self.release),
                "--archive",
                str(self.archive),
                *(["--baselines-dir", str(self.baselines)] if baselines else []),
            ]
        )
        out = capsys.readouterr().out
        lines = [
            line.split() for line in out.splitlines() if line.startswith("COLLECT ")
        ]
        return code, {line[1]: line[2] for line in lines if len(line) > 2}, out

    def ssh(self) -> list[dict[str, Any]]:
        return records(self.root / "ssh.jsonl")

    def scp(self) -> list[dict[str, Any]]:
        return records(self.root / "scp.jsonl")

    def archived(self, run_id: str) -> dict[str, bytes]:
        return {
            str(p.relative_to(self.archive / run_id)): p.read_bytes()
            for p in (self.archive / run_id).rglob("*")
            if p.is_file()
        }


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    return Rig(tmp_path, monkeypatch)


def test_collect_copies_verified_settled_evidence_once_and_never_touches_the_rest(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    written = host_run(
        rig.host, SETTLED, "settled", report=convention_report(SETTLED, tmp_path)
    )
    host_run(rig.host, HELD, "held")
    host_run(rig.host, INCOMPLETE, "incomplete")
    host_before, baselines_before = snapshot(rig.host), snapshot(rig.baselines)

    code, states, _ = rig.collect(capsys)

    assert code == 0
    assert states == {SETTLED: "collected", HELD: "held", INCOMPLETE: "incomplete"}
    assert sorted(p.name for p in rig.archive.iterdir()) == [SETTLED]
    final = rig.archive / SETTLED
    assert stat.S_IMODE(final.stat().st_mode) == 0o700
    contents = rig.archived(SETTLED)
    assert set(written.values()) <= set(contents.values())
    collected = json.loads(contents["collected.json"])
    assert collected["run_id"] == SETTLED
    assert all(
        hashlib.sha256(raw).hexdigest() in contents["collected.json"].decode()
        for raw in written.values()
    )
    # Fixed SSH grammar and options; held/incomplete runs are never copied.
    (call,) = rig.ssh()
    runtime = rig.host / "releases" / SHA
    assert call["argv"][: len(SSH_OPTIONS)] == SSH_OPTIONS
    assert call["argv"][-2] == "tailtag-test"
    assert call["argv"][-1].startswith(f"cd -- {runtime} && exec {runtime}/.venv/bin/")
    assert call["argv"][-1].endswith(f"inventory --root {rig.host}")
    assert all(
        HELD not in " ".join(c["argv"]) and INCOMPLETE not in " ".join(c["argv"])
        for c in rig.scp()
    )
    assert snapshot(rig.host) == host_before
    assert snapshot(rig.baselines) == baselines_before

    # A second pass is idempotent: skipped, no transfer, nothing in the archive moves.
    archive_before, transfers = snapshot(rig.archive), len(rig.scp())
    code, states, _ = rig.collect(capsys)
    assert code == 0
    assert states == {SETTLED: "skipped", HELD: "held", INCOMPLETE: "incomplete"}
    assert len(rig.scp()) == transfers
    assert snapshot(rig.archive) == archive_before
    assert snapshot(rig.host) == host_before
    assert snapshot(rig.baselines) == baselines_before


def test_collect_archives_verified_operator_evidence_beside_the_run(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host_run(rig.host, SETTLED, "settled", report=convention_report(SETTLED, tmp_path))
    operator = operator_evidence(rig.host, SETTLED)
    host_run(rig.host, GOOD, "settled", report=convention_report(GOOD, tmp_path / "s"))
    host_before = snapshot(rig.host)

    code, states, _ = rig.collect(capsys)

    assert (code, states) == (0, {SETTLED: "collected", GOOD: "collected"})
    contents = rig.archived(SETTLED)
    assert contents[f"{SETTLED}.used.json"] == operator["used"]
    assert contents[f"{SETTLED}.bridge.json"] == operator["bridge"]
    recorded = json.loads(contents["collected.json"])["files"]
    assert recorded["used"] == digest(operator["used"])
    assert recorded["bridge"] == digest(operator["bridge"])
    # A Mac-mode run has no operator evidence: nothing extra is fetched or recorded.
    assert not any(".used." in n or ".bridge." in n for n in rig.archived(GOOD))
    assert set(json.loads(rig.archived(GOOD)["collected.json"])["files"]) == {
        "report",
        "stages",
        "host",
    }
    assert snapshot(rig.host) == host_before


@pytest.mark.parametrize("case", ["convention", "journeys"])
def test_collect_evaluates_only_convention_schema_5_reports(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    report = (
        convention_report(SETTLED, tmp_path)
        if case == "convention"
        else journeys_report(SETTLED)
    )
    host_run(rig.host, SETTLED, "settled", report=report)

    code, states, out = rig.collect(capsys)

    assert (code, states) == (0, {SETTLED: "collected"})
    contents = rig.archived(SETTLED)
    evaluations = [name for name in contents if name.endswith(".evaluation.json")]
    if case == "convention":
        assert evaluations == [f"{SETTLED}.evaluation.json"]
        artifact = json.loads(contents[evaluations[0]])
        assert artifact["kind"] == "evaluation"
        assert artifact["report"]["run_id"] == SETTLED
    else:
        assert evaluations == []
        # The contract says "records evaluation: not_applicable" without saying where.
        assert "not_applicable" in out + b"".join(contents.values()).decode(
            errors="replace"
        )


@pytest.mark.parametrize(
    ("kind", "fault"),
    [
        ("report", "flip"),
        ("report", "truncate"),
        ("host", "flip"),
        ("stages", "truncate"),
        ("report", "fail"),
        ("report", "invalid"),
        ("report", "misattributed"),
        ("used", "flip"),
        ("bridge", "truncate"),
    ],
)
def test_collect_leaves_no_evidence_for_a_run_whose_transfer_does_not_verify(
    rig: Rig,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    fault: str,
) -> None:
    # A valid report for another run must not be archived under this run.
    bad = convention_report(GOOD if fault == "misattributed" else SETTLED, tmp_path)
    if fault == "invalid":
        bad["outcome"] = "not-an-outcome"
    host_run(rig.host, SETTLED, "settled", report=bad)
    if kind in {"used", "bridge"}:
        operator_evidence(rig.host, SETTLED)
    host_run(rig.host, GOOD, "settled", report=convention_report(GOOD, tmp_path / "s"))
    if fault not in {"invalid", "misattributed"}:
        rig.tampering(SETTLED, kind, fault)

    code, states, _ = rig.collect(capsys)

    assert code != 0
    assert states == {SETTLED: "failed", GOOD: "collected"}
    # A failed run leaves neither a final nor a `.partial` directory behind.
    assert sorted(p.name for p in rig.archive.iterdir()) == [GOOD]


def inventory_text(
    top: dict[str, Any] | None = None,
    run: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> str:
    """A well-formed one-run inventory with the named fields overridden."""
    entry: dict[str, Any] = {
        "run_id": SETTLED,
        "state": "settled",
        "files": {
            "report": digest(b"report"),
            "stages": None,
            "host": digest(b"host"),
        },
    }
    entry.update(run or {})
    if files:
        entry["files"].update(files)
    return json.dumps(
        {"schema_version": 1, "runs": [entry], "omitted": 0, **(top or {})}
    )


UNTRUSTED = {
    "traversal": inventory_text(run={"run_id": "../x"}),
    "absolute": inventory_text(run={"run_id": "/etc"}),
    "unhyphenated-uuid": inventory_text(run={"run_id": SETTLED.replace("-", "")}),
    "bad-digest": inventory_text(files={"report": {"sha256": "ABC", "bytes": 6}}),
    "uppercase-digest": inventory_text(
        files={"report": {"sha256": "A" * 64, "bytes": 6}}
    ),
    "oversize": inventory_text(
        files={"report": {"sha256": "a" * 64, "bytes": 33_554_433}}
    ),
    "empty": inventory_text(files={"report": {"sha256": "a" * 64, "bytes": 0}}),
    "boolean-size": inventory_text(
        files={"report": {"sha256": "a" * 64, "bytes": True}}
    ),
    "unknown-state": inventory_text(run={"state": "archived"}),
    "held-with-files": inventory_text(run={"state": "held"}),
    "settled-without-files": inventory_text(run={"files": None}),
    "extra-run-key": inventory_text(run={"extra": 1}),
    "extra-file": inventory_text(files={"extra": digest(b"x")}),
    "bad-operator-digest": inventory_text(
        files={"used": {"sha256": "ABC", "bytes": 6}}
    ),
    "extra-top-key": inventory_text(top={"extra": 1}),
    "wrong-version": inventory_text(top={"schema_version": 2}),
    "omitted-negative": inventory_text(top={"omitted": -1}),
    "omitted-boolean": inventory_text(top={"omitted": True}),
    "omitted-string": inventory_text(top={"omitted": "1"}),
    "omitted-missing": json.dumps(
        {"schema_version": 1, "runs": json.loads(inventory_text())["runs"]}
    ),
    "duplicate-run": json.dumps(
        {
            "schema_version": 1,
            "runs": json.loads(inventory_text())["runs"] * 2,
            "omitted": 0,
        }
    ),
    "not-json": "not json\n",
    "oversize-stdout": "x" * 70_000,
}


@pytest.mark.parametrize("name", sorted(UNTRUSTED))
def test_collect_refuses_untrusted_inventory_before_any_transfer(
    rig: Rig, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    host_run(rig.host, SETTLED, "settled")
    (rig.root / "inventory-stdout").write_text(UNTRUSTED[name])

    code, _, out = rig.collect(capsys)

    assert code != 0
    assert rig.scp() == []
    assert list(rig.archive.iterdir()) == []
    assert "../x" not in out and "/etc" not in out


def test_collect_reports_omitted_runs_once_and_still_succeeds(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    held = {"run_id": HELD, "state": "held", "files": None}
    canned = {"schema_version": 1, "runs": [held], "omitted": 3}
    (rig.root / "inventory-stdout").write_text(json.dumps(canned))

    code, states, out = rig.collect(capsys)

    assert (code, states) == (0, {HELD: "held"})
    assert out.splitlines().count("COLLECT omitted=3") == 1
    assert rig.scp() == []


def test_collect_fails_an_existing_final_directory_without_collected_json(
    rig: Rig, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host_run(rig.host, SETTLED, "settled", report=convention_report(SETTLED, tmp_path))
    existing = rig.archive / SETTLED
    existing.mkdir(mode=0o700)
    identity = existing.stat().st_ino

    code, states, _ = rig.collect(capsys)

    assert code != 0 and states == {SETTLED: "failed"}
    assert rig.scp() == []
    assert existing.stat().st_ino == identity and list(existing.iterdir()) == []
    assert [p.name for p in rig.archive.iterdir()] == [SETTLED]


@pytest.mark.parametrize("name", ["host root", "host*root"])
def test_collect_refuses_a_host_root_that_scp_would_interpret(
    rig: Rig, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    # scp remote paths are not shell-quoted, so such a root must never reach ssh/scp.
    rig.host = rig.root / name
    (rig.host / "runs").mkdir(mode=0o700, parents=True)
    host_run(rig.host, SETTLED, "settled")

    code, _, _ = rig.collect(capsys)

    assert code != 0
    assert rig.ssh() == [] and rig.scp() == []
    assert list(rig.archive.iterdir()) == []


def test_collect_refuses_when_the_remote_inventory_cannot_be_captured(
    rig: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    host_run(rig.host, SETTLED, "settled")
    (rig.root / "ssh-fails").touch()

    code, _, _ = rig.collect(capsys)

    assert code != 0 and rig.scp() == [] and list(rig.archive.iterdir()) == []
