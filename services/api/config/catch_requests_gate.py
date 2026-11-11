"""The one server gate for reusable tags and catch requests.

With the gate off, the new operations return 404 and the v1 flow works as
before. With the gate on, the new operations work and the v1 player operations
retire. See the reusable TailTag contract, section "Gate".
"""

from __future__ import annotations

from collections.abc import Mapping

GATE_ENVIRONMENT_VARIABLE = "CATCH_REQUESTS_ENABLED"


def parse_catch_requests_enabled(environment: Mapping[str, str]) -> bool:
    """Return the gate from the environment. Only ``true`` or ``false`` is valid."""
    value = environment.get(GATE_ENVIRONMENT_VARIABLE)
    if value is None or value == "false":
        return False
    if value == "true":
        return True
    message = f"{GATE_ENVIRONMENT_VARIABLE} must be true or false."
    raise RuntimeError(message)


def catch_requests_enabled() -> bool:
    """Read the gate from Django settings at request time."""
    from django.conf import settings

    return bool(getattr(settings, "CATCH_REQUESTS_ENABLED", False))
