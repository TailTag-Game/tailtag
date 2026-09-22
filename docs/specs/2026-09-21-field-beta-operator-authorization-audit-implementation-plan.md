# Field-Beta Operator Authorization and Auditability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the eight existing sensitive Django-admin mutations with explicit operation permissions, durable privacy-safe audit evidence, and a usable non-superuser Staging operator path.

**Architecture:** Keep authorization at the Django-admin boundary and state changes in the existing transactional domain services. Add one closed `operator_audit` module whose admin-action coordinator wraps the complete POST handler in a transaction, writes success in the same commit, and records denied/rejected/failed attempts only after any domain rollback. Provision dedicated non-superuser staff through Django's native User/Group/Permission machinery without introducing an operator UI or provider-authentication redesign.

**Tech Stack:** Python 3.13, Django 6.0, PostgreSQL, pytest-django, strict Pyright, Ruff, Semgrep, Railway Staging.

## Global Constraints

- The frozen specification is `docs/specs/2026-09-21-field-beta-operator-authorization-audit.md`; do not reinterpret or weaken it.
- Execution is STANDARD EXPANDED with SECURITY, DATA INTEGRITY, and TEST ADEQUACY assurance.
- The sensitive mutation set contains exactly eight actions; D1-D3 close unlisted authority paths instead of adding actions.
- `is_staff` grants admin-site access only. Generic `view_*`, `change_*`, or `delete_*` permissions never substitute for a sensitive permission, except the approved `catches.delete_catch` correction authority.
- Domain services remain request/user-agnostic state-transition boundaries.
- Audit events contain no Clerk identifiers, emails, credentials, tokens, payloads, private URLs, request bodies, exception details, or object snapshots.
- Successful state and audit rows commit atomically. Cascades create one top-level audit event.
- No audit viewer, operator-management UI, generalized RBAC, operator HTTP API, provider redesign, #198 observability, or #204 reset behavior is added.
- Test authors may add or change acceptance tests but must not add production seams. Implementers must not weaken approved tests.
- Run narrow PostgreSQL-backed tests first and `make api-check` before completion. Track and remove only task-created disposable containers/networks; preserve reusable volumes and unrelated services.
- No live Staging mutation occurs without separate explicit user authorization.

## File and interface map

### New audit unit

- `services/api/operator_audit/apps.py` — Django app registration only.
- `services/api/operator_audit/models.py` — closed enums and immutable `OperatorAuditEvent` persistence contract.
- `services/api/operator_audit/services.py` — generic `OperatorTransition[T]` and database audit writer; no Django request dependency.
- `services/api/operator_audit/admin_actions.py` — the narrow Django-admin POST coordinator; binds one attempt to a request, owns transaction/outcome classification, and calls the audit writer.
- `services/api/operator_audit/migrations/0001_initial.py` — audit table and database constraints.
- `services/api/tests/test_operator_audit.py` — model, privacy, actor/outcome, transaction, rollback, and coordinator acceptance tests.

The stable interfaces are:

```python
class OperatorAction(models.TextChoices): ...
class OperatorActorClass(models.TextChoices): ...
class OperatorAuditOutcome(models.TextChoices): ...
class OperatorTargetType(models.TextChoices): ...

@dataclass(frozen=True)
class OperatorTransition[T]:
    value: T
    changed: bool

def run_sensitive_admin_attempt(
    request: HttpRequest,
    *,
    permission: str,
    action: OperatorAction,
    target_type: OperatorTargetType,
    target_id: int,
    handler: Callable[[], HttpResponse],
    rejected_exceptions: tuple[type[Exception], ...] = (),
) -> HttpResponse: ...

def execute_bound_operator_transition[T](
    request: HttpRequest,
    operation: Callable[[], OperatorTransition[T]],
) -> T: ...
```

`run_sensitive_admin_attempt` is called only for POSTs that express one of the
eight sensitive intents. It writes `denied` before raising `PermissionDenied`
when authority is absent; otherwise it binds the attempt, opens the outer atomic
transaction, and invokes `handler`. A normal response without a call to
`execute_bound_operator_transition` is a form/domain `rejected` attempt. The
execute function raises an internal rejection for `changed=False`, or writes
`succeeded` beside the domain change for `changed=True`. An unexpected exception
rolls back the outer transaction before a best-effort `failed` row is inserted.

### Existing domain units

- `accounts` — permit usable passwords for staff, retain the ordinary-player rule, and add guarded Staging operator provisioning.
- `catches` — preserve `delete_catch`; wrap individual removal only.
- `conventions` — add five operation permissions, close enrollment add/selection and playable create/delete, and wrap the four approved sensitive operations plus playability.
- `profiles` and `fursuits` — add enabled-state permissions and wrap their sole admin mutation.
- Existing domain services return `OperatorTransition[...]` from operator-only seams so changed/no-op is decided under the service's row locks.

---

### Task 1: Establish an environment-ready baseline

**Files:**
- Read: `AGENTS.md`
- Read: `CONTRIBUTING.md`
- Read: `docs/specs/2026-09-21-field-beta-operator-authorization-audit.md`
- Read: this plan

**Interfaces:**
- Consumes: current clean feature branch and repository-owned development environment.
- Produces: recorded baseline evidence and ownership of any task-created test resources.

- [ ] **Step 1: Confirm scope and worktree state**

Run:

```bash
git status --short --branch
git diff --check
docker ps --format '{{.ID}} {{.Names}} {{.Status}}'
```

Expected: only approved task artifacts are present; record any pre-existing
containers so cleanup cannot affect them.

- [ ] **Step 2: Synchronize locked tooling**

Run:

```bash
make api-setup
```

Expected: both locked uv environments synchronize without lockfile changes.

- [ ] **Step 3: Run the authoritative baseline**

Run:

```bash
make api-check
```

Expected: formatting, lint, strict typing, Semgrep, all PostgreSQL tests, Django,
migration drift, OpenAPI schema, and Gunicorn checks pass. Stop and investigate
any baseline failure before test authorship.

### Task 2: Author and approve the audit-foundation acceptance tests

**Role:** Independent `test_author`; the production implementer must not author or weaken these tests.

**Files:**
- Create: `services/api/tests/test_operator_audit.py`
- Test: `services/api/tests/test_operator_audit.py`

**Interfaces:**
- Consumes: exact enums, model fields, and coordinator signatures from the File and interface map.
- Produces: failing AC-4 through AC-7 and AC-10 tests for the audit foundation and transaction protocol.

- [ ] **Step 1: Write model and privacy-contract tests**

Cover the exact eight actions, eight target labels, three actor classes, four
outcomes, UUID identity, server time, `PROTECT` actor, absence of metadata/free
text fields, database rejection of invalid actor/outcome pairs, and creation of
the seven exact custom permissions plus the preserved Catch delete permission.
The core
assertion must be equivalent to:

```python
event = OperatorAuditEvent.objects.create(
    action=OperatorAction.SET_PROFILE_ENABLED,
    actor=operator,
    actor_class=OperatorActorClass.OPERATOR,
    affected_record_type=OperatorTargetType.PLAYER_PROFILE,
    affected_record_id=profile.pk,
    outcome=OperatorAuditOutcome.SUCCEEDED,
)
assert event.pk.version == 4
assert event.occurred_at is not None
assert set(field.name for field in OperatorAuditEvent._meta.fields) == {
    "id", "action", "actor", "actor_class", "affected_record_type",
    "affected_record_id", "outcome", "occurred_at",
}
```

- [ ] **Step 2: Write coordinator transaction tests**

Use `RequestFactory`, real Users, and `transaction.on_commit()`/forced exceptions
to prove: allowed non-superuser is `operator`; superuser is
`emergency_superuser`; missing permission records `unauthorized_actor/denied`;
`changed=False` records `rejected`; form-return-without-execution records
`rejected`; successful state and audit commit together; an exception after a
state write rolls both back and leaves only `failed`; GET creates no event; and
an audit insert failure cannot leave domain state committed.

- [ ] **Step 3: Run the focused tests and confirm the expected red state**

Run:

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_operator_audit.py
```

Expected: collection/import failures identify the absent `operator_audit` app and
interfaces, not fixture or environment failures.

- [ ] **Step 4: Perform parent test-adequacy review**

Map every test to AC-4, AC-5, AC-6, AC-7, or AC-10. Explicitly reject tests for
an audit viewer, arbitrary metadata, log retention, or cascade event sourcing.
Approve the test file unchanged before Task 3.

- [ ] **Step 5: Commit the approved red tests**

```bash
git add services/api/tests/test_operator_audit.py
git commit -m "test(api): define operator audit contract"
```

### Task 3: Implement the closed audit model and admin coordinator

**Role:** Independent `implementer` with the frozen spec and approved Task 2 tests.

**Files:**
- Create: `services/api/operator_audit/__init__.py`
- Create: `services/api/operator_audit/apps.py`
- Create: `services/api/operator_audit/models.py`
- Create: `services/api/operator_audit/services.py`
- Create: `services/api/operator_audit/admin_actions.py`
- Create: `services/api/operator_audit/migrations/__init__.py`
- Create: `services/api/operator_audit/migrations/0001_initial.py`
- Modify: `services/api/profiles/models.py`
- Create: `services/api/profiles/migrations/0002_playerprofile_operator_permission.py`
- Modify: `services/api/fursuits/models.py`
- Create: `services/api/fursuits/migrations/0003_fursuit_operator_permission.py`
- Modify: `services/api/conventions/models.py`
- Create: `services/api/conventions/migrations/0006_operator_permissions.py`
- Modify: `services/api/config/settings/base.py`
- Modify: `services/api/pyproject.toml`
- Test: `services/api/tests/test_operator_audit.py`

**Interfaces:**
- Consumes: approved tests and signatures in the File and interface map.
- Produces: `OperatorAuditEvent`, `OperatorTransition[T]`, `run_sensitive_admin_attempt`, and `execute_bound_operator_transition` for Tasks 6-7.

- [ ] **Step 1: Register the focused app and strict-type path**

Add `operator_audit.apps.OperatorAuditConfig` to `INSTALLED_APPS`, and add
`operator_audit` to Pyright's `include` list. The app config contains only:

```python
class OperatorAuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "operator_audit"
```

- [ ] **Step 2: Implement the closed enums and model**

Use `UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`, a
`ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)`, bounded
`CharField` choices, `PositiveBigIntegerField`, and `DateTimeField(auto_now_add=True)`.
Add database checks equivalent to:

```python
models.CheckConstraint(
    condition=(
        models.Q(actor_class="unauthorized_actor", outcome="denied")
        | (
            models.Q(actor_class__in=("operator", "emergency_superuser"))
            & ~models.Q(outcome="denied")
        )
    ),
    name="operator_audit_actor_outcome_valid",
)
```

Define closed values for all eight action names and the eight distinct target
types in the spec matrix. Do not add `metadata`, `message`, request, or snapshot
fields.

- [ ] **Step 3: Declare the seven custom operation permissions**

Add these `Meta.permissions` entries to their owning models and generate only the
listed profile, fursuit, and conventions migrations:

```python
("revoke_catch_credential", "Can revoke a current catch credential")
("terminate_catch_session", "Can terminate an active catch session")
("deactivate_fursuit_activation", "Can deactivate a fursuit activation")
("remove_convention_enrollment", "Can remove a convention enrollment")
("set_convention_playability", "Can change Convention playability")
("set_profile_enabled", "Can set player profile enabled state")
("set_fursuit_enabled", "Can set fursuit enabled state")
```

Catch retains its built-in `delete_catch` permission. Inspect migrations to
confirm they contain only model-option permission state.

- [ ] **Step 4: Implement transition and audit writing services**

`OperatorTransition[T]` is the exact two-field frozen dataclass. Keep the writer
private except for tests; it accepts enums and integer IDs, creates one row, and
never accepts dictionaries, strings for log messages, or request objects.

- [ ] **Step 5: Implement the complete-handler admin coordinator**

Implement the two public functions exactly as mapped. Validate `request.user` is
a persisted TailTag `User`. Check superuser before `has_perm`; check staff plus
the exact permission for normal authorization. Use a private request attribute
only to bind the typed attempt during the handler. Wrap the handler and success
audit in an outer `transaction.atomic()` and clear the binding in `finally`.
Translate no-op/known rejection to a sanitized `PermissionDenied` after writing
`rejected`; re-raise unexpected exceptions after rollback and a best-effort
`failed` write. Structured failure logging may contain only action, actor class,
target type, and integer IDs.

- [ ] **Step 6: Generate and inspect the migrations**

Run:

```bash
make api-migrations
git diff -- services/api/operator_audit/migrations/0001_initial.py \
  services/api/profiles/migrations/0002_playerprofile_operator_permission.py \
  services/api/fursuits/migrations/0003_fursuit_operator_permission.py \
  services/api/conventions/migrations/0006_operator_permissions.py
```

Expected: one audit table, its closed fields/check constraints, seven permission
declarations, and no unrelated schema change.

- [ ] **Step 7: Run the audit tests and narrow static gates**

Run:

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_operator_audit.py
uv --directory services/api run --locked --no-sync ruff format --check operator_audit tests/test_operator_audit.py
uv --directory services/api run --locked --no-sync ruff check operator_audit tests/test_operator_audit.py
uv --directory services/api run --locked --no-sync pyright operator_audit tests/test_operator_audit.py
```

Expected: all Task 2 tests pass and static gates report no findings.

- [ ] **Step 8: Commit the audit foundation**

```bash
git add services/api/operator_audit services/api/config/settings/base.py \
  services/api/pyproject.toml services/api/profiles/models.py \
  services/api/profiles/migrations/0002_playerprofile_operator_permission.py \
  services/api/fursuits/models.py \
  services/api/fursuits/migrations/0003_fursuit_operator_permission.py \
  services/api/conventions/models.py \
  services/api/conventions/migrations/0006_operator_permissions.py
git commit -m "feat(api): add durable operator audit events"
```

### Task 4: Author and approve dedicated-operator credential tests

**Role:** Independent `test_author`.

**Files:**
- Create: `services/api/tests/test_bootstrap_staging_operator.py`
- Modify: `services/api/tests/test_accounts.py`
- Test: both files above

**Interfaces:**
- Consumes: the frozen staff-only local-password and provisioning contract.
- Produces: failing AC-2, AC-6, and AC-11 tests without prescribing command internals.

- [ ] **Step 1: Add identity regression tests**

Prove ordinary `create_user` still rejects passwords/staff/superuser flags,
non-staff saves clear usable passwords, dedicated staff may set/check a local
password, superusers remain valid, and demotion from staff clears the local
password. Assert the renamed database constraint rejects a non-staff usable hash.

- [ ] **Step 2: Add guarded command acceptance tests**

Model the existing Development bootstrap test harness, but freeze exact Staging
behavior: environment `staging`, service `api`, TTY required, confirmation phrase
`bootstrap Railway Staging operator`, hidden identifier/password inputs, exact
non-secret success messages, no argument echo, password validation, unused-ID
creation, exact operator reconciliation, named Group permissions, and refusal
without mutation for player, superuser, other-group, direct-permission, or
otherwise ambiguous accounts.

The created identity must satisfy:

```python
assert operator.is_staff is True
assert operator.is_superuser is False
assert operator.check_password(password)
assert set(operator.get_all_permissions()) == EXPECTED_OPERATOR_PERMISSIONS
assert operator.groups.get().name == "TailTag Field Beta Operators"
```

- [ ] **Step 3: Run and confirm the red state**

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_accounts.py \
  tests/test_bootstrap_staging_operator.py
```

Expected: failures point to the existing superuser-only constraint and absent
Staging command.

- [ ] **Step 4: Approve scope and commit red tests**

Map cases to the dedicated-account contract and reject any test that provisions
through Clerk, modifies an ordinary player, or checks group names in application
authorization.

```bash
git add services/api/tests/test_accounts.py services/api/tests/test_bootstrap_staging_operator.py
git commit -m "test(api): define staging operator provisioning"
```

### Task 5: Implement dedicated staff credentials and Staging provisioning

**Role:** Independent `implementer`.

**Files:**
- Modify: `services/api/accounts/models.py`
- Create: `services/api/accounts/migrations/0002_staff_local_password.py`
- Create: `services/api/accounts/management/commands/bootstrap_staging_operator.py`
- Test: Task 4 files

**Interfaces:**
- Consumes: permission codenames from the frozen matrix; permissions are resolved through Django `Permission`, never group-name checks.
- Produces: a guarded interactive Staging command and staff-only local-password invariant.

- [ ] **Step 1: Narrowly expand the local-password invariant**

Keep `create_user` unchanged. Change `_can_use_local_password()` to return
`self.is_staff`; update the check constraint to
`is_staff=True OR password starts with UNUSABLE_PASSWORD_PREFIX`, named
`accounts_user_local_password_requires_staff`. Preserve automatic password
clearing whenever a user becomes non-staff.

- [ ] **Step 2: Write the schema migration**

Create `0002_staff_local_password.py` with only removal of
`accounts_user_local_password_requires_admin` and addition of
`accounts_user_local_password_requires_staff`. Do not rewrite User rows.

- [ ] **Step 3: Implement guarded Staging provisioning**

Adapt the existing Development command's parser, TTY, confirmation, validation,
transaction, race recovery, and secret-suppression patterns. Create/reconcile
only `is_staff=True`, `is_superuser=False`, exact Group membership, and zero
direct user permissions. Resolve and set this exact permission set:

```python
EXPECTED_PERMISSION_NAMES = {
    "catches.delete_catch",
    "catches.view_catch",
    "conventions.revoke_catch_credential",
    "conventions.view_fursuitcatchcredential",
    "conventions.terminate_catch_session",
    "conventions.view_fursuitcatchsession",
    "conventions.deactivate_fursuit_activation",
    "conventions.view_fursuitactivation",
    "conventions.remove_convention_enrollment",
    "conventions.view_conventionenrollment",
    "conventions.set_convention_playability",
    "conventions.view_convention",
    "profiles.set_profile_enabled",
    "profiles.view_playerprofile",
    "fursuits.set_fursuit_enabled",
    "fursuits.view_fursuit",
}
```

The command must fail before mutation if any permission is missing or an existing
identity is not the exact managed operator state.

- [ ] **Step 4: Run focused identity/command tests**

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_accounts.py \
  tests/test_bootstrap_development_operator.py \
  tests/test_bootstrap_staging_operator.py
```

Expected: both Development superuser and Staging non-superuser flows pass without
sensitive output.

- [ ] **Step 5: Commit the credential/provisioning unit**

```bash
git add services/api/accounts services/api/tests/test_accounts.py services/api/tests/test_bootstrap_staging_operator.py
git commit -m "feat(api): provision explicit staging operators"
```

### Task 6: Author and approve the eight-action admin matrix

**Role:** Independent `test_author`.

**Files:**
- Modify: `services/api/tests/test_catch_admin.py`
- Modify: `services/api/tests/test_fursuit_catch_credential_admin.py`
- Modify: `services/api/tests/test_fursuit_catch_session_admin.py`
- Modify: `services/api/tests/test_fursuit_activation_admin.py`
- Modify: `services/api/tests/test_convention_enrollment.py`
- Modify: `services/api/tests/test_player_profile_admin.py`
- Modify: `services/api/tests/test_fursuit_admin.py`
- Modify: `services/api/tests/test_conventions.py`

**Interfaces:**
- Consumes: approved custom codenames and the audit coordinator's observable contract.
- Produces: failing AC-1 through AC-9 tests for each current admin surface.

- [ ] **Step 1: Add the deterministic role matrix**

For every action, cover direct POST attempts by: non-staff player, staff without
the permission, staff with an unrelated sensitive permission, explicitly
permitted non-superuser, and superuser. Assert generic model change/delete does
not substitute, the exact domain state, and exactly one sanitized audit row with
the correct class/outcome. Read tests separately prove `view_*` is read-only and
the sensitive permission grants minimum necessary inspection.

- [ ] **Step 2: Add closed-path and mixed-Convention tests**

Prove admin enrollment add is 403, `is_active` is read-only and forged POST data
cannot change it, new Convention `ACTIVE` is rejected, playable deletion is
rejected, and no audit action outside the approved eight appears. For Convention
changes prove:

```text
change_convention only + non-playable -> non-playable = ordinary success, no audit
change_convention only + non-playable <-> ACTIVE = denied audit
set_convention_playability only + playability transition = audited success
set_convention_playability only + forged name/date = no metadata change
superuser + playability transition = emergency_superuser success
```

- [ ] **Step 3: Add outcome, rollback, and cascade cases**

Per applicable action, cover already-terminal/same-state as `rejected`, a forced
service exception as `failed` with no domain commit, and post-service failure as
rollback with no success row. For profile or fursuit disablement assert existing
credential/session consequences still occur but only one top-level event exists.
Retain all existing secret-concealment, immutable-history, row-lock, and bulk
denial assertions.

- [ ] **Step 4: Run all eight focused admin files and confirm red failures**

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_catch_admin.py \
  tests/test_fursuit_catch_credential_admin.py \
  tests/test_fursuit_catch_session_admin.py \
  tests/test_fursuit_activation_admin.py \
  tests/test_convention_enrollment.py \
  tests/test_player_profile_admin.py \
  tests/test_fursuit_admin.py \
  tests/test_conventions.py
```

Expected: new cases fail because custom permissions/admin audit wiring and closed
paths are absent; established behavior tests continue to pass.

- [ ] **Step 5: Review test adequacy and commit**

Map every case to AC-1 through AC-9 and the role/plausible-mutant matrix. Remove
tests that inspect private helper implementation rather than observable admin,
database, or audit behavior.

```bash
git add services/api/tests/test_catch_admin.py \
  services/api/tests/test_fursuit_catch_credential_admin.py \
  services/api/tests/test_fursuit_catch_session_admin.py \
  services/api/tests/test_fursuit_activation_admin.py \
  services/api/tests/test_convention_enrollment.py \
  services/api/tests/test_player_profile_admin.py \
  services/api/tests/test_fursuit_admin.py \
  services/api/tests/test_conventions.py
git commit -m "test(api): define sensitive admin authorization matrix"
```

### Task 7: Implement admin audit wiring

**Role:** Independent `implementer` with the approved Task 6 tests.

**Files:**
- Modify: `services/api/catches/admin.py`
- Modify: `services/api/catches/services.py`
- Modify: `services/api/conventions/admin.py`
- Modify: `services/api/conventions/services.py`
- Modify: `services/api/conventions/catch_credentials.py`
- Modify: `services/api/conventions/catch_sessions.py`
- Modify: `services/api/profiles/admin.py`
- Modify: `services/api/profiles/services.py`
- Modify: `services/api/fursuits/admin.py`
- Modify: `services/api/fursuits/services.py`
- Test: Task 6 files and existing concurrency/integrity tests

**Interfaces:**
- Consumes: `OperatorTransition`, `run_sensitive_admin_attempt`, and `execute_bound_operator_transition`.
- Produces: all eight audited operation boundaries using the seven custom
  permissions from Task 3 and the preserved Catch delete permission.

- [ ] **Step 1: Return lock-authoritative transition results**

Update only operator service seams to return `OperatorTransition[T]`, setting
`changed=True` inside the locked mutation branch and `changed=False` for
missing/stale/already-terminal/same-state cases. Preserve all lock ordering,
atomic scopes, timestamps, revocation/end reasons, and cascade behavior. Catch
not-found remains a rejection exception; successful removal returns
`OperatorTransition(value=None, changed=True)`.

- [ ] **Step 2: Wire Catch, credential, session, and activation**

Override only the POST mutation entry points. The per-object admin view must call
`run_sensitive_admin_attempt` around `super()` with the exact permission/action/
target tuple. The existing `save_model` or `delete_model` calls
`execute_bound_operator_transition`. Override `has_change_permission`,
`has_delete_permission`, and `has_view_permission` so custom authority grants the
necessary control/read, explicit view grants read-only access, and generic change
does not reveal or authorize a sensitive control. Keep bulk/add/edit/history
restrictions unchanged.

- [ ] **Step 3: Close enrollment authority paths and wire removal**

Return `False` from `has_add_permission`; make `user`, `convention`, and
`is_active` read-only on existing rows; keep `actions=None`; require only
`remove_convention_enrollment` for the individual delete POST; and audit the
existing removal service. Generic `delete_conventionenrollment` must not
substitute.

- [ ] **Step 4: Separate ordinary Convention edits from playability**

On add, reject `status=ACTIVE` through form validation. Reject deletion when the
persisted Convention is playable. On change, compare persisted and submitted
`Convention.is_playable` before mutation. Route a crossing through the sensitive
coordinator; let name/date and non-playable-to-non-playable edits use ordinary
`change_convention` without audit. For a custom-only operator, render name and
dates read-only; server-side checks must also reject forged metadata. Preserve
the service's existing cascade when playability is lost.

- [ ] **Step 5: Wire profile and fursuit enablement**

Make custom permission, not generic `change_*`, control the enabled checkbox and
POST. Keep normal `view_*` read-only. Wrap the existing service and its synchronous
cascade as one action. Update the admin object from `transition.value` only after
the service returns.

- [ ] **Step 6: Run the focused admin and domain regression suites**

Run the Task 6 command, then:

```bash
uv --directory services/api run --locked --no-sync pytest -q \
  tests/test_fursuit_activation_concurrency.py \
  tests/test_fursuit_catch_credential_concurrency.py \
  tests/test_fursuit_catch_session_concurrency.py \
  tests/test_player_profile_concurrency.py \
  tests/test_fursuit_concurrency.py \
  tests/test_convention_concurrency.py \
  tests/test_catch_integrity.py \
  tests/test_fursuit_catch_credential_integrity.py \
  tests/test_fursuit_catch_session_integrity.py \
  tests/test_player_profile_integrity.py \
  tests/test_fursuit_integrity.py
```

Expected: authorization/audit tests and all retained lock/integrity tests pass.

- [ ] **Step 7: Run migration and static gates**

```bash
make api-migrations-check
uv --directory services/api run --locked --no-sync ruff format --check \
  catches conventions profiles fursuits operator_audit tests
uv --directory services/api run --locked --no-sync ruff check \
  catches conventions profiles fursuits operator_audit tests
uv --directory services/api run --locked --no-sync pyright
```

Expected: no migration drift, format/lint/type errors, or unrelated changes.

- [ ] **Step 8: Commit the admin hardening unit**

```bash
git add services/api/catches services/api/conventions services/api/profiles services/api/fursuits services/api/tests
git commit -m "feat(api): harden sensitive operator actions"
```

### Task 8: Document provisioning, emergency use, evidence, and Staging proof

**Files:**
- Create: `docs/operations/operator-authorization-audit.md`
- Modify: `docs/operations/catch-administration.md`
- Modify: `docs/development/staging.md`
- Modify: `services/api/README.md`
- Modify: `services/api/tests/test_runtime_commands.py`

**Interfaces:**
- Consumes: final command name, group name, permission set, audit schema, and admin behavior.
- Produces: AC-11 operator runbook and deterministic documentation assertions; no live operation.

- [ ] **Step 1: Add documentation assertions first**

Extend runtime-command tests to require the exact production-settings Staging
invocation, target guard, hidden inputs, confirmation phrase, and prohibition on
arguments/environment credentials. Add assertions that maintained docs distinguish
normal operator and emergency superuser and name the durable audit source without
printing private identifiers.

- [ ] **Step 2: Run and confirm documentation tests fail**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_runtime_commands.py
```

Expected: new assertions fail on missing #205 documentation.

- [ ] **Step 3: Write the operator runbook**

Document the eight-action matrix, read permissions, named Group as provisioning
convenience only, exact guarded command, emergency-only superuser semantics, four
outcomes, privacy exclusions, indefinite V0 retention, #204 preservation, and the
catastrophic-database-failure limitation. State that audit rows have no viewer and
must be inspected only through approved database/operator procedures.

- [ ] **Step 4: Update Catch, API, and Staging docs**

Replace the old Catch permission/audit-log wording with `delete_catch` plus the
authoritative durable event. Update the API README's superuser-only local-password
claim to the dedicated-staff rule. Add the bounded nine-case Staging matrix and
sanitized evidence template to `staging.md`; mark its execution separately
authorized and destructive only to disposable synthetic records.

- [ ] **Step 5: Run documentation verification**

```bash
uv --directory services/api run --locked --no-sync pytest -q tests/test_runtime_commands.py
./scripts/doctor.sh
git diff --check
```

Expected: documentation tests and required documentation checks pass; the optional
Dev Container warning may remain.

- [ ] **Step 6: Commit documentation**

```bash
git add docs/operations/operator-authorization-audit.md \
  docs/operations/catch-administration.md \
  docs/development/staging.md \
  services/api/README.md \
  services/api/tests/test_runtime_commands.py
git commit -m "docs: define field-beta operator procedure"
```

### Task 9: Deterministic assurance, review, and handoff

**Files:**
- Review: every file changed since the pre-implementation base
- Modify only when resolving an in-scope BLOCKER/HIGH or contract violation

**Interfaces:**
- Consumes: all completed review units and frozen acceptance/test contracts.
- Produces: deterministic evidence, independent findings disposition, and a clean branch ready for separately authorized Staging proof.

- [ ] **Step 1: Run the authoritative repository gate**

```bash
make api-check
```

Expected: full suite passes, including Ruff, strict Pyright, Semgrep, PostgreSQL
tests, Django checks, migration drift, schema, and Gunicorn.

- [ ] **Step 2: Perform plausible-mutant analysis**

Record whether approved tests kill each mutant: replace custom permission with
`is_staff`; accept generic `change_*`; swap two permission codenames; omit denied
events; label superuser as operator; write success after separate commit; retain
success after rollback; emit one event per cascade; allow enrollment add/
`is_active`; allow ACTIVE creation/deletion; serialize a token/provider ID; delete
audit rows during #204 reset. Classify every survivor as missing protection,
equivalent/irrelevant, or requiring judgment. Add only contract-mapped tests for
meaningful survivors.

- [ ] **Step 3: Run independent specification and code reviews**

The fresh specification reviewer maps AC-1 through AC-12 to code/tests/docs. The
fresh code reviewer examines authorization ordering, admin POST reachability,
transaction nesting, audit failure behavior, password/account safety, secret
handling, migrations, concurrency preservation, and scope discipline. Resolve all
BLOCKER/HIGH findings; parent decides MEDIUM findings without automatic expansion.

- [ ] **Step 4: Re-run affected tests and the full gate after fixes**

```bash
make api-check
./scripts/doctor.sh
git diff --check
git status --short --branch
```

Expected: fresh green evidence and no uncommitted/debug/scratch files.

- [ ] **Step 5: Clean task-owned test resources**

Compare `docker ps -a` and `docker network ls` with Task 1. Stop/remove only
disposable resources created by this task and confirmed unused; restore any
pre-existing temporarily started container to its original stopped state. Do not
prune or delete volumes/images.

- [ ] **Step 6: Stop before live Staging acceptance**

Report local AC coverage, migrations, tests, review findings, security/data/API
impact, rollback considerations, retained limitations, and exact proposed Staging
matrix. Obtain separate explicit authorization before provisioning an operator,
deploying, resetting data, or executing any live Staging mutation.
