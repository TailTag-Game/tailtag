"""The headless V0 acceptance journeys and their run (#221).

SETUP is the shared fixture sequence (`fixtures.run_provisioned`): 7 leased identities,
the first 6 provisioned as 2 owners with 2 fursuits each and 4 catchers, the 7th an
onboarded outsider with no enrollment. SIMULATION receives only public `ApiClient`s:
one per identity plus one with no token and one with a fixed malformed bearer.

Each journey is a short list of steps. A step fails when the status, the code or the
shape of the response is not the expected one, and a journey stops at its first failed
step; the next journey still runs. Each journey arms the state it needs through
idempotent owner calls, so it does not depend on an earlier journey having passed.

Output is the fixed `PASS`/`FAIL` journey lines. The only thing taken from a response
body into a line is a code from a closed allowlist (a confirm outcome, a domain error
code, or an image rejection name mapped from its exact message). Tokens, payloads,
URLs, names, IDs and other body text are never written.
"""

import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Final, Literal, cast

import httpx

from tailtag_simulator.client import (
    ApiClient,
    Reply,
    Upload,
    open_client,
)
from tailtag_simulator.fixtures import (
    ACTIVE_PATH,
    FURSUITS_PATH,
    FixtureChannel,
    run_provisioned,
)
from tailtag_simulator.images import (
    content_type,
    gif_bytes,
    non_image_bytes,
    oversized_png,
)
from tailtag_simulator.phases import ME_PATH
from tailtag_simulator.pool import PROFILE_PATH, LeaseChannel
from tailtag_simulator.reconciliation import (
    HISTORY_PATH,
    Expectations,
    InspectionChannel,
    Role,
    reconcile_run,
    reconciliation_lines,
)
from tailtag_simulator.smoke import stage

MALFORMED_TOKEN: Final = "not-a-token"
FURSUIT_NAME: Final = "Sim journey"
CONFIRM_PATH: Final = "/api/catches/confirm/"
AVATAR_PATH: Final = "/api/profile/avatar/"

_OWNERS: Final = 2
_FURSUITS_PER_OWNER: Final = 2
_CATCHERS: Final = 4
_OUTSIDERS: Final = 1

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


@dataclass(frozen=True)
class JourneyImages:
    valid_a: bytes = field(repr=False)
    valid_b: bytes = field(repr=False)


@dataclass(frozen=True)
class JourneyContext:
    """All SIMULATION receives: public clients only."""

    owners: tuple[ApiClient, ApiClient]
    catchers: tuple[ApiClient, ApiClient, ApiClient, ApiClient]
    outsider: ApiClient
    anonymous: ApiClient  # no token
    malformed: ApiClient  # the fixed bearer `not-a-token`
    images: JourneyImages


@dataclass(frozen=True)
class JourneyResult:
    name: str
    failed_step: str | None
    expected: str | None  # "<status>/<code>"
    observed: str | None  # "<status>/<code>", "<status>/shape" or "error"


@dataclass(frozen=True)
class JourneyRun:
    """What SIMULATION leaves for RECONCILIATION: the results and what was expected."""

    results: tuple[JourneyResult, ...]
    expectations: Expectations
    convention: int  # 0 when no journey learned it
    created_fursuit: int | None  # the fursuit `fursuit_photo` created, if it did


class _StepFailed(Exception):
    def __init__(self, step: str, expected: str, observed: str) -> None:
        super().__init__(step)
        self.step = step
        self.expected = expected
        self.observed = observed


# -- reading replies ---------------------------------------------------------------


def _get(value: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = cast(dict[str, object], value).get(key)
    return value


def _text(body: object, *keys: str) -> str:
    value = _get(body, *keys)
    return value if isinstance(value, str) else ""


def _number(body: object, *keys: str) -> int:
    value = _get(body, *keys)
    return value if type(value) is int and value > 0 else 0


def _https(body: object, key: str) -> bool:
    return _text(body, key).startswith("https://") and len(_text(body, key)) > 8


def _is_null(body: object, key: str) -> bool:
    """The key is present and null (not merely absent)."""
    return isinstance(body, dict) and cast(dict[str, object], body).get(key, 0) is None


def _items(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _observed_code(body: object) -> str:
    """A code from the allowlist, else `other` when the body has a code field, else `-`."""
    for key in ("outcome", "code"):
        value = _get(body, key)
        if isinstance(value, str) and value in _CODES:
            return value
    for key in ("photo", "avatar"):
        messages = _items(_get(body, key))
        if len(messages) == 1 and isinstance(messages[0], str):
            known = _IMAGE_CODES.get(messages[0])
            if known is not None:
                return known
    if any(_get(body, key) is not None for key in _CODE_FIELDS):
        return "other"
    return "-"


async def _step(
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
    except Exception:  # noqa: BLE001 - any send failure, a token refresh included, is "error"
        raise _StepFailed(name, expected, "error") from None
    observed = _observed_code(reply.body)
    if reply.status != status or observed != code:
        raise _StepFailed(name, expected, f"{reply.status}/{observed}")
    if not shape(reply.body):
        raise _StepFailed(name, expected, f"{reply.status}/shape")
    return reply.body


def _upload(image: bytes) -> Upload:
    """A valid image upload; `load_fixture_images` only yields known signatures."""
    kind = content_type(image) or "application/octet-stream"
    return Upload(f"image.{kind.rpartition('/')[2]}", image, kind)


# -- the run state and the owner calls every journey shares ------------------------


@dataclass
class _Run:
    context: JourneyContext
    convention: int = 0
    fursuits: dict[int, list[int]] = field(default_factory=dict[int, list[int]])
    catch_id: int = 0  # set once journey `catch` has created the catch
    created: int = 0  # the fursuit journey `fursuit_photo` created
    expectations: Expectations = field(default_factory=Expectations)

    async def convention_id(self) -> int:
        if not self.convention:
            body = await _step(
                "convention",
                self.context.catchers[0].get(ACTIVE_PATH),
                200,
                shape=lambda b: _number(b, "enrollment", "convention", "id") > 0,
            )
            self.convention = _number(body, "enrollment", "convention", "id")
        return self.convention

    async def fursuit(self, owner: int, position: int) -> int:
        """An owner's fursuit by ID order; owner 0 or 1, position 0 or 1."""
        if owner not in self.fursuits:
            body = await _step(
                "fursuits",
                self.context.owners[owner].get(FURSUITS_PATH),
                200,
                shape=lambda b: len(_fursuit_ids(b)) >= _FURSUITS_PER_OWNER,
            )
            self.fursuits[owner] = _fursuit_ids(body)
        return self.fursuits[owner][position]

    async def activation(self, owner: int, position: int) -> str:
        convention = await self.convention_id()
        fursuit = await self.fursuit(owner, position)
        return f"/api/conventions/{convention}/fursuit-activations/{fursuit}/"

    def confirm(
        self, role: Role, client: ApiClient, fursuit: int, payload: str
    ) -> Awaitable[Reply]:
        """Confirm a catch, recording the attempted pair first."""
        self.expectations.attempt(role, fursuit)
        return client.post(CONFIRM_PATH, {"payload": payload})

    async def resolve_path(self) -> str:
        return (
            f"/api/conventions/{await self.convention_id()}/catch-credentials/resolve/"
        )


def _fursuit_ids(body: object) -> list[int]:
    ids = [_number(item, "id") for item in _items(body)]
    return sorted(ids) if all(ids) else []


async def _arm(owner: ApiClient, activation: str) -> str:
    """Start the fursuit's catch session and read its credential; return the payload."""
    await _step(
        "session",
        owner.put(f"{activation}catch-session/", {"is_active": True}),
        200,
        shape=lambda b: _get(b, "is_active") is True,
    )
    body = await _step(
        "credential",
        owner.get(f"{activation}catch-credential/"),
        200,
        shape=lambda b: bool(_text(b, "payload")),
    )
    return _text(body, "payload")


async def _stop(owner: ApiClient, activation: str) -> None:
    await _step(
        "stop",
        owner.put(f"{activation}catch-session/", {"is_active": False}),
        200,
        shape=lambda b: _get(b, "is_active") is False,
    )


async def _only_catch(client: ApiClient, run: _Run, catch: int, fursuit: int) -> None:
    """The caller's history for the run Convention is exactly this one catch."""
    convention = await run.convention_id()

    def one(body: object) -> bool:
        results = _items(_get(body, "results"))
        return (
            len(results) == 1
            and _number(results[0], "id") == catch
            and _number(results[0], "fursuit", "id") == fursuit
        )

    await _step(
        "history",
        client.get(f"{HISTORY_PATH}?convention_id={convention}"),
        200,
        shape=one,
    )


# -- the journeys ------------------------------------------------------------------


async def _unauthenticated(run: _Run) -> None:
    context = run.context
    await _step("no_token", context.anonymous.get(ME_PATH), 401)
    await _step("malformed_token", context.malformed.get(ME_PATH), 401)


async def _catch(run: _Run) -> None:
    owner, catcher = run.context.owners[0], run.context.catchers[0]
    activation = await run.activation(0, 0)
    payload = await _arm(owner, activation)
    convention = await run.convention_id()
    await _step(
        "resolve",
        catcher.post(await run.resolve_path(), {"payload": payload}),
        200,
        shape=lambda b: _get(b, "convention_id") == convention,
    )
    fursuit = await run.fursuit(0, 0)
    body = await _step(
        "confirm",
        run.confirm(Role.CATCHER0, catcher, fursuit, payload),
        201,
        "created",
        shape=lambda b: _number(b, "catch", "id") > 0,
    )
    run.catch_id = _number(body, "catch", "id")
    run.expectations.created(
        Role.CATCHER0, fursuit, run.catch_id, _text(body, "catch", "caught_at")
    )
    await _only_catch(catcher, run, run.catch_id, fursuit)


async def _retry(run: _Run) -> None:
    owner, catcher = run.context.owners[0], run.context.catchers[0]
    activation = await run.activation(0, 0)
    payload = await _arm(owner, activation)
    fursuit = await run.fursuit(0, 0)
    body = await _step(
        "confirm",
        run.confirm(Role.CATCHER0, catcher, fursuit, payload),
        200,
        "already_caught",
        shape=lambda b: (
            _number(b, "catch", "id") > 0
            and run.catch_id in (0, _number(b, "catch", "id"))
        ),
    )
    catch = _number(body, "catch", "id")
    run.expectations.confirmed(
        Role.CATCHER0, fursuit, catch, _text(body, "catch", "caught_at")
    )
    await _stop(owner, activation)
    body = await _step(
        "confirm_stopped",
        run.confirm(Role.CATCHER0, catcher, fursuit, payload),
        200,
        "already_caught",
        shape=lambda b: _number(b, "catch", "id") == catch,
    )
    run.expectations.confirmed(
        Role.CATCHER0, fursuit, catch, _text(body, "catch", "caught_at")
    )
    await _only_catch(catcher, run, catch, fursuit)


async def _stopped_session(run: _Run) -> None:
    owner, catcher = run.context.owners[0], run.context.catchers[1]
    activation = await run.activation(0, 1)
    payload = await _arm(owner, activation)
    await _stop(owner, activation)
    await _step(
        "confirm",
        run.confirm(Role.CATCHER1, catcher, await run.fursuit(0, 1), payload),
        404,
        "catch_target_unavailable",
    )


async def _stale_credential(run: _Run) -> None:
    owner, catcher = run.context.owners[1], run.context.catchers[1]
    activation = await run.activation(1, 0)
    old = await _arm(owner, activation)
    body = await _step(
        "rotate",
        owner.post(f"{activation}catch-credential/rotate/"),
        200,
        shape=lambda b: bool(_text(b, "payload")) and _text(b, "payload") != old,
    )
    new = _text(body, "payload")
    await _step(
        "confirm_old",
        run.confirm(Role.CATCHER1, catcher, await run.fursuit(1, 0), old),
        404,
        "catch_target_unavailable",
    )
    convention = await run.convention_id()
    await _step(
        "resolve_new",
        catcher.post(await run.resolve_path(), {"payload": new}),
        200,
        shape=lambda b: _get(b, "convention_id") == convention,
    )


async def _deactivated(run: _Run) -> None:
    owner, catcher = run.context.owners[1], run.context.catchers[2]
    activation = await run.activation(1, 1)
    payload = await _arm(owner, activation)
    await _step(
        "deactivate",
        owner.put(activation, {"is_active": False}),
        200,
        shape=lambda b: _get(b, "is_active") is False,
    )
    await _step(
        "confirm",
        run.confirm(Role.CATCHER2, catcher, await run.fursuit(1, 1), payload),
        404,
        "catch_target_unavailable",
    )


async def _self_catch(run: _Run) -> None:
    owner = run.context.owners[1]
    payload = await _arm(owner, await run.activation(1, 0))
    await _step(
        "confirm",
        run.confirm(Role.OWNER1, owner, await run.fursuit(1, 0), payload),
        409,
        "self_catch_not_allowed",
    )


async def _convention_mismatch(run: _Run) -> None:
    owner, catcher = run.context.owners[1], run.context.catchers[3]
    payload = await _arm(owner, await run.activation(1, 0))
    convention = await run.convention_id()
    first: _StepFailed | None = None
    try:
        await _step("leave", catcher.delete(ACTIVE_PATH), 204)
        await _step(
            "confirm",
            run.confirm(Role.CATCHER3, catcher, await run.fursuit(1, 0), payload),
            409,
            "active_convention_mismatch",
        )
    except _StepFailed as failed:
        first = failed
    try:  # the restore runs even when the check failed
        await _step(
            "restore", catcher.put(ACTIVE_PATH, {"convention_id": convention}), 200
        )
    except _StepFailed as failed:
        first = first or failed
    if first is not None:
        raise first


async def _ineligible_catcher(run: _Run) -> None:
    payload = await _arm(run.context.owners[1], await run.activation(1, 0))
    await _step(
        "confirm",
        run.confirm(
            Role.OUTSIDER, run.context.outsider, await run.fursuit(1, 0), payload
        ),
        403,
        "catcher_ineligible",
    )


async def _not_owner(run: _Run) -> None:
    intruder = run.context.owners[0]
    activation = await run.activation(1, 0)
    await _step("credential", intruder.get(f"{activation}catch-credential/"), 404)
    await _step(
        "session", intruder.put(f"{activation}catch-session/", {"is_active": True}), 404
    )


async def _avatar(run: _Run) -> None:
    client, images = run.context.catchers[2], run.context.images

    def set_avatar(name: str, image: bytes) -> Awaitable[object]:
        return _step(
            name,
            client.put_multipart(AVATAR_PATH, {}, {"avatar": _upload(image)}),
            200,
            shape=lambda b: _https(b, "avatar_url"),
        )

    await set_avatar("put_a", images.valid_a)
    await set_avatar("put_b", images.valid_b)
    await _step("delete", client.delete(AVATAR_PATH), 204)
    await _step(
        "profile",
        client.get(PROFILE_PATH),
        200,
        shape=lambda b: _is_null(b, "avatar_url"),
    )


async def _fursuit_photo(run: _Run) -> None:
    client, images = run.context.owners[0], run.context.images
    body = await _step(
        "create",
        client.post_multipart(
            FURSUITS_PATH, {"name": FURSUIT_NAME}, {"photo": _upload(images.valid_a)}
        ),
        201,
        shape=lambda b: (
            _number(b, "id") > 0
            and _get(b, "is_enabled") is True
            and _https(b, "photo_url")
        ),
    )
    run.created = _number(body, "id")
    await _step(
        "replace",
        client.put_multipart(
            f"/api/fursuits/{run.created}/photo/",
            {},
            {"photo": _upload(images.valid_b)},
        ),
        200,
        shape=lambda b: _https(b, "photo_url"),
    )


async def _image_rejections(run: _Run) -> None:
    if not run.created:
        raise _StepFailed("precondition", "201/-", "error")
    client = run.context.owners[0]
    path = f"/api/fursuits/{run.created}/photo/"
    rejected = (
        ("gif", Upload("photo.gif", gif_bytes(), "image/gif"), "unsupported_format"),
        (
            "not_image",
            Upload("photo.jpg", non_image_bytes(), "image/jpeg"),
            "invalid_image",
        ),
        (
            "oversized",
            Upload("photo.png", oversized_png(), "image/png"),
            "too_many_pixels",
        ),
    )
    for name, upload, code in rejected:
        await _step(name, client.put_multipart(path, {}, {"photo": upload}), 400, code)


_JOURNEYS: Final[tuple[tuple[str, Callable[[_Run], Awaitable[None]]], ...]] = (
    ("unauthenticated", _unauthenticated),
    ("catch", _catch),
    ("retry", _retry),
    ("stopped_session", _stopped_session),
    ("stale_credential", _stale_credential),
    ("deactivated", _deactivated),
    ("self_catch", _self_catch),
    ("convention_mismatch", _convention_mismatch),
    ("ineligible_catcher", _ineligible_catcher),
    ("not_owner", _not_owner),
    ("avatar", _avatar),
    ("fursuit_photo", _fursuit_photo),
    ("image_rejections", _image_rejections),
)
JOURNEY_NAMES: Final = tuple(name for name, _ in _JOURNEYS)


# -- SIMULATION, RECONCILIATION and the run ----------------------------------------


async def simulate_journeys(context: JourneyContext) -> JourneyRun:
    """Run every journey in order; one failing never stops the next."""
    run = _Run(context)
    results: list[JourneyResult] = []
    for name, journey in _JOURNEYS:
        run.expectations.begin(name)
        try:
            await journey(run)
        except _StepFailed as failed:
            results.append(
                JourneyResult(name, failed.step, failed.expected, failed.observed)
            )
        else:
            results.append(JourneyResult(name, None, None, None))
    return JourneyRun(
        tuple(results), run.expectations, run.convention, run.created or None
    )


def journey_lines(results: Sequence[JourneyResult]) -> list[str]:
    """One line per journey, then the summary. Only fixed names and codes appear."""
    lines = [
        f"PASS journey={result.name}"
        if result.failed_step is None
        else (
            f"FAIL journey={result.name} step={result.failed_step}"
            f" expected={result.expected} observed={result.observed}"
        )
        for result in results
    ]
    failed = sum(result.failed_step is not None for result in results)
    lines.append(
        f"FAIL journeys failed={failed}"
        if failed
        else f"PASS journeys passed={len(results)}"
    )
    return lines


async def run_journeys(
    pool: str,
    *,
    images: JourneyImages,
    prompt_secret: Callable[[], str],
    lease_channel: LeaseChannel,
    fixture_channel: FixtureChannel,
    inspection_channel: InspectionChannel,
    emit: Callable[[str], None],
    clerk_transport: httpx.AsyncBaseTransport | None = None,
    api_transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
    run_id: str | None = None,
) -> int:
    """Run the 13 journeys on Staging, reconcile them, and return the exit code.

    The exit code is 0 only if every stage, journey and reconciliation passed.
    RECONCILIATION runs after the journey lines and before release, and release always
    runs once leases may be held. A passing run cleans up after itself, and a failing one
    is retained for investigation (#223); the callback tells the shared run which part
    failed. When reconciliation completes, a failed journey is reported as `journeys`
    even if reconciliation also failed; a reconciliation stage error is `reconciliation`.
    """

    run = run_id or str(uuid.uuid4())  # reconciliation names the run to `inspect`

    async def journeys(
        origin: str, clients: tuple[ApiClient, ...], indexes: tuple[int, ...]
    ) -> Literal["pass", "journeys", "reconciliation"]:
        with stage("simulation"):
            async with AsyncExitStack() as stack:
                anonymous = await stack.enter_async_context(
                    open_client(origin, transport=api_transport)
                )
                malformed = await stack.enter_async_context(
                    open_client(origin, token=MALFORMED_TOKEN, transport=api_transport)
                )
                simulated = await simulate_journeys(
                    JourneyContext(
                        owners=(clients[0], clients[1]),
                        catchers=(clients[2], clients[3], clients[4], clients[5]),
                        outsider=clients[6],
                        anonymous=anonymous,
                        malformed=malformed,
                        images=images,
                    )
                )
        for line in journey_lines(simulated.results):
            emit(line)
        with stage("reconciliation"):
            reconciled = await reconcile_run(
                simulated.expectations,
                dict(zip(Role, clients, strict=True)),
                dict(zip(Role, indexes, strict=True)),
                inspection_channel,
                pool=pool,
                run_id=run,
                convention=simulated.convention,
                created_fursuit=simulated.created_fursuit,
            )
        for line in reconciliation_lines(reconciled):
            emit(line)
        if any(result.failed_step is not None for result in simulated.results):
            return "journeys"
        return "pass" if reconciled.passed else "reconciliation"

    return await run_provisioned(
        pool,
        _OWNERS,
        _FURSUITS_PER_OWNER,
        _CATCHERS,
        _OUTSIDERS,
        prompt_secret=prompt_secret,
        lease_channel=lease_channel,
        fixture_channel=fixture_channel,
        emit=emit,
        clerk_transport=clerk_transport,
        api_transport=api_transport,
        clock=clock,
        run_id=run,
        simulate_and_reconcile=journeys,
    )
