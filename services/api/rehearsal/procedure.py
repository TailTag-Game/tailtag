"""The one guarded provision or reset sequence shared by Railway and the replica."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Self

from .baseline import BASELINE_VERSION

if TYPE_CHECKING:
    from .safety import ResetConfiguration


class Maintenance(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(self, *args: object) -> None: ...
    def quiesce(self) -> None: ...
    def resume(self) -> None: ...


@dataclass(frozen=True)
class Outcome:
    """One failed phase name, or the observed identity and reset counts on success."""

    failure: str | None = None
    identity: Mapping[str, object] | None = None
    counts: dict[str, int] | None = None
    baseline_version: int = BASELINE_VERSION


def run(
    *,
    provision: bool,
    preflight: Callable[[], Mapping[str, object]],
    load_configuration: Callable[[], ResetConfiguration],
    maintenance: Callable[[ResetConfiguration], Maintenance],
    reset_baseline: Callable[[ResetConfiguration], dict[str, int]],
    provision_identity: Callable[[ResetConfiguration], None],
    bootstrap: Callable[[], None] | None = None,
) -> Outcome:
    """Run the already confirmed procedure and name the phase that failed, if any."""
    try:
        initial_identity = preflight()
    except Exception:  # noqa: BLE001
        return Outcome("preflight")
    try:
        if bootstrap is not None:
            bootstrap()
        configuration = load_configuration()
    except Exception:  # noqa: BLE001
        return Outcome("configuration")
    if provision:
        try:
            provision_identity(configuration)
        except Exception:  # noqa: BLE001
            return Outcome("provision")
        return Outcome(identity=initial_identity)
    try:
        with maintenance(configuration) as gate:
            try:
                gate.quiesce()
            except BaseException:  # noqa: BLE001
                return Outcome("maintenance unknown")
            try:
                counts = reset_baseline(configuration)
            except BaseException:  # noqa: BLE001
                return Outcome("maintenance retained")
            try:
                gate.resume()
                if preflight() != initial_identity:
                    raise RuntimeError
            except BaseException:  # noqa: BLE001
                try:
                    gate.quiesce()
                except Exception:  # noqa: BLE001
                    return Outcome("maintenance unknown")
                return Outcome("committed maintenance retained")
    except BaseException:  # noqa: BLE001
        return Outcome("maintenance unknown")
    return Outcome(identity=initial_identity, counts=counts)
