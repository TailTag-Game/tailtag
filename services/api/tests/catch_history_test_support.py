"""Focused fixtures for player catch-history API acceptance tests."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from accounts.models import User
from conventions.models import Convention, ConventionStatus, FursuitActivation
from fursuits.models import Fursuit
from tests.authentication_support import create_test_user
from tests.catch_test_support import CatchScenario, create_catch
from tests.fursuit_activation_test_support import create_activation_row
from tests.fursuit_catch_session_test_support import create_catch_session


@dataclass(frozen=True)
class HistoryCatch:
    """One durable Catch and the related records its history projection uses."""

    catch: Any
    fursuit: Fursuit
    convention: Convention


def create_history_catch(
    *,
    catcher_user: User,
    ordinal: int,
    convention: Convention | None = None,
    caught_at: datetime.datetime | None = None,
) -> HistoryCatch:
    """Create one valid, uniquely targeted Catch for history API tests."""
    target_owner = create_test_user()
    selected_convention = convention or Convention.objects.create(
        name=f"Catch History Convention {ordinal}",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 7, 2),
        end_date=datetime.date(2026, 7, 5),
    )
    fursuit = Fursuit.objects.create(
        owner=target_owner,
        name=f"Catch History Fursuit {ordinal}",
        photo_key=f"images/{ordinal:032x}.png",
        is_enabled=True,
    )
    activation: FursuitActivation = create_activation_row(
        fursuit=fursuit,
        convention=selected_convention,
        active=True,
    )
    catch_session = create_catch_session(activation=activation)
    catch = create_catch(
        scenario=CatchScenario(
            catcher_user=catcher_user,
            fursuit=fursuit,
            convention=selected_convention,
            activation=activation,
            catch_session=catch_session,
        )
    )
    if caught_at is not None:
        catch.__class__.objects.filter(pk=catch.pk).update(caught_at=caught_at)
        catch.refresh_from_db()
    return HistoryCatch(
        catch=catch,
        fursuit=fursuit,
        convention=selected_convention,
    )
