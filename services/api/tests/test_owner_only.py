"""Behavioral contract for the owner-only file helper (issue #315, slice 3).

One table per concern runs on every OS, with each platform's own setup:
POSIX uses uid and mode bits, Windows uses owner SIDs and access lists.
Spec references are to docs/specs/2026-10-15-windows-owner-only-files-and-process-trees.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pytest

from config import owner_only
from config.owner_only import OwnerOnlyError
from tests import windows_acl_support as acl

WIN: Final = sys.platform == "win32"
MAX: Final = 1024
CONTENT: Final = b"synthetic private content\n"
# FILE_ALL_ACCESS, or GENERIC_ALL stored unmapped.
FULL_CONTROL: Final = {"0x1f01ff", "0x10000000"}

windows_only = pytest.mark.skipif(
    not WIN, reason="Windows access lists and reparse points"
)
posix_only = pytest.mark.skipif(WIN, reason="POSIX uid and mode bits")


def _symlink(link: Path, target: Path, *, directory: bool) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except OSError:
        if WIN:
            pytest.skip("creating symlinks needs an elevated Windows account")
        raise


def _private_dir(path: Path) -> None:
    path.mkdir()
    if WIN:
        acl.make_owner_only(path, container=True)
    else:
        path.chmod(0o700)


def _private_file(path: Path, data: bytes = CONTENT) -> None:
    path.write_bytes(data)
    if WIN:
        acl.make_owner_only(path)
    else:
        path.chmod(0o600)


def _documented_icacls_recipe(folder: Path) -> None:
    """The staging.md operator recipe: reset, set the owner, drop inheritance, grant."""
    sid = acl.token_user_sid()
    grants = [f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"]
    for command in (
        ["icacls", str(folder), "/reset"],
        ["icacls", str(folder), "/setowner", f"*{sid}"],
        ["icacls", str(folder), "/inheritance:r", "/grant:r", *grants],
    ):
        subprocess.run(command, check=True, capture_output=True)


# Each builder receives (parent, file, root, monkeypatch) for a valid private
# parent/file pair and returns the path to open.
Builder = Callable[[Path, Path, Path, pytest.MonkeyPatch], Path]


def _oversized(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
    file.write_bytes(b"x" * (MAX + 1))
    return file


def _directory_as_file(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    file.unlink()
    file.mkdir()
    # Owner and access list/mode are valid, so only the type check can refuse it.
    if WIN:
        acl.make_owner_only(file, container=True)
    else:
        file.chmod(0o600)
    return file


def _missing(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
    file.unlink()
    return file


def _symlink_file(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
    real = parent / "real.json"
    _private_file(real)
    file.unlink()
    _symlink(file, real, directory=False)
    return file


def _symlink_parent(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    link = root / "link"
    _symlink(link, parent, directory=True)
    return link / file.name


def _junction_file(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    target = root / "junction-target"
    _private_dir(target)
    file.unlink()
    acl.make_junction(file, target)
    return file


def _junction_parent(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    link = root / "junction"
    acl.make_junction(link, parent)
    return link / file.name


def _file_broad(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
    if WIN:
        acl.make_owner_only(file, extra_aces="(A;;FR;;;BU)")
    else:
        file.chmod(0o644)
    return file


def _parent_broad(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
    if WIN:
        acl.make_owner_only(parent, container=True, extra_aces="(A;;FR;;;BU)")
    else:
        parent.chmod(0o755)
    return file


def _file_stricter_than_required(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    file.chmod(0o400)
    return file


def _parent_stricter_than_required(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    parent.chmod(0o500)
    return file


def _wrong_owner(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
    real_uid = os.getuid()
    mp.setattr(os, "getuid", lambda: real_uid + 1)
    return file


def _owner_admins(target: str) -> Builder:
    def build(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
        item = parent if target == "parent" else file
        try:
            acl.make_owner_only(
                item, container=target == "parent", owner=acl.ADMINISTRATORS_SID
            )
        except OSError:
            pytest.skip("this account cannot assign an Administrators owner")
        return file

    return build


def _inherit_only(sid: str) -> Builder:
    def build(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
        acl.make_owner_only(parent, container=True, extra_aces=f"(A;OICIIO;FR;;;{sid})")
        return file

    return build


def _file_with(extra: str) -> Builder:
    def build(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
        acl.make_owner_only(file, extra_aces=extra)
        return file

    return build


def _null_dacl(target: str) -> Builder:
    def build(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
        item = parent if target == "parent" else file
        acl.apply_security(item, f"O:{acl.token_user_sid()}D:NO_ACCESS_CONTROL")
        return file

    return build


# (id, builder, applies to). S3-3: every helper failure is an OwnerOnlyError.
REFUSED: Final[tuple[tuple[str, Builder, str], ...]] = (
    ("oversized", _oversized, "all"),
    ("directory-where-file-expected", _directory_as_file, "all"),
    ("missing-file", _missing, "all"),
    ("symlink-file", _symlink_file, "all"),
    ("symlink-parent", _symlink_parent, "all"),
    ("file-readable-by-others", _file_broad, "all"),
    ("parent-open-to-others", _parent_broad, "all"),
    ("file-mode-0o400", _file_stricter_than_required, "posix"),
    ("parent-mode-0o500", _parent_stricter_than_required, "posix"),
    ("wrong-owner", _wrong_owner, "posix"),
    ("junction-file", _junction_file, "windows"),
    ("junction-parent", _junction_parent, "windows"),
    ("owner-is-administrators-file", _owner_admins("file"), "windows"),
    ("owner-is-administrators-parent", _owner_admins("parent"), "windows"),
    ("parent-inherit-only-users", _inherit_only("BU"), "windows"),
    ("parent-creator-owner-inherit-only", _inherit_only("CO"), "windows"),
    ("file-object-entry", _file_with("(OA;;GA;;;WD)"), "windows"),
    (
        "file-callback-entry",
        _file_with("(XA;;FA;;;WD;(Member_of {SID(WD)}))"),
        "windows",
    ),
    ("file-null-dacl", _null_dacl("file"), "windows"),
    ("parent-null-dacl", _null_dacl("parent"), "windows"),
)


def _params(
    rows: tuple[tuple[str, Builder, str], ...],
) -> list[Any]:
    marks = {"all": [], "posix": [posix_only], "windows": [windows_only]}
    return [
        pytest.param(name, build, id=name, marks=marks[scope])
        for name, build, scope in rows
    ]


def _base(root: Path) -> tuple[Path, Path]:
    parent = root / "private"
    _private_dir(parent)
    file = parent / "manifest.json"
    _private_file(file)
    return parent, file


@pytest.mark.parametrize(("name", "build"), _params(REFUSED))
def test_open_refuses_anything_that_is_not_a_private_regular_file(
    name: str,
    build: Builder,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3-1/S3-3 and the spec's refusal tables, POSIX and Windows.

    Catches: a missing check on the parent or the file (type, reparse point,
    owner, broader allow entries including inherit-only, unsupported entry
    types, NULL DACL), a size limit that is not enforced, an exact-mode rule
    loosened to "no group/other bits" (G3), and any ctypes or OS failure
    escaping as something other than the one refusal type.
    """
    parent, file = _base(tmp_path)
    path = build(parent, file, tmp_path, monkeypatch)

    with pytest.raises(OwnerOnlyError) as caught:
        owner_only.open_owner_only_file(path, max_bytes=MAX)
    assert str(tmp_path) not in str(caught.value), "refusal must carry no detail"


def _accept_plain(parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch) -> Path:
    return file


def _accept_exactly_max(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    file.write_bytes(b"x" * MAX)
    return file


def _accept_deny_entry(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    acl.make_owner_only(file, leading_aces="(D;;FW;;;BG)")
    return file


def _accept_inherited_entries(
    parent: Path, file: Path, root: Path, mp: pytest.MonkeyPatch
) -> Path:
    """D6: a file whose only entries were inherited from a verified folder."""
    folder = root / "inherited"
    folder.mkdir()
    # A reused folder may already carry an explicit grant to another account;
    # the recipe must remove it, not just add the three allowed entries.
    subprocess.run(
        ["icacls", str(folder), "/grant", "*S-1-5-32-545:(OI)(CI)R"],
        check=True,
        capture_output=True,
    )
    _documented_icacls_recipe(folder)
    inherited = folder / "manifest.json"
    inherited.write_bytes(CONTENT)
    subprocess.run(
        ["icacls", str(inherited), "/setowner", f"*{acl.token_user_sid()}"],
        check=True,
        capture_output=True,
    )
    access = acl.read_access(inherited)
    assert not access.protected, "fixture must really rely on inherited entries"
    return inherited


ACCEPTED: Final[tuple[tuple[str, Builder, str], ...]] = (
    ("owner-only", _accept_plain, "all"),
    ("exactly-max-bytes", _accept_exactly_max, "all"),
    ("extra-basic-deny-entry", _accept_deny_entry, "windows"),
    ("inherited-entries-via-documented-recipe", _accept_inherited_entries, "windows"),
)


@pytest.mark.parametrize(
    ("name", "build"),
    [
        pytest.param(
            name,
            build,
            id=name,
            marks=[] if scope == "all" else [windows_only],
        )
        for name, build, scope in ACCEPTED
    ],
)
def test_open_returns_the_bytes_of_a_checked_private_file(
    name: str, build: Builder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S3-1, D6, and the accepted list: valid objects are readable as bytes.

    Catches: over-refusal (the size limit is inclusive; deny entries and
    inherited entries from the documented operator recipe must pass), and a
    helper that returns text or an unreadable handle, since callers decode
    strictly themselves.
    """
    parent, file = _base(tmp_path)
    path = build(parent, file, tmp_path, monkeypatch)

    with owner_only.open_owner_only_file(path, max_bytes=MAX) as stream:
        data = stream.read()

    assert isinstance(data, bytes)
    assert data == path.read_bytes()


def _existing_file(root: Path) -> Path:
    victim = root / "victim.txt"
    victim.write_bytes(b"original")
    return victim


def _existing_symlink(root: Path) -> Path:
    victim = _existing_file(root)
    link = root / "link"
    _symlink(link, victim, directory=False)
    return link


def _dangling_symlink(root: Path) -> Path:
    link = root / "dangling"
    _symlink(link, root / "nowhere", directory=False)
    return link


def _dangling_junction(root: Path) -> Path:
    target = root / "gone"
    target.mkdir()
    link = root / "dangling-junction"
    acl.make_junction(link, target)
    target.rmdir()
    return link


EXISTING_NAMES: Final = (
    pytest.param(_existing_file, id="existing-file"),
    pytest.param(_existing_symlink, id="existing-symlink"),
    pytest.param(_dangling_symlink, id="dangling-symlink"),
    pytest.param(_dangling_junction, id="dangling-junction", marks=windows_only),
)


@pytest.mark.parametrize("make_name", EXISTING_NAMES)
def test_create_private_file_never_reuses_or_follows_an_existing_name(
    make_name: Callable[[Path], Path], tmp_path: Path
) -> None:
    """S3-2: creation is exclusive and does not follow links.

    Catches: CREATE_NEW without FILE_FLAG_OPEN_REPARSE_POINT (or O_EXCL without
    O_NOFOLLOW), which would write through a dangling link to an attacker-chosen
    place or overwrite an existing file.
    """
    name = make_name(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}

    with pytest.raises(OwnerOnlyError):
        owner_only.create_private_file(name)

    assert not (tmp_path / "nowhere").exists()
    assert not (tmp_path / "gone").exists()
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    assert after == before


def test_create_private_file_returns_a_writable_descriptor_with_private_access(
    tmp_path: Path,
) -> None:
    """S3-2, G3: new files are private even in a folder that grants others access.

    On Windows the folder grants Authenticated Users inheritable full control
    (the real default under a drive root), so a file that merely inherited its
    folder's list would be readable. Catches: DACL not protected, an extra or
    missing entry, owner left as the token's default (Administrators when
    elevated), and on POSIX a mode other than 0o600.
    """
    folder = tmp_path / "shared"
    folder.mkdir()
    if WIN:
        acl.apply_security(
            folder,
            f"O:{acl.token_user_sid()}D:P(A;OICI;FA;;;AU)(A;OICI;FA;;;{acl.token_user_sid()})",
        )
    path = folder / "new.bin"

    descriptor = owner_only.create_private_file(path)
    try:
        assert os.write(descriptor, b"payload") == len(b"payload")
    finally:
        os.close(descriptor)

    assert path.read_bytes() == b"payload"
    if WIN:
        access = acl.read_access(path)
        assert access.owner == acl.token_user_sid()
        assert access.protected
        assert {entry.sid for entry in access.entries} == {
            acl.token_user_sid(),
            acl.SYSTEM_SID,
            acl.ADMINISTRATORS_SID,
        }
        assert len(access.entries) == 3
        assert all(
            entry.kind == "A" and entry.rights in FULL_CONTROL
            for entry in access.entries
        )
    else:
        assert (path.stat().st_mode & 0o777) == 0o600
