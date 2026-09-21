# Staging synthetic-state reset and reseed

Issue: [#204](https://github.com/TailTag-Game/tailtag/issues/204).
Parent: #197. Prerequisites: #200 and #203. Simulation consumers: #199/#220.

## Status and phase ledger

User-approved reset/reseed behavioral boundaries are frozen by this contract.
Execution: STANDARD EXPANDED. Assurance: SECURITY, DATA INTEGRITY, RELIABILITY,
TEST ADEQUACY. Completed: alignment and focused model/platform reconnaissance.
Completed additionally: user authorized local implementation; concrete manifest,
operational design and Test Surface Contract are frozen in the
[implementation handoff](2026-09-17-staging-synthetic-reset-reseed-implementation-plan.md).
Environment baseline `make api-check` passed all gates on task-owned PostgreSQL 17.
Completed additionally: independent proposed acceptance matrix and parent
adequacy/scope approval before production implementation; first 52 authored cases
failed for the expected absent modules. Independent safety design review passed
after actual control-connection identity and committed-gate details were added.
Production implementation and independently authored tests pass Ruff and strict
Pyright checks, with no migration drift; the focused suite passes 88 cases.
Parent test-adequacy approval includes direct sentinel/asset denial, wrong actual
control identity and committed-gate-before-drain evidence with an existing writer.
Final `make api-check` confirmation passed: 1,807 tests, full strict typing,
Ruff, Semgrep and system/migration/schema/Gunicorn checks. Fresh independent
specification review passed with no findings.
Fresh code review identified one HIGH failure-classification gap: interruption
during initial quiescence or destructive reset escaped the fixed failure handler.
Independent tests reproduced six CLI failures; the minimal three-handler correction
now passes 95 focused cases and strict typing/Ruff. Local integrated operator proof
also passed real transaction rollback and retained maintenance for RuntimeError,
KeyboardInterrupt and SystemExit, with sensitive payloads suppressed.
Code reviewer recheck passed and closed the HIGH finding; no required issues remain.
Local implementation and assurance are complete for AC-1 through AC-9; all 95
focused cases also pass under CI-equivalent production settings. The task's
disposable PostgreSQL container was removed; its reusable volume is preserved.
Completed additionally: the user authorized live Staging proof and then separately
authorized one-time fixture preparation. The initial missing-fixture denial was
resolved without changing reset boundaries. The schema-only registry migration,
explicit sentinel provisioning, two equivalent live resets, preservation checks
and normal service resumption passed. AC-10 evidence is recorded below. No API
application deployment, Git commit, push or PR was performed by this proof.
Fresh independent AC-10 specification review passed. Final canonical preflight,
doctor required checks and diff validation passed after live proof and cleanup;
the optional Dev Container CLI remains unavailable.

## Outcome and non-goals

An approved operator or automation can restore one small repository-defined V0
rehearsal baseline on positively identified, quiescent Staging. Reset ownership
is explicit; synthetic Staging status alone never authorizes deletion.

This is not a fixture factory, online gameplay mutation protocol, migration or
schema-management substitute, Production reset, arbitrary truncation/flush,
backup/restore or recovery mechanism, observability implementation, or unrelated
backend/V1 work. Per-run populations, conventions, scenarios, large fixtures,
and disposable simulation media cleanup belong to #199/#220.

## Preservation and reset boundary

| State | Required treatment |
| --- | --- |
| Schema and Django migration history | Preserve; normal migrations remain separate |
| Infrastructure, configuration, secrets, environment setup and storage isolation | Preserve |
| Django/operator/admin identities, passwords, groups and permissions | Preserve |
| Reusable synthetic Clerk identity pool | Preserve; no deletion or recreation |
| TailTag `User` rows bound to reusable Clerk identities | Preserve identity and bindings |
| Designated baseline synthetic media objects | Preserve and reuse existing object keys |
| Database sentinel | Preserve; reset cannot provision or replace it |
| Explicitly owned rehearsal `Catch` records | Reset; baseline contains none |
| Owned catch credentials and sessions | Reset including historical/revoked/ended records |
| Owned activations and enrollments | Reset and reconstruct canonical state |
| Owned rehearsal Conventions and Fursuits | Reset/reseed |
| Baseline identities' `PlayerProfile` domain state | Restore deterministic baseline profiles |
| Unowned records and external objects | Preserve; ambiguous ownership or dependency conflicts deny reset |

The implementation design must freeze an explicit ownership manifest/registry
and dependency closure before tests or implementation. Names, prefixes, user
ownership, or current row values alone must not become broad deletion authority.
Unexpected unowned dependencies must cause denial or transactional rollback,
not expansion of the deletion set. Simulation records do not become #204-owned.

## Canonical baseline

Maintain exactly one small, versioned repository-defined manifest using stable
logical fixture identifiers. Resolve a fixed set of already-existing synthetic
Clerk identities and their existing TailTag Users; missing identity is a denial,
not permission to create/rebind users. Restore completed deterministic enabled
profiles, one canonical synthetic Convention, a small fixed set of synthetic
Fursuits owned by baseline identities, and documented deterministic enrollment
and activation statuses. Profile avatars and required fursuit photos reference
designated pre-provisioned synthetic objects using existing valid opaque keys.

The baseline has zero historical Catches and zero leftover catch sessions; any
intentional baseline session must be expressly specified in the manifest.
Current catch credentials are seeded only if expressly required by the baseline;
no historical or unwanted credentials remain. Do not change production token
generation/security rules merely to make token bytes deterministic.

The concrete manifest now enumerates aliases, fields, dates, statuses, asset
binding, and a baseline with zero credentials/sessions in the implementation
handoff. The small fixed-baseline boundary is frozen. Ordinary smoke/rehearsal can start an
owner session through existing behavior rather than require reset to keep a
time-limited session active forever.

Repeatability means semantic equivalence: same identities, profile values,
relationships and statuses; no duplicate baseline objects, unwanted historical
catches/sessions/credentials, or media accumulation; all domain invariants hold.
Database PKs and generated timestamps may differ. Preserve any stable identifier
that an existing public contract requires, including persistent fursuit identity
when used as an external fixture reference. Verify logical state, not identical
PKs or creation times.

## Safety and maintenance protocol

Before opening the destructive transaction, all of these must pass:

1. Reuse #203 public preflight at exactly `https://staging.tailtag.app`, capturing
   its valid immutable source/deployment identity, Staging environment and readiness.
2. Reset runtime positively identifies itself as Staging and reset capability is
   explicitly enabled only for Staging.
3. The actual connected database contains a valid persistent Staging-only random
   environment identifier matching an independently configured expected value.
   Missing, malformed, unknown, Development, Production, copied or mismatched
   targets fail closed. Sentinel schema may be migrated normally, but ordinary
   migrations must not populate reset-capable identity in every environment.
   Provisioning is an explicit, separately guarded Staging operator step; reset
   must never self-initialize the sentinel. Expected identifiers are not printed.
4. Required fixture identities and external assets are safely resolved/read
   before destructive work. Signing a media URL alone does not prove availability.
   External verification is read-only, bounded, and sanitized on failure.
5. Ordinary Staging writers are positively quiescent, including admin, all API
   replicas, workers/scheduled writers and in-flight transactions. An operator
   acknowledgement, failed HTTP request or advisory lock alone is insufficient.

Use the smallest infrastructure-supported maintenance mechanism. Establish
preflight while the canonical API is live, then stop/drain all relevant writers
and prevent replacement/pending deployments or automation from resuming writes
during maintenance. Bind the preflight, explicit runtime/database checks and
quiescence proof to one bounded operator execution; a detached stale preflight
receipt is insufficient. If the maintenance interval or target cannot be proved,
deny before destruction. The reset executor must remain available independently
of stopped gameplay processes. Recheck database identity on the same connection
used for mutation and prevent target switching. Serialize competing resets as
well; serialization does not substitute for quiescing ordinary writers.

Only after successful reconstruction/validation and commit may normal service
resume. Re-run public preflight/readiness and verify the baseline. The baseline
is authoritative when reset completes and normal service resumes, until later
gameplay changes it. Failure recovery distinguishes rollback from committed reset
with failed service resumption; never report either as complete success. A failed
maintenance/reset must leave writes prevented until safe resumption is confirmed.

## Atomic database operation

Perform scoped dependency-aware destructive cleanup and reconstruction in one
PostgreSQL transaction. Validate expected baseline and preserved-state invariants
before commit where practical. A reconstruction, validation or database failure
rolls back previous domain state rather than committing a partial baseline.
No unrestricted truncation, generic Django flush, identity deletion, Clerk writes,
R2 uploads/deletions, bucket/prefix sweeping or external rollback cleanup.

## Repository and Railway evidence

Inspected 2026-09-17:

- `accounts/models.py`: custom Django `User` owns Clerk binding, admin flags and
  permission relationships. Preserve these rows; do not use user cascades to reset.
- `profiles/models.py`: profile is one-to-one with User; unique handles and paired
  onboarding fields constrain reconstruction. Conflicting unowned handles deny.
- `conventions/models.py`: enrollment protects Convention; activation protects
  Convention and Fursuit; session/credential protect activation. Unique active
  enrollment, activation pairing, current credential and unended session invariants
  remain authoritative.
- `catches/models.py`: Catch protects User, Fursuit, Convention, activation and
  session. Remove owned catches first, then owned sessions/credentials, activations
  and enrollments, then owned fursuits/conventions; restore profiles without deleting
  Users. Verify the final concrete closure rather than assume a global table purge.
- `fursuits/models.py`: owner is protected; `tailtag_id` is a unique UUID and photo
  key is mandatory. Logical fixtures must account for persistent public identity.
- No production model deletion signals were found that automatically delete media.
  `media/service.py` explicitly deletes replaced/cleared images: avoid those mutation
  paths in reset. `media/storage.py` supports read/head checks without uploads;
  `media/keys.py` requires `images/<32 lowercase hex>.(jpg|png|webp)`, so do not invent
  human-readable baseline prefixes that violate the existing media contract.
- `conventions/catch_credentials.py` uses secure random token generation and session
  eligibility; semantic determinism must not weaken these existing rules.
- `scripts/api_staging_promote.py` checks explicit Railway selectors, disabled
  autodeploy and exact deployment evidence. Reuse those conventions; disabled
  autodeploy alone does not establish absence of writers or manual promotions.
- Installed Railway CLI is 5.57.2. Local `railway run --help` states it runs a
  **local** process with selected environment variables. `railway ssh --help`
  selects a deployment instance; it is not an executor after that instance stops.
  No authenticated live Railway calls or configuration inspection occurred here.

Railway's official [deployment reference](https://docs.railway.com/deployments/reference)
documents removing a running deployment while preserving the service.
The [deployment API](https://docs.railway.com/integrations/api/manage-deployments)
documents exact-ID stop, cancel and redeploy operations. Prefer explicit IDs over
[`railway down`](https://docs.railway.com/cli/down), which selects the latest
successful deployment and does not prove all writers stopped. These mechanisms
are design candidates, not verified task-specific maintenance guarantees.

### Concrete constraints to resolve in operational design

Stopping the API removes the #203 HTTP endpoint and the API SSH execution surface.
Therefore preflight must precede verified quiescence, with an independent executor
using positively verified Staging configuration/database connectivity. Do not
silently replace mandatory preflight with an expected outage. Actual executor
connectivity and stop/drain/resume evidence must be validated before implementation
is treated as operationally ready; private database DNS cannot be assumed reachable
by `railway run` on the operator machine.

A full database copy also copies its sentinel. Sentinel equality alone cannot
detect a clone carrying the original expected identifier/configuration. Keep the
sentinel plus independent expected value, and bind the actual database connection
to the approved Staging database resource through independently verified operator
configuration/resource identity. Copies must lose reset capability and receive
new environment identity; copied settings/sentinel cannot be accepted as proof.
The implementation handoff adds independently pinned endpoint/name and PostgreSQL
cluster identity binding, and PostgreSQL connection gating with a separate control
connection rather than stopping the API deployment. This is
an accidental-targeting guard, not cryptographic attestation against an actor able
to clone all trusted configuration and credentials.

Neither constraint changes the frozen preservation/atomicity boundaries. No
other inspected model/platform constraint makes them impractical.

## Acceptance Contract

| ID | Observable requirement |
| --- | --- |
| AC-1 | Explicit ownership/preservation manifest covers all relevant V0 models and conflicts; unowned state survives |
| AC-2 | One guarded operation restores the enumerated small canonical baseline using existing identities/assets |
| AC-3 | Two runs produce semantic equivalence without duplicate records, historical clutter or media accumulation |
| AC-4 | Users/admin permissions, migration history/schema, sentinel, infrastructure/secrets and external objects survive |
| AC-5 | Every preflight/runtime/capability/database/asset guard denies unsafe or uncertain targets before destructive work |
| AC-6 | Positive quiescence prevents ordinary writes throughout reset; inability to prove it denies destruction |
| AC-7 | Cleanup/reseed/validation is one transaction; injected failure restores previous domain state |
| AC-8 | Dependency-aware scope and domain/public identity invariants hold; no generic flush/truncation or external mutation |
| AC-9 | Tests cover successful reseed, preservation/conflicts, repeatability, every safety denial, quiescence and rollback |
| AC-10 | Actual Staging proof records sanitized baseline and safe service resumption; documentation explains limitations and failure cleanup |

## Test Surface and Scope Guard

Extend existing Django/PostgreSQL test patterns for real transaction rollback,
model constraints and preserved permissions/state. Test the eventual operator
orchestration at its external transport/process boundaries with controlled
Railway/HTTP/asset responses, including denial before destructive invocation,
pending/replacement writers, failed quiescence, target mismatch and failed resume.
Assert zero Clerk/R2 mutation calls. Independent test authors receive this frozen
contract and the enumerated manifest/signatures, not a proposed implementation.
No test-only public production API or new test infrastructure is approved.

Current implementation scope and exact files/proof are in the implementation handoff.
Live operations, provisioning or secrets changes remain outside this phase.
Later proof: environment baseline, independent tests/adequacy, `make api-check`
including Semgrep, plausible-mutant analysis of destructive guards/ownership/
atomicity, fresh spec/code review, controlled live rehearsal and sanitized evidence.
Track/clean task-created test containers/networks while preserving volumes.

## Verification evidence

On 2026-09-17, `./scripts/doctor.sh` passed all required checks on
`docs/204-reset-reseed-contract`; the optional Dev Container CLI was unavailable.
`git diff --check` passed. Parent contract/scope review accounts for all eight
user-approved decision groups and AC-1 through AC-10; the exact manifest and
operational binding remain explicit pre-implementation gates. No application
code or external state changed in that documentation phase. Local implementation
testing used container `tailtag-issue-204-postgres` and volume
`tailtag-issue-204-postgres-data`. The disposable container was stopped/removed and
its absence verified; the reusable volume was preserved and verified. No task
network was created and no unrelated containers were started.

Read-only canonical #203 preflight also passed during implementation on
2026-09-17, observing source `04f8383fe750bec712ced27a1932b82b1eabb292` and
deployment `57f17ef7-7b34-4c2f-9272-b8091b1eafad`, environment `staging`.
This is prerequisite availability evidence only, not #204 database binding,
provisioning, maintenance or reset acceptance.

Local integrated operator proof used a disposable database on task-owned
PostgreSQL 17, real migrations/ORM/maintenance connections and the normal S3
adapter with a read-only fake client. Only public preflight transport and external
asset transport were controlled. The operator entry point provisioned an empty
sentinel, reset twice with equivalent semantic counts and preserved root bindings,
then rolled back an injected precommit validation failure while leaving connections
disabled. Explicit local recovery restored connections and verified the prior
baseline. The disposable proof database was dropped in `finally`. Native invalid
confirmation and unknown-argument invocations exited 1 with only the fixed
confirmation failure. These checks do not establish live Railway privileges,
private endpoint reachability or Staging acceptance.

Final local implementation evidence on `feat/204-staging-reset-reseed`:

- `make api-check`: 1,807 tests passed (474 existing warnings), Ruff formatting/
  lint and strict Pyright passed, Semgrep 9/9 fixture checks and 9 rules on 206
  files produced zero findings, Django checks/migration drift/schema/Gunicorn
  checks passed. No dependency or lockfile changes were required.
- Independent specification review passed AC-1 through AC-9. Independent code
  review passed after closing its one HIGH interruption-classification finding.
  Six new CLI regressions failed before the three-handler correction and passed
  afterward; real late-validation rollback also covers KeyboardInterrupt.
- The focused suite also passed all 95 cases under CI-equivalent production
  settings. `./scripts/doctor.sh` passed required checks; optional Dev Container
  CLI was unavailable. `git diff --check` passed.
- Fresh integrated local operator proof passed provisioning, two equivalent
  resets, normal resumption, and rollback/retained maintenance under RuntimeError,
  KeyboardInterrupt and SystemExit. Required media uses only HEAD/GET; exception
  payloads do not appear in operator output. Its disposable database was removed.
- The parent plausible-mutant assessment is in the implementation handoff. Every
  changed code/schema/wiring/test/documentation group is within its Scope Guard.

At completion of the local phase, rollout and AC-10 were still pending. The
subsequently authorized live preparation/proof below establishes actual Staging
privileges, private-network access, required asset availability and resumption.
Normal Git integration and #202 application promotion remain separate.
For a code rollback, disable reset capability and retain the preserved registry
and domain data; do not reverse the registry migration as reset cleanup. A retained
maintenance gate needs the verified control-database recovery procedure in the
runbook before normal service resumes.

### Authorized live preparation: prerequisite denial

On 2026-09-17, the user approved continuing with live Staging proof. The approved
GitHub and Railway accounts were verified. The canonical #203 preflight passed
with source `04f8383fe750bec712ced27a1932b82b1eabb292` and deployment
`57f17ef7-7b34-4c2f-9272-b8091b1eafad`. Explicit project/environment/service
selectors resolved the approved Staging resources; the API and selected Postgres
database URLs matched without exposing their values.

The selected Postgres service has no public TCP proxy. Read-only inspection was
therefore performed through the exact running API deployment instance over
Railway SSH, verifying immutable build identity and runtime resource IDs before
querying PostgreSQL with read-only transactions. The database connection has
superuser privilege, but this does not yet establish live maintenance/resumption.

At that initial inspection, the database contained one Clerk-bound non-admin User, zero PlayerProfiles and
zero Fursuits. It cannot supply the required two distinct existing baseline
identities. No approved baseline media key or reset guard configuration is
registered in Staging configuration; asset availability remains unverified.
The registry migration is not deployed. These are preparation prerequisites,
not permission to create Clerk users, upload media, or adopt arbitrary identities.

No schema, sentinel, configuration, domain state, Clerk identity or media object
was changed. AC-10 was then incomplete. The required next step was for the identity-pool owning
process to supply two explicitly designated existing synthetic User/Clerk bindings
and a designated stable readable media key. Establish the schema and independent
Staging-only guard configuration afterward, then perform the controlled two-run
proof. Private inspection records are not repository artifacts.

### Authorized fixture preparation and live acceptance: PASS

The user subsequently authorized automating the one-time identity, User binding,
media and private-reference setup. Two explicitly named synthetic Clerk accounts
were created in the verified dedicated `TailTag Staging` instance; the user entered
and submitted their passwords. The existing application resolver established
exactly two ordinary non-admin TailTag User bindings in one transaction. Prior
Users, all other model data, permission/group through rows and schema fingerprints
were preserved. This was operator fixture preparation, not an authenticated
player API smoke test or a capability of the reset command.

One generated 256-pixel PNG visibly marked for rehearsal was normalized through
existing application code and uploaded once to a preassigned opaque key in the
configured Staging bucket. HEAD and full-content GET verified it. The designated
key and identity references were stored privately before subsequent operations;
no arbitrary identity adoption, vendor deletion or cleanup was performed.

The approved Staging resource has no public TCP proxy. The bounded operational
adaptation was exact-instance Railway SSH with the existing production Python
interpreter: a 102-file copy of reviewed repository production modules and the
reset/preflight entry points was installed into an exclusive temporary directory.
Safe archive extraction and file hashes verified its contents. Served `/app`
source, app deployment and #202 promotion were unchanged. Every invocation proved
runtime/project/environment/service/deployment/build identity, selected API/PG
URL equality via a private hash, and actual database name/system identifier.
The real canonical preflight additionally had to equal the pinned serving tuple,
including both reset preflights inside the existing failure/re-gating handler.
Independent operational safety reviews passed after closing their guard findings.

The migration executor required exactly `rehearsal.0001_initial` forward; it
created only the registry schema, preserved prior migration records/data, and
left the registry empty. Independently generated Staging-only expected identity,
endpoint/cluster pins, capability and fixture bindings were persisted in the
private operator configuration before explicitly provisioning the sentinel.
No reset capability or sentinel was established in Development or Production.

| Live observation | Result |
| --- | --- |
| Canonical #203 identity before/after both runs | Same source/deployment tuple as initial preparation; PASS |
| Normal CLI reset with committed connection gate, drain, atomic reconstruction, validation and explicit resume | Two successful runs; PASS |
| Profiles / conventions / fursuits / enrollments / activations | `2 / 1 / 2 / 2 / 2` after both runs |
| Catches / sessions / credentials | `0 / 0 / 0` after both runs |
| Semantic profiles, statuses, dates, fixture relationships and public fursuit UUIDs | Equivalent across runs; PASS |
| All three Users, group/permission assignments, migration history and schema | Unchanged across both resets; PASS |
| Sentinel identity/bindings and shared asset content digest | Preserved; PASS |
| Registered baseline root bindings after first versus second reset | Unchanged; PASS |
| Database connections and canonical readiness after each run | Allowed / ready; PASS |
| Clerk/R2 mutations during reset | None; stable assets reused |

The temporary remote operator bundle was verified and removed after proof.
Private transfer templates and transient error captures were removed. The
Staging-only expected configuration remains at
`~/.config/tailtag/staging-reset.env` with mode `0600`; the directory is `0700`.
Private preparation plans, code manifest hashes and before/first/second proof
records are retained there for operator continuity, outside Git. Do not copy this
configuration to another environment or a database clone. The sentinel, reusable
accounts, baseline domain state and designated image are intentionally retained.
No task container/network was created by live proof.

AC-10 is satisfied for this controlled normal-path Staging rehearsal. Failure,
rollback, malformed/copied identity and negative-target coverage remain the
independent local PostgreSQL/CLI test evidence; no live chaos or Production access
was performed. The observed baseline is authoritative after successful reset and
service resumption; later ordinary gameplay can change it.


### Maintained private-network command completion

The repository now owns `make api-staging-reset-ssh`, replacing reliance on the
deleted one-off transport helpers. Its frozen SSH-1–8 acceptance/test/scope
contract and completion evidence are in the
[implementation handoff](2026-09-17-staging-synthetic-reset-reseed-implementation-plan.md#repository-owned-ssh-reset-command-frozen-review-unit).
It validates the approved operator/provider/runtime and database fingerprint,
transfers only verified production source and the private nine reset values
through stdin, pins every real reset preflight, preserves fixed failure classes,
and confirms temporary-source cleanup before operator-visible success.

The maintained command passed two controlled Staging resets using the existing
provisioned sentinel, identity pool and media. Independent observations confirm
equivalent semantic baselines, unchanged protected identity/permission/schema/
migration/sentinel state and stable media, successful admission/readiness, and
absence of retained temporary directories. Both success receipts match. No new
fixture, migration, vendor mutation or deployment was part of this proof. Full
`make api-check` passed 1,862 tests and all deterministic gates; final focused
operator/CI/command checks passed 232 tests; fresh combined review passed.
Task-local source/container cleanup is complete, with the reusable test volume
and private operator configuration/receipts intentionally retained. Git delivery
is a separate remaining step and was not performed by this review unit.
