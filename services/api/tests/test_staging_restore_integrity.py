"""Semantic comparison contract for #207 source and restored integrity facts."""

# pyright: reportUnknownLambdaType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import importlib
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "staging_restore_integrity.py"

EXPECTED_SCHEMA_TABLES = frozenset(
    {
        "django_migrations",
        "django_content_type",
        "auth_permission",
        "auth_group",
        "auth_group_permissions",
        "django_admin_log",
        "django_session",
        "accounts_user",
        "accounts_user_groups",
        "accounts_user_user_permissions",
        "profiles_playerprofile",
        "fursuits_fursuit",
        "conventions_convention",
        "conventions_conventionenrollment",
        "conventions_fursuitactivation",
        "conventions_fursuitcatchsession",
        "conventions_fursuitcatchcredential",
        "catches_catch",
        "operator_audit_operatorauditevent",
        "rehearsal_stagingresetidentity",
    }
)

EXPECTED_NAMED_CONSTRAINTS = frozenset(
    {
        "accounts_user_clerk_user_id_not_empty",
        "accounts_user_local_password_requires_staff",
        "profiles_player_profile_handle_unique",
        "profiles_player_profile_handle_format",
        "profiles_player_profile_onboarding_state_consistent",
        "fursuits_fursuit_name_not_empty",
        "fursuits_fursuit_photo_key_not_empty",
        "conventions_convention_name_not_empty",
        "conventions_convention_status_valid",
        "conventions_convention_end_date_gte_start_date",
        "conventions_enrollment_user_convention_unique",
        "conventions_enrollment_user_single_active",
        "conventions_activation_fursuit_convention_unique",
        "conventions_activation_state_timestamps_valid",
        "conventions_catch_session_expiry_after_start",
        "conventions_catch_session_end_fields_paired",
        "conventions_catch_session_end_not_before_start",
        "conventions_catch_session_end_reason_valid",
        "conventions_catch_session_one_unended_per_activation",
        "conventions_catch_credential_revocation_fields_paired",
        "conventions_catch_credential_revocation_reason_valid",
        "conventions_catch_credential_token_unique",
        "conventions_catch_credential_one_current_per_activation",
        "catches_catcher_fursuit_convention_unique",
        "operator_audit_actor_outcome_valid",
        "rehearsal_reset_identity_singleton",
        "rehearsal_reset_identity_roots_complete",
    }
)

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))


@pytest.fixture
def integrity() -> ModuleType:
    """Load the planned read-only integrity interface when it is implemented."""
    assert SCRIPT.is_file(), "scripts/staging_restore_integrity.py must exist"
    return cast(Any, importlib.import_module("scripts.staging_restore_integrity"))


def source_facts(integrity: ModuleType) -> Any:
    """A sanitized snapshot with optional Catch/session/credential data absent."""
    return integrity.IntegrityFacts(
        applied_migrations=frozenset(
            {
                ("accounts", "0002_staff_local_password"),
                ("conventions", "0005_fursuitcatchcredential"),
                ("catches", "0001_initial"),
            }
        ),
        migration_leaves=frozenset(
            {
                ("accounts", "0002_staff_local_password"),
                ("conventions", "0005_fursuitcatchcredential"),
                ("catches", "0001_initial"),
            }
        ),
        table_counts={
            "accounts_user": 3,
            "profiles_playerprofile": 2,
            "fursuits_fursuit": 2,
            "conventions_convention": 1,
            "conventions_conventionenrollment": 2,
            "conventions_fursuitactivation": 2,
            "conventions_fursuitcatchsession": 0,
            "conventions_fursuitcatchcredential": 0,
            "catches_catch": 0,
        },
        constraint_fingerprints={
            "profiles_playerprofile_user_id_key": "profile-one-to-one",
            "fursuits_fursuit_tailtag_id_key": "tailtag-unique",
            "conventions_enrollment_user_convention_unique": "enrollment-pair",
            "conventions_enrollment_user_single_active": "enrollment-active",
            "conventions_activation_fursuit_convention_unique": "activation-pair",
            "conventions_activation_state_timestamps_valid": "activation-state",
            "conventions_catch_session_one_unended_per_activation": "session-current",
            "conventions_catch_credential_token_unique": "credential-token",
            "conventions_catch_credential_one_current_per_activation": "credential-current",
            "catches_catcher_fursuit_convention_unique": "catch-pair",
        },
        violations={
            "profile_user_one_to_one": 0,
            "fursuit_owner": 0,
            "fursuit_tailtag_id_unique": 0,
            "enrollment_relationships": 0,
            "enrollment_unique": 0,
            "enrollment_one_active": 0,
            "activation_relationships": 0,
            "activation_unique": 0,
            "activation_state": 0,
            "session_relationships": 0,
            "session_state": 0,
            "credential_relationships": 0,
            "credential_unique": 0,
            "credential_state": 0,
            "catch_relationships": 0,
            "catch_provenance": 0,
            "catch_unique": 0,
        },
        representative_records={
            "accounts_user": True,
            "profiles_playerprofile": True,
            "fursuits_fursuit": True,
            "conventions_convention": True,
            "conventions_conventionenrollment": True,
            "conventions_fursuitactivation": True,
            "conventions_fursuitcatchsession": False,
            "conventions_fursuitcatchcredential": False,
            "catches_catch": False,
        },
    )


def aggregate_executor(integrity: ModuleType, detect_violation: Any) -> Any:
    """Return sanitized aggregate rows while modelling one corrupt source shape."""

    def execute(query: str) -> object:
        if query == "SELECT app, name FROM django_migrations ORDER BY app, name":
            return [("conventions", "0005_fursuitcatchcredential")]
        if any(
            query == f"SELECT count(*) AS count FROM {table}"
            for table in integrity.TABLES
        ):
            return [{"count": 0}]
        if "FROM pg_tables" in query:
            return [{"name": table} for table in EXPECTED_SCHEMA_TABLES]
        if "FROM pg_constraint" in query:
            return [
                {"name": name, "definition": f"named-{name}"}
                for name in EXPECTED_NAMED_CONSTRAINTS
            ]
        if "FROM pg_index" in query:
            return []
        return [{"count": 1 if detect_violation(query) else 0}]

    return execute


def pg17_catalog_executor(
    integrity: ModuleType, omitted_not_null: tuple[str, str] | None
) -> Any:
    """Model a PG17 catalog where NOT NULL is an attribute, never contype ``n``."""

    catalog_rows: list[dict[str, object]] = [
        {
            "name": name,
            "definition": f"named-{name}",
            "kind": "c",
            "table_name": "accounts_user",
            "referenced_table": None,
            "source_column": None,
            "referenced_column": None,
            "key_count": 0,
        }
        for name in EXPECTED_NAMED_CONSTRAINTS
    ]
    catalog_rows.extend(
        {
            "name": f"unique_{table}_{column}",
            "definition": f"UNIQUE ({column})",
            "kind": "u",
            "table_name": table,
            "referenced_table": None,
            "source_column": column,
            "referenced_column": None,
            "key_count": 1,
        }
        for table, column in integrity.REQUIRED_SINGLE_COLUMN_UNIQUES
    )
    catalog_rows.extend(
        {
            "name": f"{table}_pkey",
            "definition": f"PRIMARY KEY ({table})",
            "kind": "p",
            "table_name": table,
            "referenced_table": None,
            "source_column": (
                "user_id"
                if table == "profiles_playerprofile"
                else "session_key"
                if table == "django_session"
                else "id"
            ),
            "referenced_column": None,
            "key_count": 1,
        }
        for table in EXPECTED_SCHEMA_TABLES
    )
    catalog_rows.extend(
        {
            "name": f"fk_{source_table}_{source_column}",
            "definition": "FOREIGN KEY",
            "kind": "f",
            "table_name": source_table,
            "referenced_table": referenced_table,
            "source_column": source_column,
            "referenced_column": referenced_column,
            "key_count": 1,
        }
        for source_table, source_column, referenced_table, referenced_column in integrity.REQUIRED_FOREIGN_KEYS
    )

    def execute(query: str) -> object:
        if query == "SELECT app, name FROM django_migrations ORDER BY app, name":
            return [("conventions", "0005_fursuitcatchcredential")]
        if any(
            query == f"SELECT count(*) AS count FROM {table}"
            for table in integrity.TABLES
        ):
            return [{"count": 0}]
        if "FROM pg_tables" in query:
            return [{"name": table} for table in EXPECTED_SCHEMA_TABLES]
        if "FROM pg_constraint" in query:
            return catalog_rows
        if "FROM pg_index" in query:
            return []
        if "FROM pg_attribute" in query:
            return [
                {"table_name": table, "column_name": column}
                for table, column in integrity.REQUIRED_NOT_NULL_COLUMNS
                if (table, column) != omitted_not_null
            ]
        return [{"count": 0}]

    return execute


def test_source_collection_fails_closed_when_a_read_only_fact_query_cannot_run(
    integrity: ModuleType,
) -> None:
    """AC-2/5: unread source facts cannot turn a restore into a partial pass."""
    calls: list[str] = []

    def unavailable(query: str) -> object:
        calls.append(query)
        raise OSError("source query unavailable")

    with pytest.raises(OSError):
        integrity.collect_integrity(
            unavailable,
            frozenset({("conventions", "0005_fursuitcatchcredential")}),
        )

    assert calls


@pytest.mark.parametrize(
    "check_name,detect_violation",
    (
        (
            "profile_user_one_to_one",
            lambda query: (
                "profiles_playerprofile" in query
                and "LEFT JOIN accounts_user" in query
                and "u.id IS NULL" in query
            ),
        ),
        (
            "session_state",
            lambda query: (
                "conventions_fursuitcatchsession" in query
                and "expires_at <= started_at" in query
            ),
        ),
        (
            "credential_state",
            lambda query: (
                "conventions_fursuitcatchcredential" in query
                and "(revoked_at IS NULL) <> (revocation_reason IS NULL)" in query
                and "revocation_reason NOT IN" in query
            ),
        ),
    ),
)
def test_collection_and_comparison_reject_critical_relationship_state_mutants(
    integrity: ModuleType, check_name: str, detect_violation: Any
) -> None:
    """AC-5: source facts expose orphan and paired-field corruption, not only duplicates."""
    source = integrity.collect_integrity(
        aggregate_executor(integrity, detect_violation),
        frozenset({("conventions", "0005_fursuitcatchcredential")}),
    )

    results = integrity.compare_integrity(source, source)

    assert source.violations[check_name] == 1
    assert results.checks[check_name] == "FAIL"
    assert results.overall_outcome == "FAIL"


def test_collection_rejects_a_catalog_with_only_named_model_constraints(
    integrity: ModuleType,
) -> None:
    """AC-5: the manifest requires structural primary-key/FK constraints too."""
    executor = aggregate_executor(integrity, lambda _: False)

    with pytest.raises(ValueError):
        integrity.collect_integrity(
            executor,
            frozenset({("conventions", "0005_fursuitcatchcredential")}),
        )


def test_expected_schema_manifest_covers_the_installed_django_and_v0_tables(
    integrity: ModuleType,
) -> None:
    """AC-5: a matching source/target pair cannot omit a non-domain schema table."""
    assert EXPECTED_SCHEMA_TABLES.issubset(integrity.EXPECTED_TABLES)
    assert EXPECTED_NAMED_CONSTRAINTS.issubset(integrity.REQUIRED_CONSTRAINTS)


def test_pg17_catalog_uses_attnotnull_parity_without_version_specific_not_null_constraints(
    integrity: ModuleType,
) -> None:
    """AC-5: PG17 source metadata and PG18 recovery still prove required non-null columns."""
    facts = integrity.collect_integrity(
        pg17_catalog_executor(integrity, omitted_not_null=None),
        frozenset({("conventions", "0005_fursuitcatchcredential")}),
    )

    assert (
        facts.constraint_fingerprints["not_null:profiles_playerprofile.user_id"]
        == "not_null"
    )

    with pytest.raises(ValueError):
        integrity.collect_integrity(
            pg17_catalog_executor(
                integrity, omitted_not_null=("profiles_playerprofile", "user_id")
            ),
            frozenset({("conventions", "0005_fursuitcatchcredential")}),
        )


def test_source_missing_a_required_migration_leaf_fails_before_restore_comparison(
    integrity: ModuleType,
) -> None:
    """AC-2/5: identical source/clone drift cannot hide an unapplied leaf."""
    with pytest.raises(ValueError, match="expected migration leaves"):
        integrity.collect_integrity(
            pg17_catalog_executor(integrity, omitted_not_null=None),
            frozenset({("accounts", "0002_staff_local_password")}),
        )


@pytest.mark.parametrize(
    "omitted_kind,omitted_table,omitted_column",
    (
        ("u", "accounts_user", "clerk_user_id"),
        ("u", "fursuits_fursuit", "tailtag_id"),
        ("p", "profiles_playerprofile", "user_id"),
    ),
)
def test_missing_implicit_identity_constraints_fail_closed(
    integrity: ModuleType,
    omitted_kind: str,
    omitted_table: str,
    omitted_column: str,
) -> None:
    """AC-5: source/clone agreement cannot hide missing implicit model constraints."""
    normal = pg17_catalog_executor(integrity, omitted_not_null=None)

    def missing_constraint(query: str) -> object:
        rows = normal(query)
        if "FROM pg_constraint" not in query:
            return rows
        return [
            row
            for row in rows
            if not (
                row["kind"] == omitted_kind
                and row["table_name"] == omitted_table
                and row["source_column"] == omitted_column
            )
        ]

    with pytest.raises(ValueError, match="expected (unique|primary-key) constraints"):
        integrity.collect_integrity(
            missing_constraint,
            frozenset({("conventions", "0005_fursuitcatchcredential")}),
        )


@pytest.mark.parametrize(
    "kind,table,column",
    (
        ("u", "accounts_user", "clerk_user_id"),
        ("u", "fursuits_fursuit", "tailtag_id"),
        ("p", "profiles_playerprofile", "user_id"),
    ),
)
def test_required_single_column_identity_constraint_rejects_a_composite_lookalike(
    integrity: ModuleType, kind: str, table: str, column: str
) -> None:
    """AC-5: an identity column appearing in a composite key is not its required one-column key."""
    normal = pg17_catalog_executor(integrity, omitted_not_null=None)

    def composite_lookalike(query: str) -> object:
        rows = normal(query)
        if "FROM pg_constraint" not in query:
            return rows
        matching_index = next(
            index
            for index, row in enumerate(rows)
            if row["kind"] == kind
            and row["table_name"] == table
            and row["source_column"] == column
        )
        matching = rows[matching_index]
        rows[matching_index] = {
            **matching,
            "definition": f"{matching['definition']} WITH id",
            "key_count": 2,
        }
        composite_part = {
            **matching,
            "source_column": "id",
            "definition": f"{matching['definition']} WITH id",
            "key_count": 2,
        }
        return [*rows, composite_part]

    with pytest.raises(ValueError, match="expected (unique|primary-key) constraints"):
        integrity.collect_integrity(
            composite_lookalike,
            frozenset({("conventions", "0005_fursuitcatchcredential")}),
        )


def test_required_scalar_foreign_key_rejects_a_composite_lookalike(
    integrity: ModuleType,
) -> None:
    """AC-5: the first pair in a composite FK cannot prove the required scalar relation."""
    normal = pg17_catalog_executor(integrity, omitted_not_null=None)
    expected = (
        "profiles_playerprofile",
        "user_id",
        "accounts_user",
        "id",
    )

    def composite_lookalike(query: str) -> object:
        rows = normal(query)
        if "FROM pg_constraint" not in query:
            return rows
        matching_index = next(
            index
            for index, row in enumerate(rows)
            if row["kind"] == "f"
            and (
                row["table_name"],
                row["source_column"],
                row["referenced_table"],
                row["referenced_column"],
            )
            == expected
        )
        matching = rows[matching_index]
        rows[matching_index] = {
            **matching,
            "definition": f"{matching['definition']} WITH id",
            "key_count": 2,
        }
        composite_part = {
            **matching,
            "source_column": "id",
            "referenced_column": "id",
            "definition": f"{matching['definition']} WITH id",
            "key_count": 2,
        }
        return [*rows, composite_part]

    with pytest.raises(ValueError, match="expected foreign-key constraints"):
        integrity.collect_integrity(
            composite_lookalike,
            frozenset({("conventions", "0005_fursuitcatchcredential")}),
        )


def test_matching_source_and_target_pass_while_empty_optional_domains_are_not_exercised(
    integrity: ModuleType,
) -> None:
    """AC-5: zero-row optional tables keep schema proof but cannot imply read proof."""
    source = source_facts(integrity)

    results = integrity.compare_integrity(source, source)

    assert results.overall_outcome == "PASS"
    assert results.checks["session_representative_read"] == "NOT_EXERCISED"
    assert results.checks["credential_representative_read"] == "NOT_EXERCISED"
    assert results.checks["catch_representative_read"] == "NOT_EXERCISED"
    assert results.checks["profiles_playerprofile_constraints"] == "PASS"
    assert results.checks["conventions_fursuitactivation_constraints"] == "PASS"


@pytest.mark.parametrize(
    "changed_source",
    (
        lambda facts: replace(
            facts,
            applied_migrations=facts.applied_migrations
            | frozenset({("conventions", "0006_unexpected")}),
        ),
        lambda facts: replace(
            facts,
            table_counts={**facts.table_counts, "fursuits_fursuit": 3},
        ),
        lambda facts: replace(
            facts,
            constraint_fingerprints={
                **facts.constraint_fingerprints,
                "conventions_catch_credential_one_current_per_activation": "missing",
            },
        ),
        lambda facts: replace(
            facts,
            representative_records={
                **facts.representative_records,
                "catches_catch": True,
            },
        ),
    ),
)
def test_semantic_source_target_mismatches_fail_the_restore_proof(
    integrity: ModuleType, changed_source: Any
) -> None:
    """AC-5: matching only startup or a subset of tables cannot pass recovery."""
    source = source_facts(integrity)
    restored = changed_source(source)

    results = integrity.compare_integrity(source, restored)

    assert results.overall_outcome == "FAIL"
    assert any(status == "FAIL" for status in results.checks.values())


@pytest.mark.parametrize(
    "violation_name",
    (
        "profile_user_one_to_one",
        "fursuit_tailtag_id_unique",
        "enrollment_one_active",
        "activation_state",
        "session_state",
        "credential_unique",
        "catch_provenance",
    ),
)
def test_any_source_or_target_integrity_violation_fails_even_if_the_facts_match(
    integrity: ModuleType, violation_name: str
) -> None:
    """AC-5/DATA INTEGRITY: a clone of corruption is still a failed recovery."""
    source = source_facts(integrity)
    violated = replace(source, violations={**source.violations, violation_name: 1})

    results = integrity.compare_integrity(violated, violated)

    assert results.overall_outcome == "FAIL"
    assert results.checks[violation_name] == "FAIL"
