"""Black-box contract tests for the fail-closed Semgrep fixture validator."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPOSITORY_ROOT / "scripts" / "validate_semgrep_contract.py"
API_PYTHON = REPOSITORY_ROOT / "services" / "api" / ".venv" / "bin" / "python"


def write_minimal_pair(rules: Path, fixtures: Path) -> None:
    """Create the smallest valid contract pair without requiring valid Semgrep YAML."""
    rules.mkdir()
    fixtures.mkdir()
    (rules / "example.yml").write_text("rules:\n  - id: tailtag.example.rule\n")
    (fixtures / "example.py").write_text(
        "# ruleid: tailtag.example.rule\nunsafe()\n# ok: tailtag.example.rule\nsafe()\n"
    )


def run_validator(rules: Path, fixtures: Path) -> subprocess.CompletedProcess[str]:
    """Run the future stdlib validator through the locked API interpreter."""
    return subprocess.run(
        [
            str(API_PYTHON),
            str(VALIDATOR),
            "--rules",
            str(rules),
            "--fixtures",
            str(fixtures),
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_validator_accepts_a_minimal_matching_rule_and_fixture_pair(
    tmp_path: Path,
) -> None:
    """The metadata preflight accepts a complete, matching minimal contract."""
    rules = tmp_path / "rules"
    fixtures = tmp_path / "fixtures"
    write_minimal_pair(rules, fixtures)

    completed = run_validator(rules, fixtures)

    assert completed.returncode == 0, completed.stderr


Mutation = Callable[[Path, Path], None]


def empty_rules(rules: Path, fixtures: Path) -> None:
    rules.mkdir()
    fixtures.mkdir()
    (fixtures / "example.py").write_text("# ok: tailtag.example.rule\nsafe()\n")


def empty_fixtures(rules: Path, fixtures: Path) -> None:
    rules.mkdir()
    fixtures.mkdir()
    (rules / "example.yml").write_text("rules:\n  - id: tailtag.example.rule\n")


def missing_directory(rules: Path, fixtures: Path) -> None:
    fixtures.mkdir()


def rules_not_a_directory(rules: Path, fixtures: Path) -> None:
    rules.write_text("not a directory")
    fixtures.mkdir()


def unsupported_rule_extension(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "notes.txt").write_text("unsupported")


def unsupported_fixture_extension(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (fixtures / "notes.txt").write_text("unsupported")


def unknown_annotation(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (fixtures / "example.py").write_text("# nope: tailtag.example.rule\nunsafe()\n")


def malformed_annotation(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (fixtures / "example.py").write_text("# ruleid tailtag.example.rule\nunsafe()\n")


def duplicate_rule_identifier(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "example.yml").write_text(
        "rules:\n  - id: tailtag.example.rule\n  - id: tailtag.example.rule\n"
    )


def duplicate_rule_identifier_across_files(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "second.yml").write_text("rules:\n  - id: tailtag.example.rule\n")
    (fixtures / "second.py").write_text(
        "# ruleid: tailtag.example.rule\nunsafe()\n# ok: tailtag.example.rule\nsafe()\n"
    )


def noncanonical_rule_identifier(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "example.yml").write_text("rules:\n  - id: Example_Rule\n")


def malformed_rule_declaration(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "example.yml").write_text("rules:\n  id: tailtag.example.rule\n")


def empty_rule_declaration(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "example.yml").write_text("rules:\n  - id:\n")


def ambiguous_rule_declaration(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "example.yml").write_text(
        "rules:\n  - id: tailtag.example.rule\n    id: tailtag.other.rule\n"
    )


def unsupported_inline_rule_declaration(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "example.yml").write_text(
        "rules:\n  - id: tailtag.example.rule; tailtag.other.rule\n"
    )


def basename_mismatch(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (fixtures / "example.py").rename(fixtures / "different.py")


def ambiguous_rule_basename_pairing(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "example.yaml").write_text("rules:\n  - id: tailtag.example.second\n")
    (fixtures / "example.py").write_text(
        "# ruleid: tailtag.example.rule\nunsafe()\n"
        "# ok: tailtag.example.rule\nsafe()\n"
        "# ruleid: tailtag.example.second\nunsafe_second()\n"
        "# ok: tailtag.example.second\nsafe_second()\n"
    )


def missing_ruleid_annotation(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (fixtures / "example.py").write_text("# ok: tailtag.example.rule\nsafe()\n")


def missing_ok_annotation(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (fixtures / "example.py").write_text("# ruleid: tailtag.example.rule\nunsafe()\n")


def undefined_rule_annotation(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (fixtures / "example.py").write_text(
        "# ruleid: tailtag.unknown.rule\nunsafe()\n# ok: tailtag.example.rule\nsafe()\n"
    )


def undefined_safe_rule_annotation(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (fixtures / "example.py").write_text(
        "# ruleid: tailtag.example.rule\nunsafe()\n"
        "# ok: tailtag.example.rule\nsafe()\n"
        "# ok: tailtag.unknown.rule\nalso_safe()\n"
    )


def partial_two_rule_coverage(rules: Path, fixtures: Path) -> None:
    write_minimal_pair(rules, fixtures)
    (rules / "example.yml").write_text(
        "rules:\n  - id: tailtag.example.rule\n  - id: tailtag.example.second\n"
    )


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        (empty_rules, "zero rule files"),
        (empty_fixtures, "zero fixture files"),
        (missing_directory, "filesystem error"),
        (rules_not_a_directory, "filesystem error"),
        (unsupported_rule_extension, "unsupported rule file"),
        (unsupported_fixture_extension, "unsupported fixture file"),
        (unknown_annotation, "unknown fixture annotation"),
        (malformed_annotation, "malformed fixture annotation"),
        (duplicate_rule_identifier, "duplicate rule id"),
        (duplicate_rule_identifier_across_files, "duplicate rule id"),
        (noncanonical_rule_identifier, "noncanonical rule id"),
        (malformed_rule_declaration, "malformed rule id declaration"),
        (empty_rule_declaration, "malformed rule id declaration"),
        (ambiguous_rule_declaration, "malformed rule id declaration"),
        (unsupported_inline_rule_declaration, "malformed rule id declaration"),
        (basename_mismatch, "basename mismatch"),
        (ambiguous_rule_basename_pairing, "ambiguous basename pairing"),
        (missing_ruleid_annotation, "missing ruleid annotation"),
        (missing_ok_annotation, "missing ok annotation"),
        (undefined_rule_annotation, "unknown rule id"),
        (undefined_safe_rule_annotation, "unknown rule id"),
        (partial_two_rule_coverage, "missing ruleid annotation"),
    ],
    ids=[
        "zero-rules",
        "zero-fixtures",
        "missing-directory",
        "rules-not-directory",
        "unsupported-rule-file",
        "unsupported-fixture-file",
        "unknown-annotation",
        "malformed-annotation",
        "duplicate-id",
        "duplicate-id-across-files",
        "noncanonical-id",
        "malformed-id-shape",
        "empty-id-shape",
        "ambiguous-id-shape",
        "unsupported-inline-id-shape",
        "basename-mismatch",
        "ambiguous-basename-pairing",
        "missing-ruleid",
        "missing-ok",
        "undefined-rule-id",
        "undefined-safe-rule-id",
        "partial-two-rule-coverage",
    ],
)
def test_validator_rejects_invalid_contract_metadata(
    tmp_path: Path, mutation: Mutation, diagnostic: str
) -> None:
    """Every metadata mutation fails closed with a specific actionable diagnostic."""
    rules = tmp_path / "rules"
    fixtures = tmp_path / "fixtures"
    mutation(rules, fixtures)

    completed = run_validator(rules, fixtures)

    assert completed.returncode != 0
    assert diagnostic in completed.stderr.lower()
