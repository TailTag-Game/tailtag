"""#229 U2: offline evaluation is honest, strict, comparable and read-only."""

import hashlib
import json
import stat
from pathlib import Path
from typing import Any

import pytest
from evaluation_support import (
    CONTEXT_SIGNALS,
    DEFAULT,
    IMAGE,
    OTHER_IMAGE,
    PLATFORM,
    STATEMENT,
    Edit,
    Inputs,
    as_schema_4,
    build,
    failed_run,
    limit,
    sample,
    stopped_failed_run,
)
from platform_support import skip_on_windows
from report_support import RUN_ID

from tailtag_simulator.__main__ import main
from tailtag_simulator.evaluation import (
    EvaluationFailed,
    evaluate,
    write_evaluation,
)


def run(inputs: Inputs) -> dict[str, Any]:
    return dict(
        evaluate(
            inputs.report,
            host_companion=inputs.companion,
            context=inputs.context,
            baselines_dir=inputs.baselines,
        )
    )


def results(
    artifact: dict[str, Any], check: str, operation: str | None = None
) -> set[str]:
    return {
        c["result"]
        for c in artifact["checks"]
        if c["check"] == check and operation in (None, c["operation"])
    }


def total(**changes: Any) -> Edit:
    return lambda t: t["operations"]["total"].update(
        {k: limit(v) for k, v in changes.items()}
    )


def regression(**changes: Any) -> Edit:
    return lambda t: t["regression"].update({k: limit(v) for k, v in changes.items()})


def saturation(**changes: Any) -> Edit:
    return lambda t: t["saturation"].update({k: limit(v) for k, v in changes.items()})


def baseline_p95(value: float) -> Edit:
    # Run total p95 is 50 ms; the baseline total p95 is moved to `value`.
    return lambda b: b["metrics"]["total"].update(p95=value)


def minimum_samples(count: int) -> Edit:
    return lambda t: t["minimum_samples"].update(p95=limit(count), p99=limit(count))


def sparse_baseline(value: dict[str, Any]) -> None:
    """Only the total has percentiles, from a single sample."""
    for name, metrics in value["metrics"].items():
        if name == "total":
            metrics["samples"] = 1
        else:
            metrics.update(samples=0, p50=None, p95=None, p99=None, max=None)


def evidence(**changes: Any) -> Edit:
    return lambda c: c["evidence"].update(changes)


def thresholds_with(*edits: Edit) -> Edit:
    return lambda t: [edit(t) for edit in edits]


# A companion whose samples have partial nulls; steal runs 100 -> 400 -> 350.
BUSY = [
    sample(50.0, 20.0, 100),
    sample(120.5, None, None),
    sample(80.0, 35.5, 400),
    sample(None, 10.0, 350),
]


def busy(value: dict[str, Any]) -> None:
    value["evidence"]["samples"] = BUSY


VERDICTS: dict[str, tuple[dict[str, Any], str, set[str]]] = {
    "acceptable": ({}, "acceptable", set()),
    "latency-breached": (
        {"thresholds": total(p95_ms=40)},
        "breached",
        set(),
    ),
    "error-rate-breached": (
        {"thresholds": total(error_rate=0.1)},
        "breached",
        set(),
    ),
    "regressed": (
        {
            "thresholds": regression(minimum_delta_ms=10),
            "baseline": baseline_p95(30),
        },
        "regressed",
        set(),
    ),
    "relative-change-below-minimum-delta-is-noise": (
        {
            "thresholds": regression(minimum_delta_ms=25),
            "baseline": baseline_p95(30),
        },
        "acceptable",
        set(),
    ),
    "delta-exactly-minimum-and-over-percentage-is-regressed": (
        # Run p95 50 vs baseline 30: +20 ms (the default minimum) and +67%.
        {"baseline": baseline_p95(30)},
        "regressed",
        set(),
    ),
    "delta-reached-but-percentage-not-exceeded-is-not-regressed": (
        # Run p95 50 vs baseline 40: +10 ms meets the minimum, +25% is not over 25.
        {"thresholds": regression(minimum_delta_ms=10), "baseline": baseline_p95(40)},
        "acceptable",
        set(),
    ),
    "baseline-too-few-samples": (
        # The run has 6 samples against a minimum of 2; only the baseline has 1.
        {"thresholds": minimum_samples(2), "baseline": sparse_baseline},
        "inconclusive",
        {"insufficient_samples"},
    ),
    "operations-without-a-configured-limit-are-not-regression-checked": (
        # resolve (3), confirm (2) and read (1) samples are under 4, but only the
        # total (6 samples) has p95/p99 limits configured.
        {"thresholds": minimum_samples(4)},
        "acceptable",
        set(),
    ),
    "host-attribution-mismatched": (
        {"companion": evidence(report_attribution="mismatched")},
        "not_evaluated",
        {"host_run_not_passed"},
    ),
    "host-stopped": (
        {"companion": evidence(stop_reason="report_uncertain")},
        "not_evaluated",
        {"host_run_not_passed"},
    ),
    "host-hard-stopped": (
        {"companion": evidence(hard_stop=True)},
        "not_evaluated",
        {"host_run_not_passed"},
    ),
    "host-container-failed": (
        {"companion": evidence(container_exit_code=1)},
        "not_evaluated",
        {"host_run_not_passed"},
    ),
    "too-few-samples": (
        {"thresholds": minimum_samples(200)},
        "inconclusive",
        {"insufficient_samples"},
    ),
    "no-thresholds": ({"thresholds": None}, "inconclusive", {"no_thresholds"}),
    "no-baseline": ({"baseline": None}, "inconclusive", {"no_baseline"}),
    "neither-thresholds-nor-baseline": (
        {"thresholds": None, "baseline": None},
        "inconclusive",
        {"no_thresholds", "no_baseline"},
    ),
    "generator-lag": (
        {"thresholds": saturation(lag_seconds=0.005)},
        "inconclusive",
        {"generator_saturated"},
    ),
    "generator-cpu": (
        {"thresholds": saturation(peak_cpu_percent=100), "companion": busy},
        "inconclusive",
        {"generator_saturated"},
    ),
    "generator-steal-is-last-minus-first": (
        {"thresholds": saturation(steal_ticks_delta=200), "companion": busy},
        "inconclusive",
        {"generator_saturated"},
    ),
    "steal-below-limit-is-not-saturation": (
        # Max - min would be 300; last - first is 250.
        {"thresholds": saturation(steal_ticks_delta=275), "companion": busy},
        "acceptable",
        set(),
    ),
    "inconclusive-outranks-breached": (
        {
            "thresholds": thresholds_with(
                saturation(lag_seconds=0.005), total(p95_ms=40)
            ),
            "baseline": None,
        },
        "inconclusive",
        {"generator_saturated", "no_baseline"},
    ),
    "failed-run": ({"report": failed_run}, "not_evaluated", set()),
    "stopped-failed-run": ({"report": stopped_failed_run}, "not_evaluated", set()),
    "schema-4": (
        {"report": as_schema_4},
        "not_evaluated",
        {"performance_not_measured"},
    ),
}
NOT_EVALUATED = {
    "failed-run": {"run_not_passed", "correctness_not_passed"},
    "stopped-failed-run": {"run_not_passed", "correctness_not_passed"},
    "schema-4": {"performance_not_measured"},
}


@pytest.mark.parametrize("case", VERDICTS)
def test_verdict_follows_the_contract_precedence_and_lists_every_reason(
    tmp_path: Path, case: str
) -> None:
    options, verdict, reasons = VERDICTS[case]
    artifact = run(build(tmp_path, **options))
    assert artifact["verdict"] == verdict
    assert set(artifact["reasons"]) >= reasons | NOT_EVALUATED.get(case, set())
    assert artifact["reasons"] == sorted(artifact["reasons"])
    if verdict in ("acceptable", "breached", "regressed"):
        assert artifact["reasons"] == []
    assert artifact["statement"] == STATEMENT
    if case == "latency-breached":
        (check,) = [c for c in artifact["checks"] if c["result"] == "breached"]
        assert (check["check"], check["operation"]) == ("absolute", "total")
        assert (check["observed"], check["limit"]) == (50.0, 40)
    if case == "error-rate-breached":
        assert results(artifact, "absolute", "total") == {"breached", "passed"}
    if case == "regressed":
        assert results(artifact, "regression", "total") == {"regressed", "passed"}
        (check,) = [c for c in artifact["checks"] if c["result"] == "regressed"]
        assert (check["observed"], check["baseline"]) == (50.0, 30)
    if case == "relative-change-below-minimum-delta-is-noise":
        assert results(artifact, "regression", "total") == {"passed"}
    if case == "baseline-too-few-samples":
        assert results(artifact, "absolute", "total") == {"passed"}
        assert results(artifact, "regression", "total") == {"inconclusive"}
    if case == "operations-without-a-configured-limit-are-not-regression-checked":
        regressions = [c for c in artifact["checks"] if c["check"] == "regression"]
        assert {c["operation"] for c in regressions} == {"total"}
    if case == "delta-reached-but-percentage-not-exceeded-is-not-regressed":
        assert results(artifact, "regression", "total") == {"passed"}
    if case == "too-few-samples":
        assert "inconclusive" in results(artifact, "absolute", "total")
        assert results(artifact, "regression", "total") == {"inconclusive"}
    if case == "acceptable":
        assert {c["check"] for c in artifact["checks"]} == {
            "absolute",
            "regression",
            "saturation",
        }
        assert {c["result"] for c in artifact["checks"]} == {"passed"}
    if case == "inconclusive-outranks-breached":
        assert "breached" in results(artifact, "absolute", "total")


@pytest.mark.parametrize(
    ("mode", "companion", "context_key"),
    [
        ("container", DEFAULT, f"external_host:{PLATFORM}"),
        ("container", None, "container"),
        ("checkout", DEFAULT, "checkout"),
        (None, DEFAULT, "unknown"),
        (None, None, "unknown"),
    ],
)
def test_execution_context_attests_a_host_only_for_a_matching_companion_and_container(
    tmp_path: Path, mode: str | None, companion: Any, context_key: str
) -> None:
    inputs = build(tmp_path, mode=mode, companion=companion)
    artifact = run(inputs)
    assert artifact["key"] == {**inputs.key, "execution_context": context_key}
    assert artifact["key"]["environment"] == "staging"
    assert len(artifact["key"]["plan_digest"]) == 64
    assert artifact["verdict"] == "acceptable"  # the fixture files carry this key


def test_a_baseline_for_another_key_is_never_used(tmp_path: Path) -> None:
    # The files are keyed for a bare container; this run is attested to a host.
    inputs = build(tmp_path, companion=DEFAULT)
    other = {**inputs.key, "execution_context": "container"}
    for path in inputs.baselines.iterdir():
        value = json.loads(path.read_text())
        value["key"] = other
        path.write_text(json.dumps(value))
    artifact = run(inputs)
    assert artifact["verdict"] == "inconclusive"
    assert set(artifact["reasons"]) == {"no_thresholds", "no_baseline"}
    assert artifact["baseline"] is None and artifact["thresholds"] is None


def test_differing_build_inputs_are_caveats_but_a_new_backend_is_not(
    tmp_path: Path,
) -> None:
    def differs(value: dict[str, Any]) -> None:
        report = value["report"]
        report["simulator_sha"] = "e" * 40
        report["dependency_lock_sha256"] = "d" * 64
        report["execution"]["image_id"] = OTHER_IMAGE
        report["backend"]["source_sha"] = "f" * 40

    artifact = run(build(tmp_path, baseline=differs, companion=DEFAULT))
    assert artifact["verdict"] == "acceptable"
    assert artifact["caveats"] == [
        "dependency_lock_differs",
        "image_differs",
        "simulator_sha_differs",
    ]


def test_generator_summary_comes_from_the_companion_and_context_never_moves_the_verdict(
    tmp_path: Path,
) -> None:
    def pressure(value: dict[str, Any]) -> None:
        value["signals"] = dict.fromkeys(CONTEXT_SIGNALS, "observed_pressure")
        value["signals"]["db_connections"] = "not_observed"

    plain = run(build(tmp_path / "a", companion=busy))
    informed = run(build(tmp_path / "b", companion=busy, context=pressure))
    assert plain["generator"] == {
        "status": "observed",
        "samples": 4,
        "peak_cpu_percent": 120.5,
        "peak_memory_percent": 35.5,
        "steal_ticks_delta": 250,
        "lag_seconds": 0.01,
        "image_id": IMAGE,
        "platform": PLATFORM,
    }
    assert plain["backend_context"] is None
    assert plain["caveats"] == []
    assert informed["backend_context"] == {
        **dict.fromkeys(CONTEXT_SIGNALS, "observed_pressure"),
        "db_connections": "not_observed",
    }
    assert (informed["verdict"], informed["reasons"], informed["checks"]) == (
        plain["verdict"],
        plain["reasons"],
        plain["checks"],
    )
    assert run(build(tmp_path / "c"))["generator"]["status"] == "not_observed"


def raw(text: str) -> Any:
    return text


STRICT_THRESHOLDS: dict[str, Edit | str] = {
    "unknown-key": lambda t: t.update(SENTINEL=1),
    "unknown-operation": lambda t: t["operations"].update(SENTINEL={}),
    "unknown-limit": lambda t: t["operations"]["total"].update(SENTINEL=limit(1)),
    "missing-regression": lambda t: t.pop("regression"),
    "missing-assumption": lambda t: t["regression"]["p95_percent"].pop("assumption"),
    "empty-assumption": lambda t: t["regression"]["p95_percent"].update(assumption=""),
    "assumption-too-long": lambda t: t["regression"]["p95_percent"].update(
        assumption="x" * 501
    ),
    "assumption-not-printable": lambda t: t["regression"]["p95_percent"].update(
        assumption="SENTINEL\x07"
    ),
    "value-not-a-number": lambda t: t["regression"]["p95_percent"].update(
        value="SENTINEL"
    ),
    "wrong-kind": lambda t: t.update(kind="baseline"),
    "duplicate-key": raw(
        '{"schema_version": 1, "schema_version": 1, "kind": "thresholds"}'
    ),
}
STRICT_CONTEXT: dict[str, Edit | str] = {
    "free-text-signal": lambda c: c["signals"].update(http_5xx="SENTINEL"),
    "unknown-signal": lambda c: c["signals"].update(SENTINEL="observed_normal"),
    "missing-signal": lambda c: c["signals"].pop("restarts_or_oom"),
    "extra-key": lambda c: c.update(note="SENTINEL"),
    "other-run": lambda c: c.update(run_id="523e4567-e89b-42d3-a456-426614174000"),
    "wrong-schema": lambda c: c.update(schema_version=2),
}
STRICT_COMPANION: dict[str, Edit | str] = {
    "other-run": lambda c: c.update(run_id="523e4567-e89b-42d3-a456-426614174000"),
    "other-run-in-evidence": lambda c: c["evidence"].update(
        run_id="523e4567-e89b-42d3-a456-426614174000"
    ),
    "unknown-evidence-key": lambda c: c["evidence"].update(SENTINEL=1),
    "non-numeric-sample": lambda c: c["evidence"]["samples"].append(
        sample("SENTINEL", None, None)
    ),
    "malformed": raw("{SENTINEL"),
}
STRICT_BASELINE: dict[str, Edit | str] = {
    "unknown-key": lambda b: b.update(SENTINEL=1),
}


def strict_cases() -> list[Any]:
    return [
        pytest.param(slot, name, spec, id=f"{slot}-{name}")
        for slot, cases in (
            ("thresholds", STRICT_THRESHOLDS),
            ("context", STRICT_CONTEXT),
            ("companion", STRICT_COMPANION),
            ("baseline", STRICT_BASELINE),
        )
        for name, spec in cases.items()
    ]


@pytest.mark.parametrize(("slot", "name", "spec"), strict_cases())
def test_invalid_optional_inputs_are_refused_without_echoing_them(
    tmp_path: Path, slot: str, name: str, spec: Any
) -> None:
    inputs = build(tmp_path, **{slot: spec})
    with pytest.raises(EvaluationFailed) as failure:
        run(inputs)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def cli_inputs(inputs: Inputs) -> list[str]:
    arguments = ["--baselines-dir", str(inputs.baselines)]
    for flag, path in (
        ("--host-companion", inputs.companion),
        ("--context", inputs.context),
    ):
        if path is not None:
            arguments += [flag, str(path)]
    return arguments


@pytest.mark.parametrize("kind", ["thresholds", "baseline"])
def test_ambiguous_discovery_refuses_rather_than_picking_one(
    tmp_path: Path, kind: str
) -> None:
    inputs = build(tmp_path)
    original = inputs.baselines / f"fixture.{kind}.json"
    (inputs.baselines / f"duplicate.{kind}.json").write_bytes(original.read_bytes())
    with pytest.raises(EvaluationFailed):
        run(inputs)


def test_invalid_reports_are_refused(tmp_path: Path) -> None:
    inputs = build(tmp_path)
    inputs.report.write_text('{"SENTINEL": 1}')
    with pytest.raises(EvaluationFailed) as failure:
        run(inputs)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(*roots: Path | None) -> dict[Path, bytes]:
    return {
        file: file.read_bytes()
        for root in roots
        if root is not None
        for file in ([root] if root.is_file() else sorted(root.rglob("*")))
        if file.is_file()
    }


def test_evaluation_records_exact_input_hashes_and_never_touches_its_inputs(
    tmp_path: Path,
) -> None:
    inputs = build(tmp_path, companion=DEFAULT, context=DEFAULT)
    before = snapshot(tmp_path)
    artifact = run(inputs)
    assert snapshot(tmp_path) == before  # nothing created, changed or removed
    thresholds = inputs.baselines / "fixture.thresholds.json"
    baseline = inputs.baselines / "fixture.baseline.json"
    assert artifact["schema_version"] == 1 and artifact["kind"] == "evaluation"
    assert artifact["report"]["sha256"] == digest(inputs.report)
    assert artifact["report"]["run_id"] == RUN_ID
    assert artifact["report"]["schema_version"] == 5
    assert (
        artifact["report"]["outcome"] == artifact["report"]["correctness"] == "passed"
    )
    assert artifact["thresholds"]["sha256"] == digest(thresholds)
    assert artifact["thresholds"]["path"].endswith("fixture.thresholds.json")
    assert artifact["baseline"]["report_sha256"] == "b" * 64
    assert artifact["baseline"]["path"].endswith(baseline.name)
    assert artifact["observation"]["started_at"] == "2026-10-05T12:00:00Z"
    assert artifact["observation"]["window_seconds"] == pytest.approx(2.1)
    assert artifact["observation"]["backend"]["environment"] == "staging"
    json.dumps(artifact, allow_nan=False)


@skip_on_windows(
    "POSIX file modes; Windows privacy for evaluation files is #315 slice 3."
)
def test_written_evaluation_is_private_exclusive_and_never_overwritten(
    tmp_path: Path,
) -> None:
    artifact = run(build(tmp_path))
    out = tmp_path / "evaluation.json"
    write_evaluation(artifact, out)
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert json.loads(out.read_text()) == json.loads(json.dumps(artifact))
    written = out.read_bytes()
    with pytest.raises((EvaluationFailed, OSError)):
        write_evaluation({**artifact, "verdict": "breached"}, out)
    assert out.read_bytes() == written


@skip_on_windows(
    "POSIX file modes; Windows privacy for evaluation files is #315 slice 3."
)
@pytest.mark.parametrize("explicit_out", [True, False])
def test_cli_prints_the_verdict_and_writes_one_private_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], explicit_out: bool
) -> None:
    inputs = build(tmp_path)
    out = tmp_path / "out.json"
    arguments = ["report", "evaluate", str(inputs.report), *cli_inputs(inputs)]
    status = main(arguments + (["--out", str(out)] if explicit_out else []))
    assert status == 0
    assert capsys.readouterr().out.splitlines()[0] == "PASS evaluation acceptable"
    (written,) = (
        [out]
        if explicit_out
        else list(inputs.report.parent.glob(f"{RUN_ID}.evaluation-*.json"))
    )
    assert stat.S_IMODE(written.stat().st_mode) == 0o600
    assert json.loads(written.read_text())["verdict"] == "acceptable"


def test_cli_reports_only_failure_and_writes_nothing_for_a_bad_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = build(tmp_path, context=STRICT_CONTEXT["free-text-signal"])
    out = tmp_path / "out.json"
    arguments = ["report", "evaluate", str(inputs.report), *cli_inputs(inputs)]
    assert main(arguments + ["--out", str(out)]) == 1
    assert capsys.readouterr().out == "FAIL evaluation\n"
    assert not out.exists()
    assert list(inputs.report.parent.glob("*.evaluation-*")) == []


def test_cli_never_overwrites_an_existing_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = build(tmp_path)
    out = tmp_path / "out.json"
    out.write_text("SENTINEL-existing")
    arguments = ["report", "evaluate", str(inputs.report), *cli_inputs(inputs)]
    assert main(arguments + ["--out", str(out)]) == 1
    assert capsys.readouterr().out == "FAIL evaluation\n"
    assert out.read_text() == "SENTINEL-existing"
