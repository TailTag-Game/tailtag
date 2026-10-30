"""Classify Railway and Render Development delivery events without trusting labels alone."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
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
_LABEL = "TailTag / development"
# Render names each GitHub environment "<branch> - <service>". Only the GitHub
# App identity is unforgeable, so it and the pinned service bind the event.
_RENDER_SERVICE_SUFFIX = " - tailtag-api-development"
_RENDER_LABEL = f"main{_RENDER_SERVICE_SUFFIX}"
_RENDER_APP = (14658, "render")
_RENDER_TARGET = re.compile(
    r"https://dashboard\.render\.com/web/(srv-[a-z0-9]{1,60})/deploys/dep-[a-z0-9]{1,60}"
)


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
        or deployment.get("ref") not in {"main", sha}
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


def classify_render_development_deployment_event(event: object) -> str | None:
    """Return the SHA of a successful pinned Render Development deploy, or None."""
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
    target = status.get("target_url")
    if (
        not isinstance(sha, str)
        or _SHA.fullmatch(sha) is None
        or deployment.get("environment") != _RENDER_LABEL
        or deployment.get("ref") != "main"
        or deployment.get("payload") != {}
        or _app(deployment.get("performed_via_github_app")) != _RENDER_APP
        or status.get("state") != "success"
        or status.get("environment") != _RENDER_LABEL
        or _app(status.get("performed_via_github_app")) != _RENDER_APP
        or not isinstance(target, str)
    ):
        return None
    service = _RENDER_TARGET.fullmatch(target)
    if service is None or not _pinned_render_target(
        service.group(1), status.get("environment_url")
    ):
        return None
    return sha


def is_unmatched_render_development_success(event: object) -> bool:
    """Flag a successful Render Development event that the pins reject.

    Such an event means the Render event shape drifted. The workflow fails it
    instead of skipping it, so the missing smoke check is visible.
    """
    if not isinstance(event, dict):
        return False
    document = cast(dict[str, object], event)
    status = document.get("deployment_status")
    if not isinstance(status, dict):
        return False
    status = cast(dict[str, object], status)
    environment = status.get("environment")
    return (
        _app(status.get("performed_via_github_app")) == _RENDER_APP
        and status.get("state") == "success"
        and isinstance(environment, str)
        and environment.endswith(_RENDER_SERVICE_SUFFIX)
        and classify_render_development_deployment_event(document) is None
    )


def _pinned_render_target(service_id: str, environment_url: object) -> bool:
    api_directory = Path(__file__).resolve().parents[1] / "services/api"
    if str(api_directory) not in sys.path:
        sys.path.insert(0, str(api_directory))
    from config import replacement_target_binding as binding

    if not isinstance(environment_url, str) or not environment_url.startswith(
        "https://"
    ):
        return False
    try:
        origin = binding.pinned_render_origin(
            "development", environment_url.removeprefix("https://")
        )
        binding.pinned_render_service("development", service_id)
    except binding.TargetBindingError:
        return False
    return origin == environment_url


def _app(value: object) -> tuple[int, str] | None:
    if not isinstance(value, dict):
        return None
    app = cast(dict[str, object], value)
    app_id, slug = app.get("id"), app.get("slug")
    if type(app_id) is not int or not isinstance(slug, str):
        return None
    return app_id, slug


def _creator_login(value: object) -> object:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value).get("login")


def main() -> int:
    """Read the event file and write only fixed classification and safe SHA."""
    sha: str | None = None
    target = ""
    drifted = False
    try:
        path = os.environ["GITHUB_EVENT_PATH"]
        if Path(path).stat().st_size <= 65536:
            event = json.loads(Path(path).read_text())
            sha = classify_development_deployment_event(event)
            target = "railway" if sha else ""
            if sha is None:
                sha = classify_render_development_deployment_event(event)
                target = "render" if sha else ""
                drifted = is_unmatched_render_development_success(event)
    except (OSError, KeyError, UnicodeError, ValueError):
        pass
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as stream:
            stream.write(f"should_verify={'true' if sha else 'false'}\n")
            stream.write(f"checkout_ref={sha or ''}\n")
            stream.write(f"verification_mode={'event' if sha else ''}\n")
            stream.write(f"deployment_sha={sha or ''}\n")
            stream.write(f"target={target}\n")
    if drifted:
        print("Render Development event does not match the pinned shape")
        return 1
    print("Eligible Development event" if sha else "Skip Development event")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
