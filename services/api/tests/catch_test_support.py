"""Test-only prerequisites and lazy model lookup for Catch acceptance tests."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from django.apps import apps

from accounts.models import User
from conventions.models import Convention, FursuitActivation
from fursuits.models import Fursuit
from tests.authentication_support import create_test_user
from tests.fursuit_activation_test_support import (
    create_activation_row,
    create_activation_scenario,
)
from tests.fursuit_catch_session_test_support import create_catch_session


@dataclass(frozen=True)
class CatchScenario:
    """An independently valid catcher, target, and durable provenance chain."""

    catcher_user: User
    fursuit: Fursuit
    convention: Convention
    activation: FursuitActivation
    catch_session: Any


def catch_model() -> type[Any]:
    """Resolve Catch at test execution so its absence is an ordinary RED failure."""
    return apps.get_model("catches", "Catch")


def create_catch_scenario(
    *,
    catcher_clerk_user_id: str = "catcher",
    target_owner_clerk_user_id: str = "catch_target_owner",
) -> CatchScenario:
    """Create the existing upstream state required by one valid Catch."""
    catcher_user = create_test_user(clerk_user_id=catcher_clerk_user_id)
    target = create_activation_scenario(clerk_user_id=target_owner_clerk_user_id)
    activation = create_activation_row(
        fursuit=target.fursuit,
        convention=target.convention,
        active=True,
    )
    catch_session = create_catch_session(activation=activation)
    return CatchScenario(
        catcher_user=catcher_user,
        fursuit=target.fursuit,
        convention=target.convention,
        activation=activation,
        catch_session=catch_session,
    )


def create_catch(
    *,
    scenario: CatchScenario,
    caught_at: datetime.datetime | None = None,
) -> Any:
    """Persist a Catch through the public ORM surface for acceptance evidence."""
    values: dict[str, object] = {
        "catcher_user": scenario.catcher_user,
        "fursuit": scenario.fursuit,
        "convention": scenario.convention,
        "activation": scenario.activation,
        "catch_session": scenario.catch_session,
    }
    if caught_at is not None:
        values["caught_at"] = caught_at
    return catch_model().objects.create(**values)
