"""The Staging runtime check that every simulation relay makes first (#199, #411)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

# Render runs each instance as `<service ID>-<hex>-<5-character slug>` (#411 AC1).
_RENDER_INSTANCE: Final = re.compile(r"(srv-[a-z0-9]{1,60})-[0-9a-f]{1,32}-[a-z0-9]{5}")


class TargetRefused(Exception):
    """This runtime is not the named Staging API, or not the pinned instance."""


def _render_staging(environ: Mapping[str, str]) -> bool:
    # Import only when needed: the binding module resolves the operator home
    # directory at import.
    from config import replacement_target_binding

    try:
        return (
            replacement_target_binding.runtime_host(environ) == "render"
            and replacement_target_binding.validate_runtime_target(environ) == "staging"
        )
    except replacement_target_binding.TargetBindingError:
        return False


def check(
    identity: Mapping[str, object],
    runtime_identity: Mapping[str, object],
    environ: Mapping[str, str],
    expected_instance: object,
) -> str | None:
    """Return this Render instance.

    Raises `TargetRefused` outside the named Staging API. On Render, a request
    that names an instance must reach exactly that instance, so a restart or a
    redeploy during a run fails closed.
    """
    instance = environ.get("RENDER_INSTANCE_ID")
    match = None if instance is None else _RENDER_INSTANCE.fullmatch(instance)
    # The binding module is consulted last, so a runtime without a Render
    # instance is refused without importing it.
    valid = (
        identity.get("deployment_id") is None
        and match is not None
        and match.group(1) == environ.get("RENDER_SERVICE_ID")
        and expected_instance in (None, instance)
        and _render_staging(environ)
    )
    if not (
        valid
        and identity.get("environment") == "staging"
        and isinstance(identity.get("source_sha"), str)
        and dict(runtime_identity) == dict(identity)
    ):
        raise TargetRefused
    return instance
