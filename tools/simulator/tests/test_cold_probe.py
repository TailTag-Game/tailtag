"""#359 U4: credential-free cold start samples against the replica."""

import asyncio
import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from test_host_cli import install_http

from tailtag_simulator import cold_probe, targets
from tailtag_simulator.owner_only import create_private_file
from tailtag_simulator.targets import replica_host_digest

HOST = "tailtag-api-replica-123456789012.us-east4.run.app"
ORIGIN = f"https://{HOST}"
LABEL = f"sha256:{replica_host_digest(HOST)}"


@pytest.fixture(autouse=True)
def pinned(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(targets, "REPLICA_HOST_DIGEST", replica_host_digest(HOST))
    yield


def serving(
    seen: list[httpx.Request], **replies: httpx.Response
) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        reply = replies.get(request.url.path.strip("/").replace("/", "_"))
        return reply or httpx.Response(200, json={"status": "ok"})

    return httpx.MockTransport(respond)


def run(state: str, transport: httpx.AsyncBaseTransport) -> dict[str, Any]:
    return asyncio.run(cold_probe.probe(ORIGIN, state, 1200, transport=transport))


@pytest.mark.parametrize(
    ("state", "paths"),
    [
        ("both-cold", ["/health/ready"]),
        ("app-cold", ["/health/live", "/health/ready"]),
    ],
)
def test_each_state_sends_its_requests_in_order_without_credentials(
    state: str, paths: list[str]
) -> None:
    """M1: one record per sample, the replica named only by its digest label."""
    seen: list[httpx.Request] = []

    record = run(state, serving(seen))

    assert [r.url.path for r in seen] == paths
    assert all(r.url.host == HOST and "authorization" not in r.headers for r in seen)
    assert all(r.extensions["timeout"]["read"] == 60.0 for r in seen)
    assert record["schema"] == cold_probe.SCHEMA
    assert (record["state"], record["idle_seconds"], record["target"]) == (
        state,
        1200,
        LABEL,
    )
    assert [r["outcome"] for r in record["requests"]] == ["ok"] * len(paths)
    assert record["first_within_t4"] is True
    assert HOST not in json.dumps(record)


def test_redirect_is_not_followed_and_counts_as_http() -> None:
    seen: list[httpx.Request] = []
    moved = httpx.Response(302, headers={"location": "https://elsewhere.example.test/"})

    record = run("both-cold", serving(seen, health_ready=moved))

    assert [r.url.host for r in seen] == [HOST]
    assert record["requests"][0] == {
        **record["requests"][0],
        "status": 302,
        "outcome": "http",
    }
    assert record["first_within_t4"] is False


@pytest.mark.parametrize(
    ("error", "outcome"),
    [(httpx.ReadTimeout("slow"), "timeout"), (httpx.ConnectError("down"), "transport")],
)
def test_timeout_and_transport_faults_are_recorded_not_raised(
    error: Exception, outcome: str
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise error

    record = run("both-cold", httpx.MockTransport(respond))

    assert record["requests"][0]["outcome"] == outcome
    assert record["requests"][0]["status"] is None
    assert record["first_within_t4"] is False


def test_a_slow_first_request_misses_t4() -> None:
    """M1, T-4: a 10.6-second cold start is recorded as a miss, not an error."""
    ticks = iter([100.0, 110.6])

    record = asyncio.run(
        cold_probe.probe(
            ORIGIN, "both-cold", 1200, transport=serving([]), clock=lambda: next(ticks)
        )
    )

    first = cast(list[dict[str, Any]], record["requests"])[0]
    assert first["latency_seconds"] == 10.6
    assert first["outcome"] == "ok"
    assert record["first_within_t4"] is False


def session_file(tmp_path: Path, host: str = HOST) -> Path:
    folder = tmp_path / "private"
    folder.mkdir(mode=0o700)
    path = folder / "session.json"
    os.close(create_private_file(path))
    path.write_text(json.dumps({"project": "p-1", "host": host}))
    return path


def cli(tmp_path: Path, output: Path, *extra: str) -> list[str]:
    tmp_path.mkdir(exist_ok=True)
    return [
        "--replica-session",
        str(session_file(tmp_path)),
        "--state",
        "both-cold",
        "--idle-seconds",
        "1200",
        "--output",
        str(output),
        *extra,
    ]


def test_cli_writes_one_owner_only_record_and_never_prints_the_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "ok"})

    install_http(monkeypatch, cast(Callable[[httpx.Request], Any], respond))
    output = tmp_path / "sample.json"

    code = cold_probe.main(cli(tmp_path, output))

    printed = capsys.readouterr().out
    assert code == 0
    assert printed.startswith("PASS cold_probe state=both-cold")
    assert HOST not in printed
    assert json.loads(output.read_text())["target"] == LABEL
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o600
    assert [r.url.host for r in seen] == [HOST]


def test_cli_refuses_existing_evidence_and_an_unpinned_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """M1: both refusals happen before any request is sent."""
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "ok"})

    install_http(monkeypatch, cast(Callable[[httpx.Request], Any], respond))
    output = tmp_path / "sample.json"
    output.write_text("earlier evidence\n")

    assert cold_probe.main(cli(tmp_path, output)) == 1
    assert output.read_text() == "earlier evidence\n"

    other = tmp_path / "other"
    other.mkdir()
    fresh = other / "sample.json"
    session = session_file(other, host="tailtag-api-replica-999.us-east4.run.app")
    arguments = [
        "--replica-session",
        str(session),
        "--state",
        "both-cold",
        "--idle-seconds",
        "1",
        "--output",
        str(fresh),
    ]
    assert cold_probe.main(arguments) == 1
    assert not fresh.exists()
    missing = tmp_path / "no-such-folder" / "sample.json"
    assert cold_probe.main(cli(tmp_path / "third", missing)) == 1
    assert capsys.readouterr().out.count("FAIL cold_probe") == 3
    assert seen == [], "no refusal may cost a quiet window"


def test_cli_records_a_failed_sample_without_calling_it_a_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """LOW-2: an unready replica is recorded evidence, not a passed probe."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"status": "unavailable"})

    install_http(monkeypatch, cast(Callable[[httpx.Request], Any], respond))
    output = tmp_path / "sample.json"

    assert cold_probe.main(cli(tmp_path, output)) == 1
    assert capsys.readouterr().out.startswith("RECORDED cold_probe state=both-cold")
    assert json.loads(output.read_text())["requests"][0]["outcome"] == "http"
