"""Local validation of the effective settings required for API readiness."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from ipaddress import ip_address
from typing import Final, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_domain_name
from django.http.request import split_domain_port

from authentication.clerk import ClerkVerificationConfiguration
from config import build_identity, replacement_target_binding
from config.settings.clerk import load_clerk_authentication_configuration
from config.settings.media import S3MediaConfiguration, load_s3_media_configuration

_CONFIGURATION_ERROR: Final = "Health configuration unavailable"
_PRODUCTION_SETTINGS: Final = "config.settings.production"
_STAGING_HOST: Final = "staging.tailtag.app"
_RAILWAY_HEALTHCHECK_HOST: Final = "healthcheck.railway.app"
_LOCAL_STORAGE_BACKENDS: Final = frozenset(
    {
        "django.core.files.storage.FileSystemStorage",
        "django.core.files.storage.InMemoryStorage",
    }
)


def validate_configuration() -> None:
    """Raise a fixed error unless the effective API configuration is safe to use."""
    try:
        _validate_database()
        _validate_common_settings()
        deployed = _is_deployed()
        if deployed:
            _validate_deployed_settings()
        else:
            _validate_local_settings()
    except (
        AttributeError,
        ImproperlyConfigured,
        KeyError,
        RuntimeError,
        TypeError,
        ValidationError,
        ValueError,
        OSError,
    ):
        raise ImproperlyConfigured(_CONFIGURATION_ERROR) from None


def _validate_database() -> None:
    database = cast(Mapping[str, object], settings.DATABASES["default"])
    if (
        database.get("ENGINE") != "django.db.backends.postgresql"
        or not isinstance(database.get("HOST"), str)
        or not database["HOST"]
        or not isinstance(database.get("NAME"), str)
        or not database["NAME"]
    ):
        raise ValueError


def _validate_common_settings() -> None:
    if not isinstance(settings.SECRET_KEY, str) or not settings.SECRET_KEY:
        raise ValueError
    _validate_hosts(settings.ALLOWED_HOSTS)
    _validate_origins(settings.CSRF_TRUSTED_ORIGINS)


def _validate_deployed_settings() -> None:
    if _settings_module() != _PRODUCTION_SETTINGS:
        raise ValueError
    if (
        settings.DEBUG
        or settings.SESSION_COOKIE_SECURE is not True
        or settings.CSRF_COOKIE_SECURE is not True
    ):
        raise ValueError
    _validate_clerk(settings.CLERK_AUTHENTICATION)
    _validate_storage(
        getattr(settings, "MEDIA_STORAGE_CONFIGURATION", None),
        settings.STORAGES,
        require_s3=True,
    )

    identity = build_identity.get_identity()
    replacement_target_binding.validate_runtime_target(os.environ)
    environment = identity["environment"]
    if (
        environment not in {"development", "staging"}
        or identity["deployment_id"] is None
        or _runtime_service_name() != "api"
    ):
        raise ValueError
    if environment == "staging":
        _validate_staging_phase(identity["source_sha"])
    else:
        _validate_development_candidate(identity["source_sha"])


def _validate_development_candidate(source_sha: str | None) -> None:
    if source_sha is None:
        raise ValueError
    candidate_hosts = set(settings.ALLOWED_HOSTS) - {_RAILWAY_HEALTHCHECK_HOST}
    if len(candidate_hosts) != 1:
        raise ValueError
    origin = replacement_target_binding.pinned_development_candidate_origin(
        candidate_hosts.pop()
    )
    if (
        len(settings.ALLOWED_HOSTS) != 2
        or set(settings.ALLOWED_HOSTS)
        != {origin.removeprefix("https://"), _RAILWAY_HEALTHCHECK_HOST}
        or settings.CSRF_TRUSTED_ORIGINS != [origin]
        or settings.CLERK_AUTHENTICATION.authorized_parties
        != ("http://localhost:3000",)
    ):
        raise ValueError


def _validate_staging_phase(source_sha: str | None) -> None:
    phase = os.environ.get("TAILTAG_STAGING_TARGET_PHASE")
    if source_sha is None or phase not in {"candidate", "canonical"}:
        raise ValueError
    if phase == "candidate":
        candidate_hosts = set(settings.ALLOWED_HOSTS) - {_RAILWAY_HEALTHCHECK_HOST}
        if len(candidate_hosts) != 1:
            raise ValueError
        origin = replacement_target_binding.pinned_candidate_origin(
            candidate_hosts.pop()
        )
    else:
        origin = f"https://{_STAGING_HOST}"
    host = origin.removeprefix("https://")
    expected_party = (
        "https://accounts.staging-next.tailtag.app"
        if phase == "candidate"
        else "https://accounts.staging.tailtag.app"
    )
    if (
        len(settings.ALLOWED_HOSTS) != 2
        or set(settings.ALLOWED_HOSTS) != {host, _RAILWAY_HEALTHCHECK_HOST}
        or settings.CSRF_TRUSTED_ORIGINS != [origin]
        or settings.CLERK_AUTHENTICATION.authorized_parties != (expected_party,)
    ):
        raise ValueError


def _validate_hosts(hosts: object) -> None:
    if not isinstance(hosts, Sequence) or isinstance(hosts, str) or not hosts:
        raise ValueError
    for host in cast(Sequence[object], hosts):
        if not isinstance(host, str) or host == "*" or not _valid_host(host):
            raise ValueError


def _validate_origins(origins: object) -> None:
    if not isinstance(origins, Sequence) or isinstance(origins, str):
        raise TypeError
    for origin in cast(Sequence[object], origins):
        if not isinstance(origin, str) or not _is_plain_origin(origin):
            raise ValueError


def _valid_host(host: str) -> bool:
    if host in {"localhost", "testserver"}:
        return True
    domain, port = split_domain_port(host)
    if domain != host or port:
        return False
    try:
        ip_address(domain)
    except ValueError:
        try:
            validate_domain_name(domain)
        except ValueError:
            return False
    return True


def _is_plain_origin(value: str) -> bool:
    """Use Clerk's existing configured-origin parser for Django's trusted origins."""
    from config.settings.clerk import (
        _is_plain_origin as clerk_origin,  # pyright: ignore[reportPrivateUsage]
    )

    return clerk_origin(value)


def _validate_clerk(configuration: object) -> None:
    if not isinstance(configuration, ClerkVerificationConfiguration):
        raise TypeError
    loaded = load_clerk_authentication_configuration(
        {
            "CLERK_AUTHENTICATION_ENABLED": "true",
            "CLERK_JWT_KEY": configuration.jwt_key,
            "CLERK_AUTHORIZED_PARTIES": ",".join(configuration.authorized_parties),
        }
    )
    if loaded != configuration:
        raise ValueError


def _validate_local_settings() -> None:
    configuration = getattr(settings, "CLERK_AUTHENTICATION", None)
    if configuration is not None:
        _validate_clerk(configuration)
    _validate_storage(
        getattr(settings, "MEDIA_STORAGE_CONFIGURATION", None),
        settings.STORAGES,
        require_s3=False,
    )


def _validate_storage(
    configuration: object, storages: object, *, require_s3: bool
) -> None:
    if not isinstance(storages, Mapping):
        raise TypeError
    storage_mapping = cast(Mapping[str, object], storages)
    default = storage_mapping.get("default")
    if not isinstance(default, Mapping):
        raise TypeError
    default_mapping = cast(Mapping[str, object], default)
    uses_s3 = default_mapping.get("BACKEND") == "media.storage.S3MediaStorage"
    if not require_s3 and not uses_s3:
        options = default_mapping.get("OPTIONS", {})
        if default_mapping.get(
            "BACKEND"
        ) not in _LOCAL_STORAGE_BACKENDS or not isinstance(options, Mapping):
            raise ValueError
        return
    if not isinstance(configuration, S3MediaConfiguration) or not uses_s3:
        raise ValueError
    loaded = load_s3_media_configuration(
        {
            "MEDIA_STORAGE_ENDPOINT_URL": configuration.endpoint_url,
            "MEDIA_STORAGE_BUCKET_NAME": configuration.bucket_name,
            "MEDIA_STORAGE_REGION": configuration.region,
            "MEDIA_STORAGE_ACCESS_KEY_ID": configuration.access_key_id,
            "MEDIA_STORAGE_SECRET_ACCESS_KEY": configuration.secret_access_key,
        }
    )
    options = default_mapping.get("OPTIONS")
    if not isinstance(options, Mapping):
        raise TypeError
    option_mapping = cast(Mapping[str, object], options)
    required = {
        "endpoint_url": loaded.endpoint_url,
        "bucket_name": loaded.bucket_name,
        "access_key_id": loaded.access_key_id,
        "secret_access_key": loaded.secret_access_key,
    }
    if any(option_mapping.get(name) != value for name, value in required.items()):
        raise ValueError
    if option_mapping.get("url_expiry_seconds", 600) != 600:
        raise ValueError
    region = option_mapping.get("region")
    region_name = option_mapping.get("region_name")
    if region is None and region_name is None:
        raise ValueError
    if region is not None and region != loaded.region:
        raise ValueError
    if region_name is not None and region_name != loaded.region:
        raise ValueError
    allowed = set(required) | {"region", "region_name", "url_expiry_seconds"}
    if not set(option_mapping).issubset(allowed):
        raise ValueError


def _runtime_service_name() -> str | None:
    # The identity component deliberately owns Railway's environment mapping;
    # service name is a separate routing constraint for deployed readiness.
    return os.environ.get("RAILWAY_SERVICE_NAME")


def _settings_module() -> str | None:
    # Django's override_settings replaces the active holder. The selected module
    # remains on a wrapped default holder, so inspect that effective chain rather
    # than treating a temporary override as an unknown deployed profile.
    wrapped = settings._wrapped  # pyright: ignore[reportPrivateUsage]
    while True:
        value = getattr(wrapped, "SETTINGS_MODULE", None)
        if isinstance(value, str):
            return value
        if not hasattr(wrapped, "default_settings"):
            return None
        wrapped = wrapped.default_settings


def _is_deployed() -> bool:
    module = _settings_module()
    if module == "config.settings.local":
        return any(
            name in os.environ
            for name in (
                "RAILWAY_ENVIRONMENT_NAME",
                "RAILWAY_DEPLOYMENT_ID",
                "RAILWAY_SERVICE_NAME",
            )
        )
    return True
