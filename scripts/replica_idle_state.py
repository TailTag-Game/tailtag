"""Read hybrid replica idle state and usage from the control planes (#359).

A control plane is the provider API that manages a resource. This script never
sends a request to the replica service or its database, so reading the state
cannot wake either of them.

    task replica-idle-state -- --project <PROJECT_ID> --neon-project <NEON_ID> state
    task replica-idle-state -- --project <PROJECT_ID> --neon-project <NEON_ID> \\
        usage --start 2026-10-28T10:00:00Z --end 2026-10-28T10:20:00Z

It needs the owner `gcloud` login and `NEON_API_KEY` in the environment. It
prints one JSON line with no project ID, endpoint ID, token or URL. Every fault
prints one fixed line.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final, NoReturn, cast

from scripts import api_replica_job as _job

SERVICE: Final = "tailtag-api-replica"
MONITORING: Final = "https://monitoring.googleapis.com/v3"
NEON_API: Final = "https://console.neon.tech/api/v2"
FAILURE: Final = '{"result": "FAIL_STATE"}'
_NEON_PROJECT: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,62}[a-z0-9]")
_TIME: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
# Instance count is sampled every 60 s and visible after up to 120 s, so a
# five-minute look-back always holds at least one point.
_STATE_LOOKBACK: Final = timedelta(minutes=5)
_NEON_COUNTERS: Final = ("compute_time_seconds", "active_time_seconds", "cpu_used_sec")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError


def _stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


_SERVICE_RESOURCE: Final = (
    f'resource.type="cloud_run_revision" AND resource.labels.service_name="{SERVICE}"'
)
_JOB_RESOURCE: Final = (
    'resource.type="cloud_run_job"'
    ' AND resource.labels.job_name=starts_with("tailtag-replica-")'
)


def _series(
    google: _job._Session,  # pyright: ignore[reportPrivateUsage]
    project: str,
    metric: str,
    start: datetime,
    end: datetime,
    aggregation: Mapping[str, str],
    resource: str = _SERVICE_RESOURCE,
) -> list[dict[str, object]]:
    query = urllib.parse.urlencode(
        {
            "filter": (
                f'metric.type="run.googleapis.com/container/{metric}" AND {resource}'
            ),
            "interval.startTime": _stamp(start),
            "interval.endTime": _stamp(end),
            **aggregation,
        }
    )
    listing = google.call(f"{MONITORING}/projects/{project}/timeSeries?{query}", None)
    series = listing.get("timeSeries", [])
    if not isinstance(series, list):
        raise TypeError
    return cast(list[dict[str, object]], series)


def _points(series: Mapping[str, object]) -> list[dict[str, object]]:
    points = series.get("points", [])
    if not isinstance(points, list):
        raise TypeError
    return cast(list[dict[str, object]], points)


def _value(point: Mapping[str, object], kind: str) -> float:
    value = cast(dict[str, object], point["value"])[kind]
    return float(cast(str | float, value))


def _endpoint(neon: _job._Session, neon_project: str) -> dict[str, object]:  # pyright: ignore[reportPrivateUsage]
    listing = neon.call(f"{NEON_API}/projects/{neon_project}/endpoints", None)
    endpoints = [
        cast(dict[str, object], item)
        for item in cast(list[object], listing.get("endpoints", []))
        if isinstance(item, dict) and item.get("type") == "read_write"
    ]
    if len(endpoints) != 1:
        raise ValueError
    return endpoints[0]


def read_state(
    google: _job._Session,  # pyright: ignore[reportPrivateUsage]
    neon: _job._Session,  # pyright: ignore[reportPrivateUsage]
    project: str,
    neon_project: str,
    now: datetime,
) -> dict[str, object]:
    """The latest instance count by state and the database compute state."""
    instances = {"active": 0, "idle": 0}
    series = _series(
        google,
        project,
        "instance_count",
        now - _STATE_LOOKBACK,
        now,
        {
            "aggregation.alignmentPeriod": "60s",
            "aggregation.perSeriesAligner": "ALIGN_MAX",
        },
    )
    for item in series:
        state = cast(dict[str, object], item.get("metric", {})).get("labels", {})
        name = cast(dict[str, object], state).get("state")
        points = _points(item)
        if name not in instances or not points:
            raise ValueError
        # Points arrive newest first.
        instances[cast(str, name)] += int(_value(points[0], "int64Value"))
    endpoint = _endpoint(neon, neon_project)
    return {
        "kind": "replica-idle-state",
        "observed_at": _stamp(now),
        "instances": instances,
        "database": {
            name: endpoint.get(name)
            for name in ("current_state", "suspended_at", "last_active")
        },
    }


def read_usage(
    google: _job._Session,  # pyright: ignore[reportPrivateUsage]
    neon: _job._Session,  # pyright: ignore[reportPrivateUsage]
    project: str,
    neon_project: str,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    """Cloud Run billable instance time in the window, and Neon usage counters now.

    The Neon counters are cumulative for its period, so a run's use is the
    difference between two readings. Neon calls them usage, not billing.
    """
    if end <= start:
        raise ValueError
    seconds = int((end - start).total_seconds())
    aggregation = {
        "aggregation.alignmentPeriod": f"{seconds}s",
        "aggregation.perSeriesAligner": "ALIGN_SUM",
        "aggregation.crossSeriesReducer": "REDUCE_SUM",
    }

    def billable(resource: str) -> float:
        series = _series(
            google, project, "billable_instance_time", start, end, aggregation, resource
        )
        return round(
            sum(
                _value(point, "doubleValue")
                for item in series
                for point in _points(item)
            ),
            3,
        )

    return {
        "kind": "replica-usage",
        "estimate": True,
        "start": _stamp(start),
        "end": _stamp(end),
        "cloud_run_billable_instance_seconds": billable(_SERVICE_RESOURCE),
        "cloud_run_job_billable_instance_seconds": billable(_JOB_RESOURCE),
        "neon": read_neon(neon, neon_project),
    }


def read_neon(neon: _job._Session, neon_project: str) -> dict[str, object]:  # pyright: ignore[reportPrivateUsage]
    """The Neon usage counters now. They are totals for the Neon period."""
    listing = neon.call(f"{NEON_API}/projects/{neon_project}", None)
    value = cast(dict[str, object], listing["project"])
    return {name: value[name] for name in (*_NEON_COUNTERS, "consumption_period_start")}


def _time(value: str) -> datetime:
    if _TIME.fullmatch(value) is None:
        raise ValueError
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def main(argv: Sequence[str] | None = None) -> int:
    """Print one control-plane reading, or one fixed failure line."""
    try:
        parser = _Parser(add_help=False)
        parser.add_argument("--project", required=True)
        parser.add_argument("--neon-project", required=True)
        modes = parser.add_subparsers(dest="mode", required=True)
        modes.add_parser("state", add_help=False)
        modes.add_parser("neon", add_help=False)
        usage = modes.add_parser("usage", add_help=False)
        usage.add_argument("--start", required=True)
        usage.add_argument("--end", required=True)
        arguments = parser.parse_args(argv)
        _job.valid_project(arguments.project)
        if _NEON_PROJECT.fullmatch(arguments.neon_project) is None:
            raise ValueError
        key = os.environ.get("NEON_API_KEY", "")
        if not key:
            raise ValueError
        neon = _job._Session(key)  # pyright: ignore[reportPrivateUsage]
        if arguments.mode == "neon":
            # The before-run reading needs no window and no Google call.
            result: dict[str, object] = {
                "kind": "replica-neon-usage",
                "estimate": True,
                "observed_at": _stamp(datetime.now(UTC)),
                "neon": read_neon(neon, arguments.neon_project),
            }
            print(json.dumps(result, sort_keys=True))
            return 0
        google = _job._Session()  # pyright: ignore[reportPrivateUsage]
        if arguments.mode == "state":
            result = read_state(
                google,
                neon,
                arguments.project,
                arguments.neon_project,
                datetime.now(UTC),
            )
        else:
            result = read_usage(
                google,
                neon,
                arguments.project,
                arguments.neon_project,
                _time(arguments.start),
                _time(arguments.end),
            )
        line = json.dumps(result, sort_keys=True)
    except Exception:  # noqa: BLE001
        print(FAILURE)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
