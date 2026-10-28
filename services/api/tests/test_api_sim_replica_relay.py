"""Offline acceptance contract for the hybrid replica simulator relay (#359 U2).

The Cloud Run, Cloud Logging and public health boundaries are faked at
`urllib.request.OpenerDirector.open`, as in the job runner tests. Time is
faked through `time.monotonic` and `time.sleep`. Nothing here reaches a
network, a cloud project or `gcloud`.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from tests import replica_contract
from tests.semgrep_support import task_dry_run
from tests.test_api_replica_runners import (
    BODY_SECRET,
    JOBS,
    PROJECT,
    SOURCE_SHA,
    TOKEN,
    FakeCloud,
    FakeResponse,
    result_entry,
    result_payload,
    write_config,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import api_sim_replica_relay as relay

HOST = replica_contract.RUN_APP_HOST
REVISION = replica_contract.SERVICE_REVISION
SERVICE_IDENTITY = {
    "source_sha": SOURCE_SHA,
    "deployment_id": REVISION,
    "environment": "replica",
}
VIEW = (
    f"projects/{PROJECT}/locations/global/buckets/_Default/views/simrelay-job-results"
)
FAILURE_LINE = '{"data": {}, "result": "FAIL_LAUNCHER"}\n'
# Cloud Run refuses a longer env override value (#355 AC16).
OVERRIDE_CAP = 32_768

REQUESTS: dict[str, dict[str, object]] = {
    "pool": {"operation": "status", "pool": "replica1", "arguments": {}},
    "fixture": {"operation": "status", "arguments": {"run_id": "x"}},
    "inspect": {"operation": "inspect", "arguments": {"pool": "replica1"}},
}
# One result per channel that passes that channel's existing validator.
RESULTS: dict[str, tuple[str, dict[str, object]]] = {
    "pool": ("PASS", {"available": 3, "indexes": [0, 1, 2]}),
    "fixture": ("PASS", {"status": "provisioned", "catch": 0}),
    "inspect": ("FAIL_LEASE", {}),
}


class RelayCloud(FakeCloud):
    """The job runner fake plus the public service host and execution cancel."""

    clock: float

    def __init__(self) -> None:
        super().__init__()
        self.identities: list[object] = [SERVICE_IDENTITY, SERVICE_IDENTITY]
        self.ready: object = {"status": "ok"}
        self.cancels: list[str] = []
        self.cancelled_at: list[float] = []
        self.hang_from: float | None = None

    def open(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        url = request if isinstance(request, str) else request.full_url
        if url.startswith(f"https://{HOST}/"):
            self.requests.append({"url": url, "method": "GET", "body": None})
            if url.endswith("/health/identity"):
                return _public(url, self.identities.pop(0))
            if url.endswith("/health/ready"):
                return _public(url, self.ready)
        if (
            self.hang_from is not None
            and self.clock >= self.hang_from
            and "/executions/" in url
            and not url.endswith(":cancel")
        ):
            # Near the deadline, a poll hangs until its own timeout, then fails.
            self.requests.append({"url": url, "method": "GET", "body": None})
            self.clock += float(kwargs["timeout"])
            raise TimeoutError
        if url.endswith(":cancel"):
            self.requests.append({"url": url, "method": "POST", "body": {}})
            self.cancels.append(url)
            self.cancelled_at.append(self.clock)
            return FakeResponse(b"{}")
        return super().open(request, *args, **kwargs)


def _public(url: str, value: object) -> FakeResponse:
    response = FakeResponse(json.dumps(value).encode())
    response.geturl = lambda: url  # type: ignore[method-assign]
    return response


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> RelayCloud:
    fake = RelayCloud()
    replica_contract.install_replica_pins(monkeypatch)

    def opener_open(_opener: object, request: Any, *args: Any, **kwargs: Any) -> Any:
        return fake.open(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", opener_open)
    monkeypatch.setattr(subprocess, "run", fake.run)

    def sleep(seconds: float) -> None:
        fake.clock += max(seconds, 0.001)
        assert fake.clock < 24 * 3600, "relay never gives up"

    monkeypatch.setattr(time, "sleep", sleep)
    monkeypatch.setattr(time, "monotonic", lambda: fake.clock)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    session = private / "session.json"
    write_config(session, {})
    session.write_text(json.dumps({"project": PROJECT, "host": HOST}))
    token = private / "token"
    write_config(token, {})
    token.write_bytes(TOKEN.encode() + b"\n")
    monkeypatch.setenv("TAILTAG_REPLICA_SESSION_FILE", str(session))
    monkeypatch.setenv("TAILTAG_REPLICA_TOKEN_FILE", str(token))
    return fake


def answer(
    cloud: RelayCloud, channel: str, result: str, data: Mapping[str, object]
) -> None:
    cloud.for_family(channel)
    cloud.entries = [
        result_entry(result_payload(result, data=dict(data)), job=JOBS[channel])
    ]


def call(
    channel: str = "pool",
    request: object | None = None,
    *,
    expected: object = SERVICE_IDENTITY,
    argv: list[str] | None = None,
) -> tuple[int, str]:
    body = (
        request
        if request is not None
        else {**REQUESTS[channel], "expected_identity": expected}
    )
    out = io.StringIO()
    code = relay.main(
        ["--channel", channel] if argv is None else argv,
        stdin=io.StringIO(body if isinstance(body, str) else json.dumps(body)),
        stdout=out,
    )
    return code, out.getvalue()


def runs(cloud: RelayCloud) -> list[dict[str, Any]]:
    return [r for r in cloud.requests if r["url"].endswith(":run")]


def assert_private_values_absent(output: str) -> None:
    for value in (TOKEN, PROJECT, HOST, BODY_SECRET, "googleapis", "https://"):
        assert value not in output


@pytest.mark.parametrize("channel", ["pool", "fixture", "inspect"])
def test_relay_checks_the_public_identity_then_runs_the_channel_job(
    cloud: RelayCloud, channel: str
) -> None:
    """R1, R3, R6, R7: one job run per call, read through the relay log view."""
    result, data = RESULTS[channel]
    answer(cloud, channel, result, data)

    code, out = call(channel)

    assert out == json.dumps({"result": result, "data": data}, sort_keys=True) + "\n"
    assert code == (0 if result == "PASS" else 1)
    urls = [r["url"] for r in cloud.requests]
    assert urls[:3] == [
        f"https://{HOST}/health/identity",
        f"https://{HOST}/health/ready",
        f"https://{HOST}/health/identity",
    ]
    (run,) = runs(cloud)
    assert f"/jobs/{JOBS[channel]}:run" in run["url"]
    sent = json.loads(
        run["body"]["overrides"]["containerOverrides"][0]["env"][0]["value"]
    )
    assert sent == {
        **REQUESTS[channel],
        "identity": {"source_sha": SOURCE_SHA, "environment": "replica"},
    }
    listings = [r for r in cloud.requests if r["url"].endswith("entries:list")]
    assert listings and all(r["body"]["resourceNames"] == [VIEW] for r in listings)
    assert cloud.subprocess_calls == [], "gcloud is never called"
    assert cloud.cancels == []
    assert_private_values_absent(out)


@pytest.mark.parametrize(
    ("identities", "ready", "expected", "outcome"),
    [
        pytest.param(
            [SERVICE_IDENTITY, SERVICE_IDENTITY],
            {"status": "ok"},
            {**SERVICE_IDENTITY, "deployment_id": f"{REVISION[:-3]}zzz"},
            "FAIL_TARGET",
            id="other-expected-revision",
        ),
        pytest.param(
            [SERVICE_IDENTITY, {**SERVICE_IDENTITY, "source_sha": "e" * 40}],
            {"status": "ok"},
            SERVICE_IDENTITY,
            "FAIL_TARGET",
            id="identity-changed-between-reads",
        ),
        pytest.param(
            [SERVICE_IDENTITY, SERVICE_IDENTITY],
            {"status": "unavailable"},
            SERVICE_IDENTITY,
            "FAIL_LAUNCHER",
            id="not-ready",
        ),
        pytest.param(
            [
                {
                    "source_sha": SOURCE_SHA,
                    "deployment_id": "9359c0a2-4915-42cd-9994-521ce7bc740e",
                    "environment": "staging",
                }
            ]
            * 2,
            {"status": "ok"},
            SERVICE_IDENTITY,
            "FAIL_LAUNCHER",
            id="staging-shaped-service",
        ),
    ],
)
def test_wrong_or_unusable_target_never_starts_a_job(
    cloud: RelayCloud,
    identities: list[object],
    ready: object,
    expected: object,
    outcome: str,
) -> None:
    """R3: the relay never follows a revision that the caller did not name."""
    cloud.identities = list(identities)
    cloud.ready = ready

    code, out = call(expected=expected)

    assert (code, json.loads(out)) == (1, {"result": outcome, "data": {}})
    assert runs(cloud) == []
    assert_private_values_absent(out)


@pytest.mark.parametrize(
    "case",
    ["no-session-variable", "token-readable-by-others", "unpinned-host", "extra-key"],
)
def test_private_inputs_must_be_owner_only_and_pinned(
    cloud: RelayCloud, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str
) -> None:
    """R2: no network call happens before both private files pass their checks."""
    session = Path(os.environ["TAILTAG_REPLICA_SESSION_FILE"])
    if case == "no-session-variable":
        monkeypatch.delenv("TAILTAG_REPLICA_SESSION_FILE")
    elif case == "token-readable-by-others":
        token = tmp_path / "private" / "token"
        write_config(token, {}, mode=0o644)
        token.write_text(TOKEN)
    elif case == "unpinned-host":
        session.write_text(
            json.dumps(
                {"project": PROJECT, "host": replica_contract.OTHER_RUN_APP_HOST}
            )
        )
    else:
        session.write_text(json.dumps({"project": PROJECT, "host": HOST, "x": 1}))

    code, out = call()

    assert (code, out) == (1, FAILURE_LINE)
    assert cloud.requests == []


@pytest.mark.parametrize(
    "ending", [b"", b"\r\n"], ids=["no-line-end", "windows-line-end"]
)
def test_token_file_may_end_with_one_line_end_of_either_form(
    cloud: RelayCloud, tmp_path: Path, ending: bytes
) -> None:
    """R2: a token file written on Windows or with no line end still works."""
    (tmp_path / "private" / "token").write_bytes(TOKEN.encode() + ending)

    code, out = call()

    assert (code, json.loads(out)["result"]) == (0, "PASS")


def padded(size: int) -> dict[str, object]:
    """A pool request whose job value, with the identity added, is `size` bytes."""
    base = {"operation": "status", "pool": "replica1", "arguments": {"pad": ""}}
    overhead = len(relay._job.job_request_value(SOURCE_SHA, base).encode())  # pyright: ignore[reportPrivateUsage]
    return {**base, "arguments": {"pad": "a" * (size - overhead)}}


@pytest.mark.parametrize(
    ("request_body", "outcome", "started"),
    [
        pytest.param(
            {**REQUESTS["pool"]}, "FAIL_REQUEST", False, id="no-expected-identity"
        ),
        pytest.param(
            {**REQUESTS["pool"], "expected_identity": SERVICE_IDENTITY, "extra": 1},
            "FAIL_REQUEST",
            False,
            id="extra-key",
        ),
        pytest.param(
            {
                **REQUESTS["pool"],
                "expected_identity": {
                    **SERVICE_IDENTITY,
                    "deployment_id": "9359c0a2-4915-42cd-9994-521ce7bc740e",
                },
            },
            "FAIL_REQUEST",
            False,
            id="railway-shaped-expectation",
        ),
        pytest.param(
            {**padded(OVERRIDE_CAP), "expected_identity": SERVICE_IDENTITY},
            "PASS",
            True,
            id="exactly-at-the-override-cap",
        ),
        pytest.param(
            {**padded(OVERRIDE_CAP + 1), "expected_identity": SERVICE_IDENTITY},
            "FAIL_REQUEST",
            False,
            id="one-byte-over-the-cap",
        ),
    ],
)
def test_request_shape_and_override_cap_are_checked_before_a_job_starts(
    cloud: RelayCloud, request_body: dict[str, object], outcome: str, started: bool
) -> None:
    """R1, R4: a refused request never reaches Cloud Run."""
    code, out = call("pool", request_body)

    assert json.loads(out)["result"] == outcome
    assert code == (0 if outcome == "PASS" else 1)
    assert bool(runs(cloud)) is started


@pytest.mark.parametrize("hang", [False, True], ids=["job-never-ends", "poll-hangs"])
def test_deadline_cancels_the_execution_once_and_reports_a_launcher_failure(
    cloud: RelayCloud, hang: bool
) -> None:
    """R5: a hung job is cancelled before the 180-second launcher limit.

    A hanging call cannot run past the deadline, because its timeout is cut.
    """
    cloud.never_completes = True
    cloud.hang_from = 121.0 if hang else None

    code, out = call()

    assert (code, out) == (1, FAILURE_LINE)
    assert len(runs(cloud)) == 1, "a run is never repeated"
    assert len(cloud.cancels) == 1
    assert cloud.cancels[0].endswith(
        f"/jobs/{JOBS['pool']}/executions/tailtag-replica-job-x7k2p:cancel"
    )
    # The cancel starts by the 135-second work deadline and has its own short timeout.
    assert cloud.cancelled_at[0] <= 135
    assert cloud.clock <= 150


@pytest.mark.parametrize(
    "case",
    [
        "unknown-result",
        "other-job-identity",
        "bad-data",
        "token-denied",
        "pass-from-failed-execution",
    ],
)
def test_job_results_outside_the_channel_contract_fail_closed(
    cloud: RelayCloud, case: str
) -> None:
    """R2, R7: only a validated result for the expected source passes through."""
    if case == "unknown-result":
        answer(cloud, "pool", "FAIL_EXECUTION", {})
    elif case == "other-job-identity":
        cloud.entries = [
            result_entry(
                result_payload(
                    data={"available": 3},
                    identity={"source_sha": "e" * 40, "environment": "replica"},
                ),
                job=JOBS["pool"],
            )
        ]
    elif case == "bad-data":
        answer(cloud, "pool", "PASS", {"available": "three"})
    elif case == "pass-from-failed-execution":
        cloud.execution_state = {"succeededCount": 0, "failedCount": 1}
    else:
        cloud.valid_token = "some-other-token"

    code, out = call()

    assert (code, out) == (1, FAILURE_LINE)
    assert cloud.subprocess_calls == [], "a fixed token is never refreshed"
    assert_private_values_absent(out)


def test_unknown_channel_or_extra_argument_is_a_launcher_failure(
    cloud: RelayCloud,
) -> None:
    for argv in (
        ["--channel", "reset"],
        ["--channel", "pool", "--project", PROJECT],
        [],
    ):
        assert call(argv=argv) == (1, FAILURE_LINE)
    assert cloud.requests == []


@pytest.mark.parametrize("channel", ["pool", "fixture", "inspect"])
def test_replica_relay_tasks_name_their_channel(channel: str) -> None:
    """R9: each task runs the one relay module with its fixed channel."""
    dry = task_dry_run(f"api-sim-{channel}-replica")
    assert f"-m scripts.api_sim_replica_relay --channel {channel}" in dry.stdout
