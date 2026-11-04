"""Carry one simulation relay request to Render Staging (#411 AC3, AC5).

The relays reach the Render Staging API over plain `ssh` to the Virginia
gateway (ADR 0012), with the gateway host key pinned here. The first call of a command or
run uses the service user, and the remote answer names the instance that ran
it. Later calls name that instance and use its exact ssh user. If the instance
is gone, ssh fails. If it was replaced, the remote check answers
`FAIL_TARGET`. Both fail closed.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final, cast

from scripts import api_staging_preflight as _staging_preflight
from scripts import api_staging_reset_ssh as _reset_ssh

_run = _reset_ssh._run  # pyright: ignore[reportPrivateUsage]
_json_loads = _reset_ssh._json_loads  # pyright: ignore[reportPrivateUsage]

GATEWAY: Final = "ssh.virginia.render.com"
# Render documents this key as SHA256:NCpSwboPnqL/Nvyy2Qc8Kgzpc3P/f3w5wDphhc+UZO0.
_GATEWAY_KEY: Final = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ6uO0jKQX9IjefnLz+pxTgfPhsPBhNuvxmvCFrxqxAM"
)
_INSTANCE: Final = re.compile(r"(srv-[a-z0-9]{1,60})-[0-9a-f]{1,32}-([a-z0-9]{5})")
# The remote answers without an instance only before its target check passes.
_UNPINNED_RESULTS: Final = frozenset({"FAIL_TARGET", "FAIL_BOOTSTRAP"})
_SSH_OPTIONS: Final = (
    "BatchMode=yes",
    "StrictHostKeyChecking=yes",
    "GlobalKnownHostsFile=/dev/null",
    "IdentitiesOnly=yes",
    "ForwardAgent=no",
    "ForwardX11=no",
    "ClearAllForwardings=yes",
    "UpdateHostKeys=no",
    # User ssh config must not reuse a connection, add trusted keys or run
    # local commands around the pinned gateway.
    "ControlMaster=no",
    "ControlPath=none",
    "KnownHostsCommand=none",
    "PermitLocalCommand=no",
    "ProxyCommand=none",
    "ConnectTimeout=30",
)


def active() -> bool:
    """True while Render serves Staging in either phase (#409, #452).

    Before the #452 cutover, the Virginia pools are rebuilt over these relays
    in the candidate phase. The Railway relay path stays frozen until #412.
    """
    return _staging_preflight._RENDER_STAGING_PHASE in {"candidate", "canonical"}  # pyright: ignore[reportPrivateUsage]


def _service_id() -> str:
    api_root = Path(__file__).resolve().parents[1] / "services" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))
    from config.replacement_target_binding import load_render_staging_service_id

    return load_render_staging_service_id()


def _identity() -> dict[str, object]:
    return dict(_staging_preflight.validate_render_staging_target())


def _user(service_id: str, expected_instance: object) -> str:
    if expected_instance is None:
        return service_id
    match = (
        _INSTANCE.fullmatch(expected_instance)
        if isinstance(expected_instance, str)
        else None
    )
    if match is None or match.group(1) != service_id:
        raise ValueError
    return f"{service_id}-{match.group(2)}"


def execute(
    request: Mapping[str, object],
    bootstrap: str,
    validated_output: Callable[[str], dict[str, object]],
    *,
    timeout: int,
) -> dict[str, object]:
    """Run one relay request on the Render Staging instance; any deviation raises."""
    identity = _identity()
    if "expected_identity" in request and request["expected_identity"] != identity:
        return {"result": "FAIL_TARGET", "data": {}}
    service_id = _service_id()
    expected_instance = request.get("expected_instance")
    user = _user(service_id, expected_instance)
    remote_request = {
        key: value for key, value in request.items() if key != "expected_identity"
    }
    with tempfile.TemporaryDirectory() as directory:
        known_hosts = Path(directory) / "known_hosts"
        known_hosts.write_text(f"{GATEWAY} {_GATEWAY_KEY}\n", encoding="utf-8")
        options = [*_SSH_OPTIONS, f'UserKnownHostsFile="{known_hosts}"']
        execution = _run(
            [
                "ssh",
                "-T",
                *[part for option in options for part in ("-o", option)],
                f"{user}@{GATEWAY}",
                shlex.join(["/app/.venv/bin/python", "-I", "-c", bootstrap]),
            ],
            input=json.dumps(
                {**remote_request, "identity": identity}, separators=(",", ":")
            ),
            timeout=timeout,
        )
    if execution.returncode != 0:
        raise ValueError
    value = _json_loads(execution.stdout)
    if not isinstance(value, dict):
        raise TypeError
    reply = dict(cast(dict[str, object], value))
    instance = reply.pop("instance", None)
    output = validated_output(json.dumps(reply))
    if instance is None:
        if output["result"] not in _UNPINNED_RESULTS:
            raise ValueError
        return output
    match = _INSTANCE.fullmatch(instance) if isinstance(instance, str) else None
    if (
        match is None
        or match.group(1) != service_id
        or expected_instance not in (None, instance)
    ):
        raise ValueError
    return {**output, "instance": instance}
