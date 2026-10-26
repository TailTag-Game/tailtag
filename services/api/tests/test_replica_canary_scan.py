"""Behavioral contract for the replica canary leak scan (#357 AC18).

Only gcloud is faked: it is the Secret Manager boundary. The scan reads real
files and real gzip, zip and tar archives built in a temporary directory.
"""

from __future__ import annotations

import gzip
import io
import lzma
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import replica_canary_scan as scan

PROJECT = "fake-replica-project"
PASSWORDS = {
    "migrator": "migrator-pw-Synthetic0123456789",
    "runtime": "runtime-pw-Synthetic0123456789",
    "maintainer": "maintainer-pw-Synthetic012345678",
}
SECRETS = {
    "django-secret-key": "django-synthetic-secret-key-0123456789",
    **{
        f"{role}-database-url": (
            f"postgresql://{role}:{password}@ep-synthetic.neon.test/tailtag"
            "?sslmode=verify-full&sslrootcert=system"
        )
        for role, password in PASSWORDS.items()
    },
    "media-access-key-id": "synthetic0access0key0id0123456789",
    "media-secret-access-key": "synthetic-media-secret-access-key-0123456789",
}
ADMIN_PASSWORD = "admin-pw-Synthetic0123456789"
ADMIN_URL = (
    f"postgresql://tailtag_admin:{ADMIN_PASSWORD}@ep-synthetic.neon.test/tailtag"
)
ALL_VALUES = (*SECRETS.values(), *PASSWORDS.values(), ADMIN_PASSWORD, ADMIN_URL)


def fake_gcloud(
    commands: list[list[str]], secrets: dict[str, str] | None = None
) -> Any:
    values = SECRETS if secrets is None else secrets

    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        secret = command[command.index("--secret") + 1]
        if secret not in values:
            return subprocess.CompletedProcess(command, 1, "", f"no {secret}")
        return subprocess.CompletedProcess(command, 0, f"{values[secret]}\n", "")

    return run


def fake_which(name: str) -> str:
    return f"/fake/{name}"


def install_gcloud(
    monkeypatch: MonkeyPatch, secrets: dict[str, str] | None = None
) -> list[list[str]]:
    commands: list[list[str]] = []
    monkeypatch.setattr(scan.shutil, "which", fake_which)
    monkeypatch.setattr(scan.subprocess, "run", fake_gcloud(commands, secrets))
    return commands


def gzip_bytes(content: bytes) -> bytes:
    return gzip.compress(content)


def tar_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def leaky_surfaces(root: Path) -> dict[str, Path]:
    """One leak per surface kind, including an image layer inside a saved image."""
    logs = root / "logs"
    logs.mkdir()
    (logs / "service.log").write_text(
        f"start\nkey={SECRETS['django-secret-key']}\n", encoding="utf-8"
    )
    (logs / "job.log.gz").write_bytes(
        gzip_bytes(f"password {PASSWORDS['runtime']}".encode())
    )
    actions = root / "actions.zip"
    with zipfile.ZipFile(actions, "w") as archive:
        archive.writestr("1_release.txt", f"x {SECRETS['media-secret-access-key']} y")
    layer = gzip_bytes(
        tar_bytes({"app/settings.txt": SECRETS["maintainer-database-url"].encode()})
    )
    image = root / "image.tar"
    image.write_bytes(tar_bytes({"manifest.json": b"{}", "blobs/sha256/abc": layer}))
    clean = root / "issues.json"
    clean.write_text('{"body": "nothing secret here"}', encoding="utf-8")
    return {"logs": logs, "actions": actions, "image": image, "issues": clean}


def surface_arguments(surfaces: dict[str, Path]) -> list[str]:
    return [f"{name}={path}" for name, path in surfaces.items()]


def test_counts_exact_values_in_files_and_nested_archives_without_printing_them(
    tmp_path: Path, monkeypatch: MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """AC18: a leak in a log, a gzip, a zip or an image layer is counted by alias."""
    install_gcloud(monkeypatch)
    surfaces = leaky_surfaces(tmp_path)

    status = scan.main(
        ["--project", PROJECT, *surface_arguments(surfaces)],
        environ={"NEON_ADMIN_DATABASE_URL": ADMIN_URL},
    )

    assert status == 1
    captured = capfd.readouterr()
    lines = captured.out.splitlines()
    assert "surface logs: 2 matches" in lines
    assert "  django-secret-key: 1" in lines
    assert "  runtime-database-url: 1" in lines
    assert "surface actions: 1 matches" in lines
    assert "  media-secret-access-key: 1" in lines
    assert "surface image: 1 matches" in lines
    assert "  maintainer-database-url: 1" in lines
    assert "surface issues: 0 matches" in lines
    assert "FAIL canary scan" in captured.err
    for value in ALL_VALUES:
        assert value not in captured.out + captured.err


def test_clean_surfaces_pass_after_reading_only_the_scanned_secrets(
    tmp_path: Path, monkeypatch: MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """AC18: six replica secrets plus the optional admin URL; public or empty ones are skipped."""
    commands = install_gcloud(monkeypatch)
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")

    status = scan.main(
        ["--project", PROJECT, f"outputs={tmp_path / 'state.json'}"],
        environ={"NEON_ADMIN_DATABASE_URL": ADMIN_URL},
    )

    assert status == 0
    read = [command[command.index("--secret") + 1] for command in commands]
    assert sorted(read) == sorted(SECRETS)
    assert all(
        command[command.index("--project") + 1] == PROJECT for command in commands
    )
    captured = capfd.readouterr()
    assert "surface outputs: 0 matches" in captured.out
    assert "PASS canary scan" in captured.out


@pytest.mark.parametrize(
    ("secrets", "surface_specs", "environ"),
    (
        pytest.param(
            {**SECRETS, "django-secret-key": "short"},
            ("logs={root}",),
            {},
            id="value-too-short",
        ),
        pytest.param(
            {k: v for k, v in SECRETS.items() if k != "media-access-key-id"},
            ("logs={root}",),
            {},
            id="secret-read-fails",
        ),
        pytest.param(SECRETS, (), {}, id="no-surface"),
        pytest.param(SECRETS, ("={root}",), {}, id="unnamed-surface"),
        pytest.param(SECRETS, ("logs={root}/missing",), {}, id="missing-path"),
        pytest.param(
            SECRETS,
            ("logs={root}",),
            {"NEON_ADMIN_DATABASE_URL": "https://not-a-database-url"},
            id="admin-url-malformed",
        ),
    ),
)
def test_usage_and_secret_errors_exit_2_without_echoing_values(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    secrets: dict[str, str],
    surface_specs: tuple[str, ...],
    environ: dict[str, str],
) -> None:
    """AC18: the scan never runs on a weak needle, a failed read or a bad surface."""
    install_gcloud(monkeypatch, secrets)

    status = scan.main(
        ["--project", PROJECT, *(spec.format(root=tmp_path) for spec in surface_specs)],
        environ=environ,
    )

    assert status == 2
    captured = capfd.readouterr()
    assert "surface " not in captured.out
    for value in secrets.values():
        if value != "short":
            assert value not in captured.out + captured.err
    assert "=short" not in captured.out + captured.err


def encrypted_zip_bytes() -> bytes:
    """A zip whose member is flagged as encrypted, so it cannot be read.

    The zip writer cannot encrypt, so the encryption bit is set in the local
    and central headers after writing.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("secret.txt", b"cipher text stand-in")
    data = bytearray(buffer.getvalue())
    local = data.index(b"PK\x03\x04")
    central = data.index(b"PK\x01\x02")
    data[local + 6] |= 0x1
    data[central + 8] |= 0x1
    return bytes(data)


@pytest.mark.parametrize(
    ("name", "content"),
    (
        pytest.param(
            "layer.xz", lzma.compress(b"layer file content\n" * 64), id="xz-layer"
        ),
        pytest.param("logs.zip", encrypted_zip_bytes(), id="encrypted-zip-member"),
    ),
)
def test_a_blob_the_scan_cannot_open_exits_2_instead_of_reporting_zero(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    name: str,
    content: bytes,
) -> None:
    """AC18: a closed blob could hide a leak, so the scan does not pass."""
    install_gcloud(monkeypatch)
    (tmp_path / name).write_bytes(content)

    status = scan.main(["--project", PROJECT, f"image={tmp_path}"], environ={})

    assert status == 2
    captured = capfd.readouterr()
    assert "surface image: 0 matches" in captured.out
    assert "  not opened: 1" in captured.out
    assert "FAIL canary scan" in captured.err


def test_an_admin_password_is_found_in_its_encoded_and_decoded_forms(
    tmp_path: Path, monkeypatch: MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """AC18: a percent-encoded admin password leaks in either form."""
    install_gcloud(monkeypatch)
    encoded_url = (
        "postgresql://tailtag_admin:admin%40pw%2FSynthetic0123456789"
        "@ep-synthetic.neon.test/tailtag"
    )
    (tmp_path / "raw.log").write_text(f"url={encoded_url}\n", encoding="utf-8")
    (tmp_path / "decoded.log").write_text(
        "pw=admin@pw/Synthetic0123456789\n", encoding="utf-8"
    )

    status = scan.main(
        ["--project", PROJECT, f"logs={tmp_path}"],
        environ={"NEON_ADMIN_DATABASE_URL": encoded_url},
    )

    assert status == 1
    captured = capfd.readouterr()
    assert "  neon-admin-database-url: 2" in captured.out.splitlines()
    assert "Synthetic0123456789" not in captured.out + captured.err
