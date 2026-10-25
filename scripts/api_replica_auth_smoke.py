"""Guarded bootstrap-only authentication smoke check for the hybrid replica.

One verified `/api/me/` call per synthetic Clerk user creates the API user row
that replica `provision` needs. It reuses the Staging flow with the replica pins.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Final

from scripts.api_staging_auth_smoke import DefaultSmokeRuntime, SmokeProfile, run_main

from config.replica_binding import ReplicaBindingError, validate_run_app_host

REPLICA_CLERK_INSTANCE_FINGERPRINT: Final = "4f93c7ed6c240ce2"
REPLICA_CLERK_PORTAL_ORIGIN: Final = "https://accounts.replica.tailtag.app"

# The API verifier builds a Django request, which reads settings; no database is used.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.build")

_CONFIRMATION: Final = "run-clerk-replica-auth-smoke"
_SCHEME: Final = "https://"


def _valid_target(environment: Mapping[str, str]) -> tuple[str, str] | None:
    base_url = environment.get("TAILTAG_REPLICA_API_BASE_URL", "")
    user_id = environment.get("CLERK_REPLICA_SMOKE_USER_ID", "")
    if (
        environment.get("TAILTAG_REPLICA_AUTH_SMOKE_CONFIRM") != _CONFIRMATION
        or not base_url.startswith(_SCHEME)
        or not user_id
    ):
        return None
    try:
        host = validate_run_app_host([base_url.removeprefix(_SCHEME)])
    except ReplicaBindingError:
        return None
    return f"{_SCHEME}{host}", user_id


REPLICA_PROFILE: Final = SmokeProfile(
    environment="replica",
    valid_target=_valid_target,
    instance_fingerprint=REPLICA_CLERK_INSTANCE_FINGERPRINT,
    portal_origin=REPLICA_CLERK_PORTAL_ORIGIN,
    party_variable=None,
    # A scaled-to-zero service can take over 10 s to answer its first request.
    warm_up_path="/health/ready",
)


def main() -> int:
    return run_main(
        REPLICA_PROFILE, lambda: DefaultSmokeRuntime(profile=REPLICA_PROFILE)
    )


if __name__ == "__main__":
    raise SystemExit(main())
