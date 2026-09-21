# Field-beta operator authorization and auditability

Issue: [#205](https://github.com/TailTag-Game/tailtag/issues/205).
Parent: #197. Prerequisite: #200 (complete). Related reset boundary: #204.

## Status and phase ledger

The user-approved authorization, audit, persistence, provisioning, and Staging
acceptance decisions are frozen by this contract. Execution is STANDARD EXPANDED
with SECURITY, DATA INTEGRITY, and TEST ADEQUACY assurance.

Completed: alignment and focused repository reconnaissance. Current: specification
review. Pending: resolution of the repository discoveries in
[Pre-implementation decisions](#pre-implementation-decisions), environment
readiness, implementation planning, independent test authorship and adequacy
review, implementation, deterministic and assurance gates, independent review,
and bounded Staging validation.

No production implementation or live Staging mutation is authorized by this
specification phase. The frozen portions of this contract must not be weakened to
resolve a discovery.

## Outcome

Existing sensitive Django-admin mutations use explicit operation-level
permissions and produce durable, privacy-safe audit evidence suitable for V0
field-beta operations. Ordinary staff access is not mutation authority.
Authorized non-superuser operators are the normal path; superusers remain an
audited emergency bypass.

## Sensitive-action boundary

An operation is sensitive for #205 when it directly changes gameplay authority,
player eligibility, Convention participation, or immutable gameplay history.
The approved V0 set is:

1. remove an existing Catch;
2. revoke a current catch credential;
3. terminate an active catch session;
4. deactivate a fursuit activation through the operator path;
5. remove a Convention enrollment;
6. disable or re-enable a player profile;
7. disable or re-enable a fursuit; and
8. change an existing Convention between playable and non-playable lifecycle
   states.

Convention name/date corrections and status changes that remain entirely within
the non-playable status set are ordinary administration. Existing ordinary CRUD
that does not cross an authority or eligibility boundary continues to use normal
Django model permissions.

Repository inspection found additional current admin mutations that meet the
sensitive-action definition but are not in the approved set. They are recorded
as explicit decisions rather than silently added; see
[Pre-implementation decisions](#pre-implementation-decisions).

## Non-goals

#205 does not add product actions, operator HTTP APIs, arbitrary catch awards,
an alternate gameplay-authority path, generalized RBAC, an operator-management
UI, an audit-log viewer, justification or approval workflows, provider identity
redesign, per-cascade event sourcing, #198 observability/dashboard work, #204
reset implementation, backup/restore, migration rehearsal, load simulation,
production deployment, or unrelated V1 behavior.

## Repository evidence and current boundaries

The registered project admin classes are `accounts.User`, `catches.Catch`,
`conventions.Convention`, `conventions.ConventionEnrollment`,
`conventions.FursuitActivation`, `conventions.FursuitCatchCredential`,
`conventions.FursuitCatchSession`, `fursuits.Fursuit`, and
`profiles.PlayerProfile`. Django also retains its framework Group administration.

Current sensitive mutations delegate to established transactional domain seams:

- `catches.services.remove_catch_as_operator`;
- `conventions.catch_credentials.revoke_catch_credential_as_operator`;
- `conventions.catch_sessions.terminate_session_as_operator`;
- `conventions.services.deactivate_fursuit_activation_as_operator`;
- `conventions.services.remove_convention_enrollment`;
- `profiles.services.set_profile_enabled`;
- `fursuits.services.set_fursuit_enabled`; and
- `conventions.services.set_convention_admin_state`.

Those services remain authoritative state-transition boundaries. They do not
become request-aware authorization services. The Django-admin boundary owns
actor authentication, permission enforcement, outcome classification, and audit
orchestration before invoking a service.

The current Catch admin already treats `catches.delete_catch` as explicit
individual correction authority and ties Catch inspection to it. The remaining
sensitive forms currently depend primarily on generic `change_*` permissions.
The implementation must replace that implicit authority without reopening
forbidden add, bulk, history-edit, reassignment, reactivation, or arbitrary
award paths.

## Definitive action and permission matrix

Every row also requires an authenticated `is_staff=True` user so Django admin is
reachable. `is_staff` alone never grants model inspection or mutation authority.
Except for the documented Catch exception, a generic `view_*`, `change_*`, or
`delete_*` permission never substitutes for the sensitive permission.

| Audit action | Target | Sensitive permission | Read boundary | Existing domain seam | Committed top-level effect |
| --- | --- | --- | --- | --- | --- |
| `remove_catch` | `catches.catch` | Preserve `catches.delete_catch` as the explicitly documented correction authority; a new codename provides no material separation because Catch has no other delete path | `view_catch` permits read-only inspection; `delete_catch` also permits the inspection necessary to correct | `remove_catch_as_operator` | One Catch is removed; no add, edit, or bulk path |
| `revoke_catch_credential` | `conventions.fursuitcatchcredential` | `conventions.revoke_catch_credential` | `view_fursuitcatchcredential` or the sensitive permission; read-only users never receive the revoke control | `revoke_catch_credential_as_operator` | The current credential becomes terminal with operator reason; no replacement or session mutation |
| `terminate_catch_session` | `conventions.fursuitcatchsession` | `conventions.terminate_catch_session` | `view_fursuitcatchsession` or the sensitive permission; read-only users never receive the terminate control | `terminate_session_as_operator` | The active session becomes terminal with operator reason |
| `deactivate_fursuit_activation` | `conventions.fursuitactivation` | `conventions.deactivate_fursuit_activation` | Normal `view_fursuitactivation` or the sensitive permission | `deactivate_fursuit_activation_as_operator` | Active becomes inactive; activation/reactivation remains unavailable in admin |
| `remove_convention_enrollment` | `conventions.conventionenrollment` | `conventions.remove_convention_enrollment` | Normal `view_conventionenrollment` | `remove_convention_enrollment` | One enrollment is removed and existing lifecycle consequences run |
| `set_profile_enabled` | `profiles.playerprofile` | `profiles.set_profile_enabled` | Normal `view_playerprofile` | `set_profile_enabled` | Enabled state changes to the submitted boolean and existing lifecycle consequences run |
| `set_fursuit_enabled` | `fursuits.fursuit` | `fursuits.set_fursuit_enabled` | Normal `view_fursuit` | `set_fursuit_enabled` | Enabled state changes to the submitted boolean and existing lifecycle consequences run |
| `set_convention_playability` | `conventions.convention` | `conventions.set_convention_playability` | Normal `view_convention`; ordinary metadata editing remains governed by `change_convention` | `set_convention_admin_state` | An existing Convention crosses between `ACTIVE` and the non-playable status set; any same-form metadata correction commits atomically |

Custom permissions are declared through the owning model's Django `Meta`
permissions and created through normal migrations. Authorization checks use
permission codenames, never hard-coded group names. A sensitive permission is
sufficient for its operation and the minimum target inspection required to
perform it; operators do not also need a generic `change_*` permission merely as
an accidental Django-admin prerequisite.

For the mixed Convention form:

- `change_convention` permits ordinary metadata corrections and status movement
  wholly within the non-playable set;
- `set_convention_playability` is mandatory whenever the persisted and submitted
  states differ in `Convention.is_playable`;
- a user with only ordinary change authority is denied before a playability
  transition reaches the service; and
- field/form handling must not let a narrowly authorized playability operator
  acquire unrelated metadata-edit authority accidentally.

## Read authorization

Catch, credential, and catch-session records expose intentionally restricted
gameplay or operational information. Their corresponding sensitive permission
grants the minimum inspection needed for the operation; their explicit Django
`view_*` permission grants read-only inspection. Read-only users must not see or
invoke sensitive controls.

Activation inspection may use `view_fursuitactivation` or the sensitive
deactivation permission. Profiles, fursuits, Conventions, and enrollments retain
normal explicit `view_*` behavior unless implementation reconnaissance finds a
specific field that violates an existing privacy contract. #205 does not create
a generalized read-role hierarchy. Broad `is_staff` alone never bypasses
Django's model permission checks.

Denied GET/browse attempts and the absence of general model-view permission do
not create operator audit events.

## Durable operator audit record

Introduce one narrowly scoped Django application/module for operator auditing,
with a durable `OperatorAuditEvent` model that is not registered as a new admin
viewer and is not exposed through an API. This is a cross-domain audit seam, so
it does not belong to any one gameplay model.

The authoritative record contains exactly:

| Field | Contract |
| --- | --- |
| `id` | Server-generated UUID primary key; stable event identity |
| `action` | Closed choice from the approved sensitive-action names |
| `actor` | `PROTECT` foreign key to the TailTag/Django `User`; evidence exposes only its application primary key |
| `actor_class` | Closed actor classification; the approved values and the denied-event conflict are described below |
| `affected_record_type` | Closed, stable app/model label from the action matrix |
| `affected_record_id` | Positive database record identifier supplied by the action boundary |
| `outcome` | `succeeded`, `denied`, `rejected`, or `failed` |
| `occurred_at` | Server-controlled creation timestamp |

V0 does not add a metadata JSON field. The approved consequence-count use case is
optional, and omitting an open-ended metadata container gives the strongest
privacy boundary. A later requirement may add a separately reviewed bounded
schema.

The model has no product/admin mutation surface. The audit writer accepts closed
typed values rather than arbitrary messages or request data. It never stores
Clerk identifiers, emails, credentials, QR payloads, tokens, private URLs, raw
request bodies, broad permission/group snapshots, broad object snapshots, or
exception detail.

Django `LogEntry` may continue as framework history, and structured application
logs may mirror sanitized events for visibility. Neither is the authoritative
audit contract.

## Actor classification and emergency superusers

The frozen successful-action classifications are:

- `operator`: authenticated non-superuser staff authorized by the action's
  explicit sensitive permission; and
- `emergency_superuser`: authenticated superuser exercising Django's normal
  permission bypass.

Every superuser sensitive mutation records `emergency_superuser`. Superuser
credentials are emergency-only, not the normal operator model. #205 adds no
interactive justification, approval flow, or separate break-glass account
system.

The frozen list does not provide a truthful actor class for denied attempts by a
player or staff user lacking the target permission. This must be resolved before
the audit schema is implemented; see D4 below.

## Outcome and transaction semantics

The Django-admin mutation boundary classifies exactly one top-level attempt:

- `succeeded`: the requested state transition and its authoritative audit row
  commit together;
- `denied`: an authenticated user submits a defined sensitive mutation but lacks
  its explicit authority;
- `rejected`: the actor has authority, but the request is invalid under the
  domain contract or current state, including a stale/terminal target or a
  request that produces no requested transition; and
- `failed`: an authorized operation raises an unexpected failure and does not
  commit its domain transition.

A successful admin operation wraps the existing service call and audit insert in
one outer database transaction. Existing service-level `transaction.atomic()`
blocks become nested savepoints; the domain change and `succeeded` event therefore
share the outer commit. The admin layer must not emit success with
`transaction.on_commit()` after a separately committed domain mutation.

Authorization denial occurs before the service call and writes a sanitized
`denied` event without domain mutation. Expected domain rejection runs inside a
transaction that rolls back before a separate sanitized `rejected` event is
written. Unexpected failure follows the same rollback-first shape before a
best-effort `failed` event is written in a clean transaction. Diagnostic
exception detail belongs only in sanitized structured application logging.

Audit persistence must never cause a failed domain transaction to be reported as
successful. A catastrophic database failure may prevent both domain work and the
follow-up failure event; this unavoidable limitation is documented rather than
weakened with an external log-retention dependency.

Direct POST attempts against nonexistent identifiers may record the requested
positive identifier with `rejected` or `denied`, as applicable, without copying
request bodies or attacker-controlled representations. Browsing, GET, HEAD, and
OPTIONS do not create these events.

## Cascading effects

Audit only the operator's top-level intent. Profile/fursuit disablement,
activation deactivation, enrollment removal, and Convention playability loss may
synchronously revoke credentials or terminate sessions through existing domain
services. Those consequences do not become separate operator-action events.

The first implementation omits consequence counts. Existing or future domain
observability may expose consequences under #198, but it must not represent them
as independent operator intentions.

## Persistence and reset interaction

Operator audit rows follow normal application-data durability and backup
expectations and remain until a future documented retention policy explicitly
purges them. #205 defines no automatic expiry.

The #204 reset implementation deletes only its registered rehearsal-domain
closure and currently preserves Users, groups, and permissions. The new audit
table is outside that deletion closure and must remain preserved. Audit rows use
no foreign key to disposable target records, so reset can remove synthetic domain
targets without cascading or blocking retained evidence. The actor `User` foreign
key uses `PROTECT`, consistent with retained operator identity.

#205 does not modify reset/reseed behavior merely to make audit evidence
disposable. Any future #204 decision to purge rehearsal audit evidence requires a
separate explicit contract change.

## Operator provisioning

Use Django's existing User, Group, and Permission machinery. Authorization checks
permissions, never group names. The supported Staging procedure should:

1. resolve a dedicated operator identity without elevating an ordinary player;
2. set `is_staff=True` without `is_superuser=True`;
3. create or reconcile one clearly named operator Group if maintainers choose the
   group-based procedure;
4. assign only the approved view and sensitive-operation permissions;
5. attach the dedicated operator to that Group; and
6. verify effective permissions without printing credentials or provider
   metadata.

The procedure must be idempotent or fail closed on ambiguous existing identity
state. It is provisioning documentation/tooling around Django's native machinery,
not a new operator-management product. The Development superuser bootstrap
remains development convenience and is not the normal Staging operator role.

Current `accounts.User` code and its database constraint prohibit usable local
passwords unless both `is_staff` and `is_superuser` are true. Django admin has no
Clerk authentication path. Therefore the approved non-superuser Staging operator
cannot currently authenticate. D5 must select the narrow authentication change
before this procedure can be frozen.

## Staging acceptance matrix

Use disposable synthetic records in isolated Staging. Do not publish credentials,
provider/account identifiers, private URLs, tokens, or raw logs. At minimum prove:

1. an ordinary player cannot browse or execute a sensitive admin mutation;
2. `is_staff=True` without the target sensitive permission is denied;
3. an explicitly permitted non-superuser operator succeeds;
4. an operator permitted for one action cannot cross a different sensitive
   permission boundary;
5. a superuser succeeds and the durable audit row says
   `actor_class=emergency_superuser`;
6. success creates one sanitized durable row containing action, actor application
   ID/class, target type/ID, `succeeded`, and time;
7. a submitted unauthorized mutation creates one sanitized `denied` row;
8. one profile- or fursuit-disable cascade preserves existing transactional and
   data-integrity behavior while producing one top-level audit row; and
9. Catch add/edit/bulk operations and every alternate arbitrary award path remain
   unavailable.

Use #204 reset/reseed to restore disposable domain state when appropriate, but
do not delete retained audit rows or change #204 implementation in this issue.
Live Staging mutation requires separate explicit authorization and the approved
operator identity/target preflights.

## Acceptance Contract

| ID | Observable requirement |
| --- | --- |
| AC-1 | The approved sensitive actions use the exact explicit permissions in the matrix; staff and generic permissions never silently substitute |
| AC-2 | Ordinary players and unauthorized staff cannot execute sensitive mutations; explicitly permitted non-superusers and emergency superusers follow their approved paths |
| AC-3 | Catch, credential, and session inspection follows the proportional read boundary without creating generalized RBAC |
| AC-4 | Every submitted sensitive attempt receives the defined outcome when persistence is available; GET/view denials do not create audit events |
| AC-5 | A successful domain transition and its authoritative audit row commit atomically; rollback emits no success row |
| AC-6 | Audit rows use only the closed privacy-safe schema and never contain prohibited identity, credential, payload, request, snapshot, or exception data |
| AC-7 | One top-level action produces one top-level audit event despite synchronous lifecycle cascades |
| AC-8 | Existing ownership, locking, append-only history, terminal-state, and catch-authority rules remain intact |
| AC-9 | No Catch add/edit/bulk award, credential replacement, session history edit, activation/reactivation, or other alternate gameplay-authority path is introduced |
| AC-10 | Audit evidence survives ordinary #204 Staging reset/reseed and has no automatic V0 expiry |
| AC-11 | Maintainer documentation defines normal explicit permission provisioning, emergency-superuser meaning, evidence safety, and the supported Staging procedure |
| AC-12 | The bounded Staging matrix passes with synthetic state and sanitized retained evidence |

## Test Surface Contract

Tests may exercise:

- Django admin HTTP views with real authenticated TailTag users and Django
  permissions;
- registered `ModelAdmin` permission/form methods where an HTTP assertion cannot
  isolate the boundary;
- the existing public/package-internal domain service seams listed above;
- the audit writer and `OperatorAuditEvent` ORM model;
- real PostgreSQL transactions, row locks, commit/rollback behavior, model
  constraints, and Django `transaction.on_commit()` where existing behavior uses
  it; and
- the existing Staging operator-command/process boundaries with controlled
  external responses for deterministic tests.

Tests must not expose a production API for convenience, bypass the admin boundary
to claim authorization coverage, weaken existing concurrency/integrity tests,
or assert secrets/provider metadata. Extend the closest existing admin test files
before creating broad new test infrastructure. Independent test authors map every
new case to an Acceptance Contract item, the security/data-integrity assurance
matrix, or an approved regression risk.

Required deterministic role coverage per sensitive action is: ordinary player,
staff without the target permission, explicitly permitted non-superuser,
cross-permission operator, and superuser where applicable. Targeted
plausible-mutant analysis must show tests reject at least: `is_staff` as authority,
generic `change_*` substitution, wrong permission codename, missing denied event,
success emitted before commit, success retained after rollback, superuser
misclassified as operator, cascade fan-out events, and secret-bearing audit data.

## Scope Guard

**Outcome:** explicit operation permissions and durable privacy-safe evidence for
the approved existing sensitive actions.

**Non-goals:** all items in the Non-goals section, including new actions,
generalized roles, operator/audit UIs, provider redesign, observability, and reset
implementation.

**Expected change surface after approval:** owning domain model metadata and
migrations for permissions; the existing admin classes and closest admin tests;
one narrow audit model/writer and migration with focused tests; the existing
operator/catch/Staging documentation; and only the minimum account/provisioning
surface approved under D5. Domain services change only where their current return
or exception contract cannot distinguish committed transition, expected
rejection, and no-op without duplicating domain rules in admin.

**Proof:** focused permission/outcome/transaction/privacy tests, existing domain
and concurrency regressions, migration-drift checks, repository `make api-check`
including Semgrep, plausible-mutant analysis, fresh specification and code review,
and separately authorized bounded Staging proof.

## Pre-implementation decisions

Repository inspection produced the following material decisions. Implementation
must not start until they are resolved and incorporated into this contract.

### D1 — Admin enrollment creation

`ConventionEnrollmentAdmin` currently permits `add_conventionenrollment`.
Creating a row directly establishes Convention participation and therefore meets
the frozen sensitive-action definition, but it is not in the approved mutation
set. The recommended minimum-scope resolution is to disable admin enrollment
creation; players already own enrollment creation through the authoritative API.
The alternative is to add a ninth sensitive action and permission.

### D2 — Admin active-Convention selection

The same admin currently allows generic `change_conventionenrollment` to mutate
`is_active`, which changes the player's selected gameplay Convention. The
recommended resolution is to make enrollment identity and `is_active` read-only
and retain only the explicitly approved removal action. The alternative is to add
separate sensitive set/clear-selection actions and permissions.

### D3 — Playable Convention creation and deletion

`ConventionAdmin` currently accepts `status=ACTIVE` during creation and exposes
normal deletion. Creating an already-playable Convention or deleting an ACTIVE
Convention crosses the gameplay-authority boundary without changing an existing
record between lifecycle states. The recommended resolution is to require new
Conventions to start non-playable and to reject deletion while playable; the
approved `set_convention_playability` transition then remains the sole path across
the boundary. The alternative is to add separately audited create-playable and
delete-playable actions.

### D4 — Actor class for denied attempts

The approved actor classes describe authorized operators and superusers, but a
player or staff user denied for lacking the target permission satisfies neither
definition. The recommended resolution is to add one bounded
`unauthorized_actor` class used only with `outcome=denied`; retain `operator` and
`emergency_superuser` exactly as frozen for authorized attempts. Alternatives are
to make actor class nullable on denial or redefine `operator` to include
unauthorized staff, both of which weaken interpretation.

### D5 — Non-superuser Django-admin authentication

The User model, manager, and database constraint currently reserve usable local
passwords for superusers, while Django admin has no Clerk sign-in mechanism. The
approved Staging non-superuser operator therefore cannot log in. The recommended
minimum change is a narrowly guarded dedicated-staff local credential contract and
provisioning path that cannot elevate or repurpose an ordinary player account.
Adding Clerk-backed admin authentication would be a provider/identity redesign and
is outside #205; retaining superuser-only login cannot satisfy the frozen Staging
matrix.

## Design alternatives considered

The selected design uses operation-specific admin guards, existing domain
services, and one closed cross-domain audit writer. Making every domain service
request/user-aware was rejected because authorization belongs to Django admin and
would couple player/domain seams to HTTP actors. A generic policy engine or audit
middleware was rejected as generalized RBAC/infrastructure: it would obscure
transaction boundaries and exceed the eight-action V0 contract. Railway logs or
Django `LogEntry` alone were rejected as authoritative because their retention,
schema, and outcome semantics do not meet the frozen contract.
