"""#359 U5: the host pool, fixture-smoke, cleanup and retained commands on the replica."""

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pool_support import SECRET
from test_host_cli import install_http, packaged_source
from test_replica_host_session import (
    HOST,
    IDENTITY,
    private,
    private_root,
    receipt,
)

from tailtag_simulator import __main__ as cli
from tailtag_simulator import fixtures, pool, targets
from tailtag_simulator.__main__ import main
from tailtag_simulator.targets import bound_target, replica_host_digest

RUN_ID = "0f0e0d0c-0b0a-4908-8706-050403020100"
PUBLIC_REPLIES: dict[str, dict[str, object]] = {
    "status": {"total": 3, "available": 3, "leased": 0, "quarantined": 0},
    "readmit": {},
    "retained": {"runs": [], "retained": 0, "unfinished": 0},
}


@pytest.fixture(autouse=True)
def pinned(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(targets, "REPLICA_HOST_DIGEST", replica_host_digest(HOST))
    yield


class Session:
    """The owner files of one replica session, and what each boundary saw."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = private_root(tmp_path)
        self.session = private(
            root / "session.json",
            json.dumps({"project": "synthetic-project", "host": HOST}),
        )
        self.token = private(root / "token", "synthetic-token\n")
        monkeypatch.setenv("TAILTAG_REPLICA_SESSION_FILE", str(self.session))
        monkeypatch.setenv("TAILTAG_REPLICA_TOKEN_FILE", str(self.token))
        folder = tmp_path / "replica-deployments"
        folder.mkdir()
        self.older = receipt(
            folder,
            "1-1.json",
            "2026-10-26T10:00:00Z",
            revision="tailtag-api-replica-00014-wtd",
        )
        self.receipt = receipt(folder, "2-1.json", "2026-10-27T17:46:36Z")
        self.hosts: list[str] = []
        self.served = dict(IDENTITY)
        self.launched: list[tuple[list[str], dict[str, Any]]] = []
        self.prompts: list[str] = []

        def respond(request: httpx.Request) -> httpx.Response:
            self.hosts.append(request.url.host)
            if request.url.host != HOST:
                return httpx.Response(404, json={})
            if request.url.path == "/health/ready":
                return httpx.Response(200, json={"status": "ok"})
            return httpx.Response(200, json=self.served)

        install_http(monkeypatch, respond)

        async def launch(
            command: Sequence[str], cwd: Path | None, timeout: float, request: bytes
        ) -> tuple[str, dict[str, object]]:
            envelope = cast(dict[str, Any], json.loads(request))
            self.launched.append((list(command), envelope))
            return "PASS", PUBLIC_REPLIES.get(str(envelope["operation"]), {})

        monkeypatch.setattr(pool, "run_launcher", launch)
        monkeypatch.setattr(fixtures, "run_launcher", launch)

        def prompt(text: str) -> str:
            self.prompts.append(text)
            return SECRET

        monkeypatch.setattr(cli, "_prompt_hidden", prompt)

    def flags(self) -> list[str]:
        return ["--replica-session", str(self.session), "--receipt", str(self.receipt)]


COMMANDS: dict[str, tuple[list[str], str]] = {
    "status": (["pool", "status", "--pool", "replica1"], "api-sim-pool-replica"),
    "readmit": (
        ["pool", "readmit", "--pool", "replica1", "--index", "2"],
        "api-sim-pool-replica",
    ),
    "cleanup": (
        ["cleanup", "--pool", "replica1", "--run-id", RUN_ID],
        "api-sim-fixture-replica",
    ),
    "retained": (["retained"], "api-sim-fixture-replica"),
}


@pytest.mark.parametrize("name", COMMANDS)
def test_replica_commands_use_the_replica_relays_with_the_served_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    name: str,
) -> None:
    """P3, P4: the identity is read from the replica only, then sent on every call."""
    session = Session(tmp_path, monkeypatch)
    arguments, relay = COMMANDS[name]

    code = main([*arguments, *session.flags()])

    assert [command for command, _ in session.launched] == [["task", "-s", relay]]
    assert session.launched[0][1]["expected_identity"] == IDENTITY
    assert set(session.hosts) == {HOST}
    if name != "cleanup":
        assert code == 0
        assert capsys.readouterr().out.startswith("PASS")


def test_replica_provision_prompts_for_the_replica_clerk_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """P5: the replica Clerk app is named, and nothing reaches Staging."""
    session = Session(tmp_path, monkeypatch)

    code = main(
        ["pool", "provision", "--pool", "replica1", "--size", "3", *session.flags()]
    )

    # The fake Clerk API refuses the instance check, so nothing is registered.
    assert code == 1
    assert capsys.readouterr().out == "FAIL provision\n"
    assert session.prompts == ["Clerk Replica secret:"]
    assert session.launched == []
    assert set(session.hosts) == {HOST, "api.clerk.com"}


@pytest.mark.parametrize("redeployed", [False, True])
def test_replica_fixture_smoke_binds_the_replica_and_its_relays(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    redeployed: bool,
) -> None:
    """P3, P4: the fixture smoke runs through the replica relays, on the receipt only."""
    session = Session(tmp_path, monkeypatch)
    if redeployed:
        session.served["deployment_id"] = "tailtag-api-replica-00017-abc"
    seen: dict[str, object] = {}

    async def smoke(*_: object, **kwargs: Any) -> int:
        seen["target"] = bound_target().name
        seen["lease"] = kwargs["lease_channel"]._command
        seen["fixture"] = kwargs["fixture_channel"]._command
        return 0

    monkeypatch.setattr(cli, "run_fixture_smoke", smoke)
    packaged_source(tmp_path / "source")
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", tmp_path / "source")

    code = main(
        [
            "fixture-smoke",
            "--pool",
            "replica1",
            "--owners",
            "1",
            "--catchers",
            "2",
            "--report-dir",
            str(tmp_path / "reports"),
            *session.flags(),
        ]
    )

    if redeployed:
        assert code == 1
        assert capsys.readouterr().out == "FAIL target\n"
        assert seen == {}
        return
    assert code == 0
    assert seen == {
        "target": "replica",
        "lease": ["task", "-s", "api-sim-pool-replica"],
        "fixture": ["task", "-s", "api-sim-fixture-replica"],
    }
    assert set(session.hosts) == {HOST}


REFUSALS = [
    "no-receipt",
    "no-session",
    "older-receipt",
    "unpinned-host",
    "other-env-host",
    "no-token-file",
    "shared-session",
    "served-changed",
    "malformed-receipt",
]


@pytest.mark.parametrize("fault", REFUSALS)
def test_replica_commands_refuse_before_any_relay_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    """P1 to P3: each bad premise stops the command before the relay and the prompt."""
    session = Session(tmp_path, monkeypatch)
    flags = session.flags()
    if fault == "no-receipt":
        flags = flags[:2]
    elif fault == "no-session":
        flags = flags[2:]
    elif fault == "older-receipt":
        flags[3] = str(session.older)
    elif fault == "unpinned-host":
        session.session.write_text(
            json.dumps(
                {"project": "p", "host": "tailtag-api-replica-9.us-east4.run.app"}
            )
        )
    elif fault == "other-env-host":
        other = private(
            tmp_path / "private" / "other.json",
            json.dumps(
                {"project": "p", "host": "tailtag-api-replica-9.us-east4.run.app"}
            ),
        )
        monkeypatch.setenv("TAILTAG_REPLICA_SESSION_FILE", str(other))
    elif fault == "no-token-file":
        monkeypatch.delenv("TAILTAG_REPLICA_TOKEN_FILE")
    elif fault == "shared-session":
        session.session.chmod(0o644)
    elif fault == "malformed-receipt":
        (session.receipt.parent / "3-1.json").write_text("[]")
    elif fault == "served-changed":
        session.served["deployment_id"] = "tailtag-api-replica-00017-abc"

    code = main(["pool", "provision", "--pool", "replica1", "--size", "3", *flags])

    assert code == 1
    assert capsys.readouterr().out == (
        "FAIL target\n" if fault == "served-changed" else "FAIL configuration\n"
    )
    assert session.launched == []
    assert session.prompts == []
    assert set(session.hosts) <= {HOST}
    if fault != "served-changed":
        assert session.hosts == []
