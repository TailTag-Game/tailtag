"""Disposable acceptance coverage for #243's value-free registry reconciliation."""

from __future__ import annotations

import importlib
import json
import sys
import uuid
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "services" / "api" / "rehearsal" / "registry_reconcile.py"

MATCH = "MATCH"
MISMATCH = "MISMATCH"
INDETERMINATE = "INDETERMINATE"
PASS = "PASS"
MISSING = "MISSING"
AMBIGUOUS = "AMBIGUOUS"

CHECK_KEYS = frozenset(
    {
        "registry_singleton",
        "registry_structure",
        "root_completeness",
        "reset_environment_id",
        "database_name_private_registry",
        "cluster_identifier_private_registry",
        "database_name_actual_private",
        "database_name_actual_registry",
        "cluster_identifier_actual_private",
        "cluster_identifier_actual_registry",
        "owner_binding_private_registry",
        "catcher_binding_private_registry",
        "media_binding_private_registry",
        "database_host_runtime_private",
        "database_port_runtime_private",
    }
)

PRIVATE_RESET_ID = uuid.UUID("2164d6b8-b2df-48e8-9944-da0f7df3e09e")

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture
def reconciliation() -> ModuleType:
    """Load the remote, read-only reconciler only after its implementation exists."""
    assert SCRIPT.is_file(), "rehearsal/registry_reconcile.py must exist"
    return importlib.import_module("rehearsal.registry_reconcile")


def configuration(**overrides: object) -> SimpleNamespace:
    """Return a synthetic #204 private configuration with no real operator values."""
    values: dict[str, object] = {
        "environment_id": PRIVATE_RESET_ID,
        "cluster_identifier": "742391",
        "database_host": "postgres.internal",
        "database_port": "5432",
        "database_name": "tailtag_staging",
        "owner_clerk_id": "user_synthetic_owner",
        "catcher_clerk_id": "user_synthetic_catcher",
        "media_key": "images/0123456789abcdef0123456789abcdef.png",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def registry(**overrides: object) -> SimpleNamespace:
    """Return one structurally complete, matching persisted sentinel observation."""
    values: dict[str, object] = {
        "pk": 1,
        "environment_id": PRIVATE_RESET_ID,
        "cluster_identifier": "742391",
        "database_name": "tailtag_staging",
        "owner": SimpleNamespace(clerk_user_id="user_synthetic_owner"),
        "catcher": SimpleNamespace(clerk_user_id="user_synthetic_catcher"),
        "media_key": "images/0123456789abcdef0123456789abcdef.png",
        "convention_id": 11,
        "first_fursuit_id": 12,
        "second_fursuit_id": 13,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _checks(
    module: ModuleType,
    private: object = configuration(),
    persisted: object = registry(),
    actual_name: object = "tailtag_staging",
    actual_cluster: object = "742391",
    runtime_host: object = "postgres.internal",
    runtime_port: object = "5432",
) -> dict[str, str]:
    observed = cast(
        dict[str, str],
        module.compare_authorities(
            private,
            persisted,
            actual_name,
            actual_cluster,
            runtime_host,
            runtime_port,
        ),
    )
    assert set(observed) == CHECK_KEYS
    return observed


def test_matching_private_registry_and_live_database_facts_are_value_free_matches(
    reconciliation: ModuleType,
) -> None:
    """All three authorities agree without placing any private value in evidence."""
    observed = _checks(reconciliation)

    assert observed == {
        "registry_singleton": PASS,
        "registry_structure": PASS,
        "root_completeness": PASS,
        **{
            key: MATCH
            for key in CHECK_KEYS
            - {"registry_singleton", "registry_structure", "root_completeness"}
        },
    }
    rendered = json.dumps(observed, sort_keys=True)
    for prohibited in (
        str(PRIVATE_RESET_ID),
        "742391",
        "tailtag_staging",
        "postgres.internal",
        "user_synthetic_owner",
        "images/0123456789abcdef0123456789abcdef.png",
    ):
        assert prohibited not in rendered


def test_reset_uuid_disagreement_reports_only_the_disagreement(
    reconciliation: ModuleType,
) -> None:
    """A random reset UUID mismatch never chooses registry or private config as correct."""
    observed = _checks(
        reconciliation,
        persisted=registry(
            environment_id=uuid.UUID("c81aa5b0-7124-47f6-8adf-32b154713d99")
        ),
    )

    assert observed["reset_environment_id"] == MISMATCH
    assert all(
        observed[key] == MATCH
        for key in CHECK_KEYS
        - {
            "registry_singleton",
            "registry_structure",
            "root_completeness",
            "reset_environment_id",
        }
    )


@pytest.mark.parametrize(
    ("private_name", "registry_name", "actual_name", "expected"),
    (
        (
            "tailtag_staging",
            "tailtag_staging",
            "tailtag_staging",
            (MATCH, MATCH, MATCH),
        ),
        (
            "tailtag_staging",
            "tailtag_legacy",
            "tailtag_staging",
            (MISMATCH, MATCH, MISMATCH),
        ),
        (
            "tailtag_staging",
            "tailtag_staging",
            "tailtag_replaced",
            (MATCH, MISMATCH, MISMATCH),
        ),
    ),
)
def test_database_name_three_way_comparisons_remain_separate(
    reconciliation: ModuleType,
    private_name: str,
    registry_name: str,
    actual_name: str,
    expected: tuple[str, str, str],
) -> None:
    """Live database facts can distinguish which comparisons disagree without values."""
    observed = _checks(
        reconciliation,
        private=configuration(database_name=private_name),
        persisted=registry(database_name=registry_name),
        actual_name=actual_name,
    )

    assert (
        observed["database_name_private_registry"],
        observed["database_name_actual_private"],
        observed["database_name_actual_registry"],
    ) == expected


@pytest.mark.parametrize(
    ("private_cluster", "registry_cluster", "actual_cluster", "expected"),
    (
        ("742391", "742391", "742391", (MATCH, MATCH, MATCH)),
        ("742391", "555555", "742391", (MISMATCH, MATCH, MISMATCH)),
        ("742391", "742391", "987654", (MATCH, MISMATCH, MISMATCH)),
    ),
)
def test_cluster_identifier_three_way_comparisons_remain_separate(
    reconciliation: ModuleType,
    private_cluster: str,
    registry_cluster: str,
    actual_cluster: str,
    expected: tuple[str, str, str],
) -> None:
    """Cluster replacement cannot be hidden by a single broad registry status."""
    observed = _checks(
        reconciliation,
        private=configuration(cluster_identifier=private_cluster),
        persisted=registry(cluster_identifier=registry_cluster),
        actual_cluster=actual_cluster,
    )

    assert (
        observed["cluster_identifier_private_registry"],
        observed["cluster_identifier_actual_private"],
        observed["cluster_identifier_actual_registry"],
    ) == expected


@pytest.mark.parametrize(
    ("persisted", "key", "expected"),
    (
        (registry(pk=2), "registry_singleton", AMBIGUOUS),
        (
            registry(environment_id=uuid.UUID("12345678-1234-11ee-be56-0242ac120002")),
            "registry_structure",
            MISMATCH,
        ),
        (
            registry(convention_id=None, first_fursuit_id=12, second_fursuit_id=13),
            "root_completeness",
            MISMATCH,
        ),
    ),
)
def test_structural_registry_failures_are_distinct_from_binding_equality(
    reconciliation: ModuleType,
    persisted: object,
    key: str,
    expected: str,
) -> None:
    """A malformed sentinel never becomes evidence of a private binding mismatch."""
    observed = _checks(reconciliation, persisted=persisted)

    assert observed[key] == expected


def test_missing_registry_leaves_binding_checks_indeterminate(
    reconciliation: ModuleType,
) -> None:
    """Absent persisted state cannot safely implicate private config or live database."""
    observed = _checks(reconciliation, persisted=None)

    assert observed["registry_singleton"] == MISSING
    assert all(
        observed[key] == INDETERMINATE for key in CHECK_KEYS - {"registry_singleton"}
    )


@pytest.mark.parametrize(
    ("override", "check"),
    (
        (
            {"owner": SimpleNamespace(clerk_user_id="user_other")},
            "owner_binding_private_registry",
        ),
        (
            {"catcher": SimpleNamespace(clerk_user_id="user_other")},
            "catcher_binding_private_registry",
        ),
        (
            {"media_key": "images/abcdefabcdefabcdefabcdefabcdefab.png"},
            "media_binding_private_registry",
        ),
    ),
)
def test_preserved_binding_mismatches_are_sanitized_and_separate(
    reconciliation: ModuleType,
    override: dict[str, object],
    check: str,
) -> None:
    """Operator identity and media facts remain equality-only evidence."""
    observed = _checks(reconciliation, persisted=registry(**override))

    assert observed[check] == MISMATCH


def test_runtime_database_host_and_port_are_compared_only_to_private_expectation(
    reconciliation: ModuleType,
) -> None:
    """The runtime database transport has no persisted registry equivalent."""
    observed = _checks(
        reconciliation,
        runtime_host="other.internal",
        runtime_port="6543",
    )

    assert observed["database_host_runtime_private"] == MISMATCH
    assert observed["database_port_runtime_private"] == MISMATCH


def test_compare_authorities_has_no_database_write_surface(
    reconciliation: ModuleType,
) -> None:
    """The comparison helper accepts observations and has no database executor seam."""
    observed = _checks(reconciliation)

    assert observed["registry_singleton"] == PASS
    source = SCRIPT.read_text()
    for prohibited in (
        ".save(",
        ".create(",
        ".update(",
        ".delete(",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
    ):
        assert prohibited not in source
