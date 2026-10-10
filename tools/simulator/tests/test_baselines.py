"""#229 U3: promotion is gated and atomic, baselines are one-per-key, trend is read-only."""

import ast
import hashlib
import json
import math
import os
import re
import shutil
import threading
from pathlib import Path
from typing import Any

import pytest
from evaluation_support import (
    DEFAULT,
    IMAGE,
    PLATFORM,
    Edit,
    Inputs,
    as_schema_4,
    baseline_file,
    build,
    failed_run,
    limit,
    write,
)
from report_support import RUN_ID

from tailtag_simulator import __main__ as entry
from tailtag_simulator.__main__ import main
from tailtag_simulator.baselines import PromotionFailed, baseline_slug, promote, trend
from tailtag_simulator.evaluation import evaluate, write_evaluation

RATIONALE = "Reviewed Staging reference run."
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
DEPLOYMENT = "223e4567-e89b-42d3-a456-426614174000"
VERDICTS = ("acceptable", "breached", "regressed", "inconclusive", "not_evaluated")
PACKAGE = Path(entry.__file__).parent


def snapshot(*roots: Path) -> dict[Path, bytes]:
    return {
        file: file.read_bytes()
        for root in roots
        for file in sorted(root.rglob("*"))
        if file.is_file()
    }


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose(*edits: Edit) -> Edit:
    return lambda value: [edit(value) for edit in edits]


def many_samples(value: dict[str, Any]) -> None:
    """`read` reaches 1000 samples, `confirm` 251 and `total` 1254; `resolve` stays tiny."""
    performance = value["performance"]
    window = performance["window_seconds"]["value"]
    added = {"read": 999, "confirm": 249}
    added["total"] = sum(added.values())
    for name, count in added.items():
        performance["attempts"]["value"][name]["success"] += count
        row = performance["latency_percentiles"]["value"][name]
        row["samples"] += count
        performance["throughput"]["value"][name] = row["samples"] / window
    read = performance["latency_percentiles"]["value"]["read"]
    read["p95"]["value"], read["p99"]["value"], read["max"]["value"] = 5.3, 5.6, 5.6
    traffic = value["results"]["traffic"]["value"]
    traffic["attempts"] += added["total"]
    traffic["sent"] += added["total"]


def slower_read_max(value: dict[str, Any]) -> None:
    many_samples(value)
    value["performance"]["latency_percentiles"]["value"]["read"]["max"]["value"] = 5.7


def rerun(run_id: str, day: int) -> Edit:
    def edit(value: dict[str, Any]) -> None:
        value["run_id"] = run_id
        value["timing"]["started_at"] = f"2026-10-0{day}T12:00:00Z"
        value["timing"]["ended_at"]["value"] = f"2026-10-0{day}T12:00:01Z"

    return edit


def companion_of(run_id: str) -> Edit:
    def edit(value: dict[str, Any]) -> None:
        value["run_id"] = value["evidence"]["run_id"] = run_id

    return edit


def exceeded(**changes: Any) -> Edit:
    return lambda t: t["operations"]["total"].update(
        {k: limit(v) for k, v in changes.items()}
    )


def moved(section: str, **changes: Any) -> Edit:
    return lambda t: t[section].update({k: limit(v) for k, v in changes.items()})


def regression_delta(minimum: float) -> Edit:
    return moved("regression", minimum_delta_ms=minimum)


def minimum_samples(count: int) -> Edit:
    return lambda t: t["minimum_samples"].update(p95=limit(count), p99=limit(count))


def baseline_p95(value: float) -> Edit:
    return lambda b: b["metrics"]["total"].update(p95=value)


# Each refusal: input files for build(), and overrides for promote().
REFUSALS: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
    "failed-run": ({"report": failed_run}, {}),
    "schema-4": ({"report": as_schema_4}, {}),
    "breached": ({"thresholds": exceeded(p95_ms=40)}, {}),
    "regressed": (
        {
            "thresholds": regression_delta(10),
            "baseline": baseline_p95(30),
        },
        {},
    ),
    # inconclusive only for no_baseline, yet an absolute check is breached.
    "breached-and-no-baseline": (
        {"thresholds": exceeded(p95_ms=40), "baseline": None},
        {},
    ),
    "insufficient-samples": ({"thresholds": minimum_samples(200)}, {}),
    # no_baseline alone is promotable; any other reason beside it is not.
    "saturated-and-no-baseline": (
        {"thresholds": moved("saturation", lag_seconds=0.005), "baseline": None},
        {},
    ),
    "companion-of-another-run": (
        {
            "thresholds": None,
            "baseline": None,
            "companion": companion_of("523e4567-e89b-42d3-a456-426614174000"),
        },
        {},
    ),
    "initial-thresholds-when-thresholds-exist": ({}, {"initial_thresholds": True}),
    # No operation has 200 samples, so the proposal would configure no limits.
    # (The same report promoted without the flag succeeds: first-promotion test.)
    "initial-thresholds-would-configure-nothing": (
        {"thresholds": None, "baseline": None},
        {"initial_thresholds": True},
    ),
    # A baseline for another key (descriptor digest) already sits at this run's path.
    "destination-is-another-keys-baseline": (
        {"thresholds": None, "baseline": None, "squatter": True},
        {},
    ),
    "rationale-empty": ({"thresholds": None, "baseline": None}, {"rationale": ""}),
    "rationale-too-long": (
        {"thresholds": None, "baseline": None},
        {"rationale": "x" * 1001},
    ),
    "rationale-newline": (
        {"thresholds": None, "baseline": None},
        {"rationale": "SENTINEL\nsecond line"},
    ),
    "rationale-control-character": (
        {"thresholds": None, "baseline": None},
        {"rationale": "SENTINEL\x07"},
    ),
}


@pytest.mark.parametrize("case", REFUSALS)
def test_ineligible_promotions_are_refused_and_write_nothing(
    tmp_path: Path, case: str
) -> None:
    options, overrides = REFUSALS[case]
    options = dict(options)
    squatter = options.pop("squatter", False)
    inputs = build(tmp_path, **options)
    slug = baseline_slug(inputs.key)
    # Canonical names, so the gate under test is the only reason for refusal.
    for kind in ("baseline", "thresholds"):
        fixture = inputs.baselines / f"fixture.{kind}.json"
        if fixture.exists():
            fixture.rename(inputs.baselines / f"{slug}.{kind}.json")
    if squatter:
        other = {**inputs.key, "descriptor_digest": "e" * 64}
        report = json.loads(inputs.report.read_text())
        write(inputs.baselines / f"{slug}.baseline.json", baseline_file(other, report))
    before = snapshot(tmp_path)
    with pytest.raises(PromotionFailed) as failure:
        arguments: dict[str, Any] = {
            "rationale": RATIONALE,
            "baselines_dir": inputs.baselines,
        } | overrides
        promote(
            inputs.report,
            **arguments,
            host_companion=inputs.companion,
            context=inputs.context,
        )
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)
    assert snapshot(tmp_path) == before  # no record, temp file or evaluation artifact


def assert_metrics(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    assert actual.keys() == expected.keys()
    for name, value in expected.items():
        if value is None:
            assert actual[name] is None
        else:
            assert actual[name] == pytest.approx(value), name


def test_first_promotion_records_the_run_without_thresholds_or_baseline(
    tmp_path: Path,
) -> None:
    inputs = build(
        tmp_path, thresholds=None, baseline=None, companion=DEFAULT, context=DEFAULT
    )
    report = json.loads(inputs.report.read_text())
    slug = baseline_slug(inputs.key)
    assert slug == "convention-baseline-v2-aaaaaaaaaaaa-external_host-linux-amd64"

    written = promote(
        inputs.report,
        rationale=RATIONALE,
        baselines_dir=inputs.baselines,
        host_companion=inputs.companion,
        context=inputs.context,
    )

    assert written == inputs.baselines / f"{slug}.baseline.json"
    assert [p.name for p in inputs.baselines.iterdir()] == [written.name]
    record = json.loads(written.read_text())
    assert set(record) == {
        "schema_version",
        "kind",
        "key",
        "report",
        "metrics",
        "rationale",
        "supersedes",
    }
    assert (record["schema_version"], record["kind"]) == (1, "baseline")
    assert record["key"] == inputs.key
    assert (record["rationale"], record["supersedes"]) == (RATIONALE, None)
    assert record["report"] == {
        "run_id": RUN_ID,
        "sha256": digest(inputs.report),
        "started_at": "2026-10-05T12:00:00Z",
        "simulator_sha": "f" * 40,
        "dependency_lock_sha256": report["source"]["runtime"]["dependency_lock_sha256"][
            "value"
        ],
        "backend": {
            "deployment_id": DEPLOYMENT,
            "source_sha": SOURCE_SHA,
            "environment": "staging",
        },
        "execution": {"image_id": IMAGE, "platform": PLATFORM},
    }
    assert str(tmp_path) not in written.read_text()
    metrics = record["metrics"]
    assert set(metrics) == {"auxiliary", "resolve", "confirm", "read", "total"}
    assert_metrics(
        metrics["total"],
        {
            "samples": 6,
            "p50": 20.0,
            "p95": 50.0,
            "p99": 50.0,
            "max": 50.0,
            "error_rate": 2 / 6,  # injected attempts are not part of the denominator
            "timeout_rate": 0.0,
            "throughput": 6 / 2.1,
        },
    )
    assert_metrics(
        metrics["auxiliary"],
        {
            "samples": 0,
            "p50": None,
            "p95": None,
            "p99": None,
            "max": None,
            "error_rate": None,
            "timeout_rate": None,
            "throughput": 0.0,
        },
    )
    # What was written is what offline evaluation accepts and matches by key.
    artifact = evaluate(
        inputs.report, host_companion=inputs.companion, baselines_dir=inputs.baselines
    )
    assert artifact["baseline"]["report_sha256"] == digest(inputs.report)
    assert artifact["reasons"] == ["no_thresholds"]


def default_thresholds() -> dict[str, Any]:
    def bounded(error: float, **percentiles: float) -> dict[str, float]:
        return {**percentiles, "error_rate": error, "timeout_rate": 0.01}

    return {
        "minimum_samples": {"p95": 200, "p99": 1000},
        # p95 needs 200 samples and p99 needs 1000; `resolve` (3 samples) has none.
        # read (1000): p95 5.3 and p99 5.6 round up to 11 and 12; rates floor at 0.01.
        # confirm (251): p95 only; 2 * 1/251 is below the 0.01 floor.
        # total (1254): p95 and p99 at 2 x 50; error rate 2 / 1254 doubled is still below the floor.
        "operations": {
            "read": bounded(0.01, p95_ms=11, p99_ms=12),
            "confirm": bounded(0.01, p95_ms=100),
            "total": bounded(0.01, p95_ms=100, p99_ms=100),
        },
        "regression": {
            "p95_percent": 25,
            "p99_percent": 50,
            "minimum_delta_ms": 20,
        },
        "saturation": {
            "peak_cpu_percent": 160,
            "lag_seconds": 1.0,
            "steal_ticks_delta": 1500,
        },
    }


def flatten(thresholds: dict[str, Any]) -> Any:
    """Replace each `{value, assumption}` leaf by its value; assumptions must be real."""
    if "assumption" in thresholds:
        assert set(thresholds) == {"value", "assumption"}
        text = thresholds["assumption"]
        assert 1 <= len(text) <= 500 and text.isprintable()
        return thresholds["value"]
    return {k: flatten(v) for k, v in thresholds.items()}


def test_later_promotion_replaces_the_single_record_and_initial_thresholds_are_proposed_once(
    tmp_path: Path,
) -> None:
    first = build(
        tmp_path / "first", thresholds=None, baseline=None, report=many_samples
    )
    second = build(
        tmp_path / "second", thresholds=None, baseline=None, report=slower_read_max
    )
    directory = first.baselines
    slug = baseline_slug(first.key)
    assert slug == "convention-baseline-v2-aaaaaaaaaaaa-container"

    promote(
        first.report,
        rationale="x" * 1000,
        baselines_dir=directory,
        initial_thresholds=True,
    )

    assert sorted(p.name for p in directory.iterdir()) == [
        f"{slug}.baseline.json",
        f"{slug}.thresholds.json",
    ]
    thresholds_path = directory / f"{slug}.thresholds.json"
    thresholds = json.loads(thresholds_path.read_text())
    assert (thresholds["schema_version"], thresholds["kind"]) == (1, "thresholds")
    assert thresholds["key"] == first.key
    expected = default_thresholds()
    found = flatten({k: v for k, v in thresholds.items() if k in expected})
    assert found["operations"].keys() == expected["operations"].keys()
    for name, limits in expected["operations"].items():
        assert found["operations"][name] == pytest.approx(limits)
    for section in ("minimum_samples", "regression", "saturation"):
        assert found[section] == expected[section]
    record = json.loads((directory / f"{slug}.baseline.json").read_text())
    assert record["report"]["execution"] is None  # no host companion supplied
    assert record["rationale"] == "x" * 1000
    # The proposed files are accepted as-is and the run passes its own limits.
    artifact = evaluate(first.report, baselines_dir=directory)
    assert (artifact["verdict"], artifact["reasons"]) == ("acceptable", [])

    thresholds_bytes = thresholds_path.read_bytes()
    promote(second.report, rationale="Second reference.", baselines_dir=directory)

    assert sorted(p.name for p in directory.iterdir()) == [
        f"{slug}.baseline.json",
        f"{slug}.thresholds.json",
    ]
    assert thresholds_path.read_bytes() == thresholds_bytes
    replaced = json.loads((directory / f"{slug}.baseline.json").read_text())
    assert replaced["report"]["sha256"] == digest(second.report)
    assert replaced["supersedes"] == digest(first.report)
    assert replaced["rationale"] == "Second reference."
    assert math.isclose(replaced["metrics"]["read"]["max"], 5.7)


def test_only_the_cli_entry_point_may_import_the_baseline_writer() -> None:
    def imports_baselines(tree: ast.AST) -> bool:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name.endswith(".baselines") for a in node.names):
                    return True
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[-1] == "baselines" or (
                    module in ("", "tailtag_simulator")
                    and any(a.name == "baselines" for a in node.names)
                ):
                    return True
        return False

    importers = {
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*.py")
        if imports_baselines(ast.parse(path.read_text()))
    }
    assert importers == {"__main__.py"}


def stamp(
    artifact: dict[str, Any], evaluated_at: str, **changes: Any
) -> dict[str, Any]:
    return {**artifact, "evaluated_at": evaluated_at, **changes}


def test_trend_groups_orders_marks_and_pairs_without_writing(tmp_path: Path) -> None:
    older = build(tmp_path / "a", thresholds=None, baseline=None)
    newer_id = "0b3e4567-e89b-42d3-a456-426614174000"  # sorts before RUN_ID by name
    hosted_id = "2b3e4567-e89b-42d3-a456-426614174000"
    legacy_id = "3b3e4567-e89b-42d3-a456-426614174000"
    newer = build(tmp_path / "b", report=rerun(newer_id, 6))
    hosted = build(
        tmp_path / "c",
        report=rerun(hosted_id, 7),
        companion=companion_of(hosted_id),
    )
    legacy = build(tmp_path / "d", report=compose(rerun(legacy_id, 8), as_schema_4))
    archive = tmp_path / "archive"
    for inputs in (older, newer, hosted, legacy):
        name = json.loads(inputs.report.read_text())["run_id"]
        destination = (
            archive / "nested" / f"{name}.json"
            if inputs is legacy
            else (archive / f"{name}.json")
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(inputs.report, destination)
    assert hosted.companion is not None
    shutil.copy(hosted.companion, archive / "host.json")

    promote(older.report, rationale=RATIONALE, baselines_dir=older.baselines)
    artifact = evaluate(older.report, baselines_dir=older.baselines)
    stale = {**artifact["report"], "sha256": "0" * 64}
    write_evaluation(
        stamp(artifact, "2026-10-07T00:00:00Z"), archive / "newest-valid.json"
    )
    write_evaluation(
        stamp(artifact, "2026-10-06T00:00:00Z", verdict="breached"),
        archive / "older.json",
    )
    write_evaluation(  # newest of all, but for different report bytes
        stamp(artifact, "2026-10-09T00:00:00Z", verdict="regressed", report=stale),
        archive / "stale.json",
    )
    write(archive / "broken.json", "{not json")
    write(archive / "unrelated.json", {"hello": "world"})
    write(
        archive / "invalid-report.json",
        {**json.loads(older.report.read_text()), "SENTINEL": 1},
    )
    before = snapshot(archive, older.baselines)

    lines = trend(archive, baselines_dir=older.baselines)

    assert snapshot(archive, older.baselines) == before
    row: dict[str, int] = {}
    for name, run_id in (
        ("older", RUN_ID),
        ("newer", newer_id),
        ("hosted", hosted_id),
        ("legacy", legacy_id),
    ):
        (row[name],) = [i for i, line in enumerate(lines) if run_id in line]
    assert row["older"] < row["newer"]  # time order, not file-name order
    assert not any(
        row["older"] < row[other] < row["newer"] for other in ("hosted", "legacy")
    )  # one table per comparable key; the host-attested run has its own key
    starred = [i for i, line in enumerate(lines) if re.search(r"(^|\s)\*(\s|$)", line)]
    assert starred == [row["older"]]  # only the promoted run's row
    first_row = lines[row["older"]]
    assert SOURCE_SHA[:12] in first_row and "passed" in first_row
    assert "inconclusive" in first_row  # newest evaluation that matches this report
    assert "breached" not in first_row and "regressed" not in first_row
    for other in ("newer", "hosted", "legacy"):
        assert not any(verdict in lines[row[other]] for verdict in VERDICTS)
    summary = re.fullmatch(r"skipped (\d+)", lines[-1])
    assert (
        summary is not None and int(summary.group(1)) == 3
    )  # junk only; unmatched evaluations are ignored


def test_cli_promote_prints_the_slug_and_only_failure_otherwise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = build(
        tmp_path / "good",
        thresholds=None,
        baseline=None,
        companion=DEFAULT,
        context=DEFAULT,
        report=many_samples,
    )
    assert good.companion is not None and good.context is not None
    arguments = [
        "baseline",
        "promote",
        str(good.report),
        "--rationale",
        RATIONALE,
        "--host-companion",
        str(good.companion),
        "--context",
        str(good.context),
        "--baselines-dir",
        str(good.baselines),
        "--initial-thresholds",
    ]
    assert main(arguments) == 0
    slug = baseline_slug(good.key)
    assert capsys.readouterr().out == f"PASS promotion {slug}\n"
    assert sorted(p.name for p in good.baselines.iterdir()) == [
        f"{slug}.baseline.json",
        f"{slug}.thresholds.json",
    ]

    bad = build(tmp_path / "bad", thresholds=None, baseline=None, report=failed_run)
    before = snapshot(tmp_path / "bad")
    refused = [
        "baseline",
        "promote",
        str(bad.report),
        "--rationale",
        RATIONALE,
        "--baselines-dir",
        str(bad.baselines),
    ]
    assert main(refused) == 1
    assert capsys.readouterr().out == "FAIL promotion\n"
    assert snapshot(tmp_path / "bad") == before


def test_cli_trend_prints_the_tables_then_skips_oversized_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs: Inputs = build(tmp_path / "a", thresholds=None, baseline=None)
    archive = tmp_path / "archive"
    archive.mkdir()
    shutil.copy(inputs.report, archive / inputs.report.name)
    write(archive / "oversized.json", " " * (1024 * 1024 + 1))

    assert (
        main(
            ["report", "trend", str(archive), "--baselines-dir", str(inputs.baselines)]
        )
        == 0
    )

    printed = capsys.readouterr().out.splitlines()
    assert printed == trend(archive, baselines_dir=inputs.baselines)
    assert any(RUN_ID in line for line in printed)
    assert printed[-1] == "skipped 1"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs named pipes")
def test_trend_skips_a_named_pipe_instead_of_blocking_on_it(tmp_path: Path) -> None:
    inputs: Inputs = build(tmp_path / "a", thresholds=None, baseline=None)
    archive = tmp_path / "archive"
    archive.mkdir()
    shutil.copy(inputs.report, archive / inputs.report.name)
    pipe = archive / "x.json"
    os.mkfifo(pipe)
    lines: list[list[str]] = []
    scan = threading.Thread(
        target=lambda: lines.append(trend(archive, baselines_dir=inputs.baselines)),
        daemon=True,
    )
    scan.start()
    scan.join(5)
    if scan.is_alive():  # release a reader blocked in open() so the thread ends
        os.close(os.open(pipe, os.O_WRONLY | os.O_NONBLOCK))
        scan.join(2)
        pytest.fail("trend blocked on a named pipe")
    assert any(RUN_ID in line for line in lines[0])
    assert lines[0][-1] == "skipped 1"
