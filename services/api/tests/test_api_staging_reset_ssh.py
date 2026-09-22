"""Offline acceptance contract for the repository-owned private Staging reset."""

from __future__ import annotations

import base64
import hashlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any, Self, cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "api_staging_reset_ssh.py"
CONFIGURATION_NAMES = frozenset(
    {
        "TAILTAG_STAGING_RESET_ENABLED",
        "TAILTAG_STAGING_RESET_ID",
        "TAILTAG_STAGING_DATABASE_SYSTEM_ID",
        "TAILTAG_STAGING_DATABASE_HOST",
        "TAILTAG_STAGING_DATABASE_PORT",
        "TAILTAG_STAGING_DATABASE_NAME",
        "TAILTAG_STAGING_RESET_OWNER_CLERK_ID",
        "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID",
        "TAILTAG_STAGING_RESET_MEDIA_KEY",
    }
)
SOURCE_SHA = "c070f413eec1518459f1fef21b471642765a54e9"
DEPLOYMENT_ID = "93de11d6-714f-405a-b931-a9b567d5ec1e"
INSTANCE_ID = "46d09c1e-9c09-4f31-8b86-4ce9b667c70b"
PROJECT_ID = "85324de4-be6a-49c3-a3f9-6cac13877849"
ENVIRONMENT_ID = "5f4ab4f2-af14-4b2b-a4c3-3344d281fe5e"
SERVICE_ID = "2247da27-97df-4d5d-b1dc-d21eeb7901d9"
DATABASE_URL = (
    "postgresql://synthetic_user:synthetic_password@postgres.internal:5432/tailtag"
)
DATABASE_URL_FINGERPRINT = hashlib.sha256(DATABASE_URL.encode()).hexdigest()
SENSITIVE = "synthetic-private-ssh-diagnostic"
COUNTS = {
    "profiles": 2,
    "conventions": 1,
    "fursuits": 2,
    "enrollments": 2,
    "activations": 2,
    "catches": 0,
    "sessions": 0,
    "credentials": 0,
}

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


def identity(**overrides: str) -> dict[str, str]:
    """Return the public serving tuple that every transport boundary pins."""
    return {
        "source_sha": SOURCE_SHA,
        "deployment_id": DEPLOYMENT_ID,
        "environment": "staging",
        **overrides,
    }


def configuration(**overrides: str) -> dict[str, str]:
    """Return the nine private reset bindings, with fictitious values only."""
    return {
        "TAILTAG_STAGING_RESET_ENABLED": "true",
        "TAILTAG_STAGING_RESET_ID": "2b859e84-1d92-4a8a-a72b-d3567219288d",
        "TAILTAG_STAGING_DATABASE_SYSTEM_ID": "742391",
        "TAILTAG_STAGING_DATABASE_HOST": "postgres.internal",
        "TAILTAG_STAGING_DATABASE_PORT": "5432",
        "TAILTAG_STAGING_DATABASE_NAME": "tailtag",
        "TAILTAG_STAGING_RESET_OWNER_CLERK_ID": "user_synthetic_owner",
        "TAILTAG_STAGING_RESET_CATCHER_CLERK_ID": "user_synthetic_catcher",
        "TAILTAG_STAGING_RESET_MEDIA_KEY": "images/0123456789abcdef0123456789abcdef.png",
        **overrides,
    }


def bundle_fingerprint(manifest: Mapping[str, str]) -> str:
    """Freeze the public code-bundle fingerprint representation."""
    return hashlib.sha256(
        json.dumps(dict(manifest), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def completed(
    payload: object, *, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    """Construct one offline subprocess observation."""
    return subprocess.CompletedProcess(
        args=("offline",),
        returncode=returncode,
        stdout=payload if isinstance(payload, str) else json.dumps(payload),
        stderr=stderr,
    )


@pytest.fixture
def staging_ssh() -> Any:
    """Load the approved operator only after the implementation exists."""
    assert SCRIPT.is_file(), "scripts/api_staging_reset_ssh.py must exist"
    return cast(Any, importlib.import_module("scripts.api_staging_reset_ssh"))


def write_configuration(path: Path, values: Mapping[str, str]) -> None:
    """Create a private operator file with its required containing directory."""
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(
        "# synthetic test configuration\n\n"
        + "\n".join(f"{key}={value}" for key, value in values.items())
        + "\n"
    )
    path.chmod(0o600)


def archive_bytes(members: Mapping[str, bytes]) -> tuple[str, dict[str, str]]:
    """Build a bounded synthetic tar archive and its exact member manifest."""
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(content))
    manifest = {
        name: hashlib.sha256(content).hexdigest() for name, content in members.items()
    }
    return base64.b64encode(output.getvalue()).decode(), manifest


def archive_with_unsafe_member(kind: bytes) -> tuple[str, dict[str, str]]:
    """Construct one malformed tar that a remote bootstrap must reject pre-execution."""
    safe_name = "scripts/api_staging_reset_ssh.py"
    safe_content = synthetic_remote_executor_source()
    unsafe_name = "scripts/duplicate.py" if kind == tarfile.SYMTYPE else "../escape.py"
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        safe = tarfile.TarInfo(safe_name)
        safe.size = len(safe_content)
        archive.addfile(safe, io.BytesIO(safe_content))
        unsafe = tarfile.TarInfo(unsafe_name)
        unsafe.type = kind
        unsafe.linkname = safe_name
        unsafe.size = 0
        archive.addfile(unsafe)
    return base64.b64encode(output.getvalue()).decode(), {
        safe_name: hashlib.sha256(safe_content).hexdigest(),
        unsafe_name: "0" * 64,
    }


def archive_with_duplicate_member() -> tuple[str, dict[str, str]]:
    """Construct duplicate regular member names despite a one-name manifest."""
    name = "scripts/api_staging_reset_ssh.py"
    content = synthetic_remote_executor_source()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        for member_content in (content, b"# duplicate\n"):
            member = tarfile.TarInfo(name)
            member.size = len(member_content)
            archive.addfile(member, io.BytesIO(member_content))
    return base64.b64encode(output.getvalue()).decode(), {
        name: hashlib.sha256(content).hexdigest()
    }


def mutate_bootstrap_payload(payload: dict[str, object], mutation: str) -> None:
    """Apply one hostile private-stdin mutation without changing the test transport."""
    if mutation == "unsafe-path":
        manifest = cast(dict[str, str], payload["manifest"])
        manifest["../escape.py"] = "0" * 64
    elif mutation == "unexpected-member":
        manifest = cast(dict[str, str], payload["manifest"])
        manifest["scripts/extra.py"] = "0" * 64
    elif mutation == "missing-manifest":
        payload["manifest"] = {}
    elif mutation == "malformed-bundle":
        payload["bundle"] = "not-base64"
    else:
        raise AssertionError(f"unknown payload mutation: {mutation}")


def bootstrap_payload(
    bundle: str, manifest: Mapping[str, str], **overrides: object
) -> dict[str, object]:
    """Return the sole private stdin document accepted by the remote bootstrap."""
    return {
        "bundle": bundle,
        "manifest": dict(manifest),
        "identity": identity(),
        "database_url_fingerprint": DATABASE_URL_FINGERPRINT,
        "configuration": configuration(),
        **overrides,
    }


def synthetic_remote_executor_source(
    status: int = 0, failure_output: str | None = None
) -> bytes:
    """A copied SSH helper that proves bootstrap calls its remote executor only."""
    if failure_output is not None:
        return (
            "from pathlib import Path\n"
            "def _execute_remote(request, root):\n"
            "    if not isinstance(root, Path): raise TypeError\n"
            "    Path.cwd().joinpath('synthetic-executor-ran').write_text(str(root))\n"
            f"    return {status}, {failure_output!r}\n"
        ).encode()
    return (
        "import json\n"
        "from pathlib import Path\n"
        "def _execute_remote(request, root):\n"
        "    if not isinstance(root, Path): raise TypeError\n"
        "    Path.cwd().joinpath('synthetic-executor-ran').write_text(str(root))\n"
        f"    return {status}, json.dumps({{'identity': {{'source_sha': '"
        + SOURCE_SHA
        + "', 'deployment_id': '"
        + DEPLOYMENT_ID
        + "', 'environment': 'staging'}, 'baseline_version': 1, "
        "'counts': " + json.dumps(COUNTS, sort_keys=True) + "})\n"
    ).encode()


def interrupting_remote_executor_source() -> bytes:
    """A copied executor interruption tests bootstrap cleanup independently of reset."""
    return b"def _execute_remote(request, root):\n    raise KeyboardInterrupt\n"


def leaking_remote_executor_source() -> bytes:
    """Emit synthetic diagnostics to prove bootstrap containment of copied-code output."""
    return (
        "import sys\n"
        "def _execute_remote(request, root):\n"
        f"    print({SENSITIVE!r})\n"
        f"    print({SENSITIVE!r}, file=sys.stderr)\n"
        f"    raise RuntimeError({SENSITIVE!r})\n"
    ).encode()


def isolated_bootstrap(
    staging_ssh: ModuleType,
    payload: Mapping[str, object],
    tmp_path: Path,
    environment_overrides: Mapping[str, str] | None = None,
    bootstrap: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the real bootstrap source under an isolated local interpreter."""
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "RAILWAY_PROJECT_ID": PROJECT_ID,
        "RAILWAY_ENVIRONMENT_ID": ENVIRONMENT_ID,
        "RAILWAY_SERVICE_ID": SERVICE_ID,
        "RAILWAY_DEPLOYMENT_ID": DEPLOYMENT_ID,
        "RAILWAY_GIT_COMMIT_SHA": SOURCE_SHA,
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "DATABASE_URL": DATABASE_URL,
    }
    if environment_overrides is not None:
        environment.update(environment_overrides)
    return subprocess.run(
        [sys.executable, "-I", "-c", bootstrap or staging_ssh._BOOTSTRAP],
        input=json.dumps(payload),
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )


def assert_sanitized(*values: object) -> None:
    """Private configuration and raw diagnostics never cross test observations."""
    rendered = "\n".join(str(value) for value in values)
    assert SENSITIVE not in rendered
    assert DATABASE_URL not in rendered
    assert configuration()["TAILTAG_STAGING_RESET_ID"] not in rendered


def core_output() -> str:
    """Return the exact existing reset success record for remote executor fakes."""
    return json.dumps({"identity": identity(), "baseline_version": 1, "counts": COUNTS})


def provider_active_response(status: str = "SUCCESS") -> dict[str, object]:
    """Return the sole active Staging deployment with its sole running instance."""
    return {
        "data": {
            "serviceInstance": {
                "serviceId": SERVICE_ID,
                "environmentId": ENVIRONMENT_ID,
                "activeDeployments": [
                    {
                        "id": DEPLOYMENT_ID,
                        "projectId": PROJECT_ID,
                        "serviceId": SERVICE_ID,
                        "environmentId": ENVIRONMENT_ID,
                        "status": status,
                        "instances": [{"id": INSTANCE_ID, "status": "RUNNING"}],
                    }
                ],
            }
        }
    }


def provider_config_response(database_url: str = DATABASE_URL) -> dict[str, object]:
    """Return the fixed API selector and only its test-only database URL value."""
    return {
        "data": {
            "serviceInstance": {
                "serviceId": SERVICE_ID,
                "environmentId": ENVIRONMENT_ID,
                "variables": [{"name": "DATABASE_URL", "value": database_url}],
            }
        }
    }


def assert_denied(operation: Callable[[], object]) -> None:
    """Require a fail-closed helper outcome without selecting a new error API."""
    try:
        operation()
    except Exception:  # noqa: BLE001
        return
    pytest.fail("unsafe operator input must be denied")


def mutate_configuration(path: Path, mutation: str) -> None:
    """Apply one focused malformed-file mutation while preserving other bindings."""
    if mutation == "file-mode":
        path.chmod(0o644)
    elif mutation == "directory-mode":
        path.parent.chmod(0o755)
    elif mutation == "evaluated-value":
        write_configuration(path, configuration(TAILTAG_STAGING_RESET_ID="$(unsafe)"))
    elif mutation == "quoted-value":
        write_configuration(path, configuration(TAILTAG_STAGING_RESET_ENABLED="'true'"))
    elif mutation == "shell-separator":
        write_configuration(
            path, configuration(TAILTAG_STAGING_RESET_ENABLED="true;unsafe")
        )
    elif mutation == "whitespace-value":
        write_configuration(path, configuration(TAILTAG_STAGING_RESET_ENABLED=" true"))
    elif mutation == "unknown-key":
        path.write_text(path.read_text() + "UNKNOWN=value\n")
    elif mutation == "selector-override":
        path.write_text(path.read_text() + "RAILWAY_SERVICE_ID=unapproved-selector\n")
    elif mutation == "credential-field":
        path.write_text(path.read_text() + "DATABASE_URL=postgresql://unapproved\n")
    elif mutation == "nul-byte":
        path.write_bytes(path.read_bytes() + b"\x00")
    elif mutation == "duplicate":
        path.write_text(
            "\n".join(
                [f"{key}={value}" for key, value in configuration().items()]
                + ["TAILTAG_STAGING_RESET_ID=2b859e84-1d92-4a8a-a72b-d3567219288d"]
            )
        )
    else:
        raise AssertionError(f"unknown mutation: {mutation}")


def test_read_configuration_accepts_only_the_exact_nine_literal_assignments(
    staging_ssh: ModuleType, tmp_path: Path
) -> None:
    """SSH-2: comments and blank lines do not weaken the strict private-file grammar."""
    path = tmp_path / "operator" / "staging-reset.env"
    write_configuration(path, configuration())

    assert staging_ssh._read_configuration(path) == configuration()
    assert set(staging_ssh._read_configuration(path)) == CONFIGURATION_NAMES


@pytest.mark.parametrize(
    "mutation",
    (
        "file-mode",
        "directory-mode",
        "evaluated-value",
        "quoted-value",
        "shell-separator",
        "whitespace-value",
        "unknown-key",
        "selector-override",
        "credential-field",
        "nul-byte",
        "duplicate",
    ),
)
def test_read_configuration_fails_closed_for_unsafe_file_or_content(
    staging_ssh: Any, tmp_path: Path, mutation: str
) -> None:
    """SSH-2/SECURITY: a private configuration is never shell input or a selector seam."""
    path = tmp_path / "operator" / "staging-reset.env"
    write_configuration(path, configuration())
    mutate_configuration(path, mutation)

    assert_denied(lambda: staging_ssh._read_configuration(path))


@pytest.mark.parametrize("link_parent", (False, True), ids=("file", "directory"))
def test_read_configuration_rejects_symbolic_links(
    staging_ssh: ModuleType, tmp_path: Path, link_parent: bool
) -> None:
    """SSH-2: links cannot redirect an operator-owned configuration read."""
    target = tmp_path / "target" / "staging-reset.env"
    write_configuration(target, configuration())
    path = tmp_path / "operator" / "staging-reset.env"
    if link_parent:
        path.parent.symlink_to(target.parent, target_is_directory=True)
    else:
        path.parent.mkdir(mode=0o700)
        path.symlink_to(target)

    assert_denied(lambda: staging_ssh._read_configuration(path))


def test_build_bundle_has_only_hashed_first_party_code_members(
    staging_ssh: ModuleType,
) -> None:
    """SSH-4: every transferred member is a regular, audited production source file."""
    bundle, manifest = staging_ssh._build_bundle(REPOSITORY_ROOT)
    decoded = base64.b64decode(bundle, validate=True)

    with tarfile.open(fileobj=io.BytesIO(decoded), mode="r:") as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        assert all(member.isfile() for member in members)
        assert names == set(manifest)
        assert {
            "scripts/api_staging_reset.py",
            "scripts/api_staging_preflight.py",
            "scripts/api_staging_reset_ssh.py",
        } <= names
        assert all(
            name.startswith(("services/api/", "scripts/"))
            and "/tests/" not in name
            and "__pycache__" not in name
            and not name.endswith((".env", ".pyc"))
            for name in names
        )
        for member in members:
            source = archive.extractfile(member)
            assert source is not None
            assert hashlib.sha256(source.read()).hexdigest() == manifest[member.name]


def test_generated_bundle_initializes_all_installed_django_apps(
    staging_ssh: ModuleType, tmp_path: Path
) -> None:
    """SSH-4: an installed first-party app cannot be omitted from reset source."""
    bundle, _ = staging_ssh._build_bundle(REPOSITORY_ROOT)
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()

    with tarfile.open(
        fileobj=io.BytesIO(base64.b64decode(bundle)), mode="r:"
    ) as archive:
        for member in archive.getmembers():
            source = archive.extractfile(member)
            assert source is not None
            destination = bundle_root / member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read())

    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import os, sys; "
                "from pathlib import Path; "
                "root = Path(sys.argv[1]); "
                "sys.path[:0] = [str(root), str(root / 'services' / 'api')]; "
                "os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.base'; "
                "import django; django.setup()"
            ),
            str(bundle_root),
        ],
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr


def test_remote_bootstrap_accepts_operator_audit_package_member(
    staging_ssh: ModuleType, tmp_path: Path
) -> None:
    """SSH-4/5: bootstrap policy accepts the generated first-party package set."""
    bundle, _ = staging_ssh._build_bundle(REPOSITORY_ROOT)
    with tarfile.open(
        fileobj=io.BytesIO(base64.b64decode(bundle)), mode="r:"
    ) as archive:
        members: dict[str, bytes] = {}
        for member in archive.getmembers():
            source = archive.extractfile(member)
            assert source is not None
            members[member.name] = source.read()
    members["services/api/operator_audit/apps.py"] = (
        REPOSITORY_ROOT / "services" / "api" / "operator_audit" / "apps.py"
    ).read_bytes()
    members["scripts/api_staging_reset_ssh.py"] = synthetic_remote_executor_source()
    bootstrap_bundle, bootstrap_manifest = archive_bytes(members)

    result = isolated_bootstrap(
        staging_ssh,
        bootstrap_payload(bootstrap_bundle, bootstrap_manifest),
        tmp_path,
    )

    assert result.returncode == 0, result.stderr


def test_build_bundle_rejects_a_symlink_or_unsafe_member_source(
    staging_ssh: ModuleType, tmp_path: Path
) -> None:
    """SSH-4: a repository path cannot smuggle a link or traversal into the archive."""
    (tmp_path / "services" / "api" / "safe").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "services" / "api" / "safe" / "module.py").write_text("pass\n")
    (tmp_path / "scripts" / "api_staging_reset.py").symlink_to("../../outside.py")

    assert_denied(lambda: staging_ssh._build_bundle(tmp_path))


def test_main_denies_unknown_arguments_before_configuration_or_remote_work(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SSH-1: only the explicit reset confirmation reaches the private operator."""
    calls: list[str] = []
    monkeypatch.setattr(
        sys, "argv", ["api_staging_reset_ssh.py", f"--unsafe={SENSITIVE}"]
    )

    def read_configuration(_: Path) -> None:
        calls.append("configuration")

    def execute_remote(*_: object) -> None:
        calls.append("remote")

    monkeypatch.setattr(staging_ssh, "_read_configuration", read_configuration)
    monkeypatch.setattr(staging_ssh, "_execute_remote", execute_remote)

    assert staging_ssh.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert calls == []
    assert_sanitized(captured.err)


@pytest.mark.parametrize(
    "arguments",
    (
        ["--conf", "reset-tailtag-staging"],
        ["--confirm", "wrong"],
        ["--confirm", "reset-tailtag-staging", "--provision"],
    ),
    ids=("abbreviated-confirmation", "wrong-confirmation", "provision"),
)
def test_main_rejects_noncanonical_arguments_before_configuration_or_external_work(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    """SSH-1: argparse abbreviations and reset-adjacent operations are not accepted."""
    calls: list[str] = []
    monkeypatch.setattr(sys, "argv", ["api_staging_reset_ssh.py", *arguments])

    def read_configuration(_: Path) -> None:
        calls.append("configuration")

    def run(*_: object, **__: object) -> None:
        calls.append("run")

    monkeypatch.setattr(staging_ssh, "_read_configuration", read_configuration)
    monkeypatch.setattr(staging_ssh, "_run", run)

    assert staging_ssh.main() == 1
    captured = capsys.readouterr()
    assert calls == []
    assert captured.out == ""
    assert captured.err == "FAIL staging reset confirmation\n"


def test_main_rejects_an_unapproved_railway_identity_before_provider_or_ssh(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SSH-3: an identity mismatch stops before any provider query or SSH command."""
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        sys, "argv", ["api_staging_reset_ssh.py", "--confirm", "reset-tailtag-staging"]
    )

    def read_configuration(_: Path) -> dict[str, str]:
        return configuration()

    monkeypatch.setattr(staging_ssh, "_read_configuration", read_configuration)

    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(tuple(arguments))
        return completed({"name": "unapproved", "email": SENSITIVE})

    monkeypatch.setattr(staging_ssh, "_run", run)

    assert staging_ssh.main() == 1
    captured = capsys.readouterr()
    assert calls == [("railway", "whoami", "--json")]
    assert captured.out == ""
    assert_sanitized(captured.err)


def test_main_pins_provider_target_rechecks_account_and_sends_only_stdin_private_data(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SSH-1/3/4/7: one rechecked identity gates the exact instance and safe response."""
    bundle, manifest = archive_bytes({"scripts/api_staging_reset.py": b"pass\n"})
    calls: list[tuple[tuple[str, ...], str | None]] = []
    remote_output = json.dumps(
        {
            "identity": identity(),
            "baseline_version": 1,
            "counts": COUNTS,
            "bundle_fingerprint": bundle_fingerprint(manifest),
            "cleanup_confirmed": True,
        }
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "api_staging_reset_ssh.py",
            "--confirm",
            "reset-tailtag-staging",
            "--config",
            str(tmp_path / "fictitious-config"),
        ],
    )

    def read_configuration(_: Path) -> dict[str, str]:
        return configuration()

    def build_bundle(_: Path) -> tuple[str, dict[str, str]]:
        return bundle, manifest

    def validate_target(_: str) -> dict[str, str]:
        return identity()

    monkeypatch.setattr(staging_ssh, "_read_configuration", read_configuration)
    monkeypatch.setattr(staging_ssh, "_build_bundle", build_bundle)
    preflight = importlib.import_module("scripts.api_staging_preflight")
    monkeypatch.setattr(preflight, "validate_target", validate_target)

    def run(
        arguments: list[str], *, input: str | None = None, **_: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append((tuple(arguments), input))
        if arguments == ["railway", "whoami", "--json"]:
            return completed(
                {"name": "Finn the Panther", "email": "finn@finnthepanther.com"}
            )
        if arguments[:2] == ["railway", "api"]:
            variables = json.loads(arguments[-1])
            assert variables == {
                "serviceId": SERVICE_ID,
                "environmentId": ENVIRONMENT_ID,
            }
            if "StagingResetActive" in arguments[2]:
                return completed(provider_active_response())
            if "StagingResetConfiguration" in arguments[2]:
                return completed(provider_config_response())
        if arguments[:3] == ["railway", "variable", "list"]:
            service_id = arguments[arguments.index("--service") + 1]
            return completed(
                {
                    "RAILWAY_PROJECT_ID": PROJECT_ID,
                    "RAILWAY_ENVIRONMENT_ID": ENVIRONMENT_ID,
                    "RAILWAY_SERVICE_ID": service_id,
                    "RAILWAY_ENVIRONMENT_NAME": "staging",
                    "DATABASE_URL": DATABASE_URL,
                }
            )
        if arguments[:2] == ["railway", "ssh"]:
            return completed(remote_output)
        raise AssertionError(f"unapproved external command: {arguments}")

    monkeypatch.setattr(staging_ssh, "_run", run)

    assert staging_ssh.main() == 0
    assert [command[:2] for command, _ in calls] == [
        ("railway", "whoami"),
        ("railway", "api"),
        ("railway", "variable"),
        ("railway", "variable"),
        ("railway", "whoami"),
        ("railway", "ssh"),
    ]
    ssh_arguments, ssh_input = calls[-1]
    assert ssh_arguments == (
        "railway",
        "ssh",
        "--project",
        PROJECT_ID,
        "--service",
        SERVICE_ID,
        "--environment",
        ENVIRONMENT_ID,
        "--deployment-instance",
        INSTANCE_ID,
        "--",
        "/app/.venv/bin/python",
        "-I",
        "-c",
        staging_ssh._BOOTSTRAP,
    )
    assert ssh_input is not None
    assert json.loads(ssh_input) == bootstrap_payload(bundle, manifest)
    assert DATABASE_URL not in " ".join(ssh_arguments)
    assert configuration()["TAILTAG_STAGING_RESET_ID"] not in " ".join(ssh_arguments)
    assert json.loads(capsys.readouterr().out) == json.loads(remote_output)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("diagnostic", SENSITIVE),
        ("baseline_version", True),
        ("baseline_version", 2),
        ("counts", {**COUNTS, "catches": 1}),
        ("counts", {**COUNTS, "profiles": 3}),
    ),
    ids=(
        "extra-private-field",
        "boolean-version",
        "wrong-version",
        "catches",
        "profiles",
    ),
)
def test_main_rejects_an_ssh_response_with_private_or_extra_fields(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    """SSH-7: a clean exit status does not authorize untrusted response publication."""
    bundle, manifest = archive_bytes({"scripts/api_staging_reset.py": b"pass\n"})
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset_ssh.py", "--confirm", "reset-tailtag-staging"],
    )

    def read_configuration(_: Path) -> dict[str, str]:
        return configuration()

    def build_bundle(_: Path) -> tuple[str, dict[str, str]]:
        return bundle, manifest

    def validate_target(_: str) -> dict[str, str]:
        return identity()

    monkeypatch.setattr(staging_ssh, "_read_configuration", read_configuration)
    monkeypatch.setattr(staging_ssh, "_build_bundle", build_bundle)
    preflight = importlib.import_module("scripts.api_staging_preflight")
    monkeypatch.setattr(preflight, "validate_target", validate_target)

    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if arguments == ["railway", "whoami", "--json"]:
            return completed(
                {"name": "Finn the Panther", "email": "finn@finnthepanther.com"}
            )
        if arguments[:2] == ["railway", "api"]:
            return completed(
                provider_active_response()
                if "StagingResetActive" in arguments[2]
                else provider_config_response()
            )
        if arguments[:3] == ["railway", "variable", "list"]:
            service_id = arguments[arguments.index("--service") + 1]
            return completed(
                {
                    "RAILWAY_PROJECT_ID": PROJECT_ID,
                    "RAILWAY_ENVIRONMENT_ID": ENVIRONMENT_ID,
                    "RAILWAY_SERVICE_ID": service_id,
                    "RAILWAY_ENVIRONMENT_NAME": "staging",
                    "DATABASE_URL": DATABASE_URL,
                }
            )
        response: dict[str, object] = {
            "identity": identity(),
            "baseline_version": 1,
            "counts": COUNTS,
            "bundle_fingerprint": bundle_fingerprint(manifest),
            "cleanup_confirmed": True,
        }
        response[field] = value
        return completed(response)

    monkeypatch.setattr(staging_ssh, "_run", run)

    assert staging_ssh.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "maintenance unknown" in captured.err
    assert_sanitized(captured.err)


@pytest.mark.parametrize(
    "failure",
    ("active-deployment", "database-url", "empty-database-url", "second-identity"),
)
def test_main_denies_provider_or_recheck_mismatch_before_ssh(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    """SSH-3: unsafe provider observations or a stale final account check never start SSH."""
    bundle, manifest = archive_bytes({"scripts/api_staging_reset.py": b"pass\n"})
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset_ssh.py", "--confirm", "reset-tailtag-staging"],
    )

    def read_configuration(_: Path) -> dict[str, str]:
        return configuration()

    def build_bundle(_: Path) -> tuple[str, dict[str, str]]:
        return bundle, manifest

    def validate_target(_: str) -> dict[str, str]:
        return identity()

    monkeypatch.setattr(staging_ssh, "_read_configuration", read_configuration)
    monkeypatch.setattr(staging_ssh, "_build_bundle", build_bundle)
    preflight = importlib.import_module("scripts.api_staging_preflight")
    monkeypatch.setattr(preflight, "validate_target", validate_target)
    whoami_calls = 0

    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal whoami_calls
        calls.append(tuple(arguments))
        if arguments == ["railway", "whoami", "--json"]:
            whoami_calls += 1
            return completed(
                {"name": "wrong", "email": "finn@finnthepanther.com"}
                if failure == "second-identity" and whoami_calls == 2
                else {
                    "name": "Finn the Panther",
                    "email": "finn@finnthepanther.com",
                }
            )
        if arguments[:2] == ["railway", "api"]:
            return completed(
                provider_active_response(
                    "FAILED" if failure == "active-deployment" else "SUCCESS"
                )
            )
        if arguments[:3] == ["railway", "variable", "list"]:
            service_id = arguments[arguments.index("--service") + 1]
            return completed(
                {
                    "RAILWAY_PROJECT_ID": PROJECT_ID,
                    "RAILWAY_ENVIRONMENT_ID": ENVIRONMENT_ID,
                    "RAILWAY_SERVICE_ID": service_id,
                    "RAILWAY_ENVIRONMENT_NAME": "staging",
                    "DATABASE_URL": (
                        "postgresql://other:other@postgres.internal:5432/other"
                        if failure == "database-url" and service_id != SERVICE_ID
                        else ""
                        if failure == "empty-database-url"
                        else DATABASE_URL
                    ),
                }
            )
        raise AssertionError(f"SSH must not begin: {arguments}")

    monkeypatch.setattr(staging_ssh, "_run", run)

    assert staging_ssh.main() == 1
    assert not any(command[:2] == ("railway", "ssh") for command in calls)


def test_main_treats_local_ssh_transport_uncertainty_as_maintenance_unknown_without_leak_or_retry(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SSH-7/RELIABILITY: a post-SSH disconnect can never imply resumption."""
    calls = 0
    monkeypatch.setattr(
        sys, "argv", ["api_staging_reset_ssh.py", "--confirm", "reset-tailtag-staging"]
    )

    def read_configuration(_: Path) -> dict[str, str]:
        return configuration()

    monkeypatch.setattr(staging_ssh, "_read_configuration", read_configuration)

    def disconnect(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        raise TimeoutError(SENSITIVE)

    monkeypatch.setattr(staging_ssh, "_run", disconnect)

    assert staging_ssh.main() == 1
    captured = capsys.readouterr()
    assert calls == 1
    assert captured.out == ""
    assert "maintenance unknown" in captured.err
    assert_sanitized(captured.err)


def test_main_preserves_a_safe_remote_maintenance_retained_failure(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SSH-7: a safe existing-core failure is not relabeled after SSH cleanup."""
    bundle, manifest = archive_bytes({"scripts/api_staging_reset.py": b"pass\n"})
    monkeypatch.setattr(
        sys,
        "argv",
        ["api_staging_reset_ssh.py", "--confirm", "reset-tailtag-staging"],
    )

    def read_configuration(_: Path) -> dict[str, str]:
        return configuration()

    def build_bundle(_: Path) -> tuple[str, dict[str, str]]:
        return bundle, manifest

    def validate_target(_: str) -> dict[str, str]:
        return identity()

    monkeypatch.setattr(staging_ssh, "_read_configuration", read_configuration)
    monkeypatch.setattr(staging_ssh, "_build_bundle", build_bundle)
    preflight = importlib.import_module("scripts.api_staging_preflight")
    monkeypatch.setattr(preflight, "validate_target", validate_target)

    def run(arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if arguments == ["railway", "whoami", "--json"]:
            return completed(
                {"name": "Finn the Panther", "email": "finn@finnthepanther.com"}
            )
        if arguments[:2] == ["railway", "api"]:
            return completed(
                provider_active_response()
                if "StagingResetActive" in arguments[2]
                else provider_config_response()
            )
        if arguments[:3] == ["railway", "variable", "list"]:
            service_id = arguments[arguments.index("--service") + 1]
            return completed(
                {
                    "RAILWAY_PROJECT_ID": PROJECT_ID,
                    "RAILWAY_ENVIRONMENT_ID": ENVIRONMENT_ID,
                    "RAILWAY_SERVICE_ID": service_id,
                    "RAILWAY_ENVIRONMENT_NAME": "staging",
                    "DATABASE_URL": DATABASE_URL,
                }
            )
        if arguments[:2] == ["railway", "ssh"]:
            return completed(
                "",
                returncode=1,
                stderr="FAIL staging reset maintenance retained\n",
            )
        raise AssertionError(f"unapproved external command: {arguments}")

    monkeypatch.setattr(staging_ssh, "_run", run)

    assert staging_ssh.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "FAIL staging reset maintenance retained\n"


def test_remote_bootstrap_validates_complete_archive_before_synthetic_reset_and_cleans_up(
    staging_ssh: ModuleType, tmp_path: Path
) -> None:
    """SSH-5/6/7: a real isolated Python bootstrap validates, runs once, then removes source."""
    bundle, manifest = archive_bytes(
        {
            "scripts/api_staging_reset.py": b"# synthetic reset entry point\n",
            "scripts/api_staging_preflight.py": b"# synthetic preflight\n",
            "scripts/api_staging_reset_ssh.py": synthetic_remote_executor_source(),
        }
    )
    before = set(Path("/tmp").glob("tailtag-staging-reset-*"))

    result = isolated_bootstrap(
        staging_ssh, bootstrap_payload(bundle, manifest), tmp_path
    )

    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output == {
        "identity": identity(),
        "baseline_version": 1,
        "counts": COUNTS,
        "bundle_fingerprint": bundle_fingerprint(manifest),
        "cleanup_confirmed": True,
    }
    marker = tmp_path / "synthetic-executor-ran"
    assert marker.read_text().startswith("/tmp/tailtag-staging-reset-")
    assert not Path(marker.read_text()).exists()
    assert set(Path("/tmp").glob("tailtag-staging-reset-*")) <= before
    assert_sanitized(result.stdout, result.stderr)


@pytest.mark.parametrize(
    "payload_mutator",
    (
        "unsafe-path",
        "unexpected-member",
        "missing-manifest",
        "malformed-bundle",
    ),
    ids=("unsafe-path", "unexpected-member", "missing-manifest", "malformed-bundle"),
)
def test_remote_bootstrap_denies_malicious_or_incomplete_input_before_code_execution(
    staging_ssh: ModuleType,
    tmp_path: Path,
    payload_mutator: str,
) -> None:
    """SSH-5/SECURITY: unsafe archive input fails before an extracted module can run."""
    bundle, manifest = archive_bytes(
        {"scripts/api_staging_reset_ssh.py": synthetic_remote_executor_source()}
    )
    payload = bootstrap_payload(bundle, manifest)
    mutate_bootstrap_payload(payload, payload_mutator)
    before = set(Path("/tmp").glob("tailtag-staging-reset-*"))

    result = isolated_bootstrap(staging_ssh, payload, tmp_path)

    assert result.returncode != 0
    assert not (tmp_path / "synthetic-executor-ran").exists()
    assert set(Path("/tmp").glob("tailtag-staging-reset-*")) <= before
    assert_sanitized(result.stdout, result.stderr)


def test_remote_bootstrap_rejects_an_oversized_bundle_before_extracting(
    staging_ssh: ModuleType, tmp_path: Path
) -> None:
    """SSH-5: archive size limits are checked before a bounded temporary root is used."""
    payload = bootstrap_payload(base64.b64encode(b"x" * (9 * 1024 * 1024)).decode(), {})

    result = isolated_bootstrap(staging_ssh, payload, tmp_path)

    assert result.returncode != 0
    assert not (tmp_path / "synthetic-executor-ran").exists()
    assert_sanitized(result.stdout, result.stderr)


@pytest.mark.parametrize(
    "bundle_factory",
    (
        "symlink",
        "duplicate",
    ),
    ids=("symlink", "duplicate-regular-name"),
)
def test_remote_bootstrap_rejects_nonregular_or_duplicate_archive_members(
    staging_ssh: ModuleType,
    tmp_path: Path,
    bundle_factory: str,
) -> None:
    """SSH-5/SECURITY: manifest equality cannot mask links or duplicate member paths."""
    bundle, manifest = (
        archive_with_unsafe_member(tarfile.SYMTYPE)
        if bundle_factory == "symlink"
        else archive_with_duplicate_member()
    )
    before = set(Path("/tmp").glob("tailtag-staging-reset-*"))

    result = isolated_bootstrap(
        staging_ssh, bootstrap_payload(bundle, manifest), tmp_path
    )

    assert result.returncode != 0
    assert set(Path("/tmp").glob("tailtag-staging-reset-*")) <= before
    assert_sanitized(result.stdout, result.stderr)


def test_remote_bootstrap_rejects_a_first_party_test_namespace_member(
    staging_ssh: ModuleType, tmp_path: Path
) -> None:
    """SSH-4/5: a safe-looking package prefix cannot transfer tests as executable code."""
    bundle, manifest = archive_bytes(
        {
            "scripts/api_staging_reset_ssh.py": synthetic_remote_executor_source(),
            "services/api/accounts/tests/escape.py": b"raise RuntimeError('unsafe')\n",
        }
    )

    result = isolated_bootstrap(
        staging_ssh, bootstrap_payload(bundle, manifest), tmp_path
    )

    assert result.returncode != 0
    assert not (tmp_path / "synthetic-executor-ran").exists()
    assert_sanitized(result.stdout, result.stderr)


@pytest.mark.parametrize(
    "executor_source",
    (
        "handled-failure",
        "interruption",
        "leaking-exception",
    ),
    ids=("handled-failure", "interruption", "leaking-exception"),
)
def test_remote_bootstrap_cleans_temporary_source_after_failure_or_interruption(
    staging_ssh: ModuleType,
    tmp_path: Path,
    executor_source: str,
) -> None:
    """SSH-7/RELIABILITY: cleanup is not reserved for the successful reset path."""
    bundle, manifest = archive_bytes(
        {
            "scripts/api_staging_reset_ssh.py": (
                synthetic_remote_executor_source(
                    status=1,
                    failure_output="FAIL staging reset maintenance retained",
                )
                if executor_source == "handled-failure"
                else (
                    interrupting_remote_executor_source()
                    if executor_source == "interruption"
                    else leaking_remote_executor_source()
                )
            )
        }
    )
    before = set(Path("/tmp").glob("tailtag-staging-reset-*"))

    result = isolated_bootstrap(
        staging_ssh, bootstrap_payload(bundle, manifest), tmp_path
    )

    assert result.returncode != 0
    assert set(Path("/tmp").glob("tailtag-staging-reset-*")) <= before
    assert result.stdout == ""
    assert result.stderr == (
        "FAIL staging reset maintenance retained\n"
        if executor_source == "handled-failure"
        else "FAIL staging reset maintenance unknown\n"
    )
    assert_sanitized(result.stdout, result.stderr)


def test_bootstrap_denies_success_when_temporary_source_removal_fails(
    staging_ssh: ModuleType, tmp_path: Path
) -> None:
    """SSH-7: verified cleanup is a prerequisite for publishing the reset result."""
    bundle, manifest = archive_bytes(
        {"scripts/api_staging_reset_ssh.py": synthetic_remote_executor_source()}
    )
    bootstrap = (
        "import shutil\nshutil.rmtree = lambda path: None\n" + staging_ssh._BOOTSTRAP
    )

    result = isolated_bootstrap(
        staging_ssh,
        bootstrap_payload(bundle, manifest),
        tmp_path,
        bootstrap=bootstrap,
    )

    marker = tmp_path / "synthetic-executor-ran"
    retained_root = Path(marker.read_text())
    try:
        assert result.returncode != 0
        assert result.stdout == ""
        assert result.stderr == "FAIL staging reset maintenance unknown\n"
        assert retained_root.is_dir()
    finally:
        if retained_root.exists():
            shutil.rmtree(retained_root)


def test_execute_remote_requires_immutable_identity_runtime_match_and_exact_configuration(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SSH-5/6: copied code has no reset authority without the immutable runtime join."""
    artifact = tmp_path / "build-identity.json"
    artifact.write_text(json.dumps({"source_sha": SOURCE_SHA}))
    monkeypatch.setattr(staging_ssh, "_BUILD_IDENTITY_PATH", artifact)
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", SOURCE_SHA)
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", DEPLOYMENT_ID)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("RAILWAY_PROJECT_ID", PROJECT_ID)
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", ENVIRONMENT_ID)
    monkeypatch.setenv("RAILWAY_SERVICE_ID", SERVICE_ID)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    reset = importlib.import_module("scripts.api_staging_reset")
    preflight_results = [identity(), identity()]

    def canonical_preflight(_: str) -> dict[str, str]:
        return preflight_results.pop(0)

    def reset_main() -> int:
        reset.validate_target("https://staging.tailtag.app")
        reset.validate_target("https://staging.tailtag.app")
        print(core_output())
        return 0

    monkeypatch.setattr(reset, "validate_target", canonical_preflight)
    monkeypatch.setattr(reset, "main", reset_main)
    request = bootstrap_payload("bundle", {})

    status, output = staging_ssh._execute_remote(request, tmp_path)
    assert status == 0
    assert json.loads(output) == json.loads(core_output())

    for unsafe_request, environment in (
        (
            bootstrap_payload("bundle", {}, identity=identity(source_sha="a" * 40)),
            {},
        ),
        (bootstrap_payload("bundle", {}, configuration={"unexpected": "value"}), {}),
        (request, {"RAILWAY_DEPLOYMENT_ID": "1b6a4b35-4e94-4775-a4b9-304205c75786"}),
        (
            request,
            {"DATABASE_URL": "postgresql://other:other@postgres.internal:5432/other"},
        ),
    ):
        with monkeypatch.context() as scope:
            for key, value in environment.items():
                scope.setenv(key, value)
            assert staging_ssh._execute_remote(unsafe_request, tmp_path) == (
                1,
                "FAIL staging reset maintenance unknown",
            )

    artifact.unlink()
    assert staging_ssh._execute_remote(request, tmp_path) == (
        1,
        "FAIL staging reset maintenance unknown",
    )


def test_execute_remote_preserves_the_core_failure_when_its_second_preflight_changes(
    staging_ssh: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """SSH-6/RELIABILITY: copied transport pins both core preflights, including resume."""
    artifact = tmp_path / "build-identity.json"
    artifact.write_text(json.dumps({"source_sha": SOURCE_SHA}))
    monkeypatch.setattr(staging_ssh, "_BUILD_IDENTITY_PATH", artifact)
    for key, value in {
        "RAILWAY_GIT_COMMIT_SHA": SOURCE_SHA,
        "RAILWAY_DEPLOYMENT_ID": DEPLOYMENT_ID,
        "RAILWAY_ENVIRONMENT_NAME": "staging",
        "RAILWAY_PROJECT_ID": PROJECT_ID,
        "RAILWAY_ENVIRONMENT_ID": ENVIRONMENT_ID,
        "RAILWAY_SERVICE_ID": SERVICE_ID,
        "DATABASE_URL": DATABASE_URL,
    }.items():
        monkeypatch.setenv(key, value)
    reset = importlib.import_module("scripts.api_staging_reset")
    observed = [
        identity(),
        identity(deployment_id="1b6a4b35-4e94-4775-a4b9-304205c75786"),
    ]
    events: list[str] = []

    def canonical_preflight(_: str) -> dict[str, str]:
        return observed.pop(0)

    class Maintenance:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def quiesce(self) -> None:
            events.append("quiesce")

        def resume(self) -> None:
            events.append("resume")

    def reset_baseline(_: object) -> dict[str, int]:
        events.append("reset")
        return COUNTS

    def bootstrap() -> None:
        return None

    def load_configuration(_: object) -> object:
        return object()

    def maintenance(_: object) -> Maintenance:
        return Maintenance()

    monkeypatch.setattr(reset, "validate_target", canonical_preflight)
    monkeypatch.setattr(reset, "_bootstrap", bootstrap)
    monkeypatch.setattr(reset, "load_configuration", load_configuration)
    monkeypatch.setattr(reset, "DatabaseMaintenance", maintenance)
    monkeypatch.setattr(reset, "reset_baseline", reset_baseline)

    assert staging_ssh._execute_remote(bootstrap_payload("bundle", {}), tmp_path) == (
        1,
        "FAIL staging reset committed maintenance retained",
    )
    assert events == ["quiesce", "reset", "resume", "quiesce"]


def test_make_and_validation_matrices_include_the_ssh_operator() -> None:
    """SSH-8: static checks and CI cannot omit the new repository-owned helper."""
    completed_make = subprocess.run(
        ["make", "-n", "api-staging-reset-ssh"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed_make.returncode == 0, completed_make.stderr
    assert "api_staging_reset_ssh" in completed_make.stdout
    assert "--confirm reset-tailtag-staging" in completed_make.stdout

    makefile = (REPOSITORY_ROOT / "Makefile").read_text()
    pyproject = (REPOSITORY_ROOT / "services" / "api" / "pyproject.toml").read_text()
    relevance = (REPOSITORY_ROOT / "scripts" / "backend_ci_relevance.py").read_text()
    assert "override STAGING_RESET_SSH_SCRIPT :=" in makefile
    assert "$(STAGING_RESET_SSH_SCRIPT)" in makefile
    assert "scripts/api_staging_reset_ssh.py" in pyproject
    assert "scripts/api_staging_reset_ssh.py" in relevance
