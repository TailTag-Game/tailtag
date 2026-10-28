"""Credential-free cold start samples against the hybrid replica (#359 AC5, AC14).

Run it from the host release, separately from any simulator run:

    python -m tailtag_simulator.cold_probe --replica-session FILE \\
        --state both-cold --idle-seconds 1200 --output FILE

The origin comes only from the owner-only relay session file, through the
replica pin. The record names the target by its digest label, never its origin.
"""

import argparse
import asyncio
import json
import os
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

import httpx

from .host_operator import replica_session_host
from .owner_only import create_private_file
from .targets import resolve_target

SCHEMA: Final = "tailtag-replica-cold-probe-v1"
TIMEOUT_SECONDS: Final = 60.0
T4_SECONDS: Final = 5.0
# What each state measures, in request order (#359 AC14).
PATHS: Final = {
    "both-cold": ("/health/ready",),
    "database-cold": ("/health/ready",),
    "app-cold": ("/health/live", "/health/ready"),
}
_BODIES: Final = {"/health/live": {"status": "ok"}, "/health/ready": {"status": "ok"}}


async def _sample(
    client: httpx.AsyncClient, path: str, clock: Callable[[], float]
) -> dict[str, object]:
    started = clock()
    status: int | None = None
    try:
        reply = await client.get(path)
        status = reply.status_code
        try:
            body: object = reply.json()
        except ValueError:
            body = None
        outcome = "ok" if status == 200 and body == _BODIES[path] else "http"
    except httpx.TimeoutException:
        outcome = "timeout"
    except httpx.HTTPError:
        outcome = "transport"
    return {
        "path": path,
        "status": status,
        "outcome": outcome,
        "latency_seconds": round(clock() - started, 3),
    }


async def probe(
    origin: str,
    state: str,
    idle_seconds: int,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    """Send the requests of `state` in order and return one sample record."""
    target = resolve_target("replica", origin)
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    async with httpx.AsyncClient(
        base_url=target.origin,
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    ) as client:
        requests: list[dict[str, object]] = [
            await _sample(client, path, clock) for path in PATHS[state]
        ]
    first = requests[0]
    return {
        "schema": SCHEMA,
        "state": state,
        "idle_seconds": idle_seconds,
        "started_at": started_at,
        "target": target.report_origin,
        "requests": requests,
        "first_within_t4": first["outcome"] == "ok"
        and float(str(first["latency_seconds"])) <= T4_SECONDS,
    }


def _write(fd: int, record: dict[str, object]) -> None:
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tailtag_simulator.cold_probe")
    parser.add_argument("--replica-session", type=Path, required=True)
    parser.add_argument("--state", choices=sorted(PATHS), required=True)
    parser.add_argument("--idle-seconds", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.idle_seconds < 0:
            raise ValueError
        origin = f"https://{replica_session_host(args.replica_session)}"
        # Claim the evidence file before any request: a missing folder or an
        # existing file must not cost a quiet window.
        fd = create_private_file(args.output)
        try:
            record = asyncio.run(probe(origin, args.state, args.idle_seconds))
        except BaseException:
            os.close(fd)
            args.output.unlink()
            raise
        _write(fd, record)
    except Exception:  # noqa: BLE001 - public error is deliberately detail-free
        print("FAIL cold_probe", flush=True)
        return 1
    requests = cast(list[dict[str, object]], record["requests"])
    summary = " ".join(
        f"{r['path']}={r['outcome']}:{r['latency_seconds']}s" for r in requests
    )
    passed = all(r["outcome"] == "ok" for r in requests)
    verdict = "PASS" if passed else "RECORDED"
    print(f"{verdict} cold_probe state={args.state} {summary}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
