"""Run-owned, bounded safety accounting; no network or privileged dependencies."""

import asyncio
import math
import re
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator, Mapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from fractions import Fraction
from typing import TypeVar, cast

T = TypeVar("T")
MAX_EVIDENCE_COUNTER = 2**63 - 1


def _count(value: object) -> int:
    return cast(int, value)


_DEFAULTS: dict[str, object] = {
    "requests": 10000,
    "seconds": 900,
    "in_flight": 10,
    "population": 250,
    "final_requests": 1000,
    "final_seconds": 600,
    "poll_seconds": 10,
    "error_window_seconds": 10,
    "error_min_samples": 20,
    "error_percent": 50,
    "error_windows": 2,
}
_MAX = {
    "requests": 1000000,
    "seconds": 86400,
    "in_flight": 250,
    "population": 250,
    "final_requests": 5000,
    "final_seconds": 1800,
    "poll_seconds": 30,
}
_INTEGRAL = {
    "requests",
    "in_flight",
    "population",
    "final_requests",
    "error_min_samples",
    "error_windows",
}
_REASONS = {
    "identity_mismatch",
    "readiness",
    "catastrophic_errors",
    "request_ceiling",
    "duration_ceiling",
    "population_ceiling",
    "correctness",
    "resource_saturation",
    "report_failure",
}
_PHASES = {
    "target",
    "attribution",
    "retention",
    "release",
    "preflight",
    "setup",
    "simulation",
    "reconciliation",
    "finalization",
    "cleanup",
}
_CURRENT: ContextVar["SafetyRuntime | None"] = ContextVar(
    "safety_runtime", default=None
)
_PHASE: ContextVar[str] = ContextVar("safety_phase", default="target")
_CONTROL: ContextVar[bool] = ContextVar("safety_control", default=False)


class ProbeInvalid(Exception):
    """A probe returned invalid or unsafe target evidence."""


class ProbeUnavailable(Exception):
    """Readiness could not be established."""


class SafetyAborted(Exception):
    """A fixed, sanitized safety classification."""

    def __init__(self, reason: str) -> None:
        self.reason = reason if reason in _REASONS else "correctness"
        super().__init__(self.reason)


def active_runtime() -> "SafetyRuntime | None":
    return _CURRENT.get()


def resolve_safety_policy(value: Mapping[str, object]) -> dict[str, object]:
    if set(value) - set(_DEFAULTS):
        raise ValueError("invalid safety policy")
    policy = {**_DEFAULTS, **value}
    for key, number in policy.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError("invalid safety policy")  # noqa: TRY004 - configuration contract
        try:
            finite = math.isfinite(number)
        except OverflowError:
            finite = False
        if not finite or number <= 0:
            raise ValueError("invalid safety policy")
        if key in _INTEGRAL and (not isinstance(number, int)):
            raise ValueError("invalid safety policy")
        if key in _MAX and number > _MAX[key]:
            raise ValueError("invalid safety policy")
        if (
            key == "poll_seconds"
            and number < 5
            or key == "error_percent"
            and number > 100
        ):
            raise ValueError("invalid safety policy")
    return policy


def _identity(value: object, local: bool) -> dict[str, object]:
    if not isinstance(value, dict) or set(cast(dict[str, object], value)) != {
        "source_sha",
        "deployment_id",
        "environment",
    }:
        raise ProbeInvalid
    identity = cast(dict[str, object], value)
    sha, deployment, environment = (
        identity["source_sha"],
        identity["deployment_id"],
        identity["environment"],
    )
    valid_sha = isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) is not None
    if local:
        valid = (
            environment is None and deployment is None and (sha is None or valid_sha)
        )
    else:
        try:
            valid = (
                environment == "staging"
                and valid_sha
                and isinstance(deployment, str)
                and str(uuid.UUID(deployment)) == deployment
            )
        except ValueError:
            valid = False
    if not valid:
        raise ProbeInvalid
    return dict(identity)


class SafetyRuntime:
    """One execution budget and one finalization reserve with owned cancellation."""

    def __init__(
        self,
        policy: Mapping[str, object],
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        observe: Callable[[Mapping[str, object]], None] | None = None,
        persist: Callable[[Mapping[str, object]], None] | None = None,
    ) -> None:
        self.policy = resolve_safety_policy(policy)
        self._now, self._sleep, self._observe = monotonic, sleep, observe
        self._persist = persist
        self._started = monotonic()
        self._final_start: float | None = None
        self._identity: dict[str, object] | None = None
        self._local = False
        self._probe: Callable[[], Awaitable[dict[str, object]]] | None = None
        self.abort_reason: str | None = None
        self._abort_time = 0.0
        self._abort_event = asyncio.Event()
        self._identity_denied = False
        self._identity_event = asyncio.Event()
        self._finalization_event = asyncio.Event()
        self._ready = asyncio.Event()
        self._ready.set()
        self._ordinary = asyncio.Semaphore(_count(self.policy["in_flight"]))
        self._control = asyncio.Semaphore(1)
        self._monitor: asyncio.Task[None] | None = None
        self._allowed = False
        self._final_exhausted = False
        self._execution = self._budget()
        self._finalization = {
            **self._budget(),
            "started": False,
            "allowed": False,
            **dict.fromkeys(
                ("reconciliation", "retention", "release", "clerk_closure"),
                "not_attempted",
            ),
        }
        self._preflight = {"checks": 0, "passed": 0, "failed": 0, "last": "unverified"}
        self._probes = {
            "checks": 0,
            "passed": 0,
            "failed": 0,
            "last": "unverified",
            "consecutive_failures": 0,
            "paused": False,
        }
        self._errors = {
            "closed_windows": 0,
            "qualifying_windows": 0,
            "consecutive_windows": 0,
            "current_completed": 0,
            "current_catastrophic": 0,
            "last_completed": 0,
            "last_catastrophic": 0,
        }
        self._window_start: float | None = None

    @staticmethod
    def _budget() -> dict[str, object]:
        return {
            "requests": 0,
            "ordinary_active": 0,
            "ordinary_peak": 0,
            "control_active": 0,
            "control_peak": 0,
            "elapsed_seconds": 0.0,
            "exhausted": None,
        }

    def _number(self, key: str) -> float:
        return float(cast(int | float, self.policy[key]))

    @contextmanager
    def scope(self) -> Generator[None]:
        token = _CURRENT.set(self)
        try:
            yield
        finally:
            _CURRENT.reset(token)

    @contextmanager
    def phase(self, name: str) -> Generator[None]:
        if name not in _PHASES:
            raise ValueError("invalid safety phase")
        token = _PHASE.set(name)
        if name == "simulation" and self._window_start is None:
            self._window_start = self._now()
        try:
            self._emit()
            yield
        finally:
            try:
                self._emit()
            finally:
                _PHASE.reset(token)

    @contextmanager
    def control(self) -> Generator[None]:
        token = _CONTROL.set(True)
        try:
            yield
        finally:
            _CONTROL.reset(token)

    def bind_probe(
        self, probe: Callable[[], Awaitable[dict[str, object]]], *, local: bool = False
    ) -> None:
        if self._identity is not None:
            raise ValueError("target already pinned")
        self._probe, self._local = probe, local

    def _budget_state(self) -> dict[str, object]:
        return self._finalization if self._final_start is not None else self._execution

    def _remaining(self) -> float:
        final = self._final_start is not None
        start = self._final_start if final else self._started
        assert start is not None
        return self._number("final_seconds" if final else "seconds") - (
            self._now() - start
        )

    def _guard(self) -> None:
        if self.abort_reason and self._final_start is None:
            raise SafetyAborted(self.abort_reason)
        if self._identity_denied or self._final_exhausted:
            raise SafetyAborted(self.abort_reason or "duration_ceiling")
        if self._remaining() <= 0:
            self._exhaust("seconds")

    def _exhaust(self, kind: str) -> None:
        self._budget_state()["exhausted"] = kind
        if self._final_start is not None:
            self._final_exhausted = True
        reason = {
            "requests": "request_ceiling",
            "seconds": "duration_ceiling",
            "population": "population_ceiling",
        }[kind]
        self.abort(reason)
        raise SafetyAborted(self.abort_reason or reason)

    def _emit(self, *, persist: bool = True) -> None:
        try:
            if self._observe is not None:
                self._observe(self.snapshot())
            if persist and self._persist is not None:
                self._persist(self.snapshot())
        except Exception:  # noqa: BLE001 - boundary fails closed without external details
            recovering = self._final_start is not None and self.abort_reason is not None
            self.abort("report_failure", emit=False)
            # Best effort records the first abort even when only cache validation failed.
            # Do not recurse when the report boundary itself remains unavailable.
            for callback in (self._observe, self._persist):
                try:
                    if callback is not None:
                        callback(self.snapshot())
                except Exception:  # noqa: BLE001, S110 - original failure stays latched
                    pass
            if not recovering:
                raise SafetyAborted(self.abort_reason or "report_failure") from None

    def abort(self, reason: str, *, emit: bool = True) -> None:
        if reason not in _REASONS:
            raise ValueError("invalid safety reason")
        if reason == "identity_mismatch":
            self._identity_denied = True
            self._identity_event.set()
            self._allowed = False
            self._finalization["allowed"] = False
        if self.abort_reason is None:
            self.abort_reason = reason
            self._abort_time = max(0.0, self._now() - self._started)
            self._abort_event.set()
        if emit:
            self._emit()

    async def _race(
        self,
        work: Awaitable[T],
        *,
        seconds: float | None = None,
        ignore_abort: bool = False,
    ) -> T:
        deadline = self._now() + (self._remaining() if seconds is None else seconds)
        operation = asyncio.ensure_future(work)
        timer = asyncio.ensure_future(
            self._sleep(max(0.0, self._remaining() if seconds is None else seconds))
        )
        abort = (
            None
            if ignore_abort
            else asyncio.create_task(
                (
                    self._identity_event
                    if self._final_start is not None
                    else self._abort_event
                ).wait()
            )
        )
        transition = (
            asyncio.create_task(self._finalization_event.wait())
            if seconds is None and self._final_start is None
            else None
        )
        owned = (
            [operation, timer]
            + ([abort] if abort is not None else [])
            + ([transition] if transition is not None else [])
        )
        try:
            while True:
                tasks = (
                    [operation, timer]
                    + ([abort] if abort is not None else [])
                    + ([transition] if transition is not None else [])
                )
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                if operation.done():
                    result = await operation
                    if not ignore_abort and (
                        self._identity_denied
                        or (self.abort_reason is not None and self._final_start is None)
                    ):
                        raise SafetyAborted(self.abort_reason or "identity_mismatch")
                    # A completed operation exactly at its budget boundary may pass.
                    if self._remaining() < 0:
                        self._exhaust("seconds")
                    if seconds is not None and self._now() > deadline:
                        raise ProbeUnavailable
                    return result
                if transition is not None and transition.done():
                    # The outer lifecycle owns both phases. Transfer its clock once,
                    # deriving time from the existing reserve rather than resetting it.
                    previous = [timer] + ([abort] if abort is not None else [])
                    for task in previous:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(
                        *cast(list[Awaitable[object]], previous), return_exceptions=True
                    )
                    timer = asyncio.ensure_future(
                        self._sleep(max(0.0, self._remaining()))
                    )
                    abort = (
                        None
                        if ignore_abort
                        else asyncio.create_task(self._identity_event.wait())
                    )
                    owned.append(timer)
                    if abort is not None:
                        owned.append(abort)
                    transition = None
                    continue
                if timer.done():
                    if seconds is not None:
                        self._guard()
                        raise ProbeUnavailable
                    self._exhaust("seconds")
                raise SafetyAborted(self.abort_reason or "correctness")
        finally:
            for task in owned:
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                *cast(list[Awaitable[object]], owned), return_exceptions=True
            )

    async def run_phase(self, work: Awaitable[T]) -> T:
        async def guarded() -> T:
            self._guard()
            return await work

        try:
            return await self._race(guarded())
        finally:
            await self._join_owned(work)

    async def run_closure(self, work: Awaitable[T]) -> T:
        """Bound independently verified non-TailTag closure by the existing reserve.

        This does not relax any public HTTP or privileged target admission gate.
        """
        try:
            if self._final_start is None:
                raise ValueError("finalization not started")
            if self._finalization["exhausted"] == "seconds" or self._remaining() <= 0:
                self._exhaust("seconds")
            return await self._race(work, ignore_abort=True)
        finally:
            await self._join_owned(work)

    @staticmethod
    async def _join_owned(work: Awaitable[object]) -> None:
        """Join caller-supplied tasks even when admission rejects their work."""
        if isinstance(work, asyncio.Future):
            if not work.done():
                work.cancel()
            await asyncio.gather(work, return_exceptions=True)
        elif asyncio.iscoroutine(work):
            work.close()

    @asynccontextmanager
    async def request(self) -> AsyncGenerator[Callable[[], None]]:
        self._guard()
        control = _CONTROL.get()
        if self._final_start is not None and not self._allowed and not control:
            raise SafetyAborted(self.abort_reason or "readiness")
        if self._final_start is not None and _PHASE.get() == "simulation":
            raise SafetyAborted(self.abort_reason or "correctness")
        semaphore = self._control if control else self._ordinary
        acquired = False

        async def acquire() -> None:
            nonlocal acquired
            while True:
                if not control and self._final_start is None:
                    await self._ready.wait()
                await semaphore.acquire()
                if control or self._final_start is not None or self._ready.is_set():
                    acquired = True
                    return
                semaphore.release()

        try:
            await self._race(acquire())
        except BaseException:
            if acquired:
                semaphore.release()
            raise
        budget = self._budget_state()
        key = "control" if control else "ordinary"
        active = False
        started = False

        def start_send() -> None:
            nonlocal started
            if not active or started:
                raise ValueError("invalid send admission")
            self._guard()
            limit = self._number(
                "final_requests" if self._final_start is not None else "requests"
            )
            if _count(budget["requests"]) >= limit:
                self._exhaust("requests")
            budget["requests"] = _count(budget["requests"]) + 1
            started = True

        try:
            self._guard()
            budget[key + "_active"] = _count(budget[key + "_active"]) + 1
            budget[key + "_peak"] = max(
                _count(budget[key + "_peak"]), _count(budget[key + "_active"])
            )
            active = True
            self._emit(persist=False)
            yield start_send
        finally:
            if active:
                budget[key + "_active"] = _count(budget[key + "_active"]) - 1
            active = False
            semaphore.release()
            self._emit(persist=False)

    def _close_windows(self) -> None:
        if self._window_start is None:
            return
        length = self._number("error_window_seconds")
        elapsed = self._now() - self._window_start
        quotient = Fraction(elapsed) / Fraction(length)
        windows = quotient.numerator // quotient.denominator
        if windows <= 0:
            return
        errors = self._errors
        completed, catastrophic = (
            errors["current_completed"],
            errors["current_catastrophic"],
        )
        qualifying = completed >= self._number(
            "error_min_samples"
        ) and catastrophic * 100 >= completed * self._number("error_percent")
        errors["closed_windows"] = min(
            MAX_EVIDENCE_COUNTER, errors["closed_windows"] + windows
        )
        errors["last_completed"], errors["last_catastrophic"] = (
            (completed, catastrophic) if windows == 1 else (0, 0)
        )
        if qualifying:
            errors["qualifying_windows"] = min(
                MAX_EVIDENCE_COUNTER, errors["qualifying_windows"] + 1
            )
            errors["consecutive_windows"] = min(
                MAX_EVIDENCE_COUNTER, errors["consecutive_windows"] + 1
            )
            if errors["consecutive_windows"] >= self._number("error_windows"):
                self.abort("catastrophic_errors")
        else:
            errors["consecutive_windows"] = 0
        if windows > 1:
            errors["consecutive_windows"] = 0
        errors["current_completed"] = errors["current_catastrophic"] = 0
        self._window_start = self._now() - math.fmod(elapsed, length)

    def _outcome(self, catastrophic: bool) -> None:
        if (
            _PHASE.get() != "simulation"
            or _CONTROL.get()
            or self._final_start is not None
        ):
            return
        self._close_windows()
        self._errors["current_completed"] += 1
        self._errors["current_catastrophic"] += int(catastrophic)
        self._emit(persist=False)

    def observed_reply(self, status: int) -> None:
        self._outcome(500 <= status <= 599)

    def observed_transport_failure(self) -> None:
        self._outcome(True)

    async def _check(self, *, periodic: bool) -> dict[str, object]:
        stats = self._probes if periodic else self._preflight
        try:
            if self._probe is None:
                raise ProbeInvalid
            with self.scope(), self.control():
                try:
                    identity = _identity(
                        await self._race(
                            self._probe(), seconds=min(15, self._remaining())
                        ),
                        self._local,
                    )
                except (SafetyAborted, ProbeInvalid, ProbeUnavailable):
                    raise
                except Exception:  # noqa: BLE001 - external probe errors are sanitized
                    raise ProbeUnavailable from None
            if self._identity is not None and identity != self._identity:
                stats["last"] = "mismatch"
                raise ProbeInvalid
            self._identity = identity
        except ProbeUnavailable:
            stats["failed"] = min(MAX_EVIDENCE_COUNTER, _count(stats["failed"]) + 1)
            stats["checks"] = min(
                MAX_EVIDENCE_COUNTER, _count(stats["passed"]) + _count(stats["failed"])
            )
            stats["last"] = "unavailable"
            if periodic:
                self._probes["consecutive_failures"] = (
                    _count(self._probes["consecutive_failures"]) + 1
                )
                self._probes["paused"] = True
                self._ready.clear()
            if not periodic or _count(self._probes["consecutive_failures"]) >= 2:
                self.abort("readiness")
            self._emit()
            if not periodic:
                raise SafetyAborted(self.abort_reason or "readiness") from None
            return {}
        except ProbeInvalid:
            stats["failed"] = min(MAX_EVIDENCE_COUNTER, _count(stats["failed"]) + 1)
            stats["checks"] = min(
                MAX_EVIDENCE_COUNTER, _count(stats["passed"]) + _count(stats["failed"])
            )
            if stats["last"] != "mismatch":
                stats["last"] = "invalid"
            self.abort("identity_mismatch")
            self._emit()
            if not periodic:
                raise SafetyAborted(self.abort_reason or "identity_mismatch") from None
            return {}
        stats["passed"] = min(MAX_EVIDENCE_COUNTER, _count(stats["passed"]) + 1)
        stats["checks"] = min(
            MAX_EVIDENCE_COUNTER, _count(stats["passed"]) + _count(stats["failed"])
        )
        stats["last"] = "passed"
        if periodic:
            self._probes["consecutive_failures"] = 0
            self._probes["paused"] = False
            self._ready.set()
        self._emit()
        return dict(identity)

    async def check_target(self) -> dict[str, object]:
        self._guard()
        return await self._check(periodic=False)

    async def privileged_identity(self) -> dict[str, object]:
        return await self.check_target()

    async def start_monitor(self) -> None:
        if self._monitor is not None:
            return

        async def monitor() -> None:
            next_probe = self._now() + self._number("poll_seconds")
            try:
                while self.abort_reason is None:
                    await self._sleep(
                        min(
                            max(0, next_probe - self._now()),
                            self._number("error_window_seconds"),
                            max(0, self._remaining()),
                        )
                    )
                    self._guard()
                    self._close_windows()
                    if self.abort_reason is None and self._now() >= next_probe:
                        await self._check(periodic=True)
                        next_probe = self._now() + self._number("poll_seconds")
                    else:
                        self._emit()
            except SafetyAborted:
                pass
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - boundary fails closed without external details
                self.abort("readiness")

        self._monitor = asyncio.create_task(monitor())

    async def stop_monitor(self) -> None:
        if self._monitor is not None:
            self._monitor.cancel()
            await asyncio.gather(self._monitor, return_exceptions=True)
            self._monitor = None

    async def begin_finalization(self) -> bool:
        if self._final_start is not None:
            return self._allowed
        self._final_start = self._now()
        self._finalization_event.set()
        self._finalization["started"] = True
        if not self._identity_denied:
            try:
                await self.check_target()
                self._allowed = True
            except SafetyAborted:
                pass
        self._finalization["allowed"] = self._allowed
        self._emit()
        return self._allowed

    def can_reconcile(self) -> bool:
        return (
            not self._identity_denied
            and self._allowed
            and self.abort_reason
            in {
                None,
                "correctness",
                "request_ceiling",
                "duration_ceiling",
                "population_ceiling",
            }
        )

    def validate_population(self, count: int) -> None:
        if isinstance(count, bool) or count < 0:
            raise ValueError("invalid population")
        if count > self._number("population"):
            self._exhaust("population")

    def record_finalization(self, operation: str, outcome: str) -> None:
        if operation not in {
            "reconciliation",
            "retention",
            "release",
            "clerk_closure",
        } or outcome not in {
            "not_attempted",
            "passed",
            "failed",
            "skipped",
            "uncertain",
        }:
            raise ValueError("invalid finalization result")
        self._finalization[operation] = outcome
        self._emit()

    def snapshot(self) -> dict[str, object]:
        execution = dict(self._execution)
        execution["elapsed_seconds"] = max(
            0.0,
            (self._final_start if self._final_start is not None else self._now())
            - self._started,
        )
        finalization = dict(self._finalization)
        finalization["elapsed_seconds"] = (
            0.0
            if self._final_start is None
            else max(0.0, self._now() - self._final_start)
        )
        return {
            "policy": dict(self.policy),
            "target": {
                "identity": None if self._identity is None else dict(self._identity),
                "evidence": "unverified"
                if self._identity is None
                else "local"
                if self._local
                else "staging",
            },
            "preflight": dict(self._preflight),
            "probes": dict(self._probes),
            "execution": execution,
            "finalization": finalization,
            "errors": dict(self._errors),
            "abort": None
            if self.abort_reason is None
            else {"reason": self.abort_reason, "elapsed_seconds": self._abort_time},
            "resources": {"monitoring": "unavailable"},
            "concurrency": {
                "ordinary_limit": self.policy["in_flight"],
                "control_limit": 1,
                "combined_limit": _count(self.policy["in_flight"]) + 1,
            },
        }
