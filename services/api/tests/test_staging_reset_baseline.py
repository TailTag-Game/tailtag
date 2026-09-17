"""Real ORM acceptance tests for #204's owned reset closure and atomic reseed."""

from __future__ import annotations

import datetime
import importlib
import sys
import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, ClassVar, NoReturn, Protocol, cast

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from accounts.models import User
from catches.models import Catch
from conventions.models import (
    Convention,
    ConventionEnrollment,
    ConventionStatus,
    FursuitActivation,
    FursuitCatchCredential,
    FursuitCatchSession,
)
from fursuits.models import Fursuit
from profiles.models import PlayerProfile

if TYPE_CHECKING:
    from rehearsal.models import StagingResetIdentity
    from rehearsal.safety import ResetConfiguration

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
MEDIA_KEY = "images/0123456789abcdef0123456789abcdef.png"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


class RecordingS3Client:
    """Normal S3 adapter fake that permits reads and forbids all external mutation."""

    events: ClassVar[list[tuple[str, str]]] = []

    def head_object(self, **kwargs: object) -> dict[str, object]:
        assert kwargs["Key"] == MEDIA_KEY
        type(self).events.append(("head", MEDIA_KEY))
        return {"ContentLength": 24}

    def get_object(self, **kwargs: object) -> dict[str, object]:
        assert kwargs["Key"] == MEDIA_KEY
        type(self).events.append(("get", MEDIA_KEY))
        from io import BytesIO

        return {"Body": BytesIO(b"pre-provisioned-image")}

    def put_object(self, **_: object) -> object:
        raise AssertionError("reset must not upload baseline media")

    def delete_object(self, **_: object) -> object:
        raise AssertionError("reset must not delete baseline media")

    def generate_presigned_url(self, *_: object, **__: object) -> str:
        raise AssertionError("a signed URL is not asset availability evidence")


def fake_s3_client(*_: object, **__: object) -> RecordingS3Client:
    return RecordingS3Client()


class MissingS3Client(RecordingS3Client):
    """S3 transport reports the registered key absent at the normal HEAD seam."""

    def head_object(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        from botocore.exceptions import ClientError

        raise ClientError({"Error": {"Code": "404"}}, "HeadObject")


class UnreadableS3Client(RecordingS3Client):
    """A successful HEAD cannot substitute for a bounded readable object."""

    def get_object(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        from botocore.exceptions import ClientError

        raise ClientError({"Error": {"Code": "403"}}, "GetObject")


class EmptyS3Client(RecordingS3Client):
    """An empty object is not a usable pre-provisioned fixture asset."""

    def get_object(self, **kwargs: object) -> dict[str, object]:
        assert kwargs["Key"] == MEDIA_KEY
        from io import BytesIO

        return {"Body": BytesIO()}


def missing_s3_client(*_: object, **__: object) -> MissingS3Client:
    return MissingS3Client()


def unreadable_s3_client(*_: object, **__: object) -> UnreadableS3Client:
    return UnreadableS3Client()


def empty_s3_client(*_: object, **__: object) -> EmptyS3Client:
    return EmptyS3Client()


def returning[T](value: T) -> Callable[[object], T]:
    """Create a named, typed callback for normal monkeypatch seams."""

    def callback(_: object) -> T:
        return value

    return callback


def quiescent(_: object) -> None:
    """Allow reset tests to isolate ORM reconciliation from maintenance mechanics."""


def fail_validation(failure: BaseException) -> Callable[[object], NoReturn]:
    """Inject a late public validation denial to exercise transaction rollback."""

    def callback(_: object) -> NoReturn:
        raise failure

    return callback


def registry_model() -> type[StagingResetIdentity]:
    """Keep the runtime registry lookup aligned with the static Django model type."""
    from django.apps import apps

    return apps.get_model("rehearsal", "StagingResetIdentity")


class GroupMembership(Protocol):
    """The small observed part of Django's dynamically typed M2M manager."""

    def add(self, *objects: Group) -> None: ...
    def get(self) -> Group: ...


class UserWithGroups(Protocol):
    """Avoid Django-stubs' unresolved through-model parameter in this assertion."""

    groups: GroupMembership


def current_database_configuration(
    safety: ModuleType, *, owner: User, catcher: User
) -> ResetConfiguration:
    """Build a real local configuration so provision exercises its public guard."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), (pg_control_system()).system_identifier"
        )
        database_name, system_identifier = cursor.fetchone()
    database = settings.DATABASES["default"]
    return safety.ResetConfiguration(
        environment_id=uuid.uuid4(),
        cluster_identifier=str(system_identifier),
        database_host=str(database["HOST"]),
        database_port=str(database["PORT"]),
        database_name=str(database_name),
        owner_clerk_id=owner.clerk_user_id,
        catcher_clerk_id=catcher.clerk_user_id,
        media_key=MEDIA_KEY,
    )


def s3_storage_settings(
    client_factory: Callable[..., object] = fake_s3_client,
) -> dict[str, dict[str, object]]:
    return {
        "default": {
            "BACKEND": "media.storage.S3MediaStorage",
            "OPTIONS": {
                "endpoint_url": "https://s3.example.test",
                "bucket_name": "tailtag-staging-media",
                "access_key_id": "test-only-access-key",
                "secret_access_key": "test-only-secret",
                "region_name": "auto",
                "client_factory": client_factory,
            },
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }


@pytest.fixture
def reset_modules() -> tuple[ModuleType, ModuleType, ModuleType]:
    """Import only the frozen #204 modules once their app and migration exist."""
    assert (API_ROOT / "rehearsal" / "models.py").is_file()
    return (
        importlib.import_module("rehearsal.baseline"),
        importlib.import_module("rehearsal.reset"),
        importlib.import_module("rehearsal.safety"),
    )


def profile(user: User, *, handle: str, enabled: bool = False) -> PlayerProfile:
    return PlayerProfile.objects.create(
        user=user,
        handle=handle,
        display_name="Before Reset",
        avatar_key="images/fedcba9876543210fedcba9876543210.png",
        onboarding_completed_at=timezone.now() - datetime.timedelta(days=7),
        is_enabled=enabled,
    )


def active_graph(
    *, owner: User, catcher: User, convention: Convention, fursuit: Fursuit
) -> tuple[FursuitActivation, FursuitCatchSession, FursuitCatchCredential, Catch]:
    ConventionEnrollment.objects.create(
        user=owner, convention=convention, is_active=True
    )
    ConventionEnrollment.objects.create(
        user=catcher, convention=convention, is_active=True
    )
    activation = FursuitActivation.objects.create(
        fursuit=fursuit,
        convention=convention,
        is_active=True,
        activated_at=timezone.now(),
    )
    session = FursuitCatchSession.objects.create(
        activation=activation,
        started_at=timezone.now(),
        expires_at=timezone.now() + datetime.timedelta(hours=1),
    )
    credential = FursuitCatchCredential.objects.create(
        activation=activation, token=str(activation.pk).zfill(43)
    )
    catch = Catch.objects.create(
        catcher_user=catcher,
        fursuit=fursuit,
        convention=convention,
        activation=activation,
        catch_session=session,
    )
    return activation, session, credential, catch


def semantic_snapshot(identity: StagingResetIdentity) -> dict[str, object]:
    """Project only the baseline's durable semantic state, never incidental PKs/times."""
    return {
        "profiles": list(
            PlayerProfile.objects.filter(user__in=(identity.owner, identity.catcher))
            .order_by("user__clerk_user_id")
            .values_list(
                "user__clerk_user_id",
                "handle",
                "display_name",
                "avatar_key",
                "is_enabled",
            )
        ),
        "convention": Convention.objects.filter(pk=identity.convention_id)
        .values_list("name", "status", "start_date", "end_date")
        .get(),
        "fursuits": list(
            Fursuit.objects.filter(
                pk__in=(identity.first_fursuit_id, identity.second_fursuit_id)
            )
            .order_by("tailtag_id")
            .values_list("tailtag_id", "name", "owner_id", "photo_key", "is_enabled")
        ),
        "enrollments": list(
            ConventionEnrollment.objects.filter(convention_id=identity.convention_id)
            .order_by("user__clerk_user_id")
            .values_list("user__clerk_user_id", "is_active")
        ),
        "activations": list(
            FursuitActivation.objects.filter(convention_id=identity.convention_id)
            .order_by("fursuit__tailtag_id")
            .values_list("fursuit__tailtag_id", "is_active", "deactivated_at")
        ),
        "counts": {
            "catches": Catch.objects.filter(
                fursuit_id__in=(identity.first_fursuit_id, identity.second_fursuit_id)
            ).count(),
            "sessions": FursuitCatchSession.objects.filter(
                activation__fursuit_id__in=(
                    identity.first_fursuit_id,
                    identity.second_fursuit_id,
                )
            ).count(),
            "credentials": FursuitCatchCredential.objects.filter(
                activation__fursuit_id__in=(
                    identity.first_fursuit_id,
                    identity.second_fursuit_id,
                )
            ).count(),
        },
    }


def registered_identity_configuration(
    *, owner: User, catcher: User
) -> tuple[StagingResetIdentity, ResetConfiguration]:
    """Create the persistent identity fixture required by direct safety tests."""
    from rehearsal.safety import ResetConfiguration

    environment_id = uuid.uuid4()
    identity = registry_model().objects.create(
        id=1,
        environment_id=environment_id,
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
    )
    return identity, ResetConfiguration(
        environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )


@pytest.mark.django_db(transaction=True)
def test_identity_guard_requires_an_actual_readable_registered_asset(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
) -> None:
    """AC-4/5/8: URL generation cannot substitute for bounded read-only asset proof."""
    _, _, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    environment_id = uuid.uuid4()
    registry_model().objects.create(
        id=1,
        environment_id=environment_id,
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
    )
    configuration = safety.ResetConfiguration(
        environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    RecordingS3Client.events.clear()
    with override_settings(STORAGES=s3_storage_settings()):
        identity = safety.validate_identity(configuration)

    assert identity.owner_id == owner.pk
    assert identity.catcher_id == catcher.pk
    assert RecordingS3Client.events == [("head", MEDIA_KEY), ("get", MEDIA_KEY)]


@pytest.mark.django_db(transaction=True)
def test_identity_guard_denies_an_absent_persistent_sentinel(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
) -> None:
    """AC-5: reset cannot initialize or infer a missing registry identity."""
    _, _, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    configuration = current_database_configuration(safety, owner=owner, catcher=catcher)

    with (
        override_settings(STORAGES=s3_storage_settings()),
        pytest.raises(safety.ResetSafetyError),
    ):
        safety.validate_identity(configuration)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "configuration_change",
    (
        {"environment_id": uuid.uuid4()},
        {"cluster_identifier": "999"},
        {"database_name": "another_database"},
        {"owner_clerk_id": "wrong-owner"},
        {"catcher_clerk_id": "wrong-catcher"},
        {"media_key": "images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png"},
    ),
)
def test_identity_guard_denies_every_mismatched_sentinel_binding(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    configuration_change: dict[str, object],
) -> None:
    """AC-1/4/5: each registered binding is exact reset authority, never advisory."""
    _, _, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    _, configuration = registered_identity_configuration(owner=owner, catcher=catcher)

    with (
        override_settings(STORAGES=s3_storage_settings()),
        pytest.raises(safety.ResetSafetyError),
    ):
        safety.validate_identity(replace(configuration, **configuration_change))


@pytest.mark.django_db(transaction=True)
def test_identity_guard_denies_an_admin_bound_to_the_synthetic_pool(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
) -> None:
    """AC-1/4/5: privileged users can never become reusable reset-pool identities."""
    _, _, safety = reset_modules
    owner = User.objects.create_superuser("admin-owner", password="password")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    _, configuration = registered_identity_configuration(owner=owner, catcher=catcher)

    with (
        override_settings(STORAGES=s3_storage_settings()),
        pytest.raises(safety.ResetSafetyError),
    ):
        safety.validate_identity(configuration)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "client_factory",
    (missing_s3_client, unreadable_s3_client, empty_s3_client),
)
def test_identity_guard_denies_missing_or_unreadable_registered_media(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    client_factory: Callable[..., object],
) -> None:
    """AC-4/5/8: HEAD, bounded read, and non-empty content all prove asset safety."""
    _, _, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    _, configuration = registered_identity_configuration(owner=owner, catcher=catcher)

    with (
        override_settings(STORAGES=s3_storage_settings(client_factory)),
        pytest.raises(safety.ResetSafetyError),
    ):
        safety.validate_identity(configuration)


@pytest.mark.django_db(transaction=True)
def test_identity_guard_denies_non_s3_storage_even_with_a_registered_identity(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
) -> None:
    """AC-4/5: a local executor filesystem cannot prove the Staging media fixture."""
    _, _, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    _, configuration = registered_identity_configuration(owner=owner, catcher=catcher)

    with (
        override_settings(
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
                },
            }
        ),
        pytest.raises(safety.ResetSafetyError),
    ):
        safety.validate_identity(configuration)


@pytest.mark.django_db(transaction=True)
def test_provision_binds_only_preexisting_identities_and_creates_no_baseline_roots(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
) -> None:
    """AC-1/2/4: provisioning establishes the preserved registry, never fixture data."""
    _, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    configuration = current_database_configuration(safety, owner=owner, catcher=catcher)
    before_users = list(User.objects.order_by("pk").values_list("pk", "clerk_user_id"))

    with override_settings(STORAGES=s3_storage_settings()):
        reset.provision_identity(configuration)

    identity = registry_model().objects.get(pk=1)
    assert (identity.owner_id, identity.catcher_id) == (owner.pk, catcher.pk)
    assert (
        identity.convention_id,
        identity.first_fursuit_id,
        identity.second_fursuit_id,
    ) == (None, None, None)
    assert (
        list(User.objects.order_by("pk").values_list("pk", "clerk_user_id"))
        == before_users
    )
    assert Convention.objects.count() == 0
    assert Fursuit.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_provision_denies_missing_identity_or_existing_sentinel_without_rebinding(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
) -> None:
    """AC-1/4/5: provision cannot create/adopt identities or overwrite a sentinel."""
    _, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    configuration = current_database_configuration(safety, owner=owner, catcher=catcher)
    missing = safety.ResetConfiguration(
        configuration.environment_id,
        configuration.cluster_identifier,
        configuration.database_host,
        configuration.database_port,
        configuration.database_name,
        owner.clerk_user_id,
        "missing-catcher",
        MEDIA_KEY,
    )

    with (
        override_settings(STORAGES=s3_storage_settings()),
        pytest.raises(safety.ResetSafetyError),
    ):
        reset.provision_identity(missing)
    assert registry_model().objects.count() == 0

    registry_model().objects.create(
        id=1,
        environment_id=configuration.environment_id,
        cluster_identifier=configuration.cluster_identifier,
        database_name=configuration.database_name,
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
    )
    with (
        override_settings(STORAGES=s3_storage_settings()),
        pytest.raises(safety.ResetSafetyError),
    ):
        reset.provision_identity(configuration)
    assert registry_model().objects.get(pk=1).owner_id == owner.pk


@pytest.mark.django_db(transaction=True)
def test_first_reset_binds_all_null_registry_roots_atomically(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/2/7: first reset creates the fixed roots and registers all three together."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    assert reset.reset_baseline(configuration)["fursuits"] == 2

    identity.refresh_from_db()
    assert identity.convention_id is not None
    assert identity.first_fursuit_id is not None
    assert identity.second_fursuit_id is not None
    assert {
        Fursuit.objects.get(pk=identity.first_fursuit_id).tailtag_id,
        Fursuit.objects.get(pk=identity.second_fursuit_id).tailtag_id,
    } == {baseline.FIRST_FURSUIT_TAILTAG_ID, baseline.SECOND_FURSUIT_TAILTAG_ID}


@pytest.mark.django_db(transaction=True)
def test_first_reset_fixed_uuid_collision_rolls_back_without_partial_registration(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/7/8: an unregistered fixture UUID can never be silently adopted."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    stranger = User.objects.create_user("uuid-collision-owner")
    collision = Fursuit.objects.create(
        owner=stranger,
        name="Unowned Collision",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    with pytest.raises(safety.ResetSafetyError):
        reset.reset_baseline(configuration)

    identity.refresh_from_db()
    assert (
        identity.convention_id,
        identity.first_fursuit_id,
        identity.second_fursuit_id,
    ) == (None, None, None)
    assert Fursuit.objects.get(pk=collision.pk).owner_id == stranger.pk
    assert Convention.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_reset_rebuilds_only_registered_closure_and_preserves_identity_admin_and_media(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/2/4/8: owned state is reconstructed while all protected state survives."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    operator = User.objects.create_superuser("admin-preserved", password="password")
    group = Group.objects.create(name="preserved-admin-group")
    cast(UserWithGroups, operator).groups.add(group)
    profile(owner, handle="tt_rehearsal_catcher")
    profile(catcher, handle="tt_rehearsal_owner")
    unowned_user = User.objects.create_user("unowned-user")
    unowned_profile = profile(unowned_user, handle="unowned_profile", enabled=True)
    unowned_convention = Convention.objects.create(
        name="Unowned Convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 1, 2),
    )
    unowned_fursuit = Fursuit.objects.create(
        owner=unowned_user,
        name="Unowned Fursuit",
        photo_key="images/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
    )
    unowned_catcher = User.objects.create_user("unowned-catcher")
    _, unowned_session, unowned_credential, unowned_catch = active_graph(
        owner=unowned_user,
        catcher=unowned_catcher,
        convention=unowned_convention,
        fursuit=unowned_fursuit,
    )
    user_snapshot = list(
        User.objects.filter(pk__in=(owner.pk, catcher.pk, operator.pk))
        .order_by("pk")
        .values_list(
            "pk", "clerk_user_id", "password", "last_login", "is_staff", "is_superuser"
        )
    )
    convention = Convention.objects.create(
        name="TailTag Canonical Rehearsal",
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 1, 2),
    )
    first = Fursuit.objects.create(
        owner=owner,
        name="Wrong First",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
        is_enabled=False,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Wrong Second",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
        is_enabled=False,
    )
    active_graph(owner=owner, catcher=catcher, convention=convention, fursuit=first)
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        environment_id=identity.environment_id,
        cluster_identifier="123",
        database_host="127.0.0.1",
        database_port="55404",
        database_name="test_tailtag",
        owner_clerk_id=owner.clerk_user_id,
        catcher_clerk_id=catcher.clerk_user_id,
        media_key=MEDIA_KEY,
    )

    counts = reset.reset_baseline(configuration)

    assert counts == {
        "profiles": 2,
        "conventions": 1,
        "fursuits": 2,
        "enrollments": 2,
        "activations": 2,
        "catches": 0,
        "sessions": 0,
        "credentials": 0,
    }
    identity.refresh_from_db()
    assert semantic_snapshot(identity)["counts"] == {
        "catches": 0,
        "sessions": 0,
        "credentials": 0,
    }
    assert list(
        PlayerProfile.objects.filter(user__in=(owner, catcher))
        .order_by("user__clerk_user_id")
        .values_list("handle", "display_name", "avatar_key", "is_enabled")
    ) == [
        ("tt_rehearsal_catcher", "TailTag Rehearsal Catcher", MEDIA_KEY, True),
        ("tt_rehearsal_owner", "TailTag Rehearsal Owner", MEDIA_KEY, True),
    ]
    assert (
        Fursuit.objects.get(pk=first.pk).tailtag_id == baseline.FIRST_FURSUIT_TAILTAG_ID
    )
    assert (
        Fursuit.objects.get(pk=second.pk).tailtag_id
        == baseline.SECOND_FURSUIT_TAILTAG_ID
    )
    assert cast(UserWithGroups, User.objects.get(pk=operator.pk)).groups.get() == group
    assert (
        list(
            User.objects.filter(pk__in=(owner.pk, catcher.pk, operator.pk))
            .order_by("pk")
            .values_list(
                "pk",
                "clerk_user_id",
                "password",
                "last_login",
                "is_staff",
                "is_superuser",
            )
        )
        == user_snapshot
    )
    assert PlayerProfile.objects.get(pk=unowned_profile.pk).handle == "unowned_profile"
    assert Convention.objects.filter(pk=unowned_convention.pk).exists()
    assert Fursuit.objects.filter(pk=unowned_fursuit.pk).exists()
    assert Catch.objects.filter(pk=unowned_catch.pk).exists()
    assert FursuitCatchSession.objects.filter(pk=unowned_session.pk).exists()
    assert FursuitCatchCredential.objects.filter(pk=unowned_credential.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_second_reset_is_semantically_identical_and_keeps_registered_roots(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-3: rerunning removes later owned history without duplicate fixture records."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2036, 9, 1),
    )
    first = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Panther",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Fox",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    reset.reset_baseline(configuration)
    first_state = semantic_snapshot(identity)
    first_root_pks = (
        identity.convention_id,
        identity.first_fursuit_id,
        identity.second_fursuit_id,
    )
    activation = FursuitActivation.objects.get(fursuit_id=identity.first_fursuit_id)
    session = FursuitCatchSession.objects.create(
        activation=activation,
        started_at=timezone.now(),
        expires_at=timezone.now() + datetime.timedelta(hours=1),
    )
    FursuitCatchCredential.objects.create(activation=activation, token="B" * 43)
    Catch.objects.create(
        catcher_user=catcher,
        fursuit=first,
        convention=convention,
        activation=activation,
        catch_session=session,
    )
    reset.reset_baseline(configuration)
    identity.refresh_from_db()

    assert semantic_snapshot(identity) == first_state
    assert (
        identity.convention_id,
        identity.first_fursuit_id,
        identity.second_fursuit_id,
    ) == first_root_pks
    assert Convention.objects.filter(pk=identity.convention_id).count() == 1
    assert (
        Fursuit.objects.filter(
            tailtag_id__in=(
                baseline.FIRST_FURSUIT_TAILTAG_ID,
                baseline.SECOND_FURSUIT_TAILTAG_ID,
            )
        ).count()
        == 2
    )


@pytest.mark.django_db(transaction=True)
def test_unowned_dependency_or_handle_conflict_denies_without_expanding_deletion_scope(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/5/8: ownership ambiguity must roll back instead of being adopted or deleted."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    stranger = User.objects.create_user("unowned-catcher")
    profile(owner, handle="before_reset_owner")
    profile(catcher, handle="before_reset_catcher")
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2036, 9, 1),
    )
    first = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Panther",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Fox",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    _, session, _, malformed_catch = active_graph(
        owner=owner, catcher=catcher, convention=convention, fursuit=first
    )
    foreign_convention = Convention.objects.create(
        name="Foreign Provenance Convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 2, 1),
        end_date=datetime.date(2026, 2, 2),
    )
    foreign_fursuit = Fursuit.objects.create(
        owner=stranger,
        name="Foreign Provenance Fursuit",
        photo_key="images/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png",
    )
    foreign_activation = FursuitActivation.objects.create(
        fursuit=foreign_fursuit,
        convention=foreign_convention,
        is_active=True,
        activated_at=timezone.now(),
    )
    foreign_session = FursuitCatchSession.objects.create(
        activation=foreign_activation,
        started_at=timezone.now(),
        expires_at=timezone.now() + datetime.timedelta(hours=1),
    )
    Catch.objects.create(
        catcher_user=stranger,
        fursuit=first,
        convention=convention,
        activation=foreign_activation,
        catch_session=foreign_session,
    )
    owned_second_activation = FursuitActivation.objects.create(
        fursuit=second,
        convention=convention,
        is_active=True,
        activated_at=timezone.now(),
    )
    owned_second_session = FursuitCatchSession.objects.create(
        activation=owned_second_activation,
        started_at=timezone.now(),
        expires_at=timezone.now() + datetime.timedelta(hours=1),
    )
    malformed_catch.activation = owned_second_activation
    malformed_catch.catch_session = owned_second_session
    malformed_catch.save(update_fields=["activation", "catch_session"])
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    with pytest.raises(safety.ResetSafetyError):
        reset.reset_baseline(configuration)

    assert Catch.objects.filter(catcher_user=stranger, fursuit=first).count() == 1
    assert FursuitCatchSession.objects.filter(pk=session.pk).exists()
    assert FursuitCatchSession.objects.filter(pk=foreign_session.pk).exists()
    assert FursuitCatchSession.objects.filter(pk=owned_second_session.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_unowned_profile_handle_conflict_denies_without_mutating_any_owned_root(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/4/5: an unowned desired handle is not deleted or stolen during reseed."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    stranger = User.objects.create_user("unowned-handle-holder")
    profile(owner, handle="before_reset_owner")
    profile(catcher, handle="before_reset_catcher")
    conflict = PlayerProfile.objects.create(
        user=stranger,
        handle="tt_rehearsal_owner",
        display_name="Unowned Handle Holder",
        onboarding_completed_at=timezone.now(),
    )
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 1, 2),
    )
    first = Fursuit.objects.create(
        owner=owner,
        name="Wrong First",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Wrong Second",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    with pytest.raises(safety.ResetSafetyError):
        reset.reset_baseline(configuration)

    assert PlayerProfile.objects.get(pk=conflict.pk).handle == "tt_rehearsal_owner"
    assert Convention.objects.get(pk=convention.pk).status == ConventionStatus.DRAFT


@pytest.mark.django_db(transaction=True)
def test_registered_root_owner_mismatch_denies_instead_of_rebinding_or_deleting(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/4/8: registry FKs never authorize changing a fursuit's protected owner."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    stranger = User.objects.create_user("unowned-root-owner")
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 1, 2),
    )
    mismatched = Fursuit.objects.create(
        owner=stranger,
        name="Rehearsal Panther",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Fox",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
        convention=convention,
        first_fursuit=mismatched,
        second_fursuit=second,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    with pytest.raises(safety.ResetSafetyError):
        reset.reset_baseline(configuration)

    assert Fursuit.objects.get(pk=mismatched.pk).owner_id == stranger.pk


@pytest.mark.django_db(transaction=True)
def test_registered_root_uuid_mismatch_denies_instead_of_rewriting_public_identity(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/8: a registered root's externally stable fursuit UUID is immutable."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 1, 2),
    )
    wrong_uuid = uuid.uuid4()
    first = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Panther",
        tailtag_id=wrong_uuid,
        photo_key=MEDIA_KEY,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Fox",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    with pytest.raises(safety.ResetSafetyError):
        reset.reset_baseline(configuration)

    assert Fursuit.objects.get(pk=first.pk).tailtag_id == wrong_uuid


@pytest.mark.django_db(transaction=True)
def test_extra_baseline_user_enrollment_denies_without_changing_active_selection(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1/5/8: reset cannot erase unrelated enrollment state to make itself work."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    profile(owner, handle="before_reset_owner")
    profile(catcher, handle="before_reset_catcher")
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2036, 9, 1),
    )
    extra = Convention.objects.create(
        name="Unowned Extra Convention",
        status=ConventionStatus.ACTIVE,
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 1, 2),
    )
    extra_enrollment = ConventionEnrollment.objects.create(
        user=owner, convention=extra, is_active=True
    )
    first = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Panther",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Rehearsal Fox",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
    )
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    with pytest.raises(safety.ResetSafetyError):
        reset.reset_baseline(configuration)

    assert ConventionEnrollment.objects.get(pk=extra_enrollment.pk).is_active is True


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("failure_type", (RuntimeError, KeyboardInterrupt))
def test_validation_failure_rolls_back_all_owned_cleanup_and_reconstruction(
    reset_modules: tuple[ModuleType, ModuleType, ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[BaseException],
) -> None:
    """AC-7/RELIABILITY: late ordinary or interrupt failure cannot commit a partial baseline."""
    baseline, reset, safety = reset_modules
    owner = User.objects.create_user("user_rehearsal_owner")
    catcher = User.objects.create_user("user_rehearsal_catcher")
    profile(owner, handle="before_reset_owner")
    profile(catcher, handle="before_reset_catcher")
    convention = Convention.objects.create(
        name=baseline.CONVENTION_NAME,
        status=ConventionStatus.DRAFT,
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 1, 2),
    )
    first = Fursuit.objects.create(
        owner=owner,
        name="Wrong First",
        tailtag_id=baseline.FIRST_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
        is_enabled=False,
    )
    second = Fursuit.objects.create(
        owner=owner,
        name="Wrong Second",
        tailtag_id=baseline.SECOND_FURSUIT_TAILTAG_ID,
        photo_key=MEDIA_KEY,
        is_enabled=False,
    )
    _, session, credential, catch = active_graph(
        owner=owner, catcher=catcher, convention=convention, fursuit=first
    )
    identity = registry_model().objects.create(
        id=1,
        environment_id=uuid.uuid4(),
        cluster_identifier="123",
        database_name="test_tailtag",
        owner=owner,
        catcher=catcher,
        media_key=MEDIA_KEY,
        convention=convention,
        first_fursuit=first,
        second_fursuit=second,
    )
    monkeypatch.setattr(reset, "validate_identity", returning(identity))
    monkeypatch.setattr(reset, "assert_quiescent", quiescent)
    monkeypatch.setattr(
        reset,
        "validate_baseline",
        fail_validation(failure_type()),
    )
    configuration = safety.ResetConfiguration(
        identity.environment_id,
        "123",
        "127.0.0.1",
        "55404",
        "test_tailtag",
        owner.clerk_user_id,
        catcher.clerk_user_id,
        MEDIA_KEY,
    )

    with pytest.raises(failure_type):
        reset.reset_baseline(configuration)

    assert Catch.objects.filter(pk=catch.pk).exists()
    assert FursuitCatchSession.objects.filter(pk=session.pk).exists()
    assert FursuitCatchCredential.objects.filter(pk=credential.pk).exists()
    assert Convention.objects.get(pk=convention.pk).status == ConventionStatus.DRAFT
    assert Fursuit.objects.get(pk=first.pk).is_enabled is False
