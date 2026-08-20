"""Fail closed on the repository's Semgrep rule and fixture metadata contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RULE_EXTENSIONS = {".yml", ".yaml"}
FIXTURE_EXTENSIONS = {".py"}
RULE_ID = re.compile(r"tailtag\.[a-z0-9]+(?:[.-][a-z0-9]+)+\Z")
RULE_DECLARATION = re.compile(r"^\s*-\s+id:\s*([^\s#]+)\s*(?:#.*)?$")
ANY_ID_DECLARATION = re.compile(r"^\s*(?:-\s+)?id:\s*(.*)$")
ANNOTATION = re.compile(r"^\s*#\s*(ruleid|ok):\s*([^\s#]+)\s*$")
ANNOTATION_CANDIDATE = re.compile(
    r"^\s*#\s*(ruleid|ok|todoruleid|todook)(?::|\s)"
)


class ContractError(Exception):
    """An actionable fixture metadata contract violation."""


def files_in(directory: Path, extensions: set[str], kind: str) -> list[Path]:
    try:
        if not directory.is_dir():
            raise ContractError(f"filesystem error: {directory} is not a directory")
        entries = sorted(directory.iterdir())
    except OSError as error:
        raise ContractError(f"filesystem error: {error}") from error
    files: list[Path] = []
    for entry in entries:
        if entry.is_dir() and entry.name == "__pycache__":
            continue
        if not entry.is_file() or entry.suffix not in extensions:
            raise ContractError(f"unsupported {kind} file: {entry.name}")
        files.append(entry)
    if not files:
        raise ContractError(f"zero {kind} files")
    return files


def rule_ids(rule_files: list[Path]) -> set[str]:
    declared: set[str] = set()
    for rule_file in rule_files:
        try:
            lines = rule_file.read_text().splitlines()
        except OSError as error:
            raise ContractError(f"filesystem error: {error}") from error
        for line in lines:
            candidate = ANY_ID_DECLARATION.match(line)
            if not candidate:
                continue
            declaration = RULE_DECLARATION.match(line)
            if not declaration:
                raise ContractError("malformed rule id declaration")
            identifier = declaration.group(1)
            if not RULE_ID.fullmatch(identifier):
                raise ContractError(f"noncanonical rule id: {identifier}")
            if identifier in declared:
                raise ContractError(f"duplicate rule id: {identifier}")
            declared.add(identifier)
    if not declared:
        raise ContractError("malformed rule id declaration")
    return declared


def fixture_annotations(
    fixture_files: list[Path], declared: set[str]
) -> tuple[set[str], set[str]]:
    ruleids: set[str] = set()
    oks: set[str] = set()
    for fixture_file in fixture_files:
        try:
            lines = fixture_file.read_text().splitlines()
        except OSError as error:
            raise ContractError(f"filesystem error: {error}") from error
        for line in lines:
            annotation = ANNOTATION.match(line)
            if annotation:
                kind, identifier = annotation.groups()
                if identifier not in declared:
                    raise ContractError(f"unknown rule id: {identifier}")
                (ruleids if kind == "ruleid" else oks).add(identifier)
                continue
            candidate = ANNOTATION_CANDIDATE.match(line)
            if candidate:
                kind = candidate.group(1)
                if kind in {"ruleid", "ok"}:
                    raise ContractError("malformed fixture annotation")
                raise ContractError(f"unknown fixture annotation: {kind}")
    return ruleids, oks


def validate(rules_directory: Path, fixtures_directory: Path) -> None:
    rule_files = files_in(rules_directory, RULE_EXTENSIONS, "rule")
    fixture_files = files_in(fixtures_directory, FIXTURE_EXTENSIONS, "fixture")
    rule_stems = [path.stem for path in rule_files]
    fixture_stems = [path.stem for path in fixture_files]
    if len(rule_stems) != len(set(rule_stems)):
        raise ContractError("ambiguous basename pairing")
    if len(fixture_stems) != len(set(fixture_stems)):
        raise ContractError("ambiguous basename pairing")
    if set(rule_stems) != set(fixture_stems):
        raise ContractError("basename mismatch")
    declared = rule_ids(rule_files)
    ruleids, oks = fixture_annotations(fixture_files, declared)
    for identifier in sorted(declared):
        if identifier not in ruleids:
            raise ContractError(f"missing ruleid annotation: {identifier}")
        if identifier not in oks:
            raise ContractError(f"missing ok annotation: {identifier}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--fixtures", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        validate(arguments.rules, arguments.fixtures)
    except ContractError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
