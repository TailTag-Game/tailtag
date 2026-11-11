"""Offline acceptance tests for the finite replacement Staging candidate origin."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Final

import pytest
from pytest import MonkeyPatch

from config import replacement_target_binding
from tests.clerk_settings_contract import (
    valid_clerk_public_key as _valid_clerk_public_key,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

CANDIDATE_HOST: Final = "synthetic-api.up.railway.app"
CANDIDATE_ORIGIN: Final = f"https://{CANDIDATE_HOST}"
DEVELOPMENT_HOST: Final = "dev.tailtag.app"
DEVELOPMENT_CLERK_PORTAL_ORIGIN: Final = "https://holy-lioness-3896.accounts.dev"
DEVELOPMENT_CLERK_PORTAL_DIGEST: Final = (
    "3cde8d9faf99b1089cc040f1db5342845a83120fea890634a3ad0ec85c9c4179"
)
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


class FakeClock:
    """Controlled monotonic clock whose sleep advances time without waiting."""

    _MAX_SLEEPS: Final = 1000

    def __init__(self) -> None:
        self.now = 1000.0
        self.start = self.now
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        assert len(self.sleeps) < self._MAX_SLEEPS, "retry loop did not terminate"
        self.now += seconds

    @property
    def elapsed(self) -> float:
        return self.now - self.start


@pytest.fixture
def fake_clock(preflight: ModuleType, monkeypatch: MonkeyPatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(
        preflight,
        "time",
        SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep),
    )
    return clock


def _assert_binding_denied(operation: Callable[[], object]) -> None:
    with pytest.raises(replacement_target_binding.TargetBindingError) as caught:
        operation()
    assert str(caught.value) == "Replacement target binding unavailable"
    assert SENSITIVE not in str(caught.value)
    assert CANDIDATE_HOST not in str(caught.value)


def test_development_clerk_portal_origin_uses_exact_code_owned_pin() -> None:
    """The hosted Development Clerk party is bound to its reviewed framing."""
    assert (
        hashlib.sha256(
            f"tailtag-development-clerk-portal-v1\0{DEVELOPMENT_CLERK_PORTAL_ORIGIN}".encode()
        ).hexdigest()
        == DEVELOPMENT_CLERK_PORTAL_DIGEST
    )
    assert (
        replacement_target_binding.fingerprint_development_clerk_portal_origin(
            DEVELOPMENT_CLERK_PORTAL_ORIGIN
        )
        == DEVELOPMENT_CLERK_PORTAL_DIGEST
    )
    assert (
        replacement_target_binding.pinned_development_clerk_portal_origin(
            DEVELOPMENT_CLERK_PORTAL_ORIGIN
        )
        == DEVELOPMENT_CLERK_PORTAL_ORIGIN
    )


@pytest.mark.parametrize(
    "origin",
    (
        "https://other.accounts.dev",
        "http://holy-lioness-3896.accounts.dev",
        "https://holy-lioness-3896.accounts.dev:443",
        "https://holy-lioness-3896.accounts.dev/",
    ),
    ids=("other-portal", "insecure-scheme", "explicit-port", "trailing-slash"),
)
def test_development_clerk_portal_pin_rejects_alternate_origins(origin: str) -> None:
    """The code-owned pin accepts only the exact hosted HTTPS origin."""
    _assert_binding_denied(
        lambda: replacement_target_binding.pinned_development_clerk_portal_origin(
            origin
        )
    )


_TRANSPORT_FAILURE: Final = object()
_FETCH_LATENCY_SECONDS: Final = 1.5


RENDER_DEVELOPMENT_ORIGIN: Final = "https://tailtag-api-development.onrender.com"
RENDER_DEVELOPMENT_IDENTITY: Final = {**DEVELOPMENT_IDENTITY, "deployment_id": None}


@pytest.mark.parametrize(
    "expected_sha", (None, RENDER_DEVELOPMENT_IDENTITY["source_sha"])
)
def test_render_development_preflight_accepts_null_deployment_on_pinned_host(
    preflight: ModuleType, monkeypatch: MonkeyPatch, expected_sha: str | None
) -> None:
    """#408 AC18: the pinned Render host reports no runtime deploy ID."""
    monkeypatch.setenv("TAILTAG_DEVELOPMENT_API_BASE_URL", RENDER_DEVELOPMENT_ORIGIN)
    calls: list[str] = []
    responses: list[object] = [
        RENDER_DEVELOPMENT_IDENTITY,
        {"status": "ok"},
        RENDER_DEVELOPMENT_IDENTITY,
    ]

    def fetch(url: str) -> object:
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    assert (
        preflight.validate_development_candidate_target(expected_sha)
        == RENDER_DEVELOPMENT_IDENTITY
    )
    assert calls == [
        RENDER_DEVELOPMENT_ORIGIN + "/health/identity",
        RENDER_DEVELOPMENT_ORIGIN + "/health/ready",
        RENDER_DEVELOPMENT_ORIGIN + "/health/identity",
    ]


def test_render_development_preflight_waits_through_a_full_render_deploy(
    preflight: ModuleType, monkeypatch: MonkeyPatch, fake_clock: FakeClock
) -> None:
    """#408 D4: a CI-started deploy builds and migrates before the SHA serves."""
    monkeypatch.setenv("TAILTAG_DEVELOPMENT_API_BASE_URL", RENDER_DEVELOPMENT_ORIGIN)
    old_identity = {**RENDER_DEVELOPMENT_IDENTITY, "source_sha": "b" * 40}
    elapsed_before_new_sha = 10 * 60

    def fetch(url: str) -> object:
        if url.endswith("/health/ready"):
            return {"status": "ok"}
        if fake_clock.elapsed < elapsed_before_new_sha:
            return old_identity
        return RENDER_DEVELOPMENT_IDENTITY

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    assert (
        preflight.validate_development_candidate_target(
            RENDER_DEVELOPMENT_IDENTITY["source_sha"]
        )
        == RENDER_DEVELOPMENT_IDENTITY
    )
    assert fake_clock.elapsed >= elapsed_before_new_sha
    assert fake_clock.elapsed < preflight._RENDER_DEPLOY_DEADLINE_SECONDS


# staging.tailtag.app serves Virginia Staging since the #452 cutover.
RENDER_STAGING_ORIGIN: Final = "https://staging.tailtag.app"
RENDER_STAGING_HOST_ORIGIN: Final = "https://tailtag-api-stg.onrender.com"
RENDER_STAGING_IDENTITY: Final = {**IDENTITY, "deployment_id": None}


def test_render_staging_cli_checks_the_current_public_origin(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """#409 AC5/AC13: the Render Staging host reports no runtime deploy ID."""
    calls: list[str] = []
    responses: list[object] = [
        RENDER_STAGING_IDENTITY,
        {"status": "ok"},
        RENDER_STAGING_IDENTITY,
    ]

    def fetch(url: str) -> object:
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    monkeypatch.setattr(sys, "argv", ["api_staging_preflight.py", "--render-staging"])

    assert preflight.main() == 0
    assert json.loads(capsys.readouterr().out) == RENDER_STAGING_IDENTITY
    assert calls == [
        RENDER_STAGING_ORIGIN + "/health/identity",
        RENDER_STAGING_ORIGIN + "/health/ready",
        RENDER_STAGING_ORIGIN + "/health/identity",
    ]


@pytest.mark.parametrize(
    ("identity", "expected_sha"),
    (
        (IDENTITY, None),
        ({**RENDER_STAGING_IDENTITY, "environment": "development"}, None),
        (RENDER_STAGING_IDENTITY, "b" * 40),
    ),
    ids=("railway-deploy-id", "development-identity", "other-sha"),
)
def test_render_staging_preflight_rejects_identities_outside_its_target(
    preflight: ModuleType,
    monkeypatch: MonkeyPatch,
    identity: dict[str, object],
    expected_sha: str | None,
) -> None:
    """#409 AC8: only a null-ID Staging identity of the expected SHA passes."""
    responses: list[object] = [identity, {"status": "ok"}, identity]

    def fetch(_: str) -> object:
        return responses.pop(0)

    monkeypatch.setattr(preflight, "_fetch_json", fetch)
    with pytest.raises(preflight.TargetSafetyError):
        preflight.validate_render_staging_target(expected_sha)


def test_render_staging_origin_follows_the_cutover_phase(
    preflight: ModuleType, monkeypatch: MonkeyPatch
) -> None:
    """#409 AC4/AC13, #452 AC17: one constant moves the public origin."""
    assert preflight.render_staging_origin() == RENDER_STAGING_ORIGIN
    monkeypatch.setattr(preflight, "_RENDER_STAGING_PHASE", "candidate")
    assert preflight.render_staging_origin() == RENDER_STAGING_HOST_ORIGIN
