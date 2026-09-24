"""Offline acceptance tests for the finite replacement Staging candidate origin."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Final, NoReturn, cast

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from pytest import MonkeyPatch

from authentication.clerk import ClerkVerificationConfiguration
from config import replacement_target_binding
from health.configuration import validate_configuration
from tests.clerk_settings_contract import (
    valid_clerk_public_key as _valid_clerk_public_key,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from tests.test_api_staging_preflight import RecordingOpener, Response
from tests.test_health import (
    configure_staging_identity,
    configured_deployed_settings,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

PROJECT: Final = "a1111111-1111-4111-8111-111111111111"
DEVELOPMENT: Final = "22222222-2222-4222-8222-222222222222"
STAGING: Final = "33333333-3333-4333-8333-333333333333"
API: Final = "d4444444-4444-4444-8444-444444444444"
POSTGRES: Final = "55555555-5555-4555-8555-555555555555"
OLD_PROJECT: Final = "66666666-6666-4666-8666-666666666666"
CANDIDATE_HOST: Final = "synthetic-api.up.railway.app"
OTHER_HOST: Final = "other-api.up.railway.app"
CANDIDATE_ORIGIN: Final = f"https://{CANDIDATE_HOST}"
DEVELOPMENT_HOST: Final = "synthetic-development-api.up.railway.app"
DEVELOPMENT_ORIGIN: Final = f"https://{DEVELOPMENT_HOST}"
CANONICAL_ORIGIN: Final = "https://staging.tailtag.app"
IDENTITY: Final = {
    "source_sha": "a" * 40,
    "deployment_id": "77777777-7777-4777-8777-777777777777",
    "environment": "staging",
}
SENSITIVE: Final = "private-candidate-value-must-not-appear"
DEVELOPMENT_IDENTITY: Final = {**IDENTITY, "environment": "development"}


@pytest.fixture
def preflight() -> ModuleType:
    return importlib.import_module("scripts.api_staging_preflight")


def _candidate_digest(hostname: str) -> str:
    return hashlib.sha256(f"tailtag-candidate-api-v1\0{hostname}".encode()).hexdigest()


def _development_digest(hostname: str) -> str:
    return hashlib.sha256(
        f"tailtag-development-api-v1\0{hostname}".encode()
    ).hexdigest()


def _manifest(tmp_path: Path, *, hostname: object = CANDIDATE_HOST) -> Path:
    parent = tmp_path / "tailtag"
    parent.mkdir(mode=0o700)
    parent.chmod(0o700)
    path = parent / "staging-clean-rebuild-targets.json"
    path.write_text(
        json.dumps(
            {
                "rebuild_railway_project_id": PROJECT,
                "rebuild_development_environment_id": DEVELOPMENT,
                "rebuild_staging_environment_id": STAGING,
                "rebuild_api_service_id": API,
                "rebuild_postgres_service_id": POSTGRES,
                "rebuild_staging_candidate_api_domain": hostname,
            }
        )
    )
    path.chmod(0o600)
    return path


def _candidate_binding(monkeypatch: MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(
        replacement_target_binding, "_MANIFEST_PATH", path, raising=False
    )
    monkeypatch.setattr(
        replacement_target_binding,
        "_EXPECTED_DIGESTS",
        {
            "development-api": replacement_target_binding.fingerprint_tuple(
                "development-api", PROJECT, DEVELOPMENT, API
            ),
            "development-postgres": replacement_target_binding.fingerprint_tuple(
                "development-postgres", PROJECT, DEVELOPMENT, POSTGRES
            ),
            "staging-api": replacement_target_binding.fingerprint_tuple(
                "staging-api", PROJECT, STAGING, API
            ),
            "staging-postgres": replacement_target_binding.fingerprint_tuple(
                "staging-postgres", PROJECT, STAGING, POSTGRES
            ),
        },
    )
    monkeypatch.setattr(
        replacement_target_binding,
        "_EXPECTED_CANDIDATE_HOST_DIGEST",
        _candidate_digest(CANDIDATE_HOST),
        raising=False,
    )


def _development_manifest(
    tmp_path: Path, *, hostname: object = DEVELOPMENT_HOST
) -> Path:
    path = _manifest(tmp_path)
    document = json.loads(path.read_text())
    document["rebuild_development_api_domain"] = hostname
    path.write_text(json.dumps(document))
    return path


def _development_binding(monkeypatch: MonkeyPatch, path: Path) -> None:
    _candidate_binding(monkeypatch, path)
    monkeypatch.setattr(
        replacement_target_binding,
        "_EXPECTED_DEVELOPMENT_CANDIDATE_HOST_DIGEST",
        _development_digest(DEVELOPMENT_HOST),
        raising=False,
    )


def _development_preflight_binding(monkeypatch: MonkeyPatch, path: Path) -> None:
    _development_binding(monkeypatch, path)
    monkeypatch.setenv("TAILTAG_DEVELOPMENT_API_BASE_URL", DEVELOPMENT_ORIGIN)


def _assert_binding_denied(operation: Callable[[], object]) -> None:
    with pytest.raises(replacement_target_binding.TargetBindingError) as caught:
        operation()
    assert str(caught.value) == "Replacement target binding unavailable"
    assert SENSITIVE not in str(caught.value)
    assert CANDIDATE_HOST not in str(caught.value)


def test_candidate_hostname_fingerprint_has_independent_namespace_vector() -> None:
    """C-1: the reviewed hostname commitment includes framing and exact bytes."""
    assert replacement_target_binding.fingerprint_candidate_hostname(
        CANDIDATE_HOST
    ) == _candidate_digest(CANDIDATE_HOST)
    assert replacement_target_binding.fingerprint_candidate_hostname(
        OTHER_HOST
    ) != _candidate_digest(CANDIDATE_HOST)


def test_candidate_origin_uses_only_pinned_private_manifest(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """C-1: all four Railway selectors and the exact hostname jointly authorize it."""
    path = _manifest(tmp_path)
    _candidate_binding(monkeypatch, path)
    before = path.read_bytes()

    assert replacement_target_binding.load_candidate_origin() == CANDIDATE_ORIGIN
    assert path.read_bytes() == before

    document = json.loads(path.read_text())
    document["rebuild_railway_project_id"] = OLD_PROJECT
    document["expected_candidate_digest"] = _candidate_digest(OTHER_HOST)
    path.write_text(json.dumps(document))
    _assert_binding_denied(replacement_target_binding.load_candidate_origin)

    document["rebuild_railway_project_id"] = PROJECT
    document["rebuild_staging_candidate_api_domain"] = OTHER_HOST
    path.write_text(json.dumps(document))
    _assert_binding_denied(replacement_target_binding.load_candidate_origin)


@pytest.mark.parametrize(
    "hostname",
    (
        None,
        "",
        OTHER_HOST,
        "https://synthetic-api.up.railway.app",
        "synthetic-api.up.railway.app:443",
        "synthetic-api.up.railway.app/path",
        "SYNTHETIC-api.up.railway.app",
        " synthetic-api.up.railway.app",
        "synthetic-api.up.railway.app.",
        "localhost",
    ),
)
def test_candidate_origin_rejects_missing_changed_or_malformed_hostname(
    monkeypatch: MonkeyPatch, tmp_path: Path, hostname: object
) -> None:
    """C-1: no normalization, alternate origin or manifest-supplied pin redirects."""
    path = _manifest(tmp_path, hostname=hostname)
    _candidate_binding(monkeypatch, path)
    _assert_binding_denied(replacement_target_binding.load_candidate_origin)


def test_candidate_origin_rejects_unsafe_manifest_mode(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """C-1: candidate origin inherits the owner-only selector file boundary."""
    path = _manifest(tmp_path)
    _candidate_binding(monkeypatch, path)
    path.chmod(0o644)
    _assert_binding_denied(replacement_target_binding.load_candidate_origin)


def test_candidate_origin_requires_manifest_hostname_field(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """C-1: missing candidate selector has no host fallback."""
    path = _manifest(tmp_path)
    _candidate_binding(monkeypatch, path)
    document = json.loads(path.read_text())
    del document["rebuild_staging_candidate_api_domain"]
    path.write_text(json.dumps(document))
    _assert_binding_denied(replacement_target_binding.load_candidate_origin)


def test_candidate_origin_rejects_duplicate_hostname_key(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """C-1: ambiguous private configuration cannot choose a later hostname."""
    path = _manifest(tmp_path)
    _candidate_binding(monkeypatch, path)
    document = path.read_text()
    path.write_text(
        document[:-1]
        + ',"rebuild_staging_candidate_api_domain":"other-api.up.railway.app"}'
    )
    _assert_binding_denied(replacement_target_binding.load_candidate_origin)


def test_candidate_preflight_uses_bounded_identity_ready_identity_sequence(
    preflight: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """C-3: exact pinned HTTPS origin returns an explicitly candidate-only tuple."""
    _candidate_binding(monkeypatch, _manifest(tmp_path))
    calls: list[str] = []
    responses: list[object] = [IDENTITY, {"status": "ok"}, IDENTITY]

    def fetch(url: str) -> object:
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)

    assert preflight.validate_candidate_target() == {
        "phase": "candidate",
        "identity": IDENTITY,
    }
    assert calls == [
        CANDIDATE_ORIGIN + "/health/identity",
        CANDIDATE_ORIGIN + "/health/ready",
        CANDIDATE_ORIGIN + "/health/identity",
    ]
    assert responses == []


@pytest.mark.parametrize(
    "responses",
    (
        [dict(IDENTITY, unexpected=SENSITIVE)],
        [IDENTITY, {"status": "unavailable"}],
        [IDENTITY, {"status": "ok"}, dict(IDENTITY, source_sha="b" * 40)],
    ),
    ids=("extra-identity", "not-ready", "identity-drift"),
)
def test_candidate_preflight_rejects_body_mismatch_without_leak(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    responses: list[object],
) -> None:
    """C-3: uncertain identity or readiness cannot produce candidate evidence."""
    _candidate_binding(monkeypatch, _manifest(tmp_path))
    remaining = list(responses)
    calls: list[str] = []

    def fetch(url: str) -> object:
        calls.append(url)
        return remaining.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    with pytest.raises(preflight.TargetSafetyError) as caught:
        preflight.validate_candidate_target()
    assert SENSITIVE not in str(caught.value)
    assert len(calls) == len(responses)


def test_candidate_preflight_rejects_redirected_response(
    preflight: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """C-3: Railway candidate cannot redirect the read to a different URL."""
    _candidate_binding(monkeypatch, _manifest(tmp_path))
    opener = RecordingOpener(
        Response(
            body=json.dumps(IDENTITY).encode(),
            url="https://other.invalid/health/identity",
        )
    )

    def build_opener(*_: object) -> RecordingOpener:
        return opener

    monkeypatch.setattr(preflight.urllib.request, "build_opener", build_opener)

    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_candidate_target()
    assert len(opener.calls) == 1
    assert opener.calls[0][0].full_url == CANDIDATE_ORIGIN + "/health/identity"


def test_canonical_preflight_rejects_candidate_origin_before_fetch(
    preflight: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """C-4: candidate domain cannot masquerade as canonical via old entry point."""

    def must_not_fetch(_: str) -> NoReturn:
        raise AssertionError("candidate origin reached canonical transport")

    monkeypatch.setattr(preflight, "_fetch_json", must_not_fetch)
    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_target(CANDIDATE_ORIGIN)


def test_candidate_cli_emits_envelope_and_rejects_arbitrary_url(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """C-3/C-4: finite selector output cannot be confused with canonical tuple."""

    def candidate_result() -> dict[str, object]:
        return {"phase": "candidate", "identity": IDENTITY}

    monkeypatch.setattr(
        preflight,
        "validate_candidate_target",
        candidate_result,
    )
    monkeypatch.setattr(sys, "argv", ["api_staging_preflight.py", "--candidate"])
    assert preflight.main() == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {"phase": "candidate", "identity": IDENTITY}
    assert CANDIDATE_HOST not in captured.out

    def must_not_fetch() -> NoReturn:
        raise AssertionError("arbitrary candidate URL must not be fetched")

    monkeypatch.setattr(preflight, "validate_candidate_target", must_not_fetch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_preflight.py", "--candidate", "https://other.invalid"],
    )
    assert preflight.main() == 1
    denied = capsys.readouterr()
    assert denied.out == ""
    assert "https://other.invalid" not in denied.err


@pytest.mark.parametrize("manifest_state", ("missing", "malformed"))
def test_candidate_cli_hides_missing_or_malformed_manifest(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    manifest_state: str,
) -> None:
    """C-1/C-3/T-8: private-file failure has only a fixed public denial."""
    path = _manifest(tmp_path)
    _candidate_binding(monkeypatch, path)
    if manifest_state == "missing":
        path.unlink()
    else:
        path.write_text("{bad-json " + SENSITIVE)
    monkeypatch.setattr(sys, "argv", ["api_staging_preflight.py", "--candidate"])

    assert preflight.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "FAIL staging preflight unavailable" in captured.err
    assert "Traceback" not in captured.err
    assert SENSITIVE not in captured.err
    assert CANDIDATE_HOST not in captured.err
    assert str(path) not in captured.err


def test_canonical_mutation_consumer_rejects_candidate_envelope(
    preflight: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """C-4: candidate evidence cannot authorize the canonical reset launcher."""
    consumer = importlib.import_module("scripts.api_staging_reset_ssh")

    def candidate_as_canonical(_: str) -> dict[str, object]:
        return {"phase": "candidate", "identity": IDENTITY}

    monkeypatch.setattr(
        preflight,
        "validate_target",
        candidate_as_canonical,
    )
    with pytest.raises(ValueError, match="preflight unavailable"):
        consumer._preflight()


@pytest.mark.parametrize("phase", ("candidate", "canonical"))
def test_deployed_staging_readiness_accepts_only_matching_exact_phase_profile(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
    phase: str,
) -> None:
    """C-2: exact target, hosts, CSRF and single Clerk party jointly pass."""
    _candidate_binding(monkeypatch, _manifest(tmp_path))
    configure_staging_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")
    monkeypatch.setenv("TAILTAG_STAGING_TARGET_PHASE", phase)
    configured = configured_deployed_settings(valid_clerk_public_key)
    if phase == "candidate":
        configured.update(
            ALLOWED_HOSTS=[CANDIDATE_HOST, "healthcheck.railway.app"],
            CSRF_TRUSTED_ORIGINS=[CANDIDATE_ORIGIN],
            CLERK_AUTHENTICATION=ClerkVerificationConfiguration(
                jwt_key=valid_clerk_public_key,
                authorized_parties=("https://accounts.staging-next.tailtag.app",),
            ),
        )
    with override_settings(**configured):
        assert validate_configuration() is None
    reordered = {
        **configured,
        "ALLOWED_HOSTS": list(reversed(cast(list[str], configured["ALLOWED_HOSTS"]))),
    }
    with override_settings(**reordered):
        assert validate_configuration() is None


@pytest.mark.parametrize(
    ("phase", "changed"),
    (
        (
            "candidate",
            {"ALLOWED_HOSTS": ["staging.tailtag.app", "healthcheck.railway.app"]},
        ),
        ("canonical", {"ALLOWED_HOSTS": [CANDIDATE_HOST, "healthcheck.railway.app"]}),
        (
            "candidate",
            {
                "ALLOWED_HOSTS": [
                    CANDIDATE_HOST,
                    "healthcheck.railway.app",
                    "other.invalid",
                ]
            },
        ),
        ("canonical", {"ALLOWED_HOSTS": ["staging.tailtag.app"]}),
        ("candidate", {"CSRF_TRUSTED_ORIGINS": [CANONICAL_ORIGIN]}),
        ("canonical", {"CSRF_TRUSTED_ORIGINS": [CANONICAL_ORIGIN, CANDIDATE_ORIGIN]}),
        ("candidate", {"CLERK_PARTIES": ("https://accounts.staging.tailtag.app",)}),
        (
            "canonical",
            {
                "CLERK_PARTIES": (
                    "https://accounts.staging.tailtag.app",
                    "https://accounts.staging-next.tailtag.app",
                )
            },
        ),
    ),
    ids=(
        "candidate-host-swap",
        "canonical-host-swap",
        "extra-host",
        "missing-healthcheck-host",
        "candidate-csrf-swap",
        "extra-csrf",
        "candidate-clerk-swap",
        "extra-clerk-party",
    ),
)
def test_deployed_staging_readiness_denies_phase_swaps_and_extra_origins(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
    phase: str,
    changed: dict[str, object],
) -> None:
    """C-2: minimally plausible mismatches fail with one fixed readiness error."""
    _candidate_binding(monkeypatch, _manifest(tmp_path))
    configure_staging_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")
    monkeypatch.setenv("TAILTAG_STAGING_TARGET_PHASE", phase)
    configured = configured_deployed_settings(valid_clerk_public_key)
    if phase == "candidate":
        configured.update(
            ALLOWED_HOSTS=[CANDIDATE_HOST, "healthcheck.railway.app"],
            CSRF_TRUSTED_ORIGINS=[CANDIDATE_ORIGIN],
            CLERK_AUTHENTICATION=ClerkVerificationConfiguration(
                jwt_key=valid_clerk_public_key,
                authorized_parties=("https://accounts.staging-next.tailtag.app",),
            ),
        )
    changed = dict(changed)
    parties = changed.pop("CLERK_PARTIES", None)
    if parties is not None:
        configured["CLERK_AUTHENTICATION"] = ClerkVerificationConfiguration(
            jwt_key=valid_clerk_public_key,
            authorized_parties=cast(tuple[str, ...], parties),
        )
    configured.update(changed)
    with override_settings(**configured), pytest.raises(ImproperlyConfigured) as caught:
        validate_configuration()
    assert str(caught.value) == "Health configuration unavailable"
    assert SENSITIVE not in str(caught.value)


@pytest.mark.parametrize("phase", (None, "staging", "CANDIDATE", ""))
def test_deployed_staging_readiness_rejects_missing_or_unknown_phase(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    valid_clerk_public_key: str,
    phase: str | None,
) -> None:
    """C-2: deployed Staging has no implicit phase default or fuzzy selector."""
    _candidate_binding(monkeypatch, _manifest(tmp_path))
    configure_staging_identity(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "SETTINGS_MODULE", "config.settings.production")
    if phase is None:
        monkeypatch.delenv("TAILTAG_STAGING_TARGET_PHASE", raising=False)
    else:
        monkeypatch.setenv("TAILTAG_STAGING_TARGET_PHASE", phase)
    with (
        override_settings(**configured_deployed_settings(valid_clerk_public_key)),
        pytest.raises(ImproperlyConfigured) as caught,
    ):
        validate_configuration()
    assert str(caught.value) == "Health configuration unavailable"


def test_development_origin_requires_private_selector_and_code_owned_host_pin(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """D-1: only the full replacement selector plus exact hostname yields HTTPS."""
    path = _development_manifest(tmp_path)
    _development_binding(monkeypatch, path)
    before = path.read_bytes()

    assert replacement_target_binding.load_development_candidate_origin() == (
        DEVELOPMENT_ORIGIN
    )
    assert path.read_bytes() == before

    document = json.loads(path.read_text())
    document["rebuild_development_environment_id"] = STAGING
    document["expected_development_candidate_digest"] = _development_digest(
        DEVELOPMENT_HOST
    )
    path.write_text(json.dumps(document))
    _assert_binding_denied(replacement_target_binding.load_development_candidate_origin)


def test_development_host_fingerprint_uses_independent_reviewed_framing() -> None:
    """D-1: Development hostname commitment has its own exact namespace."""
    assert replacement_target_binding.fingerprint_development_candidate_hostname(
        DEVELOPMENT_HOST
    ) == _development_digest(DEVELOPMENT_HOST)
    assert _development_digest(DEVELOPMENT_HOST) != _candidate_digest(DEVELOPMENT_HOST)


@pytest.mark.parametrize(
    "hostname",
    (
        None,
        "",
        OTHER_HOST,
        "http://synthetic-development-api.up.railway.app",
        "synthetic-development-api.up.railway.app:443",
        "synthetic-development-api.up.railway.app/path",
        "SYNTHETIC-development-api.up.railway.app",
        " synthetic-development-api.up.railway.app",
        "synthetic-development-api.up.railway.app.",
        "localhost",
    ),
)
def test_development_origin_rejects_missing_changed_or_malformed_hostname(
    monkeypatch: MonkeyPatch, tmp_path: Path, hostname: object
) -> None:
    """D-1: unsafe or changed private domain never selects a public target."""
    path = _development_manifest(tmp_path, hostname=hostname)
    _development_binding(monkeypatch, path)
    _assert_binding_denied(replacement_target_binding.load_development_candidate_origin)


def test_development_origin_rejects_unsafe_or_ambiguous_manifest(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """D-1: file permissions and duplicate hostname keys fail closed."""
    path = _development_manifest(tmp_path)
    _development_binding(monkeypatch, path)
    path.chmod(0o644)
    _assert_binding_denied(replacement_target_binding.load_development_candidate_origin)

    path.chmod(0o600)
    document = path.read_text()
    path.write_text(
        document[:-1] + ',"rebuild_development_api_domain":"other-api.up.railway.app"}'
    )
    _assert_binding_denied(replacement_target_binding.load_development_candidate_origin)


def test_development_origin_rejects_missing_manifest_field(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """D-1: no implicit Development hostname is available to operators."""
    path = _manifest(tmp_path)
    _development_binding(monkeypatch, path)
    _assert_binding_denied(replacement_target_binding.load_development_candidate_origin)


def test_development_preflight_requires_stable_public_event_sha(
    preflight: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """D-4: accepted event SHA joins the exact pinned Development HTTP tuple."""
    _development_preflight_binding(monkeypatch, _development_manifest(tmp_path))
    calls: list[str] = []
    responses: list[object] = [
        DEVELOPMENT_IDENTITY,
        {"status": "ok"},
        DEVELOPMENT_IDENTITY,
    ]

    def fetch(url: str) -> object:
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    assert (
        preflight.validate_development_candidate_target(
            DEVELOPMENT_IDENTITY["source_sha"]
        )
        == DEVELOPMENT_IDENTITY
    )
    assert calls == [
        DEVELOPMENT_ORIGIN + "/health/identity",
        DEVELOPMENT_ORIGIN + "/health/ready",
        DEVELOPMENT_ORIGIN + "/health/identity",
    ]
    assert responses == []


def test_manual_development_preflight_checks_current_health_without_event_attribution(
    preflight: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """D-4: manual verification has no event SHA to claim as deployed."""
    _development_preflight_binding(monkeypatch, _development_manifest(tmp_path))
    responses: list[object] = [
        DEVELOPMENT_IDENTITY,
        {"status": "ok"},
        DEVELOPMENT_IDENTITY,
    ]

    def fetch(_: str) -> object:
        return responses.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    assert preflight.validate_development_candidate_target(None) == (
        DEVELOPMENT_IDENTITY
    )
    assert responses == []


@pytest.mark.parametrize(
    "configured_url",
    (
        None,
        "",
        "http://synthetic-development-api.up.railway.app",
        DEVELOPMENT_ORIGIN + "/",
        DEVELOPMENT_ORIGIN + ":443",
        DEVELOPMENT_ORIGIN + "/path",
        DEVELOPMENT_ORIGIN + "?environmentId=other",
        DEVELOPMENT_ORIGIN + "#fragment",
        "https://user@synthetic-development-api.up.railway.app",
        "https://other-api.up.railway.app",
    ),
)
def test_development_preflight_rejects_unpinned_action_url_before_transport(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    configured_url: str | None,
) -> None:
    """D-4: the Actions variable can select only the reviewed HTTPS origin."""
    _development_preflight_binding(monkeypatch, _development_manifest(tmp_path))
    if configured_url is None:
        monkeypatch.delenv("TAILTAG_DEVELOPMENT_API_BASE_URL")
    else:
        monkeypatch.setenv("TAILTAG_DEVELOPMENT_API_BASE_URL", configured_url)
    calls: list[str] = []

    def fetch(url: str) -> None:
        calls.append(url)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)

    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_development_candidate_target(
            DEVELOPMENT_IDENTITY["source_sha"]
        )
    assert calls == []


@pytest.mark.parametrize(
    "responses",
    (
        [{**DEVELOPMENT_IDENTITY, "source_sha": "b" * 40}],
        [{**DEVELOPMENT_IDENTITY, "environment": "staging"}],
        [{**DEVELOPMENT_IDENTITY, "deployment_id": None}],
        [DEVELOPMENT_IDENTITY, {"status": "unavailable"}],
        [
            DEVELOPMENT_IDENTITY,
            {"status": "ok"},
            {**DEVELOPMENT_IDENTITY, "source_sha": "b" * 40},
        ],
    ),
    ids=(
        "event-sha-mismatch",
        "wrong-environment",
        "missing-deployment",
        "not-ready",
        "identity-drift",
    ),
)
def test_development_preflight_rejects_unattributed_or_unstable_public_target(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    responses: list[object],
) -> None:
    """D-4: status-only health and a SHA-only match cannot establish delivery."""
    _development_preflight_binding(monkeypatch, _development_manifest(tmp_path))
    remaining = list(responses)
    calls: list[str] = []

    def fetch(url: str) -> object:
        calls.append(url)
        return remaining.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    with pytest.raises(preflight.TargetSafetyError) as caught:
        preflight.validate_development_candidate_target(
            DEVELOPMENT_IDENTITY["source_sha"]
        )
    assert SENSITIVE not in str(caught.value)
    assert len(calls) == len(responses)


def test_development_preflight_rejects_redirected_identity_response(
    preflight: ModuleType, monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    """D-4: the pinned origin cannot redirect identity reads elsewhere."""
    _development_preflight_binding(monkeypatch, _development_manifest(tmp_path))
    opener = RecordingOpener(
        Response(
            body=json.dumps(DEVELOPMENT_IDENTITY).encode(),
            url="https://other.invalid/health/identity",
        )
    )

    def build_opener(*_: object) -> RecordingOpener:
        return opener

    monkeypatch.setattr(
        preflight.urllib.request,
        "build_opener",
        build_opener,
    )

    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_development_candidate_target(
            DEVELOPMENT_IDENTITY["source_sha"]
        )
    assert len(opener.calls) == 1
    assert opener.calls[0][0].full_url == (DEVELOPMENT_ORIGIN + "/health/identity")
