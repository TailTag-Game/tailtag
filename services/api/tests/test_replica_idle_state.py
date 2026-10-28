"""Offline contract for the hybrid replica control-plane reader (#359 U4).

Cloud Monitoring, the Neon API and `gcloud` are faked at
`urllib.request.OpenerDirector.open` and `subprocess.run`, as in the job runner
tests. Nothing here reaches a network or a cloud project.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_api_replica_runners import BODY_SECRET, PROJECT, TOKEN, FakeResponse

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import replica_idle_state as reader

NEON_PROJECT = "synthetic-neon-12345678"
NEON_KEY = "synthetic-neon-key"
ENDPOINT_ID = "ep-synthetic-endpoint-1"
FAILURE = '{"result": "FAIL_STATE"}\n'


class Planes:
    """Fake Cloud Monitoring and Neon API behind urllib, plus `gcloud`."""

    def __init__(self) -> None:
        self.requests: list[dict[str, str | None]] = []
        self.queries: list[dict[str, list[str]]] = []
        self.job_series: list[dict[str, Any]] = [
            {"points": [{"value": {"doubleValue": 3.0}}]}
        ]
        self.instance_series: list[dict[str, Any]] = [
            {
                "metric": {"labels": {"state": "idle"}},
                # Newest first. The oldest point must never be read.
                "points": [
                    {"value": {"int64Value": "1"}},
                    {"value": {"int64Value": "3"}},
                ],
            },
            {
                "metric": {"labels": {"state": "active"}},
                "points": [{"value": {"int64Value": "0"}}],
            },
        ]
        self.billable_series: list[dict[str, Any]] = [
            {"points": [{"value": {"doubleValue": 42.5}}]},
            {"points": [{"value": {"doubleValue": 7.25}}]},
        ]
        self.endpoints: list[dict[str, Any]] = [
            {
                "id": ENDPOINT_ID,
                "type": "read_write",
                "current_state": "idle",
                "suspended_at": "2026-10-28T10:05:00Z",
                "last_active": "2026-10-28T10:00:00Z",
            },
            {"id": "ep-read-only", "type": "read_only", "current_state": "active"},
        ]

    def open(self, request: Any, *args: Any, **kwargs: Any) -> FakeResponse:
        url = cast(str, request.full_url)
        authorization = dict(request.header_items()).get("Authorization")
        self.requests.append(
            {"url": url, "method": request.get_method(), "auth": authorization}
        )
        parts = urllib.parse.urlsplit(url)
        if parts.netloc == "monitoring.googleapis.com":
            assert authorization == f"Bearer {TOKEN}"
            query = urllib.parse.parse_qs(parts.query)
            self.queries.append(query)
            metric = query["filter"][0]
            if "instance_count" in metric:
                series = self.instance_series
            elif "cloud_run_job" in metric:
                series = self.job_series
            else:
                series = self.billable_series
            return FakeResponse(json.dumps({"timeSeries": series}).encode())
        if parts.netloc == "console.neon.tech":
            assert authorization == f"Bearer {NEON_KEY}"
            if parts.path.endswith("/endpoints"):
                return FakeResponse(json.dumps({"endpoints": self.endpoints}).encode())
            return FakeResponse(
                json.dumps(
                    {
                        "project": {
                            "id": NEON_PROJECT,
                            "compute_time_seconds": 3600,
                            "active_time_seconds": 900,
                            "cpu_used_sec": 120,
                            "consumption_period_start": "2026-10-01T00:00:00Z",
                        }
                    }
                ).encode()
            )
        raise urllib.error.HTTPError(
            url, 404, "unexpected", cast(Any, {}), io.BytesIO(BODY_SECRET.encode())
        )

    def run(
        self, args: Any, *pargs: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        argv = [str(part) for part in args]
        assert "print-access-token" in argv
        return subprocess.CompletedProcess(argv, 0, f"{TOKEN}\n", "")


@pytest.fixture
def planes(monkeypatch: pytest.MonkeyPatch) -> Planes:
    fake = Planes()

    def opener_open(_opener: object, request: Any, *args: Any, **kwargs: Any) -> Any:
        return fake.open(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", opener_open)
    monkeypatch.setattr(subprocess, "run", fake.run)

    def which(name: str) -> str:
        return name

    monkeypatch.setattr(reader._job.shutil, "which", which)  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setenv("NEON_API_KEY", NEON_KEY)
    return fake


def call(capsys: pytest.CaptureFixture[str], *mode: str) -> tuple[int, str]:
    code = reader.main(["--project", PROJECT, "--neon-project", NEON_PROJECT, *mode])
    out = capsys.readouterr().out
    return code, out


def assert_private_values_absent(out: str) -> None:
    for value in (
        PROJECT,
        NEON_PROJECT,
        ENDPOINT_ID,
        TOKEN,
        NEON_KEY,
        BODY_SECRET,
        "https://",
    ):
        assert value not in out


def test_state_reads_only_the_control_planes(
    planes: Planes, capsys: pytest.CaptureFixture[str]
) -> None:
    """M2: the instance count by state and the read-write compute state."""
    code, out = call(capsys, "state")

    assert code == 0
    result = json.loads(out)
    assert result["kind"] == "replica-idle-state"
    assert result["instances"] == {"active": 0, "idle": 1}
    assert result["database"] == {
        "current_state": "idle",
        "suspended_at": "2026-10-28T10:05:00Z",
        "last_active": "2026-10-28T10:00:00Z",
    }
    assert [q["aggregation.perSeriesAligner"] for q in planes.queries] == [
        ["ALIGN_MAX"]
    ]
    hosts = {urllib.parse.urlsplit(cast(str, r["url"])).netloc for r in planes.requests}
    assert hosts == {"monitoring.googleapis.com", "console.neon.tech"}
    assert all(r["method"] == "GET" for r in planes.requests)
    monitoring = next(
        cast(str, r["url"]) for r in planes.requests if "monitoring" in str(r["url"])
    )
    assert 'service_name="tailtag-api-replica"' in urllib.parse.unquote(monitoring)
    assert_private_values_absent(out)


def test_usage_sums_billable_time_and_reports_neon_counters_as_an_estimate(
    planes: Planes, capsys: pytest.CaptureFixture[str]
) -> None:
    """M2: AC22 inputs. Neon counters are usage, not billing."""
    code, out = call(
        capsys,
        "usage",
        "--start",
        "2026-10-28T10:00:00Z",
        "--end",
        "2026-10-28T10:20:00Z",
    )

    assert code == 0
    result = json.loads(out)
    assert result["estimate"] is True
    assert result["cloud_run_billable_instance_seconds"] == 49.75
    assert result["cloud_run_job_billable_instance_seconds"] == 3.0
    assert {q["aggregation.perSeriesAligner"][0] for q in planes.queries} == {
        "ALIGN_SUM"
    }
    job_filter = next(
        q["filter"][0] for q in planes.queries if "cloud_run_job" in q["filter"][0]
    )
    assert 'job_name=starts_with("tailtag-replica-")' in job_filter
    assert result["neon"] == {
        "compute_time_seconds": 3600,
        "active_time_seconds": 900,
        "cpu_used_sec": 120,
        "consumption_period_start": "2026-10-01T00:00:00Z",
    }
    monitoring = next(
        cast(str, r["url"]) for r in planes.requests if "monitoring" in str(r["url"])
    )
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(monitoring).query)
    assert query["aggregation.alignmentPeriod"] == ["1200s"]
    assert query["aggregation.crossSeriesReducer"] == ["REDUCE_SUM"]
    assert_private_values_absent(out)


@pytest.mark.parametrize(
    "case",
    [
        "two-read-write",
        "unknown-state",
        "no-neon-key",
        "bad-window",
        "bad-time",
        "bad-project",
    ],
)
def test_ambiguous_or_invalid_readings_print_one_fixed_line(
    planes: Planes,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: str,
) -> None:
    mode: tuple[str, ...] = ("state",)
    if case == "two-read-write":
        planes.endpoints.append({**planes.endpoints[0], "id": "ep-second"})
    elif case == "unknown-state":
        planes.instance_series[0]["metric"]["labels"]["state"] = "warm"
    elif case == "no-neon-key":
        monkeypatch.delenv("NEON_API_KEY")
    elif case == "bad-window":
        mode = (
            "usage",
            "--start",
            "2026-10-28T10:20:00Z",
            "--end",
            "2026-10-28T10:00:00Z",
        )
    elif case == "bad-time":
        mode = ("usage", "--start", "yesterday", "--end", "2026-10-28T10:00:00Z")

    if case == "bad-project":
        code = reader.main(
            ["--project", "Bad_Project", "--neon-project", NEON_PROJECT, "state"]
        )
        out = capsys.readouterr().out
    else:
        code, out = call(capsys, *mode)

    assert (code, out) == (1, FAILURE)
    if case in {"no-neon-key", "bad-time", "bad-project"}:
        assert planes.requests == []


def test_neon_mode_reads_only_the_neon_counters(
    planes: Planes, capsys: pytest.CaptureFixture[str]
) -> None:
    """M2, AC22: the before-run reading needs no window and no Google call."""
    code, out = call(capsys, "neon")

    assert code == 0
    result = json.loads(out)
    assert result["kind"] == "replica-neon-usage"
    assert result["neon"]["compute_time_seconds"] == 3600
    assert {
        urllib.parse.urlsplit(cast(str, r["url"])).netloc for r in planes.requests
    } == {"console.neon.tech"}
    assert_private_values_absent(out)
