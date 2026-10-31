"""Name the hosting platform of a guarded Staging operator command (#410)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal


def staging_platform(
    environment: Mapping[str, str],
) -> Literal["railway", "render"] | None:
    """Return "render" only for the pinned Render Staging service.

    Any other Render runtime, or a runtime with both platforms' variables,
    returns None. A runtime with no Render variables returns "railway", and
    the caller then applies its own unchanged Railway target checks.
    """
    # Import here, not at module load: the binding resolves the operator home
    # directory at import, and commands that only parse arguments need none.
    from config import replacement_target_binding

    try:
        if replacement_target_binding.runtime_host(environment) != "render":
            return "railway"
        if replacement_target_binding.validate_runtime_target(environment) != (
            "staging"
        ):
            return None
    except replacement_target_binding.TargetBindingError:
        return None
    return "render"
