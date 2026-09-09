# V0 Catch domain and database invariants

**Issue:** [#174 — Implement the V0 Catch domain and database
invariants](https://github.com/TailTag-Game/tailtag/issues/174)

**Parent:** [#173 — Establish V0 catch creation and persistent
collections](https://github.com/TailTag-Game/tailtag/issues/173)

**Status:** Approved design, Acceptance Contract, and Test Surface Contract;
frozen on 2026-09-08 before production implementation

## Goal

Establish Catch as the durable V0 gameplay fact and give PostgreSQL final
authority over canonical catch uniqueness. This issue creates only the domain
and persistence contract. It does not authorize catch creation, expose an API,
or add a second mutable collection-entry source of truth.

## Domain ownership

Create a dedicated `catches` Django application. Register
`catches.apps.CatchesConfig` in the backend settings and define the Catch model
in that application.

Catch is the durable source from which later collection and history reads will
be derived. The application must not introduce a separate collection-entry
model.

## Persistence contract

Create `catches.Catch` with exactly these domain fields:

| Field | Contract |
| --- | --- |
| `catcher_user` | Required foreign key to `settings.AUTH_USER_MODEL`, `on_delete=PROTECT`, `related_name="catches"` |
| `fursuit` | Required foreign key to `fursuits.Fursuit`, `on_delete=PROTECT`, `related_name="catches"` |
| `convention` | Required foreign key to `conventions.Convention`, `on_delete=PROTECT`, `related_name="catches"` |
| `activation` | Required foreign key to `conventions.FursuitActivation`, `on_delete=PROTECT`, `related_name="catches"` |
| `catch_session` | Required foreign key to `conventions.FursuitCatchSession`, `on_delete=PROTECT`, `related_name="catches"` |
| `caught_at` | `DateTimeField(auto_now_add=True)` |

The repository-default `BigAutoField` supplies the internal Catch primary key.
There is no credential or token field and no `created_at` or `updated_at`
field.

The initial catches migration uses Django's swappable dependency for
`settings.AUTH_USER_MODEL` and explicit dependencies on the current fursuits
and conventions migrations.

## Integrity and provenance

Add this named PostgreSQL uniqueness constraint:

```python
models.UniqueConstraint(
    fields=["catcher_user", "fursuit", "convention"],
    name="catches_catcher_fursuit_convention_unique",
)
```

It is the final integrity defense establishing at most one Catch for a catcher,
fursuit, and Convention tuple.

Activation and catch-session provenance are required. Issue #174 does not add
database triggers or model validation that claims to universally enforce
cross-table consistency among the direct fursuit and Convention relationships,
the activation, and the session. The canonical write service in #175 must
establish that consistency before creating a Catch.

No custom manager or queryset is introduced.

## Timestamp, ordering, and representation

`caught_at` is server-owned. `auto_now_add=True` prevents callers from choosing
it through normal model creation, and ordinary subsequent saves do not rewrite
it. The model does not override `save()` or `delete()` and does not attempt to
prohibit privileged ORM, migration, fixture, or future operator-correction
mechanisms.

The canonical model ordering is:

```python
["-caught_at", "-id"]
```

The safe string representation is exactly:

```text
Catch <id>: catcher <id>, fursuit <id>, convention <id>
```

Only internal database identifiers appear. Clerk/provider identifiers and
credential data must never appear. No special `__repr__` is added.

## Administrative and behavioral boundaries

Issue #174 does not register Catch in Django admin. Issue #178 owns Catch admin
registration, discovery, permissions, correction, removal, and audit behavior.

Issue #175 owns the sole normal application creation seam, authoritative
validation, cross-table provenance consistency, duplicate recovery, and the
stable already-caught result. The database duplicate-insert race in #174 proves
constraint enforcement only: no more than one row for the canonical tuple may
persist. It must not translate the losing insert into an application-level
outcome.

## Acceptance Contract

- **AC-01 — Dedicated domain:** A registered `catches` Django application owns
  `Catch`; no second collection-entry model exists.
- **AC-02 — Exact relationships:** Catch has required `catcher_user`, `fursuit`,
  `convention`, `activation`, and `catch_session` foreign keys with `PROTECT`
  deletion and `related_name="catches"`.
- **AC-03 — TailTag identity:** `catcher_user` targets
  `settings.AUTH_USER_MODEL`, not a Clerk/provider identifier.
- **AC-04 — Server timestamp:** `caught_at` is a timezone-aware,
  server-selected `DateTimeField(auto_now_add=True)` value that normal creation
  cannot choose and ordinary saves do not rewrite.
- **AC-05 — Minimal record:** Catch has no credential/token, `created_at`, or
  `updated_at` field.
- **AC-06 — Canonical uniqueness:** PostgreSQL enforces the named uniqueness
  constraint on `(catcher_user, fursuit, convention)`.
- **AC-07 — Required provenance:** Activation and catch-session provenance
  cannot be omitted.
- **AC-08 — Historical protection:** Deleting any referenced catcher, fursuit,
  Convention, activation, or catch session is protected while Catch refers to
  it.
- **AC-09 — Deterministic reads:** The default ordering is exactly
  `["-caught_at", "-id"]` and produces newest-first results with a stable ID
  tie-breaker.
- **AC-10 — Safe representation:** `str(catch)` exactly follows the approved
  internal-ID-only format and contains no provider identity or credential data.
- **AC-11 — Migration contract:** The initial migration is clean, uses the
  swappable user dependency plus explicit current fursuits and conventions
  dependencies, and repository checks detect drift.
- **AC-12 — Database race boundary:** A PostgreSQL duplicate-insert race can
  persist at most one Catch for the canonical tuple; no stable request recovery
  behavior is added.
- **AC-13 — Scope boundary:** No validation/creation service, serializer, URL,
  HTTP API, OpenAPI change, admin registration, model validation, custom
  manager/queryset, persistence-method override, correction workflow, or
  collection-entry model is introduced.

## Test Surface Contract

Tests may use the public Django model and ORM surface, model metadata, database
transactions, and repository-standard PostgreSQL concurrency helpers. They may
construct prerequisite accounts, fursuits, Conventions, activations, and catch
sessions through existing test support or direct ORM setup.

Tests may use privileged `QuerySet.update()` only to arrange deterministic
historical timestamps for ordering evidence. That setup capability is not a
normal creation contract and must not become production behavior.

The approved test surface covers:

- application registration and exact model metadata;
- required relationships, reverse names, and deletion behavior;
- timestamp selection, timezone awareness, and stability;
- named uniqueness enforcement;
- required provenance;
- actual queryset ordering;
- exact safe string representation;
- PostgreSQL duplicate-insert constraint behavior; and
- migration drift through the repository-owned check.

Tests must not require a creation service, duplicate-result translation,
cross-table provenance enforcement, admin behavior, HTTP behavior, or new
production testing seams.

## Scope Guard

**Outcome:** Add the dedicated Catch domain and its PostgreSQL-backed historical
integrity contract so #175 can build one authoritative creation service on it.

**Non-goals:** Application catch authority, eligibility checks, cross-table
provenance enforcement, stable duplicate recovery, catch APIs, collection and
history APIs, operator workflows, credentials, progression, social features,
offline synchronization, and unrelated cleanup.

**Expected change surface:** Backend settings; a new `catches` application with
its model and initial migration; focused backend test support and model,
constraint, deletion, timestamp, ordering, representation, and PostgreSQL race
tests; this specification. No existing product service or API module should
change.

**Proof:** Acceptance-first PostgreSQL-backed tests mapped to AC-01 through
AC-13; migration-drift validation; deterministic `make api-check` including
Semgrep; independent specification, code-quality, test-adequacy, and scope
review; and parent authoritative diff and verification review.

## Deferred work

- #175: authoritative validation, cross-table provenance consistency, creation,
  and stable duplicate recovery.
- #176: catch-confirmation HTTP API and OpenAPI contract.
- #177: player collection and catch-history APIs derived from Catch.
- #178: restricted Catch administration, correction/removal, and audit.
- #179: composed Railway Development validation and durable Wave 3 evidence.
