"""Shared public gameplay checks and bounded complete catch history."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final, cast
from urllib.parse import parse_qsl, urlsplit

from tailtag_simulator.client import ApiClient, Reply

_CODES: Final = frozenset(
    {
        "created",
        "already_caught",
        "catcher_ineligible",
        "active_convention_mismatch",
        "self_catch_not_allowed",
        "catch_target_unavailable",
    }
)
# The API's image rejections carry no code: the exact message is the identity.
_IMAGE_CODES: Final = {
    "Upload a JPEG, PNG, or static WebP image.": "unsupported_format",
    "Upload a valid image.": "invalid_image",
    "The photo dimensions are too large.": "too_many_pixels",
}
_CODE_FIELDS: Final = ("outcome", "code", "photo", "avatar")


class StepFailed(Exception):
    def __init__(self, step: str, expected: str, observed: str) -> None:
        super().__init__(step)
        self.step = step
        self.expected = expected
        self.observed = observed


# -- reading replies ---------------------------------------------------------------


def get_value(value: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = cast(dict[str, object], value).get(key)
    return value


def text_value(body: object, *keys: str) -> str:
    value = get_value(body, *keys)
    return value if isinstance(value, str) else ""


def positive_number(body: object, *keys: str) -> int:
    value = get_value(body, *keys)
    return value if type(value) is int and value > 0 else 0


def list_items(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _observed_code(body: object) -> str:
    """A code from the allowlist, else `other` when the body has a code field, else `-`."""
    for key in ("outcome", "code"):
        value = get_value(body, key)
        if isinstance(value, str) and value in _CODES:
            return value
    for key in ("photo", "avatar"):
        messages = list_items(get_value(body, key))
        if len(messages) == 1 and isinstance(messages[0], str):
            known = _IMAGE_CODES.get(messages[0])
            if known is not None:
                return known
    if any(get_value(body, key) is not None for key in _CODE_FIELDS):
        return "other"
    return "-"


async def step(
    name: str,
    sending: Awaitable[Reply],
    status: int,
    code: str = "-",
    *,
    shape: Callable[[object], bool] = lambda _body: True,
) -> object:
    """Await one request; fail the journey unless status, code and shape all match."""
    expected = f"{status}/{code}"
    try:
        reply = await sending
    except StepFailed:
        raise
    except Exception:  # noqa: BLE001 - any send failure, a token refresh included, is "error"
        raise StepFailed(name, expected, "error") from None
    observed = _observed_code(reply.body)
    if reply.status != status or observed != code:
        raise StepFailed(name, expected, f"{reply.status}/{observed}")
    try:
        valid = shape(reply.body)
    except Exception:  # noqa: BLE001 - malformed bodies have fixed diagnostics
        valid = False
    if not valid:
        raise StepFailed(name, expected, f"{reply.status}/shape")
    return reply.body


async def arm_session(
    owner: ApiClient,
    activation: str,
    *,
    observed_session: Callable[[object], None] | None = None,
) -> str:
    """Start the fursuit's catch session and read its credential; return the payload."""
    session = await step(
        "session",
        owner.put(f"{activation}catch-session/", {"is_active": True}),
        200,
        shape=lambda b: get_value(b, "is_active") is True,
    )
    if observed_session is not None:
        observed_session(session)
    body = await step(
        "credential",
        owner.get(f"{activation}catch-credential/"),
        200,
        shape=lambda b: bool(text_value(b, "payload")),
    )
    return text_value(body, "payload")


async def stop_session(owner: ApiClient, activation: str) -> None:
    await step(
        "stop",
        owner.put(f"{activation}catch-session/", {"is_active": False}),
        200,
        shape=lambda b: get_value(b, "is_active") is False,
    )


@dataclass(frozen=True)
class HistoryEntry:
    catch_id: int
    fursuit: int
    caught_at: str


def _next_page(value: object, client: ApiClient, convention: int, page: int) -> None:
    if not isinstance(value, str):
        raise TypeError
    link = urlsplit(value)
    bound = urlsplit(str(client._client.base_url))  # pyright: ignore[reportPrivateUsage]
    if (
        (link.scheme, link.hostname, link.port)
        != (bound.scheme, bound.hostname, bound.port)
        or link.username is not None
        or link.password is not None
        or link.path != "/api/catches/"
        or link.fragment
        or page >= 10
    ):
        raise ValueError
    query = parse_qsl(link.query, keep_blank_values=True, strict_parsing=True)
    wanted = {
        "page": str(page + 1),
        "page_size": "20",
        "convention_id": str(convention),
    }
    if len(query) != 3 or dict(query) != wanted:
        raise ValueError


async def read_history(client: ApiClient, convention: int) -> tuple[HistoryEntry, ...]:
    """Read at most ten canonical pages; response links are validated, never forwarded."""
    rows: list[HistoryEntry] = []
    ids: set[int] = set()
    targets: set[int] = set()
    count: int | None = None
    try:
        if type(convention) is not int or convention <= 0:
            raise ValueError
        for page in range(1, 11):
            path = f"/api/catches/?convention_id={convention}&page_size=20&page={page}"
            body = await step("history", client.get(path), 200)
            if not isinstance(body, dict):
                raise TypeError
            data = cast(dict[str, object], body)
            total = data["catch_count"]
            if type(total) is not int or not 0 <= total <= 200:
                raise ValueError
            if count is not None and total != count:
                raise ValueError
            count = total
            items = data["results"]
            if not isinstance(items, list) or len(cast(list[object], items)) > 20:
                raise ValueError
            for item in cast(list[object], items):
                id_, target, at = (
                    positive_number(item, "id"),
                    positive_number(item, "fursuit", "id"),
                    text_value(item, "caught_at"),
                )
                if not id_ or not target or not at or id_ in ids or target in targets:
                    raise ValueError
                if positive_number(item, "convention", "id") != convention:
                    raise ValueError
                ids.add(id_)
                targets.add(target)
                rows.append(HistoryEntry(id_, target, at))
            if len(rows) > count:
                raise ValueError
            next_ = data["next"]
            if next_ is None:
                if len(rows) != count:
                    raise ValueError
                return tuple(rows)
            if not items or len(rows) >= count:
                raise ValueError
            _next_page(next_, client, convention, page)
    except StepFailed:
        raise
    except Exception:  # noqa: BLE001 - all parsing failures have fixed diagnostics
        raise StepFailed("history", "200/-", "200/shape") from None
    raise StepFailed("history", "200/-", "200/shape")
