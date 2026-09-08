"""Shared deterministic storage test configuration."""

from __future__ import annotations

import pytest
from pytest_django.fixtures import SettingsWrapper


@pytest.fixture(autouse=True)
def deterministic_storage(settings: SettingsWrapper) -> None:
    """Keep media and static storage independent of the selected settings profile."""
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
