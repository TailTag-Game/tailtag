"""Name the hosting platform of a guarded Staging operator command (#410)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal


def staging_platform(
    environment: Mapping[str, str],
) -> Literal["render"] | None:
    """Return "render" only for the pinned Render Staging service.

    Any other runtime returns None.
    """
    # Import here, not at module load: the binding resolves the operator home
    # directory at import, and commands that only parse arguments need none.
    from config import replacement_target_binding

    try:
        if replacement_target_binding.runtime_host(environment) != "render":
            return None
        if replacement_target_binding.validate_runtime_target(environment) != (
            "staging"
        ):
            return None
    except replacement_target_binding.TargetBindingError:
        return None
    return "render"
