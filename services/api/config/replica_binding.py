"""Bind a Cloud Run process to the pinned hybrid replica project and region."""

from __future__ import annotations

import hashlib
import http.client
import re
import urllib.request
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, cast

from config.settings.media import S3MediaConfiguration

_ERROR: Final = "Replica target binding unavailable"
_METADATA_URL: Final = "http://metadata.google.internal/computeMetadata/v1/"
_METADATA_TIMEOUT_SECONDS: Final = 1
_METADATA_MAX_BYTES: Final = 256
_PROJECT_NUMBER: Final = re.compile(r"[1-9][0-9]{0,19}")
_REGION: Final = re.compile(r"[a-z]+-[a-z]+[0-9]+")
_REGION_VALUE: Final = re.compile(
    r"projects/([1-9][0-9]{0,19})/regions/([a-z]+-[a-z]+[0-9]+)"
)
_LABEL: Final = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_NAME: Final = re.compile(r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")
_DEPLOYMENT_ID: Final = re.compile(r"[a-z][a-z0-9-]{0,62}")
_HOST: Final = re.compile(rf"{_LABEL}(?:\.{_LABEL})+")
_ENDPOINT_URL: Final = re.compile(rf"https://({_LABEL}(?:\.{_LABEL})+)")
_DATABASE_NAME: Final = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,62}")
_BUCKET_NAME: Final = re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]")

SERVICE_NAME: Final = "tailtag-api-replica"
_JOB_NAMES: Final = (
    "tailtag-replica-migrate",
    "tailtag-replica-reset",
    "tailtag-replica-fixture",
    "tailtag-replica-pool",
    "tailtag-replica-inspect",
    "tailtag-replica-registry-reconcile",
)

# Reviewed pin digests. Each one hashes private infrastructure identifiers.
_EXPECTED_TARGET_DIGESTS: Final[dict[str, str]] = {
    "tailtag-api-replica": "a9f39692357c66a62eee98cef292d0a8f9ba8c1c6684f77a6d925c2581bb8b02",
    "tailtag-replica-migrate": "52d527a87e4c1b8675960269460042f527e09afee121b99c1ff4c06391ab6de0",
    "tailtag-replica-reset": "59cdc92a9a27e31b538df45431a62a13a8c47cd79afb2378efdfe89e39757ca1",
    "tailtag-replica-fixture": "64cb4e23acdad6a91065c0903ca5da1f24b838a05020ef61b86491c3d465abff",
    "tailtag-replica-pool": "5b8ccc01ef376ae99a8ae3054c4d3cc4442f382f17caa1090d88094df9109dd0",
    "tailtag-replica-inspect": "36f50df105db508e96661403ea51709de2659abe306ff1e0b8ccfab402c7f136",
    "tailtag-replica-registry-reconcile": "f0fa82c05726595c6fbb53982dfe56acb12b2502524b1ae555135010f3cf9fae",
}
_EXPECTED_HOST_DIGEST: Final = (
    "a78605fc99f91d19d469ea8f20de7fb5a301360cd4014b561d311cdb35fdd21a"
)
_EXPECTED_DATABASE_DIGEST: Final = (
    "d9f06b60de7430521367cd7ae4f08878d430018c222aadb5cb2885710e66ddf7"
)
_EXPECTED_MEDIA_DIGEST: Final = (
    "9fd972562fed420687ef1e41d52e6efb104a14b8d2b29633774e0c690d9df613"
)
_PROBE_HOSTS: Final[frozenset[str]] = frozenset()
# Cloud Run serves a traffic tag at `TAG---` plus the deterministic host. The
# release gates test a no-traffic candidate revision through this one tag.
CANDIDATE_TAG: Final = "candidate"
_CANDIDATE_PREFIX: Final = f"{CANDIDATE_TAG}---"

_location: tuple[str, str] | None = None


class ReplicaBindingError(ValueError):
    """Raised with a fixed message when a Cloud Run target cannot be proven."""


@dataclass(frozen=True, slots=True)
class CloudRunTarget:
    """The proven Cloud Run service revision or job execution of this process."""

    name: str
    kind: Literal["service", "job"]
    deployment_id: str


def _digest(tag: str, *parts: str) -> str:
    return hashlib.sha256("\0".join([tag, *parts]).encode()).hexdigest()


def _checked(pattern: re.Pattern[str], value: object) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ReplicaBindingError(_ERROR)
    return value


def target_digest(project_number: str, region: str, name: str) -> str:
    """Return the pin digest of one Cloud Run service or job name."""
    return _digest(
        "tailtag-replica-v1",
        _checked(_PROJECT_NUMBER, project_number),
        _checked(_REGION, region),
        _checked(_NAME, name),
    )


def host_digest(host: str) -> str:
    """Return the pin digest of the run.app host."""
    return _digest("tailtag-replica-host-v1", _checked(_HOST, host))


def database_digest(host: str, name: str) -> str:
    """Return the pin digest of the database host and name."""
    return _digest(
        "tailtag-replica-database-v1",
        _checked(_HOST, host),
        _checked(_DATABASE_NAME, name),
    )


def media_digest(endpoint_url: str, bucket_name: str) -> str:
    """Return the pin digest of the media endpoint and bucket."""
    _checked(_ENDPOINT_URL, endpoint_url)
    return _digest(
        "tailtag-replica-media-v1", endpoint_url, _checked(_BUCKET_NAME, bucket_name)
    )


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: object, **__: object) -> None:
        return None


def _fetch_metadata(path: str) -> str:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _RefuseRedirects()
    )
    request = urllib.request.Request(
        _METADATA_URL + path, headers={"Metadata-Flavor": "Google"}
    )
    try:
        with opener.open(request, timeout=_METADATA_TIMEOUT_SECONDS) as response:
            body = cast(bytes, response.read(_METADATA_MAX_BYTES + 1))
            if response.status != 200 or len(body) > _METADATA_MAX_BYTES:
                raise ReplicaBindingError(_ERROR)
        return body.decode("ascii")
    except (OSError, ValueError, http.client.HTTPException):
        raise ReplicaBindingError(_ERROR) from None


def _project_location() -> tuple[str, str]:
    global _location
    if _location is not None:
        return _location
    project_number = _checked(
        _PROJECT_NUMBER, _fetch_metadata("project/numeric-project-id")
    )
    region_value = _REGION_VALUE.fullmatch(_fetch_metadata("instance/region"))
    if region_value is None or region_value.group(1) != project_number:
        raise ReplicaBindingError(_ERROR)
    _location = (project_number, region_value.group(2))
    return _location


def read_cloud_run_target(environ: Mapping[str, str]) -> CloudRunTarget | None:
    """Return the proven Cloud Run target, or None when this is not Cloud Run."""
    service = environ.get("K_SERVICE")
    job = environ.get("CLOUD_RUN_JOB")
    if service is None and job is None:
        return None
    if service is not None and job is not None:
        raise ReplicaBindingError(_ERROR)
    kind: Literal["service", "job"]
    if service is not None:
        kind, name, deployment_id = "service", service, environ.get("K_REVISION")
    else:
        kind, name, deployment_id = (
            "job",
            cast(str, job),
            environ.get("CLOUD_RUN_EXECUTION"),
        )
    deployment = _checked(_DEPLOYMENT_ID, deployment_id)
    if not deployment.startswith(f"{name}-") or (name == SERVICE_NAME) != (
        kind == "service"
    ):
        raise ReplicaBindingError(_ERROR)
    expected = _EXPECTED_TARGET_DIGESTS.get(name)
    project_number, region = _project_location()
    if expected is None or target_digest(project_number, region, name) != expected:
        raise ReplicaBindingError(_ERROR)
    return CloudRunTarget(name=name, kind=kind, deployment_id=deployment)


def validate_run_app_host(allowed_hosts: Sequence[str]) -> str:
    """Return the one pinned run.app host that ALLOWED_HOSTS must consist of.

    The release candidate tag host of that same host may also be present (#356).
    """
    hosts = set(allowed_hosts)
    if len(hosts) != len(allowed_hosts):
        raise ReplicaBindingError(_ERROR)
    run_app_hosts = {
        host for host in hosts - _PROBE_HOSTS if not host.startswith(_CANDIDATE_PREFIX)
    }
    if len(run_app_hosts) != 1:
        raise ReplicaBindingError(_ERROR)
    host = next(iter(run_app_hosts))
    if host_digest(host) != _EXPECTED_HOST_DIGEST:
        raise ReplicaBindingError(_ERROR)
    if not hosts - _PROBE_HOSTS - {host} <= {_CANDIDATE_PREFIX + host}:
        raise ReplicaBindingError(_ERROR)
    return host


def validate_candidate_host(host: str) -> str:
    """Return the candidate tag host only if it tags the pinned run.app host."""
    if not host.startswith(_CANDIDATE_PREFIX):
        raise ReplicaBindingError(_ERROR)
    service_host = host.removeprefix(_CANDIDATE_PREFIX)
    if host_digest(service_host) != _EXPECTED_HOST_DIGEST:
        raise ReplicaBindingError(_ERROR)
    return host


def is_pinned_job(
    identity: Mapping[str, object],
    runtime_identity: Mapping[str, object],
    environ: Mapping[str, str],
    job_names: Collection[str],
) -> bool:
    """Return whether this process is one of the named replica jobs, as claimed."""
    try:
        target = read_cloud_run_target(environ)
    except ReplicaBindingError:
        return False
    return (
        target is not None
        and target.kind == "job"
        and target.name in job_names
        and identity.get("environment") == "replica"
        and identity.get("deployment_id") == target.deployment_id
        and dict(runtime_identity) == dict(identity)
    )


def validate_database_target(database_settings: Mapping[str, object]) -> None:
    """Require verified database TLS and the pinned database."""
    options = database_settings.get("OPTIONS")
    if not isinstance(options, Mapping):
        raise ReplicaBindingError(_ERROR)
    option_mapping = cast(Mapping[str, object], options)
    root_certificate = option_mapping.get("sslrootcert")
    if (
        option_mapping.get("sslmode") != "verify-full"
        or not isinstance(root_certificate, str)
        or not root_certificate
    ):
        raise ReplicaBindingError(_ERROR)
    database_host = database_settings.get("HOST")
    database_name = database_settings.get("NAME")
    if not isinstance(database_host, str) or not isinstance(database_name, str):
        raise ReplicaBindingError(_ERROR)
    if database_digest(database_host, database_name) != _EXPECTED_DATABASE_DIGEST:
        raise ReplicaBindingError(_ERROR)


def validate_data_targets(
    database_settings: Mapping[str, object], media_configuration: S3MediaConfiguration
) -> None:
    """Require verified database TLS and the pinned database and media targets."""
    validate_database_target(database_settings)
    validate_media_target(
        media_configuration.endpoint_url, media_configuration.bucket_name
    )


def validate_media_target(endpoint_url: str, bucket_name: str) -> None:
    """Require the pinned replica media endpoint and bucket."""
    if media_digest(endpoint_url, bucket_name) != _EXPECTED_MEDIA_DIGEST:
        raise ReplicaBindingError(_ERROR)
