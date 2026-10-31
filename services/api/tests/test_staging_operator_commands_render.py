"""The five #243 operator commands accept only Render Staging on Render (#410 AC9)."""

from __future__ import annotations

import getpass
import importlib
import sys
from collections.abc import Callable
from io import StringIO
from typing import NoReturn, cast

import pytest
from django.core.management import CommandError, call_command

from accounts.models import User
from tests import (
    test_staging_emergency_operator as emergency,
)
from tests import (
    test_staging_managed_operator_recovery as recovery,
)
from tests import (
    test_staging_validation_operator as lifecycle,
)

STAGING_SERVICE = "srv-stagingops0"
DEVELOPMENT_SERVICE = "srv-developops0"
SOURCE_SHA = "856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a"
RENDER_IDENTITY: dict[str, str | None] = {
    "environment": "staging",
    "source_sha": SOURCE_SHA,
    "deployment_id": None,
}


@pytest.fixture
def render_runtime(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Pin fictitious Render services, then select the runtime one test needs."""
    from config import build_identity
    from config import replacement_target_binding as binding

    monkeypatch.setattr(
        binding,
        "_EXPECTED_RENDER_DIGESTS",
        {
            "development": binding.fingerprint_render_service(
                "development", DEVELOPMENT_SERVICE
            ),
            "staging": binding.fingerprint_render_service("staging", STAGING_SERVICE),
        },
    )
    monkeypatch.setattr(build_identity, "get_identity", lambda: dict(RENDER_IDENTITY))

    def select(target: str) -> None:
        for name in (
            "RAILWAY_ENVIRONMENT_NAME",
            "RAILWAY_SERVICE_NAME",
            "RAILWAY_DEPLOYMENT_ID",
        ):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("RENDER", "true")
        monkeypatch.setenv(
            "RENDER_SERVICE_ID",
            DEVELOPMENT_SERVICE if target == "render-development" else STAGING_SERVICE,
        )
        if target == "mixed":
            monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")

    select("render-staging")
    return select


def run_guarded(
    monkeypatch: pytest.MonkeyPatch,
    module: str,
    *,
    confirmation: str,
    hidden: tuple[str, ...],
    expected_identity: object = RENDER_IDENTITY,
) -> StringIO:
    """Run a replace or rotate command as the Render SSH entry point will."""
    terminal = recovery.Tty()
    answers = iter(hidden)
    monkeypatch.setattr(sys, "stdin", terminal)
    monkeypatch.setattr(sys, "stdout", terminal)
    monkeypatch.setattr(sys, "stderr", recovery.Tty())
    monkeypatch.setattr("builtins.input", lambda _prompt="": confirmation)

    def read_hidden(_prompt: str = "", **_: object) -> str:
        return next(answers)

    monkeypatch.setattr(getpass, "getpass", read_hidden)
    command = importlib.import_module(f"accounts.management.commands.{module}")
    command.Command().execute(
        expected_identity=expected_identity,
        force_color=False,
        no_color=False,
        skip_checks=True,
        stdout=terminal,
        stderr=recovery.Tty(),
    )
    return terminal


@pytest.mark.django_db
@pytest.mark.parametrize("phrase", ["render", "railway"])
def test_lifecycle_provision_on_render_staging_needs_the_render_phrase(
    monkeypatch: pytest.MonkeyPatch, render_runtime: object, phrase: str
) -> None:
    """The Railway phrase cannot confirm a Render action, so a mixup fails closed."""
    confirmation = (
        "provision Render Staging validation operator"
        if phrase == "render"
        else lifecycle.PROVISION_CONFIRMATION
    )
    secrets = (
        lifecycle.OPERATOR_IDENTIFIER,
        lifecycle.INITIAL_PASSWORD,
        lifecycle.INITIAL_PASSWORD,
    )

    def provision() -> None:
        lifecycle.invoke_command(
            monkeypatch,
            "provision",
            confirmation=confirmation,
            hidden_inputs=secrets if phrase == "render" else (),
            environment=None,
            service=None,
        )

    if phrase == "railway":
        with pytest.raises(CommandError, match="Confirmation failed"):
            provision()
        assert not User.objects.filter(
            clerk_user_id=lifecycle.OPERATOR_IDENTIFIER
        ).exists()
        return
    provision()
    lifecycle.assert_exact_active_limited_role(
        User.objects.get(clerk_user_id=lifecycle.OPERATOR_IDENTIFIER),
        lifecycle.INITIAL_PASSWORD,
    )


@pytest.mark.django_db
def test_emergency_create_and_decommission_use_render_text_on_render_staging(
    monkeypatch: pytest.MonkeyPatch, render_runtime: object
) -> None:
    """Both emergency commands bind the #204 sentinel and name Render Staging."""
    emergency._install_registry()  # pyright: ignore[reportPrivateUsage]

    emergency._invoke(  # pyright: ignore[reportPrivateUsage]
        monkeypatch, confirmation="bootstrap Render Staging emergency operator"
    )
    actor = User.objects.get(clerk_user_id=emergency.IDENTIFIER)
    assert cast(bool, actor.is_superuser) is True  # pyright: ignore[reportUnknownMemberType]

    _, _, prompts = emergency._invoke_decommission(  # pyright: ignore[reportPrivateUsage]
        monkeypatch, confirmation="Y"
    )
    actor.refresh_from_db()
    assert prompts == ["Decommission the Render Staging emergency operator? [Y/N]: "]
    assert cast(bool, actor.is_superuser) is False  # pyright: ignore[reportUnknownMemberType]
    assert not actor.has_usable_password()


@pytest.mark.django_db
def test_managed_replace_and_rotate_accept_a_render_identity_with_no_deploy_id(
    monkeypatch: pytest.MonkeyPatch, render_runtime: object
) -> None:
    """Render has no runtime deploy ID, so the expected identity holds None."""
    recovery.seed_roles()

    replaced = run_guarded(
        monkeypatch,
        "replace_staging_managed_operator",
        confirmation="replace Render Staging managed operator",
        hidden=(recovery.NEW_IDENTIFIER, recovery.NEW_PASSWORD, recovery.NEW_PASSWORD),
    )
    rotated = run_guarded(
        monkeypatch,
        "rotate_staging_managed_password",
        confirmation="rotate Render Staging managed operator password",
        hidden=(recovery.OLD_PASSWORD, recovery.OLD_PASSWORD),
    )

    assert replaced.getvalue().count("POSTCONDITION_PASS") == 1
    assert rotated.getvalue().count("POSTCONDITION_PASS") == 1
    operator = User.objects.get(clerk_user_id=recovery.NEW_IDENTIFIER)
    assert operator.check_password(recovery.OLD_PASSWORD)


@pytest.mark.django_db
def test_render_refuses_an_expected_identity_with_a_railway_deploy_id(
    monkeypatch: pytest.MonkeyPatch, render_runtime: object
) -> None:
    """Rotate inherits this check from replace, so one command proves it."""
    recovery.seed_roles()

    with pytest.raises(CommandError, match="unavailable for the current target"):
        run_guarded(
            monkeypatch,
            "replace_staging_managed_operator",
            confirmation="",
            hidden=(),
            expected_identity={
                **RENDER_IDENTITY,
                "deployment_id": recovery.DEPLOYMENT_ID,
            },
        )


def _forbidden_prompt(_prompt: str = "", **_: object) -> NoReturn:
    raise AssertionError("a refused target must not prompt")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("command", "target"),
    [
        # Each command must call the guard. One mixed runtime proves its rule.
        *(
            (command, "render-development")
            for command in (
                "lifecycle",
                "emergency-create",
                "emergency-decommission",
                "replace_staging_managed_operator",
                "rotate_staging_managed_password",
            )
        ),
        ("lifecycle", "mixed"),
    ],
)
def test_every_command_refuses_other_render_targets_before_any_prompt(
    monkeypatch: pytest.MonkeyPatch,
    render_runtime: Callable[[str], None],
    target: str,
    command: str,
) -> None:
    """Only the pinned Render Staging service passes, so Development fails closed."""
    render_runtime(target)
    monkeypatch.setattr("builtins.input", _forbidden_prompt)
    monkeypatch.setattr(getpass, "getpass", _forbidden_prompt)
    terminal = recovery.Tty()
    monkeypatch.setattr(sys, "stdin", terminal)
    monkeypatch.setattr(sys, "stdout", terminal)

    with pytest.raises(CommandError, match="unavailable for the current target"):
        if command == "lifecycle":
            call_command(lifecycle.COMMAND_NAME, "provision", stdout=terminal)
        elif command == "emergency-create":
            call_command("bootstrap_staging_emergency_operator", stdout=terminal)
        elif command == "emergency-decommission":
            call_command("decommission_staging_emergency_operator", stdout=terminal)
        else:
            run_guarded(monkeypatch, command, confirmation="", hidden=())
