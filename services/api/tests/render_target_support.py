"""Synthetic Render targets for the guarded operator command tests (#412)."""

from __future__ import annotations

import importlib
import os

import pytest

STAGING_SERVICE = "srv-optargetstaging0000"
DEVELOPMENT_SERVICE = "srv-optargetdevelop0000"
UNPINNED_SERVICE = "srv-optargetunpinned000"


def pin_render_services(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the two synthetic services and stub the separately tested AC5 gate."""
    binding = importlib.import_module("config.replacement_target_binding")
    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_DIGESTS",
        {
            "development": binding.fingerprint_render_service(
                "development", DEVELOPMENT_SERVICE
            ),
            "staging": binding.fingerprint_render_service("staging", STAGING_SERVICE),
        },
    )
    safety = importlib.import_module("rehearsal.safety")
    monkeypatch.setattr(safety, "validate_database", _skip_database_check)
    monkeypatch.setattr(safety, "load_configuration", _skip_configuration_load)


def _skip_database_check(configuration: object) -> None:
    del configuration


def _skip_configuration_load(environment: object) -> None:
    del environment


def select_render_service(
    monkeypatch: pytest.MonkeyPatch, service_id: str | None = STAGING_SERVICE
) -> None:
    """Run as that Render service, or with no Render variables when None."""
    for name in list(os.environ):
        if name.startswith(("RAILWAY_", "RENDER")):
            monkeypatch.delenv(name)
    if service_id is not None:
        monkeypatch.setenv("RENDER", "true")
        monkeypatch.setenv("RENDER_SERVICE_ID", service_id)


INSTANCE = f"{STAGING_SERVICE}-874b544b8-k7qws"
RENDER_STAGING_ENVIRON = {
    "RENDER": "true",
    "RENDER_SERVICE_ID": STAGING_SERVICE,
    "RENDER_INSTANCE_ID": INSTANCE,
}
