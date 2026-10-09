"""#228 U3: explicit amd64 build selection, preserving ordinary provenance."""

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from report_support import git
from test_provenance import (
    source_repo as source_repo,  # noqa: PLC0414 -- pytest fixture registration
)

from tailtag_simulator.provenance import main


@pytest.mark.parametrize(
    "platform", ["linux/amd64", "linux/arm64", "SENTINEL-invalid-platform"]
)
def test_explicit_host_platform_is_validated_before_docker_and_keeps_source_hashes(
    source_repo: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    real_run: Callable[..., Any] = subprocess.run
    calls: list[list[str]] = []
    packaged: list[dict[str, Any]] = []

    def run(arguments: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if arguments[0] != "docker":
            return real_run(arguments, **kwargs)
        calls.append(arguments)
        assert arguments[1] == "build" and not kwargs.get("shell", False)
        context = Path(arguments[-1])
        record = json.loads((context / "source.json").read_text())
        packaged.append(record)
        for name, digest in record["manifest"].items():
            assert hashlib.sha256((context / name).read_bytes()).hexdigest() == digest
        return subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(subprocess, "run", run)
    try:
        code = main(
            [
                "build",
                "--root",
                str(source_repo),
                "--tag",
                "tailtag-test:228",
                "--platform",
                platform,
            ]
        )
    except SystemExit as outcome:
        code = outcome.code if isinstance(outcome.code, int) else 1
    if platform != "linux/amd64":
        assert code != 0 and calls == [] and packaged == []
        return
    assert code == 0 and len(calls) == 1
    assert calls[0][calls[0].index("--platform") + 1] == "linux/amd64"
    assert packaged[0]["simulator_sha"] == git(source_repo, "rev-parse", "HEAD")
    assert (
        packaged[0]["dependency_lock_sha256"]
        == hashlib.sha256(
            (source_repo / "tools/simulator/uv.lock").read_bytes()
        ).hexdigest()
    )
    assert not Path(calls[0][-1]).exists()


def test_inspect_emits_actual_closed_source_identity_for_release_verification(
    source_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["inspect", "--root", str(source_repo)]) == 0
    value = json.loads(capsys.readouterr().out)
    assert set(value) == {"simulator_sha", "provenance", "reason", "runtime"}
    assert value["simulator_sha"] == {
        "value": git(source_repo, "rev-parse", "HEAD"),
        "reason": None,
    }
    assert value["provenance"] == "clean" and value["reason"] is None
    assert value["runtime"]["dependency_lock_sha256"] == {
        "value": hashlib.sha256(
            (source_repo / "tools/simulator/uv.lock").read_bytes()
        ).hexdigest(),
        "reason": None,
    }
