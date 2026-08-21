"""Shared deterministic media-storage test configuration."""

from __future__ import annotations

import pytest
from pytest_django.fixtures import SettingsWrapper


@pytest.fixture(autouse=True)
def deterministic_default_storage(settings: SettingsWrapper) -> None:
    """Keep media tests local while preserving Django's staticfiles storage alias."""
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    }
