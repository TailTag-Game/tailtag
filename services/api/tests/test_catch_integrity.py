"""PostgreSQL persistence acceptance contract for the V0 Catch domain."""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from tests.catch_test_support import (
    catch_model,
    create_catch,
    create_catch_scenario,
)


@pytest.mark.django_db
def test_catch_is_the_exact_minimal_dedicated_domain_model() -> None:
    """AC-01/04/05/09/13: rejects a misplaced, expanded, or hooked Catch model."""
    assert apps.is_installed("catches")
    model = catch_model()
    assert {item.__name__ for item in apps.get_app_config("catches").get_models()} == {
        "Catch"
    }
    fields = {field.name: field for field in model._meta.fields}
    assert set(fields) == {
        "id",
        "catcher_user",
        "fursuit",
        "convention",
        "activation",
        "catch_session",
        "caught_at",
    }
    assert isinstance(fields["id"], models.BigAutoField)
    assert fields["id"].primary_key is True
    assert isinstance(fields["caught_at"], models.DateTimeField)
    assert fields["caught_at"].auto_now_add is True
    assert model._meta.ordering == ["-caught_at", "-id"]
    assert model.save is models.Model.save
    assert model.delete is models.Model.delete
    for method_name in (
        "clean_fields",
        "clean",
        "validate_unique",
        "validate_constraints",
        "full_clean",
    ):
        assert getattr(model, method_name) is getattr(models.Model, method_name)
    assert "__repr__" not in model.__dict__
    assert [(manager.name, manager.__class__) for manager in model._meta.managers] == [
        ("objects", models.Manager)
    ]


@pytest.mark.django_db
def test_catch_has_exact_protected_relationships_and_named_canonical_constraint() -> (
    None
):
    """AC-02/03/06/07/13: rejects weak provenance or a noncanonical identity tuple."""
    model = catch_model()
    fields = {field.name: field for field in model._meta.fields}
    expected_labels = {
        "catcher_user": "accounts.User",
        "fursuit": "fursuits.Fursuit",
        "convention": "conventions.Convention",
        "activation": "conventions.FursuitActivation",
        "catch_session": "conventions.FursuitCatchSession",
    }
    for name, label in expected_labels.items():
        field = fields[name]
        assert isinstance(field, models.ForeignKey)
        assert field.null is False
        assert field.remote_field.on_delete is models.PROTECT
        assert field.remote_field.related_name == "catches"
        assert field.remote_field.model._meta.label == label
    assert (
        fields["catcher_user"].remote_field.model._meta.label
        == settings.AUTH_USER_MODEL
    )

    assert len(model._meta.constraints) == 1
    constraint = model._meta.constraints[0]
    assert isinstance(constraint, models.UniqueConstraint)
    assert tuple(constraint.fields) == ("catcher_user", "fursuit", "convention")
    assert constraint.name == "catches_catcher_fursuit_convention_unique"


@pytest.mark.django_db
def test_catch_timestamp_is_server_owned_timezone_aware_and_stable_after_save() -> None:
    """AC-04: rejects caller-controlled or save-mutated catch timestamps."""
    scenario = create_catch_scenario()
    caller_value = timezone.now() - datetime.timedelta(days=365)
    before = timezone.now()
    catch = create_catch(scenario=scenario, caught_at=caller_value)
    after = timezone.now()
    assert before <= catch.caught_at <= after
    assert timezone.is_aware(catch.caught_at)
    assert catch.caught_at != caller_value

    original = catch.caught_at
    catch.save()
    catch.refresh_from_db()
    assert catch.caught_at == original


@pytest.mark.django_db
def test_catch_database_enforces_canonical_uniqueness_and_required_provenance() -> None:
    """AC-06/07: rejects duplicate canonical facts and missing durable provenance."""
    scenario = create_catch_scenario()
    create_catch(scenario=scenario)
    with pytest.raises(IntegrityError), transaction.atomic():
        create_catch(scenario=scenario)

    for omitted in ("activation", "catch_session"):
        omitted_scenario = create_catch_scenario(
            catcher_clerk_user_id=f"catcher_missing_{omitted}",
            target_owner_clerk_user_id=f"catch_target_owner_missing_{omitted}",
        )
        values: dict[str, Any] = {
            "catcher_user": omitted_scenario.catcher_user,
            "fursuit": omitted_scenario.fursuit,
            "convention": omitted_scenario.convention,
            "activation": omitted_scenario.activation,
            "catch_session": omitted_scenario.catch_session,
        }
        with pytest.raises(IntegrityError), transaction.atomic():
            catch_model().objects.create(
                **{name: value for name, value in values.items() if name != omitted}
            )


@pytest.mark.django_db
def test_catch_protects_referenced_catcher_and_catch_session_history() -> None:
    """AC-08: rejects deletion of a directly referenced historical edge."""
    scenario = create_catch_scenario()
    catch = create_catch(scenario=scenario)

    with pytest.raises(models.ProtectedError):
        scenario.catcher_user.delete()
    assert catch_model().objects.filter(pk=catch.pk).exists()

    with pytest.raises(models.ProtectedError):
        scenario.catch_session.delete()
    assert catch_model().objects.filter(pk=catch.pk).exists()


@pytest.mark.django_db
def test_catch_default_ordering_and_text_are_exact_and_provider_safe() -> None:
    """AC-09/10: rejects unstable history order or provider-bearing text."""
    older = create_catch(
        scenario=create_catch_scenario(
            catcher_clerk_user_id="clerk_provider_identifier_old",
            target_owner_clerk_user_id="catch_target_owner_old",
        )
    )
    lower_id_newer = create_catch(
        scenario=create_catch_scenario(
            catcher_clerk_user_id="clerk_provider_identifier_lower",
            target_owner_clerk_user_id="catch_target_owner_lower",
        )
    )
    higher_id_newer = create_catch(
        scenario=create_catch_scenario(
            catcher_clerk_user_id="clerk_provider_identifier_high",
            target_owner_clerk_user_id="catch_target_owner_high",
        )
    )
    newer_at = timezone.now()
    catch_model().objects.filter(pk=older.pk).update(
        caught_at=newer_at - datetime.timedelta(days=1)
    )
    catch_model().objects.filter(pk__in=(lower_id_newer.pk, higher_id_newer.pk)).update(
        caught_at=newer_at
    )

    assert list(
        catch_model()
        .objects.filter(pk__in=(older.pk, lower_id_newer.pk, higher_id_newer.pk))
        .values_list("pk", flat=True)
    ) == [higher_id_newer.pk, lower_id_newer.pk, older.pk]
    assert str(higher_id_newer) == (
        f"Catch {higher_id_newer.pk}: catcher {higher_id_newer.catcher_user_id}, "
        f"fursuit {higher_id_newer.fursuit_id}, convention {higher_id_newer.convention_id}"
    )
    assert "clerk_provider_identifier_high" not in str(higher_id_newer)
