"""The fixture launcher channel against a real subprocess (#220 F-7, F-8 at the seam).

Only where it differs from `pool.LauncherChannel` (see test_pool.py): the request
carries no pool name outside its arguments, the failure type is `FixtureFailed`
with the relay's `quarantined` count, and PASS returns the relay's count data.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from pool_support import POOL, RUN_ID

from tailtag_simulator.fixtures import FixtureFailed, FixtureLauncherChannel

ARGUMENTS = {
    "pool": POOL,
    "run_id": RUN_ID,
    "owners": [1, 2],
    "catchers": [3],
    "fursuits_per_owner": 1,
}
COUNTS = {"convention": 1, "enrollment": 3, "fursuit": 2, "activation": 2}


def launcher(
    tmp_path: Path,
    stdout: str,
    *,
    code: int = 0,
    hang: bool = False,
    timeout: float = 3,
) -> tuple[FixtureLauncherChannel, Path]:
    record = tmp_path / "record.json"
    script = (
        "import json, sys, time\n"
        "stdin = sys.stdin.read()\n"
        f"open({str(record)!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], 'stdin': stdin}}))\n"
        f"time.sleep(30) if {hang} else None\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.exit({code})\n"
    )
    return FixtureLauncherChannel(
        [sys.executable, "-c", script], timeout_seconds=timeout
    ), record


def _pass(data: object = COUNTS) -> str:
    return json.dumps({"data": data, "result": "PASS"})


def test_request_goes_on_stdin_without_pool_or_run_id_in_argv_and_pass_returns_counts(
    tmp_path: Path,
) -> None:
    channel, record = launcher(tmp_path, _pass() + "\n")

    data = asyncio.run(channel.call("provision", ARGUMENTS))

    assert data == COUNTS
    seen = json.loads(record.read_text())
    assert seen["argv"] == []
    # Exactly the relay's request: an operation and its arguments, nothing else.
    assert json.loads(seen["stdin"]) == {
        "operation": "provision",
        "arguments": ARGUMENTS,
    }


# stdout, exit code, hang, expected (result, quarantined); None result = anything but PASS
FAILURES: dict[str, tuple[str, int, bool, tuple[str | None, int | None]]] = {
    "dirty-with-count": (
        '{"data": {"quarantined": 2}, "result": "FAIL_DIRTY"}\n',
        1,
        False,
        ("FAIL_DIRTY", 2),
    ),
    "lease": ('{"data": {}, "result": "FAIL_LEASE"}\n', 1, False, ("FAIL_LEASE", None)),
    "malformed-failure-code": (
        '{"data": {}, "result": "FAIL_bad SENTINEL"}\n',
        1,
        False,
        ("FAIL_LAUNCHER", None),
    ),
    "pass-with-nonzero-exit": (_pass(), 1, False, (None, None)),
    "failure-result-with-zero-exit": (
        '{"data": {}, "result": "FAIL_TARGET"}\n',
        0,
        False,
        (None, None),
    ),
    "not-json": ("SENTINEL-OUTPUT not json\n", 0, False, ("FAIL_LAUNCHER", None)),
    "trailing-text": (
        _pass() + "\nSENTINEL-OUTPUT\n",
        0,
        False,
        ("FAIL_LAUNCHER", None),
    ),
    "timeout": (_pass(), 0, True, ("FAIL_LAUNCHER", None)),
}


@pytest.mark.parametrize("case", FAILURES)
def test_launcher_failures_become_a_detail_free_fixture_failure(
    tmp_path: Path, case: str
) -> None:
    stdout, code, hang, (result, quarantined) = FAILURES[case]
    channel, _ = launcher(tmp_path, stdout, code=code, hang=hang, timeout=0.5)

    with pytest.raises(FixtureFailed) as exc:
        asyncio.run(channel.call("provision", ARGUMENTS))

    if result is None:
        assert exc.value.result != "PASS"
    else:
        assert (exc.value.result, exc.value.quarantined) == (result, quarantined)
    assert "SENTINEL" not in f"{exc.value}{exc.value!r}"


def test_a_launcher_that_cannot_be_started_is_a_fixture_failure() -> None:
    channel = FixtureLauncherChannel(["/nonexistent/sim-fixture-launcher"])

    with pytest.raises(FixtureFailed) as exc:
        asyncio.run(channel.call("provision", ARGUMENTS))

    assert exc.value.result == "FAIL_LAUNCHER"
