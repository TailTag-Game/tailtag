"""Classify Railway Development delivery events without trusting display labels alone."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_SHA = re.compile(r"[0-9a-f]{40}")
_EXPECTED_GENERATION_DIGEST = (
    "28f2adc0fdba2d36145b5c2bff65ab15e15022cf1bf41df50442641a637ea3ae"
)
_LABEL = "TailTag Rebuild / development"


def fingerprint_development_generation(project: str, environment: str) -> str:
    """Hash canonical provider IDs in the reviewed event namespace."""
    if _UUID.fullmatch(project) is None or _UUID.fullmatch(environment) is None:
        raise ValueError("Invalid generation")
    fields = ("tailtag-rebuild-event-v1", "development", project, environment)
    return hashlib.sha256("\0".join(fields).encode()).hexdigest()


def _link(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "railway.com"
            or parsed.fragment
            or not parsed.path.startswith("/project/")
        ):
            return None
        project = parsed.path.removeprefix("/project/")
        if _UUID.fullmatch(project) is None:
            return None
        prefix = "environmentId="
        if not parsed.query.startswith(prefix):
            return None
        environment = parsed.query.removeprefix(prefix)
        if _UUID.fullmatch(environment) is None:
            return None
        if (
            value
            != f"https://railway.com/project/{project}?environmentId={environment}"
        ):
            return None
        return project, environment
    except ValueError:
        return None


def classify_development_deployment_event(event: object) -> str | None:
    """Return only an eligible canonical source SHA; deny every shape drift."""
    if not isinstance(event, dict):
        return None
    document = cast(dict[str, object], event)
    deployment = document.get("deployment")
    status = document.get("deployment_status")
    if not isinstance(deployment, dict) or not isinstance(status, dict):
        return None
    deployment = cast(dict[str, object], deployment)
    status = cast(dict[str, object], status)
    sha = deployment.get("sha")
    payload = deployment.get("payload")
    if not isinstance(payload, dict):
        return None
    payload = cast(dict[str, object], payload)
    if (
        not isinstance(sha, str)
        or _SHA.fullmatch(sha) is None
        or deployment.get("environment") != _LABEL
        or deployment.get("ref") != "main"
        or _creator_login(deployment.get("creator")) != "railway-app[bot]"
        or set(payload) != {"environmentId"}
        or status.get("state") != "success"
        or status.get("environment") != _LABEL
        or _creator_login(status.get("creator")) != "railway-app[bot]"
    ):
        return None
    target = _link(status.get("target_url"))
    environment_link = _link(status.get("environment_url"))
    if (
        target is None
        or target != environment_link
        or payload.get("environmentId") != target[1]
    ):
        return None
    if fingerprint_development_generation(*target) != _EXPECTED_GENERATION_DIGEST:
        return None
    return sha


def _creator_login(value: object) -> object:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value).get("login")


def main() -> int:
    """Read the event file and write only fixed classification and safe SHA."""
    sha: str | None = None
    try:
        path = os.environ["GITHUB_EVENT_PATH"]
        if Path(path).stat().st_size <= 65536:
            sha = classify_development_deployment_event(
                json.loads(Path(path).read_text())
            )
    except (OSError, KeyError, UnicodeError, ValueError):
        pass
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as stream:
            stream.write(f"should_verify={'true' if sha else 'false'}\n")
            stream.write(f"checkout_ref={sha or ''}\n")
            stream.write(f"verification_mode={'event' if sha else ''}\n")
            stream.write(f"deployment_sha={sha or ''}\n")
    print("Eligible Development event" if sha else "Skip Development event")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
