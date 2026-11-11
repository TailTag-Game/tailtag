"""Catch request constraints and the #505 schema migration (AC15, AC16, AC24, AC25)."""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from catches.models import Catch, CatchRequest, CatchRequestState
from tests.authentication_support import force_authenticated_client
from tests.catch_test_support import create_catch_confirmation_scenario
from tests.fursuit_tag_test_support import (
    PreviewScenario,
    create_preview_scenario,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def gate_on(settings: Any) -> None:
    """The scenario helper reads the tag through the gated owner API."""
    settings.CATCH_REQUESTS_ENABLED = True


def _row(scenario: PreviewScenario, **values: Any) -> CatchRequest:
    fields: dict[str, Any] = {
        "player": scenario.catcher,
        "fursuit": scenario.fursuit,
        "convention": scenario.convention,
        "activation": scenario.activation,
        "catch_session": scenario.session,
        "state": CatchRequestState.PENDING,
        "requested_at": timezone.now(),
    }
    fields.update(values)
    return CatchRequest.objects.create(**fields)


def test_a_trio_holds_at_most_one_pending_request() -> None:
    """AC16: the named partial unique constraint. Other states may repeat."""
    scenario = create_preview_scenario("one_pending")
    now = timezone.now()
    _row(scenario)
    _row(scenario, state=CatchRequestState.WITHDRAWN, withdrawn_at=now)

    with (
        pytest.raises(IntegrityError, match="catches_request_one_pending_per_trio"),
        transaction.atomic(),
    ):
        _row(scenario)


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"state": "approved"}, "catches_request_state_times"),
        ({"declined_at": "now"}, "catches_request_state_times"),
        (
            {"state": "declined", "declined_at": "now", "approved_at": "now"},
            "catches_request_state_times",
        ),
        (
            {"state": "withdrawn", "withdrawn_at": "now", "invalidated_at": "now"},
            "catches_request_state_times",
        ),
        ({"state": "expired"}, "catches_request_state_times"),
        ({"decline_blocked": True}, "catches_request_block_needs_decline"),
    ],
)
def test_state_and_decision_times_must_agree(
    values: dict[str, Any], constraint: str
) -> None:
    """AC15: each state carries its own time and no conflicting one."""
    scenario = create_preview_scenario("state_times")
    now = timezone.now()
    resolved = {key: now if value == "now" else value for key, value in values.items()}

    with pytest.raises(IntegrityError, match=constraint), transaction.atomic():
        _row(scenario, **resolved)


@pytest.mark.parametrize("state", ["withdrawn", "invalidated"])
def test_a_final_state_can_keep_a_counted_decline(state: str) -> None:
    """AC15: self-leave and operator actions keep declined_at for the cooldown."""
    scenario = create_preview_scenario(f"counted_{state}")
    now = timezone.now()

    row = _row(
        scenario,
        state=state,
        declined_at=now,
        decline_blocked=True,
        **{f"{state}_at": now},
    )

    assert row.pk


def test_an_older_image_can_insert_a_catch_and_a_fursuit() -> None:
    """AC1, AC24: the new columns have database defaults for old-image inserts."""
    scenario = create_preview_scenario("old_image")
    caught_at = timezone.now() - datetime.timedelta(hours=1)
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO catches_catch (catcher_user_id, fursuit_id, convention_id,"
            " activation_id, catch_session_id, caught_at)"
            " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, approved_at",
            [
                scenario.catcher.pk,
                scenario.fursuit.pk,
                scenario.convention.pk,
                scenario.activation.pk,
                scenario.session.pk,
                caught_at,
            ],
        )
        catch_id, approved_at = cursor.fetchone()
        cursor.execute(
            "INSERT INTO fursuits_fursuit (owner_id, name, tailtag_id, photo_key,"
            " is_enabled, tag_version, created_at, updated_at)"
            " SELECT owner_id, 'Old Image', gen_random_uuid(), photo_key, true, 0,"
            " now(), now() FROM fursuits_fursuit WHERE id = %s"
            " RETURNING catch_approval_mode",
            [scenario.fursuit.pk],
        )
        (mode,) = cursor.fetchone()

    assert Catch.objects.filter(pk=catch_id).exists()
    assert approved_at is not None
    assert mode == "manual"


def test_the_migration_backfills_approved_at_from_caught_at() -> None:
    """AC24, AC25: existing catches keep caught_at and gain an equal approved_at."""
    from django.db.migrations.executor import MigrationExecutor

    scenario = create_preview_scenario("backfill")
    caught_at = datetime.datetime(2026, 7, 3, 15, 4, 5, 123456, tzinfo=datetime.UTC)
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    executor.migrate([("catches", "0001_initial")])
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO catches_catch (catcher_user_id, fursuit_id,"
                " convention_id, activation_id, catch_session_id, caught_at)"
                " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                [
                    scenario.catcher.pk,
                    scenario.fursuit.pk,
                    scenario.convention.pk,
                    scenario.activation.pk,
                    scenario.session.pk,
                    caught_at,
                ],
            )
            (catch_id,) = cursor.fetchone()
            # Fire the deferred foreign key checks before the next ALTER TABLE.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        MigrationExecutor(connection).migrate(latest)

        catch = Catch.objects.get(pk=catch_id)
        assert catch.caught_at == caught_at
        assert catch.approved_at == caught_at
        assert (catch.activation_id, catch.catch_session_id) == (
            scenario.activation.pk,
            scenario.session.pk,
        )
    finally:
        MigrationExecutor(connection).migrate(latest)


def test_a_v1_confirmation_records_equal_catch_and_approval_times(
    settings: Any,
) -> None:
    """AC25: the v1 path sets both times from one value while the gate is off."""
    settings.CATCH_REQUESTS_ENABLED = False
    scenario = create_catch_confirmation_scenario()

    response = force_authenticated_client(user=scenario.catcher_user).post(
        "/api/catches/confirm/",
        {"payload": scenario.payload},
        content_type="application/json",
    )

    assert response.status_code == 201
    catch = Catch.objects.get()
    assert catch.approved_at == catch.caught_at
