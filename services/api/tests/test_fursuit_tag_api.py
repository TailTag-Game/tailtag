"""Owner tag read and replacement acceptance tests (#504 AC1, AC2, AC5 to AC7, AC9, AC11, AC13, AC15)."""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml
from django.db import connection
from django.test import Client

from catches.models import Catch
from conventions.models import FursuitActivation, FursuitCatchSession
from fursuits.models import Fursuit, FursuitTag
from fursuits.tags import revoke_tag_as_operator
from tests.catch_test_support import create_catch, create_catch_scenario
from tests.fursuit_tag_test_support import (
    GENERIC_NOT_FOUND,
    PREVIEW_PATH,
    assert_logs_hold_no_token,
    assert_no_token_leak,
    create_player,
    create_suit,
    owner_client,
    replace_path,
    tag_path,
)

pytestmark = pytest.mark.django_db

_PAYLOAD = re.compile(r"\Ahttps://tailtag\.app/t#[A-Za-z0-9_-]{43}\Z")


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    settings.CATCH_REQUESTS_ENABLED = True


def _replace(user: Any, fursuit: Fursuit, body: object) -> Any:
    return owner_client(user).post(
        replace_path(fursuit.pk), body, content_type="application/json"
    )


def test_first_read_creates_one_reusable_tag_and_repeat_reads_return_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    owner, _ = create_player("first_read")
    fursuit = create_suit(owner)

    first = owner_client(owner).get(tag_path(fursuit.pk))
    second = owner_client(owner).get(tag_path(fursuit.pk))

    assert first.status_code == 200
    body = first.json()
    assert body["fursuit_id"] == fursuit.pk
    assert body["state"] == "current"
    assert body["tag_version"] == 1
    assert _PAYLOAD.fullmatch(body["payload"])
    assert first.headers["Cache-Control"] == "no-store"
    assert second.json() == body
    assert FursuitTag.objects.filter(fursuit=fursuit).count() == 1
    # The tag needs no convention, activation, or session, and creates none.
    assert not FursuitActivation.objects.filter(fursuit=fursuit).exists()
    assert not FursuitCatchSession.objects.exists()
    assert_logs_hold_no_token(caplog)


def test_replacement_ends_old_copies_and_keeps_identity_catches_and_session(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scenario = create_catch_scenario(target_owner_clerk_user_id="tag_replace_owner")
    owner = scenario.fursuit.owner
    catch = create_catch(scenario=scenario)
    old = owner_client(owner).get(tag_path(scenario.fursuit.pk)).json()
    tailtag_id = scenario.fursuit.tailtag_id

    response = _replace(owner, scenario.fursuit, {"expected_version": 1})

    assert response.status_code == 200
    new = response.json()
    assert new["state"] == "current"
    assert new["tag_version"] == 2
    assert new["payload"] != old["payload"]
    assert response.headers["Cache-Control"] == "no-store"
    old_row = FursuitTag.objects.get(created_version=1, fursuit=scenario.fursuit)
    assert old_row.revocation_reason == "owner_replacement"
    assert owner_client(owner).get(tag_path(scenario.fursuit.pk)).json() == new
    fursuit = Fursuit.objects.get(pk=scenario.fursuit.pk)
    assert fursuit.tailtag_id == tailtag_id
    assert Catch.objects.filter(pk=catch.pk).exists()
    session = FursuitCatchSession.objects.get(pk=scenario.catch_session.pk)
    assert session.ended_at is None
    assert FursuitActivation.objects.get(pk=scenario.activation.pk).is_active
    assert_logs_hold_no_token(caplog)


def test_stale_replacement_conflicts_without_payload_or_change() -> None:
    owner, _ = create_player("stale")
    fursuit = create_suit(owner)
    current = owner_client(owner).get(tag_path(fursuit.pk)).json()

    response = _replace(owner, fursuit, {"expected_version": 0})

    assert response.status_code == 409
    assert response.json() == {
        "code": "tag_version_conflict",
        "detail": "The tag changed. Read the current tag.",
        "current": {"fursuit_id": fursuit.pk, "state": "current", "tag_version": 1},
    }
    assert_no_token_leak(response.content.decode())
    assert FursuitTag.objects.filter(fursuit=fursuit).count() == 1
    assert owner_client(owner).get(tag_path(fursuit.pk)).json() == current


def test_replacement_on_a_never_tagged_suit_follows_the_version_rule() -> None:
    owner, _ = create_player("never_tagged")
    fursuit = create_suit(owner)

    stale = _replace(owner, fursuit, {"expected_version": 3})
    created = _replace(owner, fursuit, {"expected_version": 0})

    assert stale.status_code == 409
    assert stale.json()["current"] == {
        "fursuit_id": fursuit.pk,
        "state": "none",
        "tag_version": 0,
    }
    assert created.status_code == 200
    assert created.json()["tag_version"] == 1
    assert created.json()["state"] == "current"
    assert FursuitTag.objects.filter(fursuit=fursuit).count() == 1


def test_operator_revocation_leaves_a_revoked_read_until_the_owner_replaces() -> None:
    owner, _ = create_player("revoked_read")
    fursuit = create_suit(owner)
    owner_client(owner).get(tag_path(fursuit.pk))
    revoke_tag_as_operator(FursuitTag.objects.get(fursuit=fursuit).pk)

    first = owner_client(owner).get(tag_path(fursuit.pk))
    second = owner_client(owner).get(tag_path(fursuit.pk))
    rows_after_reads = FursuitTag.objects.filter(fursuit=fursuit).count()
    replaced = _replace(owner, fursuit, {"expected_version": 2})

    revoked = {
        "fursuit_id": fursuit.pk,
        "state": "revoked",
        "tag_version": 2,
        "payload": None,
    }
    assert first.json() == revoked
    assert second.json() == revoked
    assert rows_after_reads == 1
    assert replaced.status_code == 200
    assert replaced.json()["state"] == "current"
    assert replaced.json()["tag_version"] == 3


@pytest.mark.parametrize("method", ["get", "replace"])
def test_owner_errors_use_the_contract_codes(method: str) -> None:
    owner, _ = create_player(f"errors_{method}")
    other, _ = create_player(f"errors_other_{method}")
    disabled = create_suit(owner, enabled=False)
    foreign = create_suit(other)
    ineligible_owner, _ = create_player(f"errors_ineligible_{method}", enabled=False)
    ineligible_suit = create_suit(ineligible_owner)

    def call(user: Any, fursuit: Fursuit) -> Any:
        if method == "get":
            return owner_client(user).get(tag_path(fursuit.pk))
        return _replace(user, fursuit, {"expected_version": 0})

    not_owned = call(owner, foreign)
    disabled_suit = call(owner, disabled)
    ineligible = call(ineligible_owner, ineligible_suit)

    assert not_owned.status_code == 404
    assert not_owned.json() == {
        "code": "fursuit_not_found",
        "detail": "The fursuit was not found.",
    }
    assert disabled_suit.status_code == 409
    assert disabled_suit.json() == {
        "code": "fursuit_disabled",
        "detail": "The fursuit is disabled.",
    }
    assert ineligible.status_code == 403
    assert not FursuitTag.objects.exists()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expected_version": "1"},
        {"expected_version": True},
        {"expected_version": -1},
        {"expected_version": 1, "extra": 1},
        [1],
    ],
)
def test_replacement_rejects_a_body_that_is_not_one_non_negative_integer(
    body: object,
) -> None:
    owner, _ = create_player("bad_body")
    fursuit = create_suit(owner)

    response = _replace(owner, fursuit, body)

    assert response.status_code == 400
    assert response.json() == {
        "expected_version": ["A non-negative integer is required."]
    }
    assert not FursuitTag.objects.exists()


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "tag"), ("post", "replace"), ("post", "preview")],
)
def test_gate_off_hides_the_new_operations(
    settings: Any, method: str, path: str
) -> None:
    settings.CATCH_REQUESTS_ENABLED = False
    owner, _ = create_player(f"gate_off_{path}")
    fursuit = create_suit(owner)
    url = {
        "tag": tag_path(fursuit.pk),
        "replace": replace_path(fursuit.pk),
        "preview": PREVIEW_PATH,
    }[path]
    client = owner_client(owner)

    response = (
        client.get(url)
        if method == "get"
        else client.post(url, {"expected_version": 0}, content_type="application/json")
    )

    assert response.status_code == 404
    assert response.json() == GENERIC_NOT_FOUND
    assert not FursuitTag.objects.exists()


def test_an_older_image_can_insert_a_fursuit_without_the_tag_version_column() -> None:
    owner, _ = create_player("old_image")
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO fursuits_fursuit "
            "(owner_id, name, tailtag_id, photo_key, is_enabled, created_at, updated_at) "
            "VALUES (%s, 'Old Image', gen_random_uuid(), 'images/a.png', true, now(), now()) "
            "RETURNING id",
            [owner.pk],
        )
        row = cursor.fetchone()
    assert row is not None
    assert Fursuit.objects.get(pk=row[0]).tag_version == 0


@pytest.mark.parametrize(
    "path", ["/api/catches/preview/", "/api/fursuits/{id}/tag/replace/"]
)
def test_openapi_marks_the_tag_request_bodies_required(path: str) -> None:
    response = Client().get("/api/schema/")
    schema = yaml.safe_load(response.content)

    assert schema["paths"][path]["post"]["requestBody"]["required"] is True
