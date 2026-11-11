"""The committed OpenAPI snapshot gate fails only on real contract drift."""

from __future__ import annotations

from pathlib import Path

import pytest

from config import openapi_snapshot

RENDERED = b"openapi: 3.0.3\ninfo:\n  title: TailTag API\n"


@pytest.mark.parametrize(
    ("committed", "expected_exit"),
    [
        pytest.param(RENDERED, 0, id="identical"),
        pytest.param(RENDERED.replace(b"\n", b"\r\n"), 0, id="crlf-checkout"),
        pytest.param(RENDERED.replace(b"TailTag", b"TailTaG"), 1, id="one-byte-drift"),
        pytest.param(None, 1, id="missing"),
    ],
)
def test_check_fails_only_on_drift(
    committed: bytes | None,
    expected_exit: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    snapshot = tmp_path / "schema.yaml"
    if committed is not None:
        snapshot.write_bytes(committed)
    monkeypatch.setattr(openapi_snapshot, "SNAPSHOT", snapshot)
    monkeypatch.setattr(openapi_snapshot, "render_schema", lambda: RENDERED)

    assert openapi_snapshot.main(["--check"]) == expected_exit
    if expected_exit:
        assert "task api-schema" in capsys.readouterr().err
