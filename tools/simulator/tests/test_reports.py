"""#224 strict consumer/schema and durable storage contracts (AC3-5,7-8,10-13).

Real catalog, validator, recorder and files; only clocks and filesystem faults
are substituted. Expected schema is the independently authored literal fixture.
"""

import hashlib
import json
import os
import socket
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from report_support import (
    DATA,
    RUN_ID,
    ReportClock,
    commit,
    git,
    literal_report,
    read_report,
    recorder,
    repository,
)

from tailtag_simulator.__main__ import main
from tailtag_simulator.client import MAX_RESPONSE_BYTES, REQUEST_TIMEOUT_SECONDS
from tailtag_simulator.fixtures import RETENTION_CAP
from tailtag_simulator.pool import LAUNCHER_TIMEOUT_SECONDS, LEASE_TTL_SECONDS
from tailtag_simulator.reports import (
    ReportFailed,
    RunReport,
    load_report,
    validate_report,
)
from tailtag_simulator.scenarios import (
    ScenarioRejected,
    resolve_scenario,
    validate_catalog,
)


@pytest.mark.parametrize("seed", [-42, 0, 2**80])
def test_supported_literal_report_retains_its_meaning_and_integer_seed(
    seed: int,
) -> None:
    value = literal_report()
    value["scenario"]["seed"] = seed
    assert validate_report(value) == value


def _replace(value: dict[str, Any], path: tuple[str, ...], replacement: object) -> None:
    current = value
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = replacement


INVALID_VALUES = [
    (("schema_version",), 2),
    (("schema_version",), True),
    (("run_id",), "SENTINEL-PRIVATE-UUID"),
    (("scenario", "version"), 0),
    (("scenario", "version"), 2),
    (("scenario", "seed"), True),
    (("scenario", "consumes_randomness"), True),
    (("scenario", "descriptor_digest"), "0" * 64),
    (("scenario", "descriptor", "api_contract"), "unsupported-SENTINEL"),
    (("scenario", "configuration", "target"), "production"),
    (("scenario", "configuration", "base_url"), "https://SENTINEL.example"),
    (("population", "identities"), 1001),
    (("population", "roles", "player"), True),
    (("profile", "operations"), ["me_second", "me_first"]),
    (("timing", "duration_seconds", "value"), -1),
    (("timing", "duration_seconds", "value"), float("inf")),
    (("timing", "started_at"), "2026-10-05T12:00:00-07:00"),
    (("performance", "duration_seconds", "value"), 0),
    (("performance", "duration_seconds", "value"), True),
    (("performance", "throughput"), {"value": 0, "reason": "not_implemented"}),
    (("performance", "resource_context", "reason"), "SENTINEL-detail"),
    (("source", "simulator_sha", "value"), "f" * 39),
    (("source", "provenance"), "unknown"),
    (("target", "starting", "value", "deployment_id"), None),
    (("target", "final", "value", "source_sha"), "0" * 40),
    (("phases", "cleanup", "status"), "passed"),
    (("phases", "simulation", "status"), "failed"),
    (("correctness",), "failed"),
    pytest.param(
        ("correctness",),
        "passed_after_failed_reconciliation",
        id="failed-smoke-false-correctness",
    ),
    (("failure",), {"stage": "setup", "code": "SENTINEL-exception"}),
    (("results", "journeys", "items"), [{"name": "SENTINEL", "status": "passed"}]),
]


@pytest.mark.parametrize(("path", "replacement"), INVALID_VALUES)
def test_invalid_or_contradictory_reports_are_rejected_without_payload_details(
    path: tuple[str, ...], replacement: object
) -> None:
    value = literal_report()
    if path == ("correctness",) and replacement == "passed_after_failed_reconciliation":
        value["outcome"] = "failed"
        value["correctness"] = "failed"
        value["phases"]["reconciliation"]["status"] = "failed"
        value["phases"]["reconciliation"]["code"] = "FAIL_RECONCILIATION"
        value["failure"] = {"stage": "reconciliation", "code": "FAIL_RECONCILIATION"}
        assert validate_report(value) == value  # Truthful failed evidence is supported.
        replacement = "passed"
    if path == ("performance", "duration_seconds", "value") and replacement is True:
        value["timing"]["duration_seconds"]["value"] = 1.0
    _replace(value, path, replacement)
    with pytest.raises(ReportFailed) as failure:
        validate_report(value)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


# Every closed object boundary gets one unknown-key fault, not neighboring examples.
CLOSED_OBJECTS = [
    (),
    ("scenario",),
    ("scenario", "descriptor"),
    ("scenario", "descriptor", "configuration"),
    ("scenario", "configuration"),
    ("source",),
    ("source", "runtime"),
    ("source", "simulator_sha"),
    ("target",),
    ("target", "starting", "value"),
    ("timing",),
    ("population",),
    ("population", "roles"),
    ("population", "fixtures"),
    ("profile",),
    ("limits",),
    ("limits", "response_bytes"),
    ("phases",),
    ("phases", "target"),
    ("results",),
    ("results", "journeys"),
    ("results", "checks"),
    ("performance",),
]


@pytest.mark.parametrize("path", CLOSED_OBJECTS)
def test_unapproved_nested_fields_cannot_enter_a_report(path: tuple[str, ...]) -> None:
    value = literal_report()
    current = value
    for key in path:
        current = current[key]
    current["SENTINEL-private"] = "sk_live_SECRET"
    with pytest.raises(ReportFailed):
        validate_report(value)


@pytest.mark.parametrize(
    "body",
    [
        DATA.read_text().replace(
            '"schema_version": 1', '"schema_version": 1, "schema_version": 1'
        ),
        DATA.read_text().replace('"seed": -42', '"seed": -42, "seed": -42'),
        '{"number":NaN}',
        '{"number":Infinity}',
        '{"number":-Infinity}',
        '{"private":"SENTINEL"',
        "[" * 1000 + "0" + "]" * 1000,
        DATA.read_text() + " " * 2_000_000,
    ],
)
def test_reader_rejects_ambiguous_malformed_deep_or_oversized_json_safely(
    tmp_path: Path, body: str
) -> None:
    path = tmp_path / "SENTINEL-private-report.json"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ReportFailed) as failure:
        load_report(path)
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)


@pytest.mark.parametrize("valid", [True, False])
def test_report_validation_cli_is_offline_and_exposes_only_fixed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    valid: bool,
) -> None:
    path = tmp_path / "report.json"
    path.write_text(DATA.read_text() if valid else '{"SENTINEL":"sk_live_SECRET"}')
    reached: list[str] = []

    def trip(*_args: object, **_kwargs: object) -> Any:
        reached.append("external")
        raise AssertionError("offline validation touched an external boundary")

    monkeypatch.setattr(socket.socket, "connect", trip)
    monkeypatch.setattr(subprocess, "Popen", trip)
    import getpass

    monkeypatch.setattr(getpass, "getpass", trip)
    assert main(["report", "validate", str(path)]) == (0 if valid else 1)
    assert capsys.readouterr().out == ("PASS report\n" if valid else "FAIL report\n")
    assert reached == []


@pytest.mark.parametrize(
    ("scenario", "version", "config"),
    [
        ("smoke", True, {"target": "staging"}),
        ("smoke", 0, {"target": "staging"}),
        ("smoke", 2, {"target": "staging"}),
        ("unknown", 1, {}),
        ("smoke", 1, {"target": "production"}),
        ("smoke", 1, {"target": "local", "base_url": "http://evil.example"}),
        ("smoke", 1, {"target": "staging", "token": "SENTINEL"}),
        ("pool-smoke", 1, {"pool": "p1"}),
        ("pool-smoke", 1, {"count": 3}),
        ("pool-smoke", 1, {"pool": "p1", "count": True}),
        ("pool-smoke", 1, {"pool": "p1", "count": 0}),
        ("pool-smoke", 1, {"pool": "p1", "count": 1001}),
        ("pool-smoke", 1, {"pool": "Bad_Pool", "count": 1}),
        ("fixture-smoke", 1, {"pool": "p1", "owners": 51}),
        ("fixture-smoke", 1, {"pool": "p1", "catchers": 201}),
        ("fixture-smoke", 1, {"pool": "p1", "fursuits": 6}),
        ("fixture-smoke", 1, {"pool": "p1", "owners": -1}),
        ("journeys", 1, {"pool": "p1", "owners": 3}),
    ],
)
def test_configuration_refuses_unsupported_or_unsafe_workloads(
    scenario: str, version: int, config: dict[str, object]
) -> None:
    with pytest.raises(ScenarioRejected) as failure:
        resolve_scenario(scenario, version, config)
    assert "SENTINEL" not in str(failure.value)


@pytest.mark.parametrize(
    ("scenario", "config", "effective"),
    [
        (
            "smoke",
            {"target": "local"},
            {"target": "local", "base_url": "http://127.0.0.1:8000"},
        ),
        (
            "pool-smoke",
            {"pool": "p1", "count": 1000},
            {"target": "staging", "base_url": None, "pool": "p1", "count": 1000},
        ),
        (
            "fixture-smoke",
            {"pool": "p1", "owners": 50, "fursuits": 5, "catchers": 200},
            {
                "target": "staging",
                "base_url": None,
                "pool": "p1",
                "owners": 50,
                "fursuits": 5,
                "catchers": 200,
            },
        ),
        (
            "journeys",
            {"pool": "p1"},
            {"target": "staging", "base_url": None, "pool": "p1"},
        ),
    ],
)
def test_supported_boundary_inputs_resolve_without_changing_scenario_version(
    scenario: str, config: dict[str, object], effective: dict[str, object]
) -> None:
    resolved = resolve_scenario(scenario, 1, config)
    assert resolved["configuration"] == effective
    assert resolved["id"] == scenario and resolved["version"] == 1


def test_smoke_catalog_matches_the_independent_descriptor_contract() -> None:
    expected = literal_report()["scenario"]
    resolved = resolve_scenario("smoke", 1, {"target": "staging"})
    assert resolved["descriptor"] == expected["descriptor"]
    assert resolved["descriptor_digest"] == expected["descriptor_digest"]


@pytest.mark.parametrize(
    "change", ["edit", "remove", "shallow", "historical_duplicate", "dotfile_removed"]
)
def test_committed_scenario_history_cannot_be_changed_removed_or_unverified(
    tmp_path: Path, change: str
) -> None:
    value = literal_report()["scenario"]
    entry = {**value["descriptor"], "descriptor_digest": value["descriptor_digest"]}
    relative = "tools/simulator/tailtag_simulator/scenarios/smoke-v1.json"
    canonical_entry = json.dumps(entry)
    historical_entry = canonical_entry
    if change == "historical_duplicate":
        # Last-wins parsing yields exactly the canonical current entry, hiding
        # an ambiguous earlier descriptor unless historical blobs are strict.
        historical_entry = canonical_entry.replace(
            '"id": "smoke"', '"id": "SENTINEL-ambiguous", "id": "smoke"', 1
        )
    files: dict[str, str | bytes] = {relative: historical_entry}
    dotfile = str(Path(relative).with_name(".json"))
    if change == "dotfile_removed":
        files[dotfile] = canonical_entry
    root = repository(tmp_path / "repo", files)
    if change == "historical_duplicate":
        (root / relative).write_text(canonical_entry)
        commit(root, "Canonical current descriptor after ambiguous historical JSON")
    elif change == "dotfile_removed":
        # Current *.json glob includes this name; its history must remain in
        # the same scope even though Path('.json').suffix is empty.
        (root / dotfile).unlink()
        commit(root, "Remove literal dot-json artifact while preserving valid smoke")
    else:
        validate_catalog(root)
    if change == "remove":
        (root / relative).unlink()
    elif change == "edit":
        entry["operations"] = ["me_second", "me_first"]
        descriptor = {k: v for k, v in entry.items() if k != "descriptor_digest"}
        entry["descriptor_digest"] = hashlib.sha256(
            json.dumps(
                descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
        (root / relative).write_text(json.dumps(entry))
        commit(root, "Changed historical descriptor despite matching digest")
    elif change == "shallow":
        (root / "README.md").write_text("Second fixture commit")
        commit(root, "Second fixture commit")
        shallow = tmp_path / "shallow"
        git(tmp_path, "clone", "--depth", "1", root.as_uri(), str(shallow))
        root = shallow
    with pytest.raises(ScenarioRejected):
        validate_catalog(root)


def test_nested_historical_json_cannot_collide_with_the_flat_catalog(
    tmp_path: Path,
) -> None:
    value = literal_report()["scenario"]
    entry = {**value["descriptor"], "descriptor_digest": value["descriptor_digest"]}
    directory = "tools/simulator/tailtag_simulator/scenarios"
    nested = f"{directory}/archive/smoke-v1.json"
    root = repository(
        tmp_path / "repo",
        {
            f"{directory}/smoke-v1.json": json.dumps(entry),
            nested: '{"SENTINEL": "unrelated nested artifact"}',
        },
    )
    (root / nested).unlink()
    commit(root, "Remove unrelated nested artifact while preserving flat catalog")
    validate_catalog(root)


def test_published_limits_match_runtime_owners_and_literal_report_meanings(
    tmp_path: Path,
) -> None:
    report = RunReport(tmp_path, "fixture-smoke", config={"pool": "p1"}, run_id=RUN_ID)
    limits = cast(dict[str, dict[str, object]], load_report(report.path)["limits"])
    expected = json.loads((DATA.parent / "report-v1-journeys.json").read_text())[
        "limits"
    ]
    assert limits == expected
    assert {
        name: limits[name]["value"]
        for name in (
            "response_bytes",
            "request_timeout",
            "lease_ttl",
            "launcher_timeout",
            "retained_runs",
        )
    } == {
        "response_bytes": MAX_RESPONSE_BYTES,
        "request_timeout": REQUEST_TIMEOUT_SECONDS,
        "lease_ttl": LEASE_TTL_SECONDS,
        "launcher_timeout": LAUNCHER_TIMEOUT_SECONDS,
        "retained_runs": RETENTION_CAP,
    }


def test_constructor_persists_running_evidence_before_any_lifecycle_work(
    tmp_path: Path,
) -> None:
    report = RunReport(tmp_path, "smoke", config={"target": "staging"}, run_id=RUN_ID)
    value = read_report(report.path)
    assert report.path == tmp_path / f"{RUN_ID}.json"
    assert value["outcome"] == "running"
    assert value["correctness"] == "not_observed"
    assert value["source"]["simulator_sha"] == {"value": None, "reason": "not_observed"}
    assert all(
        phase["status"] in {"not_reached", "not_applicable"}
        for phase in value["phases"].values()
    )


@pytest.mark.parametrize("symlink", [False, True])
def test_reservation_never_overwrites_existing_evidence_or_symlinks(
    tmp_path: Path, symlink: bool
) -> None:
    path = tmp_path / f"{RUN_ID}.json"
    prior = tmp_path / "prior.json"
    prior.write_text("SENTINEL-prior-evidence")
    if symlink:
        path.symlink_to(prior)
    else:
        path.write_text("SENTINEL-prior-evidence")
    with pytest.raises(ReportFailed):
        RunReport(tmp_path, "smoke", config={"target": "staging"}, run_id=RUN_ID)
    assert prior.read_text() == path.read_text() == "SENTINEL-prior-evidence"


def test_initial_storage_failure_is_detail_free_and_cannot_create_a_run(
    tmp_path: Path,
) -> None:
    output = tmp_path / "SENTINEL-private-dir"
    output.write_text("occupied")
    with pytest.raises(ReportFailed) as failure:
        RunReport(output, "smoke", config={"target": "staging"})
    assert "SENTINEL" not in str(failure.value) + repr(failure.value)
    assert output.read_text() == "occupied"


def test_failed_atomic_snapshot_preserves_last_document_blocks_success_and_removes_temps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = recorder(tmp_path)
    prior = report.path.read_bytes()

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("SENTINEL-storage-secret")

    monkeypatch.setattr(os, "replace", fail_replace)
    report.begin("target")
    assert report.write_failed
    assert report.finish(0) != 0
    assert report.path.read_bytes() == prior
    assert read_report(report.path)["outcome"] == "running"
    assert set(tmp_path.iterdir()) == {report.path}


def test_elapsed_time_uses_monotonic_clock_when_utc_clock_moves_backwards(
    tmp_path: Path,
) -> None:
    clock = ReportClock()
    report = recorder(tmp_path, clock=clock)
    report.begin("target")
    clock.wall -= timedelta(hours=1)
    clock.elapsed += 2.5
    report.end("target", "failed", "FAIL_TARGET")
    assert report.finish(1) == 1
    value = read_report(report.path)
    assert value["phases"]["target"]["duration_seconds"] == {
        "value": 2.5,
        "reason": None,
    }
    assert value["timing"]["duration_seconds"] == {"value": 2.5, "reason": None}
    assert value["timing"]["ended_at"]["value"].endswith(("Z", "+00:00"))


@pytest.mark.parametrize("adapter", ["source", "target", "results", "phase"])
def test_recorder_adapters_reject_unsanitized_payloads_without_persisting_them(
    tmp_path: Path, adapter: str
) -> None:
    report = recorder(tmp_path)
    prior = report.path.read_bytes()
    with pytest.raises(ReportFailed):
        if adapter == "source":
            report.record_source(
                {"simulator_sha": "SENTINEL", "token": "sk_live_SECRET"}
            )
        elif adapter == "target":
            report.record_target(
                "staging", "https://staging.tailtag.app", {"source_sha": "SENTINEL"}
            )
        elif adapter == "results":
            report.record_results(
                journeys={
                    "items": [
                        {"name": "catch", "status": "passed", "token": "SENTINEL"}
                    ],
                    "passed": 1,
                    "failed": 0,
                    "reason": None,
                }
            )
        else:
            report.begin("SENTINEL")
    assert report.path.read_bytes() == prior


RUN_COMMANDS = [
    ["smoke", "--target", "staging"],
    ["pool-smoke", "--pool", "p1", "--count", "3"],
    ["fixture-smoke", "--pool", "p1"],
    ["journeys", "--pool", "p1"],
]


@pytest.mark.parametrize("arguments", RUN_COMMANDS)
def test_initial_cli_report_storage_failure_prevents_all_external_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arguments: list[str]
) -> None:
    import getpass

    output = tmp_path / "SENTINEL-not-a-directory"
    output.write_text("occupied")
    reached: list[str] = []

    def trip(*_args: object, **_kwargs: object) -> Any:
        reached.append("external")
        raise AssertionError("initial report failure permitted external work")

    monkeypatch.setattr(socket.socket, "connect", trip)
    monkeypatch.setattr(subprocess, "Popen", trip)
    monkeypatch.setattr(getpass, "getpass", trip)
    assert main([*arguments, "--report-dir", str(output)]) != 0
    assert reached == []


@pytest.mark.parametrize("arguments", RUN_COMMANDS)
def test_accepted_cli_run_persists_failed_unknown_source_before_provider_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arguments: list[str]
) -> None:
    import getpass
    import importlib

    entry = importlib.import_module("tailtag_simulator.__main__")
    unknown = tmp_path / "unknown-source"
    unknown.mkdir()
    output = tmp_path / "reports"
    monkeypatch.setattr(entry, "REPOSITORY_ROOT", unknown)
    reached: list[str] = []

    def trip(*_args: object, **_kwargs: object) -> Any:
        reached.append("external")
        raise AssertionError("unknown provenance permitted external work")

    monkeypatch.setattr(socket.socket, "connect", trip)
    monkeypatch.setattr(getpass, "getpass", trip)
    original: Any = subprocess.Popen

    def launch(arguments: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(arguments, (list, tuple)) and arguments[0] == "git":
            return original(arguments, *args, **kwargs)
        return trip()

    monkeypatch.setattr(subprocess, "Popen", launch)
    assert main([*arguments, "--report-dir", str(output)]) != 0
    reports = list(output.glob("*.json"))
    assert len(reports) == 1
    value = read_report(reports[0])
    assert value["scenario"]["id"] == arguments[0]
    assert value["outcome"] == "failed" and value["correctness"] == "not_observed"
    assert value["source"]["provenance"] in {"unknown", "rejected"}
    assert value["source"]["simulator_sha"]["value"] is None
    assert value["phases"]["provenance"]["status"] == "failed"
    assert value["phases"]["target"]["status"] == "not_reached"
    assert reached == []


def test_two_accepted_invocations_reserve_distinct_run_artifacts(
    tmp_path: Path,
) -> None:
    first = RunReport(tmp_path, "smoke", config={"target": "staging"})
    second = RunReport(tmp_path, "smoke", config={"target": "staging"})
    assert first.run_id != second.run_id
    assert set(tmp_path.iterdir()) == {first.path, second.path}


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_journeys",
        "unobserved_journeys",
        "missing_checks",
        "unobserved_cleanup",
        "discrepancy_count",
        "failed_journey_false_correctness",
    ],
)
def test_journey_reports_cannot_claim_success_without_complete_results_or_hide_named_checks(
    mutation: str,
) -> None:
    value = json.loads((DATA.parent / "report-v1-journeys.json").read_text())
    # Hand-authored complete report is a positive control, never built by recorder.
    assert validate_report(value) == value
    if mutation == "missing_journeys":
        value["results"]["journeys"] = {
            "items": [],
            "passed": 0,
            "failed": 0,
            "reason": None,
        }
    elif mutation == "unobserved_journeys":
        value["results"]["journeys"] = {
            "items": [],
            "passed": 0,
            "failed": 0,
            "reason": "not_observed",
        }
    elif mutation == "missing_checks":
        value["results"]["checks"] = {"items": [], "count": 0, "reason": "not_observed"}
    elif mutation == "unobserved_cleanup":
        value["results"]["cleanup"] = {"value": None, "reason": "not_observed"}
    elif mutation == "failed_journey_false_correctness":
        value["outcome"] = "failed"
        value["correctness"] = "failed"
        value["phases"]["release"]["status"] = "failed"
        value["phases"]["release"]["code"] = "FAIL_RELEASE"
        value["failure"] = {"stage": "release", "code": "FAIL_RELEASE"}
        value["results"]["journeys"]["items"][1]["status"] = "failed"  # catch
        value["results"]["journeys"]["passed"] = 12
        value["results"]["journeys"]["failed"] = 1
        assert validate_report(value) == value  # Failed result evidence remains valid.
        value["correctness"] = "passed"
    else:
        value["outcome"] = "failed"
        value["correctness"] = "failed"
        value["phases"]["reconciliation"]["status"] = "failed"
        value["phases"]["reconciliation"]["code"] = "FAIL_RECONCILIATION"
        value["failure"] = {"stage": "reconciliation", "code": "FAIL_RECONCILIATION"}
        value["results"]["checks"] = {
            "items": [
                {
                    "check": "duplicate",
                    "journey": "catch",
                    "role": "catcher0",
                    "expected": 1,
                    "observed": 2,
                }
            ],
            "count": 1,
            "reason": None,
        }
        assert validate_report(value) == value  # Partial failed evidence is allowed.
        value["results"]["checks"]["count"] = 0
    with pytest.raises(ReportFailed):
        validate_report(value)
