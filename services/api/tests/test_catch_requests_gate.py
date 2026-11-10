"""Catch request gate parsing and v1 retirement (#504 AC14, AC16).

With the gate off, the existing v1 suites prove that v1 works as before.
"""

from __future__ import annotations

from typing import Any

import pytest

from catches.models import Catch
from config.catch_requests_gate import parse_catch_requests_enabled
from conventions.models import FursuitCatchCredential
from tests.authentication_support import force_authenticated_client
from tests.catch_credential_test_support import (
    owner_credential_path,
    resolution_path,
    rotation_path,
)
from tests.catch_test_support import create_catch_confirmation_scenario
from tests.fursuit_tag_test_support import GENERIC_NOT_FOUND, TARGET_UNAVAILABLE


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ({}, False),
        ({"CATCH_REQUESTS_ENABLED": "false"}, False),
        ({"CATCH_REQUESTS_ENABLED": "true"}, True),
    ],
)
def test_gate_reads_only_true_or_false(
    environment: dict[str, str], expected: bool
) -> None:
    assert parse_catch_requests_enabled(environment) is expected


@pytest.mark.parametrize("value", ["", "True"])
def test_gate_stops_startup_for_any_other_value(value: str) -> None:
    with pytest.raises(RuntimeError, match="must be true or false"):
        parse_catch_requests_enabled({"CATCH_REQUESTS_ENABLED": value})


@pytest.mark.django_db
def test_gate_on_retires_the_four_v1_operations(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True
    scenario = create_catch_confirmation_scenario()
    catcher = force_authenticated_client(user=scenario.catcher_user)
    owner = force_authenticated_client(user=scenario.target_user)
    convention_id = scenario.convention.pk
    fursuit_id = scenario.fursuit.pk
    credentials_before = list(FursuitCatchCredential.objects.values())

    resolve = catcher.post(
        resolution_path(convention_id),
        {"payload": scenario.payload},
        content_type="application/json",
    )
    confirm = catcher.post(
        "/api/catches/confirm/",
        {"payload": scenario.payload},
        content_type="application/json",
    )
    fetch = owner.get(owner_credential_path(convention_id, fursuit_id))
    rotate = owner.post(
        rotation_path(convention_id, fursuit_id), b"", content_type="application/json"
    )

    assert (resolve.status_code, resolve.json()) == (404, TARGET_UNAVAILABLE)
    assert (confirm.status_code, confirm.json()) == (404, TARGET_UNAVAILABLE)
    assert (fetch.status_code, fetch.json()) == (404, GENERIC_NOT_FOUND)
    assert (rotate.status_code, rotate.json()) == (404, GENERIC_NOT_FOUND)
    assert not Catch.objects.exists()
    assert list(FursuitCatchCredential.objects.values()) == credentials_before
