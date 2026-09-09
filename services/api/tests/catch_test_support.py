"""Test-only prerequisites and lazy model lookup for Catch acceptance tests."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.utils import timezone

from accounts.models import User
from conventions.catch_credentials import format_catch_credential_payload
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile
from tests.authentication_support import create_test_user
from tests.catch_credential_test_support import TOKEN_A, create_credential
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


@dataclass(frozen=True)
class CatchConfirmationScenario:
    """A complete, independently valid graph for confirming one catch."""

    catcher_user: User
    catcher_profile: PlayerProfile
    catcher_enrollment: ConventionEnrollment
    target_user: User
    target_profile: PlayerProfile
    fursuit: Fursuit
    convention: Convention
    target_enrollment: ConventionEnrollment
    activation: FursuitActivation
    credential: Any
    catch_session: Any
    payload: str


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


def create_catch_confirmation_scenario(
    *,
    catcher_clerk_user_id: str = "catch_confirmation_catcher",
    target_owner_clerk_user_id: str = "catch_confirmation_target",
    token: str = TOKEN_A,
    self_catch: bool = False,
) -> CatchConfirmationScenario:
    """Create the exact currently eligible graph for the catch service contract."""
    target_user = create_test_user(clerk_user_id=target_owner_clerk_user_id)
    target_profile = PlayerProfile.objects.create(
        user=target_user,
        handle=f"catch_target_{target_user.pk}",
        display_name="Catch Target",
        onboarding_completed_at=timezone.now(),
        is_enabled=True,
    )
    convention = Convention.objects.create(
        name=f"Catch Confirmation Convention {target_user.pk}",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 7, 2),
        end_date=datetime.date(2026, 7, 5),
    )
    target_enrollment = ConventionEnrollment.objects.create(
        user=target_user, convention=convention, is_active=False
    )
    fursuit = Fursuit.objects.create(
        owner=target_user,
        name=f"Catch Confirmation Fursuit {target_user.pk}",
        photo_key="images/0123456789abcdef0123456789abcdef.png",
        is_enabled=True,
    )
    activation = create_activation_row(
        fursuit=fursuit, convention=convention, active=True
    )
    credential = create_credential(activation=activation, token=token)
    catch_session = create_catch_session(activation=activation)

    if self_catch:
        catcher_user = target_user
        catcher_profile = target_profile
        target_enrollment.is_active = True
        target_enrollment.save(update_fields=["is_active", "updated_at"])
        catcher_enrollment = target_enrollment
    else:
        catcher_user = create_test_user(clerk_user_id=catcher_clerk_user_id)
        catcher_profile = PlayerProfile.objects.create(
            user=catcher_user,
            handle=f"catcher_{catcher_user.pk}",
            display_name="Catch Catcher",
            onboarding_completed_at=timezone.now(),
            is_enabled=True,
        )
        catcher_enrollment = ConventionEnrollment.objects.create(
            user=catcher_user, convention=convention, is_active=True
        )

    return CatchConfirmationScenario(
        catcher_user=catcher_user,
        catcher_profile=catcher_profile,
        catcher_enrollment=catcher_enrollment,
        target_user=target_user,
        target_profile=target_profile,
        fursuit=fursuit,
        convention=convention,
        target_enrollment=target_enrollment,
        activation=activation,
        credential=credential,
        catch_session=catch_session,
        payload=format_catch_credential_payload(token),
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
