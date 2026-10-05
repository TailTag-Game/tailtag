"""Strict privacy bounded run evidence and atomic filesystem snapshots."""

import copy
import json
import math
import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from tailtag_simulator.scenarios import (
    JOURNEYS,
    ScenarioRejected,
    canonical,
    resolve_scenario,
)
from tailtag_simulator.targets import STAGING_ORIGIN

STAGES = (
    "provenance",
    "target",
    "setup",
    "simulation",
    "reconciliation",
    "attribution",
    "cleanup",
    "retention",
    "release",
)
CODES = frozenset(
    {
        "FAIL_REPORT",
        "FAIL_PROVENANCE",
        "FAIL_TARGET",
        "FAIL_SETUP",
        "FAIL_SIMULATION",
        "FAIL_RECONCILIATION",
        "FAIL_ATTRIBUTION",
        "FAIL_CLEANUP",
        "FAIL_RETAIN",
        "FAIL_RELEASE",
        "FAIL_INTERRUPTED",
        "FAIL_LEASE",
        "FAIL_RUN_UNKNOWN",
        "FAIL_LIMIT",
        "FAIL_REQUEST",
        "FAIL_BOOTSTRAP",
        "FAIL_LAUNCHER",
        "FAIL_RUN_EXISTS",
        "FAIL_DIRTY",
        "FAIL_INVARIANT",
        "FAIL_ERROR",
        "FAIL_STORAGE",
        "FAIL_VERIFY",
        "FAIL_SLOT",
        "FAIL_INSUFFICIENT",
        "FAIL_RETAINED_LIMIT",
    }
)
CHECKS = frozenset(
    {
        "inspect",
        "contamination",
        "duplicate",
        "missing",
        "unexpected",
        "catch_id",
        "caught_at",
        "provenance",
        "window",
        "history",
        "count",
        "fixture_photo",
        "created_fursuit",
        "avatar",
    }
)
ROLES = frozenset(
    {"owner0", "owner1", "catcher0", "catcher1", "catcher2", "catcher3", "outsider"}
)
CLEANUP = (
    "convention",
    "enrollment",
    "fursuit",
    "activation",
    "catch",
    "session",
    "credential",
    "image",
    "readmitted",
)


class ReportFailed(Exception):
    """Unapproved report or storage failure; carries no input details."""


def _require(condition: bool) -> None:
    if not condition:
        raise ReportFailed


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    _require(isinstance(value, dict) and set(cast(dict[str, object], value)) == keys)
    return cast(dict[str, Any], value)


def _count(value: object, maximum: int = 1000000) -> bool:
    return type(value) is int and 0 <= value <= maximum


def _number(value: object) -> bool:
    return (
        type(value) in (int, float)
        and math.isfinite(cast(float, value))
        and cast(float, value) >= 0
    )


def _uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None
    )


def _timestamp(value: object) -> bool:
    try:
        if not isinstance(value, str) or not value.endswith(("Z", "+00:00")):
            return False
        return datetime.fromisoformat(value).utcoffset() == UTC.utcoffset(None)
    except ValueError:
        return False


def unavailable(reason: str = "not_observed") -> dict[str, object]:
    return {"value": None, "reason": reason}


def observed(value: object) -> dict[str, object]:
    return {"value": value, "reason": None}


def _measurement(value: object, check: Callable[[Any], bool]) -> dict[str, Any]:
    result = _object(value, {"value", "reason"})
    if result["value"] is None:
        _require(
            result["reason"] in ("not_applicable", "not_implemented", "not_observed")
        )
    else:
        _require(result["reason"] is None and check(result["value"]))
    return result


def _source(value: object) -> None:
    source = _object(value, {"simulator_sha", "provenance", "reason", "runtime"})
    sha = _measurement(source["simulator_sha"], lambda v: _hex(v, 40))
    _require(source["provenance"] in ("clean", "unknown", "rejected"))
    if source["provenance"] == "clean":
        _require(source["reason"] is None and sha["value"] is not None)
    else:
        _require(source["reason"] in ("not_observed", "FAIL_PROVENANCE"))
    runtime = _object(source["runtime"], {"python", "httpx", "dependency_lock_sha256"})
    for key in ("python", "httpx"):
        _measurement(
            runtime[key],
            lambda v: (
                isinstance(v, str)
                and re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", v) is not None
            ),
        )
    _measurement(runtime["dependency_lock_sha256"], lambda v: _hex(v, 64))
    if source["provenance"] == "clean":
        _require(all(v["value"] is not None for v in runtime.values()))


def _identity(value: object, name: str) -> bool:
    identity = _object(value, {"source_sha", "deployment_id", "environment"})
    if name == "staging":
        return (
            _hex(identity["source_sha"], 40)
            and _uuid(identity["deployment_id"])
            and identity["environment"] == "staging"
        )
    return (
        identity["environment"] is None
        and identity["deployment_id"] is None
        and (identity["source_sha"] is None or _hex(identity["source_sha"], 40))
    )


def _target(value: object, config: Mapping[str, object]) -> None:
    target = _object(
        value, {"name", "origin", "starting", "final", "attribution", "reason"}
    )
    _require(target["name"] == config["target"])
    _require(
        target["origin"]
        == (STAGING_ORIGIN if target["name"] == "staging" else config["base_url"])
    )
    for key in ("starting", "final"):
        _measurement(target[key], lambda v: _identity(v, target["name"]))
    start, final = target["starting"]["value"], target["final"]["value"]
    if start is not None and final is not None and start == final:
        _require(target["attribution"] == "verified" and target["reason"] is None)
    elif start is not None and final is not None:
        _require(
            target["attribution"] == "unverified"
            and target["reason"] == "identity_changed"
        )
    else:
        _require(
            target["attribution"] in ("unverified", "not_observed")
            and target["reason"] in ("not_observed", "identity_unverified")
        )


def _population(scenario: str, config: dict[str, Any]) -> dict[str, object]:
    owners = config.get("owners", 2 if scenario == "journeys" else 0)
    fursuits = config.get("fursuits", 2 if scenario == "journeys" else 0)
    catchers = config.get("catchers", 4 if scenario == "journeys" else 0)
    outsiders = int(scenario == "journeys")
    roles = (
        {"player": config.get("count", 1)}
        if scenario in ("smoke", "pool-smoke")
        else {"owner": owners, "catcher": catchers}
    )
    if outsiders:
        roles["outsider"] = outsiders
    return {
        "roles": roles,
        "identities": sum(roles.values()),
        "fixtures": {
            "owners": owners,
            "fursuits_per_owner": fursuits,
            "catchers": catchers,
            "outsiders": outsiders,
            "fursuits": owners * fursuits,
        },
    }


def _limits(scenario: str) -> dict[str, object]:
    pool = scenario != "smoke"
    fixture = scenario in ("fixture-smoke", "journeys")
    definitions = {
        "response_bytes": (65536, None, "bytes", "per_response"),
        "request_timeout": (10.0, None, "seconds", "per_request"),
        "lease_ttl": (
            1800 if pool else None,
            None if pool else "not_applicable",
            "seconds",
            "lease",
        ),
        "launcher_timeout": (
            180 if pool else None,
            None if pool else "not_applicable",
            "seconds",
            "per_launcher",
        ),
        "retained_runs": (
            5 if fixture else None,
            None if fixture else "not_applicable",
            "runs",
            "before_allocation",
        ),
        "request_ceiling": (None, "not_implemented", "requests", "run"),
        "duration_ceiling": (None, "not_implemented", "seconds", "run"),
        "concurrency_ceiling": (None, "not_implemented", "requests", "run"),
    }
    return {
        key: dict(zip(("value", "reason", "unit", "scope"), values, strict=True))
        for key, values in definitions.items()
    }


def _results(value: object, scenario: str) -> None:
    result = _object(value, {"journeys", "checks", "cleanup"})
    journeys = _object(result["journeys"], {"items", "passed", "failed", "reason"})
    checks = _object(result["checks"], {"items", "count", "reason"})
    journey_items = cast(list[dict[str, Any]], journeys["items"])
    _require(
        isinstance(journeys["items"], list) and len(journey_items) <= len(JOURNEYS)
    )
    names: list[str] = []
    for raw in journey_items:
        item = _object(raw, {"name", "status"})
        _require(item["name"] in JOURNEYS and item["status"] in ("passed", "failed"))
        names.append(item["name"])
    _require(len(set(names)) == len(names))
    for status in ("passed", "failed"):
        _require(
            _count(journeys[status])
            and journeys[status] == sum(i["status"] == status for i in journey_items)
        )
    check_items = cast(list[dict[str, Any]], checks["items"])
    _require(
        isinstance(checks["items"], list)
        and len(check_items) <= 10000
        and _count(checks["count"], len(CHECKS))
    )
    for raw in check_items:
        item = _object(raw, {"check", "journey", "role", "expected", "observed"})
        _require(
            item["check"] in CHECKS
            and (item["journey"] is None or item["journey"] in JOURNEYS)
            and (item["role"] is None or item["role"] in ROLES)
            and _count(item["expected"])
            and _count(item["observed"])
        )
    _require(checks["count"] >= len({item["check"] for item in check_items}))
    if scenario != "journeys":
        _require(
            journeys
            == {"items": [], "passed": 0, "failed": 0, "reason": "not_applicable"}
            and checks == {"items": [], "count": 0, "reason": "not_applicable"}
        )
    else:
        _require(
            journeys["reason"] in (None, "not_observed")
            and checks["reason"] in (None, "not_observed")
        )
        if journeys["reason"] is not None:
            _require(not journeys["items"])
        if checks["reason"] is not None:
            _require(not checks["items"] and checks["count"] == 0)

    def cleanup(v: object) -> bool:
        return all(_count(n) for n in _object(v, set(CLEANUP)).values())

    _measurement(result["cleanup"], cleanup)
    if scenario not in ("fixture-smoke", "journeys"):
        _require(result["cleanup"] == unavailable("not_applicable"))


def validate_report(value: object) -> dict[str, object]:
    """Validate the entire external v1 document, returning an isolated copy."""
    try:
        report = _object(
            value,
            {
                "schema_version",
                "run_id",
                "scenario",
                "source",
                "target",
                "timing",
                "population",
                "profile",
                "limits",
                "phases",
                "correctness",
                "results",
                "performance",
                "outcome",
                "failure",
            },
        )
        _require(
            type(report["schema_version"]) is int
            and report["schema_version"] == 1
            and _uuid(report["run_id"])
        )
        scenario = _object(
            report["scenario"],
            {
                "id",
                "version",
                "descriptor",
                "descriptor_digest",
                "seed",
                "consumes_randomness",
                "configuration",
            },
        )
        _require(
            type(scenario["seed"]) is int
            and scenario["consumes_randomness"] is False
            and isinstance(scenario["configuration"], dict)
        )
        config = cast(dict[str, Any], scenario["configuration"])
        resolved = cast(
            dict[str, Any],
            resolve_scenario(scenario["id"], scenario["version"], config),
        )
        _require(
            all(
                canonical(scenario[key]) == canonical(resolved[key]) for key in resolved
            )
        )
        _source(report["source"])
        _target(report["target"], config)
        timing = _object(
            report["timing"], {"started_at", "ended_at", "duration_seconds"}
        )
        _require(_timestamp(timing["started_at"]))
        _measurement(timing["ended_at"], _timestamp)
        _measurement(timing["duration_seconds"], _number)
        _require(
            canonical(report["population"])
            == canonical(_population(scenario["id"], config))
        )
        _require(canonical(report["limits"]) == canonical(_limits(scenario["id"])))
        _require(
            report["profile"]
            == {
                "operations": resolved["descriptor"]["operations"],
                "waits_seconds": resolved["descriptor"]["waits_seconds"],
                "load_ramp": unavailable("not_implemented"),
            }
        )
        phases = _object(report["phases"], set(STAGES))
        inapplicable: set[str] = (
            {"cleanup", "retention", "release"}
            if scenario["id"] == "smoke"
            else ({"cleanup", "retention"} if scenario["id"] == "pool-smoke" else set())
        )
        for name, raw in phases.items():
            phase = _object(
                raw, {"status", "started_at", "ended_at", "duration_seconds", "code"}
            )
            status = phase["status"]
            _require(
                status
                in (
                    "running",
                    "passed",
                    "failed",
                    "interrupted",
                    "not_reached",
                    "not_applicable",
                )
            )
            _require(phase["code"] is None or phase["code"] in CODES)
            _require((name in inapplicable) == (status == "not_applicable"))
            for key, checker in (
                ("started_at", _timestamp),
                ("ended_at", _timestamp),
                ("duration_seconds", _number),
            ):
                _measurement(phase[key], checker)
                if status in ("not_reached", "not_applicable"):
                    _require(
                        phase[key]
                        == unavailable(
                            "not_applicable"
                            if status == "not_applicable"
                            else "not_observed"
                        )
                    )
                elif key == "started_at" or status != "running":
                    _require(phase[key]["value"] is not None)
                else:
                    _require(phase[key] == unavailable())
            if status in ("passed", "running", "not_reached", "not_applicable"):
                _require(phase["code"] is None)
        if report["source"]["provenance"] != "clean":
            _require(report["correctness"] == "not_observed")
            _require(
                report["target"]["starting"] == unavailable()
                and report["target"]["final"] == unavailable()
            )
            _require(
                all(
                    p["status"] in ("not_reached", "not_applicable")
                    for s, p in phases.items()
                    if s != "provenance"
                )
            )
        if phases["provenance"]["status"] == "passed":
            _require(report["source"]["provenance"] == "clean")
        if phases["attribution"]["status"] == "passed":
            _require(report["target"]["attribution"] == "verified")
        _require(report["correctness"] in ("passed", "failed", "not_observed"))
        _results(report["results"], scenario["id"])
        if report["correctness"] == "passed":
            _require(report["source"]["provenance"] == "clean")
            _require(report["target"]["starting"]["value"] is not None)
            _require(
                all(
                    phases[stage]["status"] == "passed"
                    for stage in (
                        "provenance",
                        "target",
                        "setup",
                        "simulation",
                        "reconciliation",
                    )
                )
            )
            if scenario["id"] == "journeys":
                _require(
                    report["results"]["journeys"]
                    == {
                        "items": [
                            {"name": name, "status": "passed"} for name in JOURNEYS
                        ],
                        "passed": len(JOURNEYS),
                        "failed": 0,
                        "reason": None,
                    }
                )
                _require(
                    report["results"]["checks"]
                    == {
                        "items": [],
                        "count": len(CHECKS),
                        "reason": None,
                    }
                )
        performance = _object(
            report["performance"],
            {
                "duration_seconds",
                "throughput",
                "latency_percentiles",
                "resource_context",
            },
        )
        _measurement(performance["duration_seconds"], _number)
        _require(
            performance
            == {
                "duration_seconds": timing["duration_seconds"],
                "throughput": unavailable("not_implemented"),
                "latency_percentiles": unavailable("not_implemented"),
                "resource_context": unavailable(),
            }
        )
        _require(report["outcome"] in ("running", "passed", "failed", "interrupted"))
        if report["failure"] is not None:
            failure = _object(report["failure"], {"stage", "code"})
            _require(
                failure["stage"] in (*STAGES, "report") and failure["code"] in CODES
            )
        if report["outcome"] == "running":
            _require(
                timing["ended_at"] == unavailable()
                and timing["duration_seconds"] == unavailable()
            )
        else:
            _require(
                timing["ended_at"]["value"] is not None
                and timing["duration_seconds"]["value"] is not None
                and all(p["status"] != "running" for p in phases.values())
            )
        if report["outcome"] == "passed":
            _require(
                report["failure"] is None
                and report["correctness"] == "passed"
                and report["source"]["provenance"] == "clean"
                and report["target"]["attribution"] == "verified"
            )
            _require(
                all(
                    phases[s]["status"] == "passed"
                    for s in STAGES
                    if s not in inapplicable and s != "retention"
                )
            )
            _require(
                not any(
                    p["status"] in ("failed", "interrupted") for p in phases.values()
                )
            )
            _require(
                not report["results"]["journeys"]["failed"]
                and not report["results"]["checks"]["items"]
            )
            if scenario["id"] in ("fixture-smoke", "journeys"):
                _require(report["results"]["cleanup"]["value"] is not None)
        elif report["outcome"] in ("failed", "interrupted"):
            _require(report["failure"] is not None)
        canonical(report)
        return copy.deepcopy(report)
    except (
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        ScenarioRejected,
    ):
        raise ReportFailed from None


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ReportFailed
        result[key] = value
    return result


def load_report(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        _require(len(data) <= 1024 * 1024)
        return validate_report(
            json.loads(
                data.decode("utf-8"),
                object_pairs_hook=_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ReportFailed()),
            )
        )
    except (OSError, ValueError, TypeError, RecursionError):
        raise ReportFailed from None


def utc_now() -> datetime:
    return datetime.now(UTC)


class RunReport:
    """Recorder with validated adapters; persistence failures never skip release."""

    def __init__(
        self,
        output_dir: Path,
        scenario_id: str,
        *,
        scenario_version: int = 1,
        seed: int = 0,
        config: Mapping[str, object],
        run_id: str | None = None,
        wall_clock: Callable[[], datetime] = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock, self._monotonic = wall_clock, monotonic
        self._run_id = run_id if run_id is not None else str(uuid.uuid4())
        self._path = output_dir / f"{self._run_id}.json"
        _require(_uuid(self._run_id) and type(seed) is int)
        self.write_failed = False
        self._finished = False
        self._starts: dict[str, float] = {}
        self._started = self._tick()
        try:
            resolved = cast(
                dict[str, Any], resolve_scenario(scenario_id, scenario_version, config)
            )
        except ScenarioRejected:
            raise ReportFailed from None
        configuration = resolved["configuration"]
        inapplicable: set[str] = (
            {"cleanup", "retention", "release"}
            if scenario_id == "smoke"
            else ({"cleanup", "retention"} if scenario_id == "pool-smoke" else set())
        )
        self._value: dict[str, Any] = {
            "schema_version": 1,
            "run_id": self._run_id,
            "scenario": {**resolved, "seed": seed, "consumes_randomness": False},
            "source": {
                "simulator_sha": unavailable(),
                "provenance": "unknown",
                "reason": "not_observed",
                "runtime": {
                    k: unavailable()
                    for k in ("python", "httpx", "dependency_lock_sha256")
                },
            },
            "target": {
                "name": configuration["target"],
                "origin": STAGING_ORIGIN
                if configuration["target"] == "staging"
                else configuration["base_url"],
                "starting": unavailable(),
                "final": unavailable(),
                "attribution": "not_observed",
                "reason": "not_observed",
            },
            "timing": {
                "started_at": self._wall(),
                "ended_at": unavailable(),
                "duration_seconds": unavailable(),
            },
            "population": _population(scenario_id, configuration),
            "profile": {
                "operations": resolved["descriptor"]["operations"],
                "waits_seconds": resolved["descriptor"]["waits_seconds"],
                "load_ramp": unavailable("not_implemented"),
            },
            "limits": _limits(scenario_id),
            "phases": {
                s: {
                    "status": "not_applicable" if s in inapplicable else "not_reached",
                    **{
                        k: unavailable(
                            "not_applicable" if s in inapplicable else "not_observed"
                        )
                        for k in ("started_at", "ended_at", "duration_seconds")
                    },
                    "code": None,
                }
                for s in STAGES
            },
            "correctness": "not_observed",
            "results": {
                "journeys": {
                    "items": [],
                    "passed": 0,
                    "failed": 0,
                    "reason": "not_observed"
                    if scenario_id == "journeys"
                    else "not_applicable",
                },
                "checks": {
                    "items": [],
                    "count": 0,
                    "reason": "not_observed"
                    if scenario_id == "journeys"
                    else "not_applicable",
                },
                "cleanup": unavailable(
                    "not_observed"
                    if scenario_id in ("fixture-smoke", "journeys")
                    else "not_applicable"
                ),
            },
            "performance": {
                "duration_seconds": unavailable(),
                "throughput": unavailable("not_implemented"),
                "latency_percentiles": unavailable("not_implemented"),
                "resource_context": unavailable(),
            },
            "outcome": "running",
            "failure": None,
        }
        validate_report(self._value)
        reserved = False
        try:
            if any(p.is_symlink() for p in (output_dir, *output_dir.parents)):
                raise ReportFailed
            output_dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            reserved = True
            os.close(fd)
            self._snapshot(initial=True)
        except (OSError, ReportFailed):
            if reserved:
                self._path.unlink(missing_ok=True)
            raise ReportFailed from None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def run_id(self) -> str:
        return self._run_id

    def _wall(self) -> str:
        value = self._clock()
        _require(value.tzinfo is not None and value.utcoffset() == UTC.utcoffset(None))
        return value.isoformat().replace("+00:00", "Z")

    def _tick(self) -> float:
        value = self._monotonic()
        _require(_number(value))
        return value

    def _snapshot(self, *, initial: bool = False) -> None:
        temporary: Path | None = None
        try:
            data = canonical(validate_report(self._value))
            _require(len(data) <= 1024 * 1024)
            if self._path.is_symlink() or not self._path.is_file():
                raise ReportFailed
            fd, name = tempfile.mkstemp(prefix=".snapshot-", dir=self._path.parent)
            temporary = Path(name)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        except (OSError, ReportFailed):
            self.write_failed = True
            if initial:
                raise ReportFailed from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    self.write_failed = True
                    if initial:
                        raise ReportFailed from None

    def _update(self, section: str, value: object) -> None:
        _require(not self._finished)
        candidate = {**self._value, section: copy.deepcopy(value)}
        validate_report(candidate)
        self._value = candidate
        self._snapshot()

    def record_source(self, source: Mapping[str, object]) -> None:
        self._update("source", dict(source))

    def record_target(
        self,
        name: str,
        origin: str,
        identity: Mapping[str, object],
        *,
        final: bool = False,
    ) -> None:
        target = copy.deepcopy(self._value["target"])
        _require(name == target["name"] and origin == target["origin"])
        _require(_identity(dict(identity), name))
        target["final" if final else "starting"] = observed(dict(identity))
        start, end = target["starting"]["value"], target["final"]["value"]
        if start is not None and end is not None:
            target["attribution"] = "verified" if start == end else "unverified"
            target["reason"] = None if start == end else "identity_changed"
        else:
            target["attribution"], target["reason"] = (
                "unverified",
                "identity_unverified",
            )
        self._update("target", target)

    def set_correctness(self, status: str) -> None:
        self._update("correctness", status)

    def record_results(
        self,
        *,
        journeys: Mapping[str, object] | None = None,
        checks: Mapping[str, object] | None = None,
        cleanup: Mapping[str, object] | None = None,
    ) -> None:
        results = copy.deepcopy(self._value["results"])
        for name, value in (
            ("journeys", journeys),
            ("checks", checks),
            ("cleanup", cleanup),
        ):
            if value is not None:
                results[name] = dict(value)
        self._update("results", results)

    def begin(self, stage: str) -> None:
        _require(stage in STAGES and not self._finished)
        phases = copy.deepcopy(self._value["phases"])
        _require(phases[stage]["status"] == "not_reached")
        start = self._tick()
        phases[stage] = {
            "status": "running",
            "started_at": observed(self._wall()),
            "ended_at": unavailable(),
            "duration_seconds": unavailable(),
            "code": None,
        }
        self._update("phases", phases)
        self._starts[stage] = start

    def end(self, stage: str, status: str, code: str | None = None) -> None:
        _require(
            stage in self._starts
            and status in ("passed", "failed", "interrupted")
            and (code is None or code in CODES)
        )
        _require(status != "passed" or code is None)
        elapsed = self._tick() - self._starts[stage]
        _require(_number(elapsed))
        phases = copy.deepcopy(self._value["phases"])
        phases[stage].update(
            status=status,
            ended_at=observed(self._wall()),
            duration_seconds=observed(elapsed),
            code=code,
        )
        candidate = {**self._value, "phases": phases}
        if status in ("failed", "interrupted") and candidate["failure"] is None:
            candidate["failure"] = {
                "stage": stage,
                "code": code
                or (
                    "FAIL_INTERRUPTED"
                    if status == "interrupted"
                    else "FAIL_" + ("RETAIN" if stage == "retention" else stage.upper())
                ),
            }
        validate_report(candidate)
        self._value = candidate
        del self._starts[stage]
        self._snapshot()

    def finish(self, exit_code: int) -> int:
        _require(type(exit_code) is int)
        if self._finished:
            return self._result
        for stage in tuple(self._starts):
            self.end(stage, "interrupted", "FAIL_INTERRUPTED")
        value = self._value
        elapsed = self._tick() - self._started
        _require(_number(elapsed))
        value["timing"]["ended_at"] = observed(self._wall())
        value["timing"]["duration_seconds"] = observed(elapsed)
        value["performance"]["duration_seconds"] = observed(elapsed)
        if self.write_failed:
            value["failure"] = {"stage": "report", "code": "FAIL_REPORT"}
        interrupted = exit_code == 130 or any(
            p["status"] == "interrupted" for p in value["phases"].values()
        )
        value["outcome"] = (
            "interrupted"
            if interrupted
            else ("failed" if exit_code or value["failure"] else "passed")
        )
        if value["outcome"] == "passed":
            try:
                validate_report(value)
            except ReportFailed:
                value["outcome"] = "failed"
                value["failure"] = {"stage": "attribution", "code": "FAIL_ATTRIBUTION"}
        elif value["failure"] is None:
            value["failure"] = {
                "stage": "simulation",
                "code": "FAIL_INTERRUPTED" if interrupted else "FAIL_SIMULATION",
            }
        self._snapshot()
        self._result = (
            exit_code
            if exit_code
            else (0 if value["outcome"] == "passed" and not self.write_failed else 1)
        )
        self._finished = True
        return self._result
