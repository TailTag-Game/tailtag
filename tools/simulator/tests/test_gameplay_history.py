"""AC10/12/15: complete bounded history, without forwarding response URLs.

Only HTTP is substituted; the real client and gameplay parser enforce the boundary.
"""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tailtag_simulator.client import open_client
from tailtag_simulator.gameplay import HistoryEntry, StepFailed, read_history

ORIGIN = "https://api.example.test"
AT = "2026-10-06T12:00:00Z"


def entry(number: int) -> dict[str, object]:
    return {
        "id": 7000 + number,
        "fursuit": {
            "id": 8000 + number,
            "name": "Private name",
            "photo_url": "https://media.example.test/SENTINEL-private-photo",
        },
        "convention": {"id": 42, "name": "Private convention"},
        "caught_at": AT,
    }


def page(
    rows: list[dict[str, object]], count: object, next_: object = None
) -> dict[str, Any]:
    return {"catch_count": count, "next": next_, "previous": None, "results": rows}


def link(number: int) -> str:
    # DRF may order query keys differently; the reader must rebuild a canonical path.
    return f"{ORIGIN}/api/catches/?page={number}&page_size=20&convention_id=42"


def read(serve: Callable[[httpx.Request], httpx.Response]) -> tuple[HistoryEntry, ...]:
    async def run() -> tuple[HistoryEntry, ...]:
        async with open_client(
            ORIGIN, token="SENTINEL-bearer", transport=httpx.MockTransport(serve)
        ) as client:
            return await read_history(client, 42)

    return asyncio.run(run())


@pytest.mark.parametrize("count", [0, 21, 200])
def test_history_reads_every_bounded_page_and_never_fetches_media(count: int) -> None:
    requests: list[int] = []

    def serve(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.example.test"
        assert request.url.path == "/api/catches/"
        assert request.url.params["convention_id"] == "42"
        assert request.url.params["page_size"] == "20"
        number = int(request.url.params.get("page", "1"))
        requests.append(number)
        start = (number - 1) * 20
        end = min(start + 20, count)
        return httpx.Response(
            200,
            json=page(
                [entry(n) for n in range(start, end)],
                count,
                link(number + 1) if end < count else None,
            ),
        )

    result = read(serve)

    assert result == tuple(HistoryEntry(7000 + n, 8000 + n, AT) for n in range(count))
    assert requests == list(range(1, max(1, (count + 19) // 20) + 1))


FAULTS: dict[str, list[dict[str, Any]]] = {
    "boolean-count": [page([], True)],
    "negative-count": [page([], -1)],
    "over-cap": [page([], 201)],
    "missing-row": [page([], 1)],
    "duplicate-id": [page([entry(0), {**entry(1), "id": 7000}], 2)],
    "duplicate-target": [
        page([entry(0), {**entry(1), "fursuit": entry(0)["fursuit"]}], 2)
    ],
    "malformed-id": [page([{**entry(0), "id": True}], 1)],
    "count-changes": [
        page([entry(n) for n in range(20)], 21, link(2)),
        page([entry(20)], 22),
    ],
    "loop": [page([entry(n) for n in range(20)], 21, link(1))],
    "foreign-origin": [
        page(
            [entry(0)],
            2,
            "https://evil.example.test/api/catches/?page=2&convention_id=42&page_size=20",
        )
    ],
    "wrong-path": [
        page([entry(0)], 2, f"{ORIGIN}/api/me/?page=2&convention_id=42&page_size=20")
    ],
    "wrong-convention": [
        page(
            [entry(0)], 2, f"{ORIGIN}/api/catches/?page=2&convention_id=99&page_size=20"
        )
    ],
    "wrong-page-size": [
        page(
            [entry(0)],
            2,
            f"{ORIGIN}/api/catches/?page=2&convention_id=42&page_size=100",
        )
    ],
    "unknown-query": [page([entry(0)], 2, link(2) + "&secret=SENTINEL-private")],
    "duplicate-query": [page([entry(0)], 2, link(2) + "&page=3")],
    "page-skip": [page([entry(0)], 2, link(3))],
    "beyond-page-cap": [
        page([entry(n) for n in range(start, start + 20)], 200, link(start // 20 + 2))
        for start in range(0, 200, 20)
    ],
}


@pytest.mark.parametrize("fault", FAULTS)
def test_invalid_history_fails_closed_without_private_diagnostics(fault: str) -> None:
    bodies = FAULTS[fault]
    requests: list[httpx.Request] = []

    def serve(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert len(requests) <= len(bodies), "invalid next URL must never be followed"
        assert request.url.host == "api.example.test"
        assert request.url.path == "/api/catches/"
        return httpx.Response(200, json=bodies[len(requests) - 1])

    with pytest.raises(StepFailed) as caught:
        read(serve)

    failure = caught.value
    assert (
        "SENTINEL"
        not in f"{failure!r}{failure.step}{failure.expected}{failure.observed}"
    )
    assert len(requests) <= 10
