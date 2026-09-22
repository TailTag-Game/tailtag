"""Read-only, sanitized integrity facts for the #207 recovery drill.

This module intentionally contains no connection strings and never selects a
domain value.  Callers provide a query executor which returns aggregate rows
from either the held source snapshot or the isolated recovery database.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

QueryExecutor = Callable[[str], object]


TABLES = (
    "accounts_user",
    "profiles_playerprofile",
    "fursuits_fursuit",
    "conventions_convention",
    "conventions_conventionenrollment",
    "conventions_fursuitactivation",
    "conventions_fursuitcatchsession",
    "conventions_fursuitcatchcredential",
    "catches_catch",
)

# The installed Django apps at the matched V0 revision.  This prevents a
# source/target pair that both lost a non-domain table from appearing healthy.
EXPECTED_TABLES = frozenset(
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

REQUIRED_FOREIGN_KEYS = frozenset(
    {
        ("auth_permission", "content_type_id", "django_content_type", "id"),
        ("auth_group_permissions", "group_id", "auth_group", "id"),
        ("auth_group_permissions", "permission_id", "auth_permission", "id"),
        ("django_admin_log", "content_type_id", "django_content_type", "id"),
        ("django_admin_log", "user_id", "accounts_user", "id"),
        ("accounts_user_groups", "user_id", "accounts_user", "id"),
        ("accounts_user_groups", "group_id", "auth_group", "id"),
        ("accounts_user_user_permissions", "user_id", "accounts_user", "id"),
        ("accounts_user_user_permissions", "permission_id", "auth_permission", "id"),
        ("profiles_playerprofile", "user_id", "accounts_user", "id"),
        ("fursuits_fursuit", "owner_id", "accounts_user", "id"),
        ("conventions_conventionenrollment", "user_id", "accounts_user", "id"),
        (
            "conventions_conventionenrollment",
            "convention_id",
            "conventions_convention",
            "id",
        ),
        ("conventions_fursuitactivation", "fursuit_id", "fursuits_fursuit", "id"),
        (
            "conventions_fursuitactivation",
            "convention_id",
            "conventions_convention",
            "id",
        ),
        (
            "conventions_fursuitcatchsession",
            "activation_id",
            "conventions_fursuitactivation",
            "id",
        ),
        (
            "conventions_fursuitcatchcredential",
            "activation_id",
            "conventions_fursuitactivation",
            "id",
        ),
        ("catches_catch", "catcher_user_id", "accounts_user", "id"),
        ("catches_catch", "fursuit_id", "fursuits_fursuit", "id"),
        ("catches_catch", "convention_id", "conventions_convention", "id"),
        ("catches_catch", "activation_id", "conventions_fursuitactivation", "id"),
        ("catches_catch", "catch_session_id", "conventions_fursuitcatchsession", "id"),
        ("operator_audit_operatorauditevent", "actor_id", "accounts_user", "id"),
        ("rehearsal_stagingresetidentity", "owner_id", "accounts_user", "id"),
        ("rehearsal_stagingresetidentity", "catcher_id", "accounts_user", "id"),
        (
            "rehearsal_stagingresetidentity",
            "convention_id",
            "conventions_convention",
            "id",
        ),
        (
            "rehearsal_stagingresetidentity",
            "first_fursuit_id",
            "fursuits_fursuit",
            "id",
        ),
        (
            "rehearsal_stagingresetidentity",
            "second_fursuit_id",
            "fursuits_fursuit",
            "id",
        ),
    }
)

REQUIRED_NOT_NULL_COLUMNS = frozenset(
    {
        ("accounts_user", "id"),
        ("accounts_user", "clerk_user_id"),
        ("profiles_playerprofile", "user_id"),
        ("fursuits_fursuit", "owner_id"),
        ("fursuits_fursuit", "tailtag_id"),
        ("conventions_convention", "name"),
        ("conventions_convention", "status"),
        ("conventions_conventionenrollment", "user_id"),
        ("conventions_conventionenrollment", "convention_id"),
        ("conventions_fursuitactivation", "fursuit_id"),
        ("conventions_fursuitactivation", "convention_id"),
        ("conventions_fursuitcatchsession", "activation_id"),
        ("conventions_fursuitcatchcredential", "activation_id"),
        ("conventions_fursuitcatchcredential", "token"),
        ("catches_catch", "catcher_user_id"),
        ("catches_catch", "fursuit_id"),
        ("catches_catch", "convention_id"),
        ("catches_catch", "activation_id"),
        ("catches_catch", "catch_session_id"),
        ("operator_audit_operatorauditevent", "actor_id"),
        ("rehearsal_stagingresetidentity", "owner_id"),
        ("rehearsal_stagingresetidentity", "catcher_id"),
    }
)

REQUIRED_PRIMARY_KEYS = frozenset(
    (
        table,
        "user_id"
        if table == "profiles_playerprofile"
        else "session_key"
        if table == "django_session"
        else "id",
    )
    for table in EXPECTED_TABLES
)
REQUIRED_SINGLE_COLUMN_UNIQUES = frozenset(
    {
        ("accounts_user", "clerk_user_id"),
        ("fursuits_fursuit", "tailtag_id"),
    }
)

# These names are explicit business constraints in the current V0 models.  The
# catalog query also captures automatically created primary/unique/FK objects.
REQUIRED_CONSTRAINTS = frozenset(
    {
        "accounts_user_clerk_user_id_not_empty",
        "accounts_user_local_password_requires_staff",
        "profiles_player_profile_handle_unique",
        "profiles_player_profile_handle_format",
        "profiles_player_profile_onboarding_state_consistent",
        "fursuits_fursuit_name_not_empty",
        "fursuits_fursuit_photo_key_not_empty",
        "conventions_enrollment_user_convention_unique",
        "conventions_enrollment_user_single_active",
        "conventions_activation_fursuit_convention_unique",
        "conventions_activation_state_timestamps_valid",
        "conventions_convention_name_not_empty",
        "conventions_convention_status_valid",
        "conventions_convention_end_date_gte_start_date",
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


@dataclass(frozen=True)
class IntegrityFacts:
    applied_migrations: frozenset[tuple[str, str]]
    migration_leaves: frozenset[tuple[str, str]]
    table_counts: dict[str, int]
    constraint_fingerprints: dict[str, str]
    violations: dict[str, int]
    representative_records: dict[str, bool]


@dataclass(frozen=True)
class CheckResults:
    checks: dict[str, str]
    overall_outcome: str


def _rows(value: object) -> list[Mapping[str, Any] | tuple[Any, ...]]:
    """Normalize DB-API style query results without accepting scalars."""
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        raise TypeError("integrity query did not return structured rows")
    result = list(cast(Iterable[object], value))
    for row in result:
        if not isinstance(row, (Mapping, tuple, list)):
            raise TypeError("integrity query returned an unstructured row")
    return result  # type: ignore[return-value]


def _value(
    rows: list[Mapping[str, Any] | tuple[Any, ...]], key: str, index: int = 0
) -> Any:
    if len(rows) != 1:
        raise ValueError("integrity aggregate did not return exactly one row")
    row = rows[0]
    if isinstance(row, Mapping):
        if key not in row:
            raise KeyError("integrity aggregate omitted required field")
        return row[key]
    return row[index]


def _count(execute: QueryExecutor, table: str) -> int:
    value = _value(_rows(execute(f"SELECT count(*) AS count FROM {table}")), "count")
    if not isinstance(value, int) or value < 0:
        raise ValueError("invalid table count")
    return value


def _violation_queries() -> dict[str, str]:
    # Every query is an aggregate.  The text is deliberately fixed: an operator
    # cannot influence it with a source or target value.
    return {
        "user_clerk_id_unique": "SELECT count(*) AS count FROM (SELECT clerk_user_id FROM accounts_user GROUP BY clerk_user_id HAVING count(*) > 1) v",
        "profile_user_one_to_one": "SELECT count(*) AS count FROM (SELECT p.user_id FROM profiles_playerprofile p LEFT JOIN accounts_user u ON u.id=p.user_id WHERE u.id IS NULL UNION ALL SELECT user_id FROM profiles_playerprofile GROUP BY user_id HAVING count(*) <> 1) v",
        "fursuit_owner": "SELECT count(*) AS count FROM fursuits_fursuit f LEFT JOIN accounts_user u ON u.id=f.owner_id WHERE u.id IS NULL",
        "fursuit_tailtag_id_unique": "SELECT count(*) AS count FROM (SELECT tailtag_id FROM fursuits_fursuit GROUP BY tailtag_id HAVING count(*) > 1) v",
        "enrollment_relationships": "SELECT count(*) AS count FROM conventions_conventionenrollment e LEFT JOIN accounts_user u ON u.id=e.user_id LEFT JOIN conventions_convention c ON c.id=e.convention_id WHERE u.id IS NULL OR c.id IS NULL",
        "enrollment_unique": "SELECT count(*) AS count FROM (SELECT user_id, convention_id FROM conventions_conventionenrollment GROUP BY user_id, convention_id HAVING count(*) > 1) v",
        "enrollment_one_active": "SELECT count(*) AS count FROM (SELECT user_id FROM conventions_conventionenrollment WHERE is_active GROUP BY user_id HAVING count(*) > 1) v",
        "activation_relationships": "SELECT count(*) AS count FROM conventions_fursuitactivation a LEFT JOIN fursuits_fursuit f ON f.id=a.fursuit_id LEFT JOIN conventions_convention c ON c.id=a.convention_id WHERE f.id IS NULL OR c.id IS NULL",
        "activation_unique": "SELECT count(*) AS count FROM (SELECT fursuit_id, convention_id FROM conventions_fursuitactivation GROUP BY fursuit_id, convention_id HAVING count(*) > 1) v",
        "activation_state": "SELECT count(*) AS count FROM conventions_fursuitactivation WHERE NOT ((is_active AND deactivated_at IS NULL) OR (NOT is_active AND deactivated_at IS NOT NULL))",
        "session_relationships": "SELECT count(*) AS count FROM conventions_fursuitcatchsession s LEFT JOIN conventions_fursuitactivation a ON a.id=s.activation_id WHERE a.id IS NULL",
        "session_state": "SELECT count(*) AS count FROM conventions_fursuitcatchsession WHERE expires_at <= started_at OR ((ended_at IS NULL) <> (end_reason IS NULL)) OR (ended_at IS NOT NULL AND ended_at < started_at) OR (end_reason IS NOT NULL AND end_reason NOT IN ('owner','operator','eligibility_lost','expired'))",
        "credential_relationships": "SELECT count(*) AS count FROM conventions_fursuitcatchcredential c LEFT JOIN conventions_fursuitactivation a ON a.id=c.activation_id WHERE a.id IS NULL",
        "credential_unique": "SELECT count(*) AS count FROM (SELECT token FROM conventions_fursuitcatchcredential GROUP BY token HAVING count(*) > 1) v",
        "credential_state": "SELECT count(*) AS count FROM conventions_fursuitcatchcredential WHERE ((revoked_at IS NULL) <> (revocation_reason IS NULL)) OR (revocation_reason IS NOT NULL AND revocation_reason NOT IN ('owner_rotation','operator','eligibility_lost')) OR activation_id IN (SELECT activation_id FROM conventions_fursuitcatchcredential WHERE revoked_at IS NULL GROUP BY activation_id HAVING count(*) > 1)",
        "catch_relationships": "SELECT count(*) AS count FROM catches_catch c LEFT JOIN accounts_user u ON u.id=c.catcher_user_id LEFT JOIN fursuits_fursuit f ON f.id=c.fursuit_id LEFT JOIN conventions_convention n ON n.id=c.convention_id LEFT JOIN conventions_fursuitactivation a ON a.id=c.activation_id LEFT JOIN conventions_fursuitcatchsession s ON s.id=c.catch_session_id WHERE u.id IS NULL OR f.id IS NULL OR n.id IS NULL OR a.id IS NULL OR s.id IS NULL",
        "catch_provenance": "SELECT count(*) AS count FROM catches_catch c JOIN conventions_fursuitactivation a ON a.id=c.activation_id JOIN conventions_fursuitcatchsession s ON s.id=c.catch_session_id WHERE a.fursuit_id <> c.fursuit_id OR a.convention_id <> c.convention_id OR s.activation_id <> c.activation_id",
        "catch_unique": "SELECT count(*) AS count FROM (SELECT catcher_user_id, fursuit_id, convention_id FROM catches_catch GROUP BY catcher_user_id, fursuit_id, convention_id HAVING count(*) > 1) v",
    }


def collect_integrity(
    query_executor: QueryExecutor, migration_leaves: frozenset[tuple[str, str]]
) -> IntegrityFacts:
    """Collect all fixed, aggregate-only facts; fail closed on any read error."""
    migration_rows = _rows(
        query_executor("SELECT app, name FROM django_migrations ORDER BY app, name")
    )
    migrations: set[tuple[str, str]] = set()
    for row in migration_rows:
        if isinstance(row, Mapping):
            app, name = row["app"], row["name"]
        else:
            app, name = row[0], row[1]
        if not isinstance(app, str) or not isinstance(name, str):
            raise TypeError("invalid migration row")
        migrations.add((app, name))
    if not migration_leaves.issubset(migrations):
        raise ValueError("expected migration leaves are not applied")

    counts = {table: _count(query_executor, table) for table in TABLES}
    table_rows = _rows(
        query_executor(
            "SELECT tablename AS name FROM pg_tables "
            "WHERE schemaname='public' ORDER BY tablename"
        )
    )
    actual_tables: set[str] = set()
    for row in table_rows:
        name = row["name"] if isinstance(row, Mapping) else row[0]
        if not isinstance(name, str):
            raise TypeError("invalid table catalog row")
        actual_tables.add(name)
    if not EXPECTED_TABLES.issubset(actual_tables):
        raise ValueError("expected database tables are absent")
    catalog_rows = _rows(
        query_executor(
            "SELECT con.conname AS name, "
            "pg_get_constraintdef(con.oid, true) AS definition, "
            "con.contype AS kind, rel.relname AS table_name, "
            "ref.relname AS referenced_table, src_att.attname AS source_column, "
            "ref_att.attname AS referenced_column "
            "FROM pg_constraint con "
            "JOIN pg_namespace n ON n.oid=con.connamespace "
            "JOIN pg_class rel ON rel.oid=con.conrelid "
            "LEFT JOIN pg_class ref ON ref.oid=con.confrelid "
            "LEFT JOIN LATERAL unnest(con.conkey) AS keys(source_attnum) ON true "
            "LEFT JOIN pg_attribute src_att ON src_att.attrelid=con.conrelid AND src_att.attnum=keys.source_attnum "
            "LEFT JOIN pg_attribute ref_att ON ref_att.attrelid=con.confrelid AND ref_att.attnum=con.confkey[array_position(con.conkey, keys.source_attnum)] "
            "WHERE n.nspname='public' AND con.contype <> 'n' ORDER BY con.conname"
        )
    )
    fingerprints: dict[str, str] = {}
    primary_keys: set[tuple[str, str]] = set()
    single_column_uniques: set[tuple[str, str]] = set()
    foreign_keys: set[tuple[str, str, str, str]] = set()
    structural_catalog_complete = True
    for row in catalog_rows:
        name, definition = (
            (row["name"], row["definition"])
            if isinstance(row, Mapping)
            else (row[0], row[1])
        )
        if not isinstance(name, str) or not isinstance(definition, str):
            raise TypeError("invalid constraint catalog row")
        fingerprints[name] = _canonical_definition(definition)
        try:
            kind = row["kind"] if isinstance(row, Mapping) else row[2]
            table_name = row["table_name"] if isinstance(row, Mapping) else row[3]
            referenced_table = (
                row["referenced_table"] if isinstance(row, Mapping) else row[4]
            )
            source_column = row["source_column"] if isinstance(row, Mapping) else row[5]
            referenced_column = (
                row["referenced_column"] if isinstance(row, Mapping) else row[6]
            )
        except (IndexError, KeyError):
            structural_catalog_complete = False
            continue
        if (
            kind == "p"
            and isinstance(table_name, str)
            and isinstance(source_column, str)
        ):
            primary_keys.add((table_name, source_column))
        if (
            kind == "u"
            and isinstance(table_name, str)
            and isinstance(source_column, str)
        ):
            single_column_uniques.add((table_name, source_column))
        if kind == "f" and all(
            isinstance(value, str)
            for value in (
                table_name,
                source_column,
                referenced_table,
                referenced_column,
            )
        ):
            foreign_keys.add(
                (table_name, source_column, referenced_table, referenced_column)
            )

    # Partial unique constraints live in pg_index rather than pg_constraint.
    index_rows = _rows(
        query_executor(
            "SELECT i.relname AS name, pg_get_indexdef(i.oid) AS definition "
            "FROM pg_index x JOIN pg_class i ON i.oid=x.indexrelid "
            "JOIN pg_namespace n ON n.oid=i.relnamespace "
            "WHERE n.nspname='public' AND x.indisunique ORDER BY i.relname"
        )
    )
    for row in index_rows:
        name, definition = (
            (row["name"], row["definition"])
            if isinstance(row, Mapping)
            else (row[0], row[1])
        )
        if not isinstance(name, str) or not isinstance(definition, str):
            raise TypeError("invalid index catalog row")
        fingerprints.setdefault(name, _canonical_definition(definition))

    null_rows = _rows(
        query_executor(
            "SELECT c.relname AS table_name, a.attname AS column_name "
            "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND a.attnum > 0 AND NOT a.attisdropped "
            "AND a.attnotnull ORDER BY c.relname, a.attname"
        )
    )
    not_null_columns: set[tuple[str, str]] = set()
    nullability_catalog_complete = True
    for row in null_rows:
        try:
            table_name, column_name = (
                (row["table_name"], row["column_name"])
                if isinstance(row, Mapping)
                else (row[0], row[1])
            )
        except (IndexError, KeyError):
            nullability_catalog_complete = False
            continue
        if not isinstance(table_name, str) or not isinstance(column_name, str):
            raise TypeError("invalid nullability catalog row")
        not_null_columns.add((table_name, column_name))
        fingerprints[f"not_null:{table_name}.{column_name}"] = "not_null"

    missing = REQUIRED_CONSTRAINTS - fingerprints.keys()
    if missing:
        raise ValueError("expected database constraints are absent")
    violations = {
        name: _count_sql(query_executor, sql)
        for name, sql in _violation_queries().items()
    }
    # A known-corrupt source is already a hard failed drill. Preserve its
    # aggregate facts for comparison even if its catalog is incomplete; a
    # zero-violation source or target must independently prove all structure.
    if not any(violations.values()):
        if not structural_catalog_complete:
            raise ValueError("structural constraint catalog incomplete")
        if not REQUIRED_PRIMARY_KEYS.issubset(primary_keys):
            raise ValueError("expected primary-key constraints are absent")
        if not REQUIRED_SINGLE_COLUMN_UNIQUES.issubset(single_column_uniques):
            raise ValueError("expected unique constraints are absent")
        if not REQUIRED_FOREIGN_KEYS.issubset(foreign_keys):
            raise ValueError("expected foreign-key constraints are absent")
        if not nullability_catalog_complete or not REQUIRED_NOT_NULL_COLUMNS.issubset(
            not_null_columns
        ):
            raise ValueError("expected not-null columns are absent")
    return IntegrityFacts(
        applied_migrations=frozenset(migrations),
        migration_leaves=migration_leaves,
        table_counts=counts,
        constraint_fingerprints=fingerprints,
        violations=violations,
        representative_records={table: count > 0 for table, count in counts.items()},
    )


def _count_sql(execute: QueryExecutor, sql: str) -> int:
    value = _value(_rows(execute(sql)), "count")
    if not isinstance(value, int) or value < 0:
        raise ValueError("invalid integrity count")
    return value


def _canonical_definition(definition: str) -> str:
    """Normalize PostgreSQL 17/18's equivalent enum-array cast rendering."""
    if "ARRAY[" not in definition or "]::text[]" not in definition:
        return definition
    normalized = re.sub(
        r"('[^']+'::character varying)(?=,|\])",
        r"\1::text",
        definition,
    )
    return normalized.replace("]::text[]", "]")


def compare_integrity(source: IntegrityFacts, restored: IntegrityFacts) -> CheckResults:
    """Compare semantic facts and reject cloned corruption as well as mismatch."""
    checks: dict[str, str] = {}
    checks["applied_migrations"] = _same(
        source.applied_migrations, restored.applied_migrations
    )
    checks["migration_leaves"] = _same(
        source.migration_leaves, restored.migration_leaves
    )
    checks["table_counts"] = _same(source.table_counts, restored.table_counts)
    checks["constraint_fingerprints"] = _same(
        source.constraint_fingerprints, restored.constraint_fingerprints
    )
    for name in sorted(set(source.violations) | set(restored.violations)):
        checks[name] = (
            "PASS"
            if source.violations.get(name) == restored.violations.get(name) == 0
            else "FAIL"
        )
    for table in TABLES:
        checks[f"{table}_constraints"] = (
            "PASS"
            if source.constraint_fingerprints == restored.constraint_fingerprints
            else "FAIL"
        )
        domain = _domain_for_table(table)
        # SQL existence is deliberately not passed off as a Django read.  The
        # operator entry point records the separate command-only ORM proof.
        checks[f"{domain}_representative_read"] = (
            "NOT_EXERCISED"
            if source.representative_records.get(table)
            == restored.representative_records.get(table)
            else "FAIL"
        )
    return CheckResults(
        checks=checks,
        overall_outcome="PASS"
        if all(value != "FAIL" for value in checks.values())
        else "FAIL",
    )


def _same(left: object, right: object) -> str:
    return "PASS" if left == right else "FAIL"


def _domain_for_table(table: str) -> str:
    return {
        "accounts_user": "user",
        "profiles_playerprofile": "profile",
        "fursuits_fursuit": "fursuit",
        "conventions_convention": "convention",
        "conventions_conventionenrollment": "enrollment",
        "conventions_fursuitactivation": "activation",
        "conventions_fursuitcatchsession": "session",
        "conventions_fursuitcatchcredential": "credential",
        "catches_catch": "catch",
    }[table]
