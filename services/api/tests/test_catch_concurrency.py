"""PostgreSQL duplicate-insert boundary acceptance test for Catch."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import IntegrityError, close_old_connections, connection, transaction

from tests.catch_test_support import catch_model, create_catch_scenario


def _configure_worker_timeouts() -> None:
    """Bound database waits below the test's future-result timeout."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('lock_timeout', '18000ms', false)")
        cursor.execute("SELECT set_config('statement_timeout', '20000ms', false)")


@pytest.mark.django_db(transaction=True)
def test_postgresql_duplicate_catch_insert_persists_exactly_one_row() -> None:
    """AC-12: a concurrent duplicate insert has one database winner and one loser."""
    assert connection.vendor == "postgresql"
    scenario = create_catch_scenario()
    barrier = Barrier(2)

    def insert_duplicate() -> str:
        close_old_connections()
        try:
            _configure_worker_timeouts()
            with transaction.atomic():
                barrier.wait(timeout=10)
                catch_model().objects.create(
                    catcher_user_id=scenario.catcher_user.pk,
                    fursuit_id=scenario.fursuit.pk,
                    convention_id=scenario.convention.pk,
                    activation_id=scenario.activation.pk,
                    catch_session_id=scenario.catch_session.pk,
                )
            return "created"
        except IntegrityError:
            return "rejected"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(insert_duplicate) for _ in range(2)]
        outcomes = [future.result(timeout=25) for future in futures]

    assert sorted(outcomes) == ["created", "rejected"]
    assert (
        catch_model()
        .objects.filter(
            catcher_user_id=scenario.catcher_user.pk,
            fursuit_id=scenario.fursuit.pk,
            convention_id=scenario.convention.pk,
        )
        .count()
        == 1
    )
