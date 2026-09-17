"""Health endpoint behavior."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn, Self

import pytest
from django.conf import settings
from django.db import DatabaseError
from django.test import Client, RequestFactory, override_settings
from pytest import MonkeyPatch

from authentication.clerk import ClerkVerificationConfiguration
from config import build_identity
from config.settings.media import S3MediaConfiguration
from health.views import ready as readiness_view
from tests.clerk_settings_contract import (
    valid_clerk_public_key as _valid_clerk_public_key,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)

SOURCE_SHA = "c070f413eec1518459f1fef21b471642765a54e9"
DEPLOYMENT_ID = "93de11d6-714f-405a-b931-a9b567d5ec1e"
SECOND_SOURCE_SHA = "d" * 40
SECOND_DEPLOYMENT_ID = "1b6a4b35-4e94-4775-a4b9-304205c75786"
SENSITIVE_DIAGNOSTIC = "health-private-diagnostic-secret"

DEPLOYED_MEDIA_CONFIGURATION = S3MediaConfiguration(
    endpoint_url="https://media.example.test",
    bucket_name="test-media-bucket",
    region="auto",
    access_key_id="test-access-key",
    secret_access_key="test-secret-key",
)
DEPLOYED_STORAGE_OPTIONS: dict[str, object] = {
    "endpoint_url": DEPLOYED_MEDIA_CONFIGURATION.endpoint_url,
    "bucket_name": DEPLOYED_MEDIA_CONFIGURATION.bucket_name,
    "region": DEPLOYED_MEDIA_CONFIGURATION.region,
    "access_key_id": DEPLOYED_MEDIA_CONFIGURATION.access_key_id,
    "secret_access_key": DEPLOYED_MEDIA_CONFIGURATION.secret_access_key,
    "url_expiry_seconds": 600,
}
DEPLOYED_STORAGES: dict[str, dict[str, object]] = {
    "default": {
        "BACKEND": "media.storage.S3MediaStorage",
        "OPTIONS": DEPLOYED_STORAGE_OPTIONS,
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
LOCAL_STORAGES: dict[str, dict[str, object]] = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": "/tmp/tailtag-test-media", "base_url": "/media/"},
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
LOCAL_STORAGE_WITHOUT_OPTIONS: dict[str, dict[str, object]] = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


def write_build_identity(path: Path, source_sha: str = SOURCE_SHA) -> None:
    """Create the immutable artifact consumed through the canonical #201 loader."""
    path.write_text(json.dumps({"source_sha": source_sha}))


def configure_staging_identity(
    monkeypatch: MonkeyPatch, tmp_path: Path, *, deployment_id: str = DEPLOYMENT_ID
) -> None:
    """Provide only #201's baked artifact and Railway runtime mapping."""
    metadata_path = tmp_path / "build-identity.json"
    write_build_identity(metadata_path)
    monkeypatch.setattr(build_identity, "_METADATA_PATH", metadata_path)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", deployment_id)
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "api")


def configure_development_identity(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Provide the #201 runtime identity allowed for a Development deployment."""
    monkeypatch.setattr(build_identity, "_METADATA_PATH", tmp_path / "absent.json")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "development")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", DEPLOYMENT_ID)
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "api")


def configure_local_profile(monkeypatch: MonkeyPatch) -> None:
    """Explicitly select the preserved local profile without Railway runtime data."""
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.local")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    monkeypatch.delenv("RAILWAY_SERVICE_NAME", raising=False)


def configured_deployed_settings(clerk_public_key: str) -> dict[str, object]:
    """Return a complete effective deployed profile without contacting vendors."""
    return {
        "DEBUG": False,
        "SECRET_KEY": "test-deployed-secret-key",
        "ALLOWED_HOSTS": ["staging.tailtag.app", "testserver"],
        "CSRF_TRUSTED_ORIGINS": ["https://staging.tailtag.app"],
        "SESSION_COOKIE_SECURE": True,
        "CSRF_COOKIE_SECURE": True,
        "CLERK_AUTHENTICATION": ClerkVerificationConfiguration(
            jwt_key=clerk_public_key,
            authorized_parties=("https://staging.tailtag.app",),
        ),
        "MEDIA_STORAGE_CONFIGURATION": DEPLOYED_MEDIA_CONFIGURATION,
        "STORAGES": DEPLOYED_STORAGES,
    }


def storage_options(**overrides: object) -> dict[str, dict[str, object]]:
    """Return deployed S3 storage with one effective-options variation."""
    return {
        **DEPLOYED_STORAGES,
        "default": {
            "BACKEND": "media.storage.S3MediaStorage",
            "OPTIONS": {**DEPLOYED_STORAGE_OPTIONS, **overrides},
        },
    }


def fail_if_called() -> NoReturn:
    """Fail when liveness attempts to reach the database."""
    message = "liveness must not access the database"
    raise AssertionError(message)


def fail_vendor_call(*_: object, **__: object) -> NoReturn:
    """Fail if a health endpoint attempts an out-of-process vendor operation."""
    raise AssertionError("health readiness must not contact a vendor")


def test_liveness_does_not_access_database(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """Liveness is available without a database connection."""
    monkeypatch.setattr("django.db.connection.ensure_connection", fail_if_called)

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


def test_liveness_ignores_invalid_build_identity_and_configuration(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """AC-1/4: process liveness has no identity or configuration dependency."""

    def unavailable_identity() -> NoReturn:
        raise ValueError(SENSITIVE_DIAGNOSTIC)

    monkeypatch.setattr(build_identity, "get_identity", unavailable_identity)
    monkeypatch.setattr("django.db.connection.ensure_connection", fail_if_called)

    with override_settings(DEBUG=False, CLERK_AUTHENTICATION=None):
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_preserves_healthy_local_development_profile(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """AC-2/3: local Development remains ready with disabled Clerk and filesystem media."""
    configure_local_profile(monkeypatch)

    with override_settings(
        DEBUG=True,
        CLERK_AUTHENTICATION=None,
        STORAGES=LOCAL_STORAGES,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "storage_backend",
    (
        "django.core.files.storage.InMemoryStorage",
        "django.core.files.storage.FileSystemStorage",
    ),
    ids=("in-memory-default-options", "filesystem-default-options"),
)
def test_readiness_preserves_local_builtin_storage_defaults(
    client: Client, monkeypatch: MonkeyPatch, storage_backend: str
) -> None:
    """AC-2/3: valid local Django storage constructors need no explicit options."""
    configure_local_profile(monkeypatch)
    local_storages = {
        **LOCAL_STORAGE_WITHOUT_OPTIONS,
        "default": {"BACKEND": storage_backend},
    }

    with override_settings(
        DEBUG=True,
        CLERK_AUTHENTICATION=None,
        STORAGES=local_storages,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_rejects_staging_runtime_claim_from_local_settings_profile(
    client: Client,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
) -> None:
    """AC-3/6: local settings cannot qualify as deployed Staging by metadata alone."""
    configure_staging_identity(monkeypatch, tmp_path)

    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.local")
    with override_settings(**configured_deployed_settings(valid_clerk_public_key)):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_rejects_unknown_settings_profile_even_without_runtime(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """AC-3: an unrecognized profile cannot inherit local-development readiness."""
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.unknown")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    monkeypatch.delenv("RAILWAY_SERVICE_NAME", raising=False)

    with override_settings(
        DEBUG=True,
        CLERK_AUTHENTICATION=None,
        STORAGES=LOCAL_STORAGES,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_rejects_malformed_enabled_clerk_configuration_in_local_profile(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """AC-3/4: local disabled Clerk is intentional, malformed enabled Clerk is not."""
    configure_local_profile(monkeypatch)
    malformed_clerk = ClerkVerificationConfiguration(
        jwt_key="not-a-public-key",
        authorized_parties=("not-an-origin",),
    )

    with override_settings(
        DEBUG=True,
        CLERK_AUTHENTICATION=malformed_clerk,
        STORAGES=LOCAL_STORAGES,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_accepts_complete_effective_staging_configuration(
    client: Client,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
) -> None:
    """AC-2/3/4: valid deployed settings use local validation plus PostgreSQL only."""
    configure_staging_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")
    monkeypatch.setattr("media.storage.boto3.client", fail_vendor_call)
    monkeypatch.setattr("authentication.clerk.authenticate_request", fail_vendor_call)

    with override_settings(**configured_deployed_settings(valid_clerk_public_key)):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_accepts_development_deployment_without_baked_source_sha(
    client: Client,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
) -> None:
    """AC-2/3: Development deployments may lack Staging's immutable source SHA."""
    configure_development_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")

    with override_settings(**configured_deployed_settings(valid_clerk_public_key)):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "runtime_overrides",
    (
        {"RAILWAY_ENVIRONMENT_NAME": None},
        {"RAILWAY_DEPLOYMENT_ID": None},
        {"RAILWAY_ENVIRONMENT_NAME": "production"},
        {"RAILWAY_ENVIRONMENT_NAME": "preview"},
        {"RAILWAY_SERVICE_NAME": "worker"},
    ),
    ids=(
        "missing-environment",
        "missing-deployment-id",
        "production-environment",
        "unknown-environment",
        "wrong-service",
    ),
)
def test_readiness_rejects_unrecognized_or_incomplete_deployed_runtime(
    client: Client,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
    runtime_overrides: dict[str, str | None],
) -> None:
    """AC-3: deployed profile/runtime classification denies uncertainty and mismatch."""
    configure_development_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")
    for name, value in runtime_overrides.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    with override_settings(**configured_deployed_settings(valid_clerk_public_key)):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    (
        {"CLERK_AUTHENTICATION": None},
        {
            "CLERK_AUTHENTICATION": ClerkVerificationConfiguration(
                jwt_key="malformed-clerk-public-key",
                authorized_parties=("https://staging.tailtag.app",),
            )
        },
        {"STORAGES": LOCAL_STORAGES},
        {"STORAGES": storage_options(region_name="unexpected-region")},
        {"STORAGES": storage_options(url_expiry_seconds=1)},
        {"STORAGES": storage_options(unexpected_option="not-a-constructor-argument")},
        {"MEDIA_STORAGE_CONFIGURATION": None},
        {
            "MEDIA_STORAGE_CONFIGURATION": S3MediaConfiguration(
                endpoint_url="http://media.example.test",
                bucket_name="test-media-bucket",
                region="auto",
                access_key_id="test-access-key",
                secret_access_key="test-secret-key",
            )
        },
        {
            "MEDIA_STORAGE_CONFIGURATION": S3MediaConfiguration(
                endpoint_url="https://media.example.test",
                bucket_name="contradictory-bucket",
                region="auto",
                access_key_id="test-access-key",
                secret_access_key="test-secret-key",
            )
        },
        {"DEBUG": True},
        {"ALLOWED_HOSTS": ["*"]},
        {"ALLOWED_HOSTS": ["staging.tailtag.app", "https://malformed.example"]},
        {"ALLOWED_HOSTS": ["staging.tailtag.app", "bad_host.example"]},
        {"CSRF_TRUSTED_ORIGINS": ["http://staging.tailtag.app"]},
    ),
    ids=(
        "disabled-clerk",
        "malformed-clerk-key",
        "filesystem-storage",
        "contradictory-region-name",
        "invalid-read-url-expiry",
        "unexpected-storage-option",
        "missing-media-configuration",
        "malformed-media-endpoint",
        "contradictory-media-options",
        "debug-enabled",
        "wildcard-host",
        "url-like-host",
        "invalid-dns-host",
        "insecure-csrf-origin",
    ),
)
def test_readiness_fails_closed_for_unsafe_effective_deployed_settings(
    client: Client,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    overrides: dict[str, object],
    valid_clerk_public_key: str,
) -> None:
    """AC-2/3/4: one unsafe deployed setting denies ordinary API readiness."""
    configure_staging_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")
    configured = configured_deployed_settings(valid_clerk_public_key)
    configured.update(overrides)

    with override_settings(**configured):
        response = client.get("/health/ready", HTTP_HOST="staging.tailtag.app")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


def test_direct_readiness_hides_empty_effective_secret_key(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
) -> None:
    """AC-3/9: invalid settings deny readiness before middleware can sign a response."""
    configure_staging_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")
    configured = configured_deployed_settings(valid_clerk_public_key)
    configured["SECRET_KEY"] = ""

    with override_settings(**configured):
        response = readiness_view(RequestFactory().get("/health/ready"))

    assert response.status_code == 503
    assert json.loads(response.content) == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_rejects_malformed_effective_clerk_authorized_party(
    client: Client,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
) -> None:
    """AC-3/4: deployed Clerk validation reuses the existing origin parser."""
    configure_staging_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")
    configured = configured_deployed_settings(valid_clerk_public_key)
    configured["CLERK_AUTHENTICATION"] = ClerkVerificationConfiguration(
        jwt_key=valid_clerk_public_key,
        authorized_parties=("not an origin",),
    )

    with override_settings(**configured):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("source_sha", "deployment_id"),
    (
        (None, DEPLOYMENT_ID),
        ("not-a-source-sha", DEPLOYMENT_ID),
        (SOURCE_SHA, "not-a-uuid"),
    ),
    ids=("missing-sha", "malformed-sha", "malformed-deployment-id"),
)
def test_readiness_hides_invalid_deployed_identity(
    client: Client,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    source_sha: str | None,
    deployment_id: str,
    valid_clerk_public_key: str,
) -> None:
    """AC-2/3/9: invalid build/runtime identity is a fixed readiness denial."""
    metadata_path = tmp_path / "build-identity.json"
    metadata_path.write_text(json.dumps({"source_sha": source_sha}))
    monkeypatch.setattr(build_identity, "_METADATA_PATH", metadata_path)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", deployment_id)
    monkeypatch.setenv("RAILWAY_SERVICE_NAME", "api")
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")

    with override_settings(**configured_deployed_settings(valid_clerk_public_key)):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"
    assert SENSITIVE_DIAGNOSTIC not in response.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ENGINE", "django.db.backends.sqlite3"),
        ("NAME", ""),
        ("HOST", ""),
    ),
    ids=("wrong-engine", "missing-name", "missing-host"),
)
def test_readiness_rejects_invalid_effective_postgresql_configuration(
    client: Client,
    monkeypatch: MonkeyPatch,
    field: str,
    value: str,
) -> None:
    """AC-2/3: readiness validates the PostgreSQL configuration it will use."""
    configure_local_profile(monkeypatch)
    database = {**settings.DATABASES["default"], field: value}

    with override_settings(
        DEBUG=True,
        CLERK_AUTHENTICATION=None,
        STORAGES=LOCAL_STORAGES,
        DATABASES={"default": database},
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_returns_success_when_postgresql_is_available(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """Readiness succeeds after Django connects to PostgreSQL."""
    # CI imports production settings; this regression case intentionally exercises
    # the preserved local profile rather than inheriting that global selection.
    configure_local_profile(monkeypatch)
    with override_settings(
        DEBUG=True,
        CLERK_AUTHENTICATION=None,
        STORAGES=LOCAL_STORAGES,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_hides_database_failure(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """Readiness returns a generic unavailable response when its query fails."""

    class FailingCursor:
        """Minimal cursor context that fails only when executing the health query."""

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, _: str) -> NoReturn:
            raise DatabaseError("health query failed")

    monkeypatch.setattr("django.db.connection.cursor", FailingCursor)
    configure_local_profile(monkeypatch)
    with override_settings(
        DEBUG=True,
        CLERK_AUTHENTICATION=None,
        STORAGES=LOCAL_STORAGES,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_readiness_hides_database_connection_failure(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """AC-2/9: connection establishment errors stay a fixed unavailable response."""

    def unavailable_connection() -> NoReturn:
        raise DatabaseError(SENSITIVE_DIAGNOSTIC)

    monkeypatch.setattr(
        "django.db.connection.ensure_connection", unavailable_connection
    )
    configure_local_profile(monkeypatch)
    with override_settings(
        DEBUG=True,
        CLERK_AUTHENTICATION=None,
        STORAGES=LOCAL_STORAGES,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"
    assert SENSITIVE_DIAGNOSTIC not in response.content.decode()


@pytest.mark.parametrize(
    ("source_sha", "deployment_id"),
    (
        (SOURCE_SHA, DEPLOYMENT_ID),
        (SECOND_SOURCE_SHA, SECOND_DEPLOYMENT_ID),
    ),
)
def test_identity_returns_only_the_canonical_safe_tuple(
    client: Client,
    monkeypatch: MonkeyPatch,
    source_sha: str,
    deployment_id: str,
) -> None:
    """AC-6/7/9: identity mirrors #201's live tuple without extra metadata."""
    observed_calls: list[object] = []

    def identity() -> dict[str, str]:
        observed_calls.append(None)
        return {
            "source_sha": source_sha,
            "deployment_id": deployment_id,
            "environment": "staging",
        }

    monkeypatch.setattr(build_identity, "get_identity", identity)
    monkeypatch.setattr("django.db.connection.ensure_connection", fail_if_called)

    response = client.get("/health/identity")

    assert response.status_code == 200
    assert response.json() == {
        "source_sha": source_sha,
        "deployment_id": deployment_id,
        "environment": "staging",
    }
    assert set(response.json()) == {"source_sha", "deployment_id", "environment"}
    assert "deployment_timestamp" not in response.json()
    assert response["Cache-Control"] == "no-store"
    assert observed_calls == [None]


def test_identity_hides_invalid_canonical_component_failure(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """AC-6/9: an unreadable #201 artifact cannot expose its diagnostic publicly."""

    def unavailable_identity() -> NoReturn:
        raise ValueError(SENSITIVE_DIAGNOSTIC)

    monkeypatch.setattr(build_identity, "get_identity", unavailable_identity)
    monkeypatch.setattr("django.db.connection.ensure_connection", fail_if_called)

    response = client.get("/health/identity")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"
    assert SENSITIVE_DIAGNOSTIC not in response.content.decode()


def test_identity_hides_unreadable_canonical_component_failure(
    client: Client, monkeypatch: MonkeyPatch
) -> None:
    """AC-6/9: identity file access errors have the same fixed public denial."""

    def unreadable_identity() -> NoReturn:
        raise OSError(SENSITIVE_DIAGNOSTIC)

    monkeypatch.setattr(build_identity, "get_identity", unreadable_identity)

    response = client.get("/health/identity")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response["Cache-Control"] == "no-store"
    assert SENSITIVE_DIAGNOSTIC not in response.content.decode()
