# #204 implementation and test handoff

Parent contract: [Staging synthetic reset/reseed](2026-09-17-staging-synthetic-reset-reseed.md).
Implementation authorized by the user on 2026-09-17. This plan concretizes that
contract without changing its boundaries. The user subsequently authorized live
Staging proof and separate one-time fixture preparation. The initial missing
prerequisites were resolved; schema/sentinel preparation and two equivalent live
resets passed. See the parent contract's sanitized live acceptance evidence. This authorization does not expand the
reset into Clerk user creation or media upload.

## Concrete manifest v1

Two pre-existing, non-admin synthetic identities have immutable aliases `owner`
and `catcher`. Their Clerk IDs and one pre-provisioned image key are supplied in
Staging-only operator configuration and registered in a preserved sentinel.
Both existing Users survive. Neither Clerk users nor media are created/deleted.

| Fixture | Desired state |
| --- | --- |
| owner profile | handle `tt_rehearsal_owner`, display name `TailTag Rehearsal Owner`, enabled, completed onboarding, registered image avatar |
| catcher profile | handle `tt_rehearsal_catcher`, display name `TailTag Rehearsal Catcher`, enabled, completed onboarding, registered image avatar |
| convention | `TailTag Canonical Rehearsal`, active, 2026-09-01 through 2036-09-01 |
| first fursuit | `Rehearsal Panther`, owner alias, enabled, registered image; tailtag UUID `e43be4ef-36d6-4a38-bf65-20f8675c2a31` |
| second fursuit | `Rehearsal Fox`, owner alias, enabled, registered image; tailtag UUID `f858b9fb-8a1a-4f87-9e6f-683cead8a7b2` |
| enrollments | both identities enrolled in the registered convention, active |
| activations | both registered fursuits active in that convention |
| catches, catch sessions, catch credentials | zero in the owned closure; owner APIs may create sessions/credentials later |

Onboarding and activation timestamps are valid current values, not equivalence
keys. Root Convention/Fursuit rows are reconciled in place once bound. UUIDs
stay stable; database PKs are not fixture lookup authority. One shared synthetic
image is sufficient for this intentionally small baseline.

## Explicit ownership and sentinel

New `rehearsal` Django app has one `StagingResetIdentity` model. Fields:
`id` (positive small PK, constrained to 1), `environment_id` (UUID, no generated
default), `cluster_identifier` (decimal string), `database_name` (string),
`owner`/`catcher` (protected FK User), `media_key` (text), `convention` (nullable
protected FK), `first_fursuit`/`second_fursuit` (nullable protected FK).
Registry roots are either all null (before the first reset) or all populated.
Migrations create only schema, never any sentinel row/identity/fixture.

The provision CLI binds already-existing distinct non-admin Users and a valid
readable synthetic image after target/database checks and exact confirmation.
It refuses an existing sentinel; no overwrite or automatic adoption. Expected
random v4 environment UUID is generated/configured by the operator independently.
Initial roots are null and first reset creates/binds all three atomically;
existing fixed UUID collisions fail rather than adopt unowned rows.

Owned domain closure is explicit: registered root convention, two registered
fursuits, registered identities' profiles, those identities' enrollments in the
root convention, and the two root fursuits' activations there with all attached
sessions/credentials and complete Catch provenance between registered identities
and those roots. Precheck *all* references touching any root/session/activation;
any edge outside this closure denies. Additional enrollments for baseline Users
outside this convention also deny rather than alter their active-selection state.
Unrelated state survives. Child cleanup order is Catch, credentials/sessions,
activations, enrollments; profiles and roots are reconciled without media services.

## Positive database binding and quiescence

`ResetConfiguration` is a frozen dataclass. `load_configuration(mapping)` requires:

- exact Railway Staging project/environment/API IDs already established by #200;
- `RAILWAY_ENVIRONMENT_NAME=staging`, `TAILTAG_STAGING_RESET_ENABLED=true`;
- canonical v4 `TAILTAG_STAGING_RESET_ID`;
- decimal `TAILTAG_STAGING_DATABASE_SYSTEM_ID`;
- pinned lowercase DNS `TAILTAG_STAGING_DATABASE_HOST`, canonical numeric
  `TAILTAG_STAGING_DATABASE_PORT`, and identifier `TAILTAG_STAGING_DATABASE_NAME`;
- distinct `TAILTAG_STAGING_RESET_OWNER_CLERK_ID` and
  `TAILTAG_STAGING_RESET_CATCHER_CLERK_ID`;
- valid opaque `TAILTAG_STAGING_RESET_MEDIA_KEY`.

The configured host/port/name must match effective Django default database
configuration, independently pinned after verifying the exact Railway Staging
Postgres resource. Compare connected `current_database()` and
`pg_control_system().system_identifier` to expectations and sentinel. A logical
database copy on another cluster/name or accidental endpoint switch fails.
Do not print identifiers, media keys, private hosts or database credentials.
This is not hostile-admin attestation. No new Clerk backend secret is required:
registered bindings resolve the curated identity pool locally; Clerk live
availability is outside reset's proof. Required image receives bounded read-only
HEAD/read checks through configured S3 storage before maintenance. Executor
filesystem/in-memory storage cannot qualify as R2 fixture availability; tests
use the existing S3 adapter with a fake client or a controlled compatible fake
at the normal storage boundary, not a new production bypass.

Use PostgreSQL infrastructure maintenance, avoiding Railway API stop/resume and
new product write-lock semantics. Local PG17 spike established:
`ALLOW_CONNECTIONS false` rejects *all* new target connections, including
superuser; the existing executor remains available. PostgreSQL refuses changing
that flag to false from the target connection itself. Therefore open a separate
control connection to `postgres` on the same pinned endpoint/cluster and retain
the Django target executor. Before any control mutation, independently query that
actual control connection's `current_database()`, superuser privilege and
`pg_control_system().system_identifier`: require `postgres` and the expected
cluster identifier, matching the executor observation. Construct control
connection parameters only from the already validated effective pinned Django
endpoint/credentials. Target name `postgres` is rejected. Require superuser
privileges, originally enabled connections, no prepared target transactions or
logical subscriptions, and bounded operations.

Hold a fixed reset advisory lock on the control DB only to serialize resets.
After mandatory canonical public preflight and every non-destructive guard/asset
check, control uses explicit psycopg autocommit (reject any surrounding Django
atomic transaction) to disable target connections. The gate must be committed
and observable as `pg_database.datallowconn=false` from both actual retained
connections before drain starts. A separately attempted bounded target connection
must also be rejected. A generic network/authentication failure alone is not gate
proof: psycopg/libpq connect failures do not reliably expose SQLSTATE (the local
disabled-connection spike returned `sqlstate=None`), so actual committed catalog
observations establish the connection gate, with the fresh denial supplementary.
Then it terminates other target sessions,
and verifies only the retained executor remains. Check the gate and sole executor
again before the destructive transaction and inside it, with identity checks on
the same connection. No ordinary writer participation is required. Pending API
instances also cannot obtain target connections. Privileged actions from other
databases remain an operator trust boundary; deliberate hostile administration
is outside this guard.

Reconstruct/validate in one transaction. On any failure after gating leave the
database gated, close both connections and emit a fixed maintenance-retained
failure; document recovery via the independently verified control database.
After commit and validation, restore originally enabled connections, re-run
canonical public preflight and require unchanged application identity. If resume
proof fails, re-gate/drain and report committed-reset/maintenance-retained failure.
If re-gating itself fails, emit fixed maintenance-unknown failure, never success.
Do not claim baseline equivalence after arbitrary concurrent resumed gameplay.
Recovery is an explicit operator procedure, not a bypass flag on reset.

## Frozen Test Surface Contract

- `rehearsal.baseline` exports constants described above, including `BASELINE_VERSION=1`.
- `rehearsal.safety.ResetConfiguration` fields: `environment_id: UUID`,
  `cluster_identifier: str`, `database_host: str`, `database_port: str`,
  `database_name: str`, `owner_clerk_id: str`, `catcher_clerk_id: str`, `media_key: str`.
  `load_configuration(environment: Mapping[str,str]) -> ResetConfiguration`;
  fixed `ResetSafetyError` for denials.
- `rehearsal.safety.validate_database(configuration) -> None` checks actual Django
  endpoint/cluster/name/superuser and no prepared transactions/subscriptions.
  `validate_identity(configuration) -> StagingResetIdentity` checks preserved row,
  bindings and readable media (use existing storage/boto transport seam).
  `assert_quiescent(configuration) -> None` requires gated DB and only executor.
- `rehearsal.safety.DatabaseMaintenance(configuration)` has `__enter__/__exit__`,
  `quiesce()`, `resume()`. Entry opens/validates both actual connections and all
  pre-maintenance guards including sentinel/assets; it does not implicitly gate.
  Exit closes/releases resources only, never implicitly resumes. The operator
  explicitly calls `quiesce()` before reset and `resume()` only after commit.
  Final public preflight/identity equality stays inside the context while the
  control connection remains available: on failed resumption proof, explicitly
  re-gate/drain before exit. Control connection uses psycopg normal connection seam;
  direct PostgreSQL integration verifies its infrastructure effects and always
  re-enables target in test cleanup, even when testing intentional retention.
- `rehearsal.reset.provision_identity(configuration) -> None` refuses existing
  sentinel and binds resolved pre-existing Users/assets; no root creation.
  `reset_baseline(configuration) -> dict[str,int]` returns exact semantic counts
  `profiles=2, conventions=1, fursuits=2, enrollments=2, activations=2,
  catches=0, sessions=0, credentials=0`. Before/in the atomic transaction require
  identity and quiescence. `validate_baseline(identity) -> dict[str,int]` is the
  package-internal production validation seam used before commit. Controlled
  validation failure exercises real rollback without adding public APIs.
- `scripts.api_staging_reset.main() -> int` is the only operator entry point.
  Arguments: `--confirm reset-tailtag-staging`; provision uses `--provision
  --confirm provision-tailtag-staging-reset`. Reuse #203 `validate_target` with
  exact canonical URL; no override. Provision is separate and non-destructive.
  Script uses `load_configuration`, `DatabaseMaintenance`, `provision_identity`,
  `reset_baseline` and existing Django setup. Tests patch normal HTTP/connection/
  storage boundaries or package-internal orchestration calls, not public bypasses.
  Success output is one JSON object with `identity` (the #203 three-field tuple),
  `baseline_version=1` and `counts` (the exact eight semantic counts). Provision
  success reports a fixed safe acknowledgement without identifiers.
  Failures print fixed phase classifications only, with no raw exceptions.

Independent tests must map to parent AC-1..10, reject plausible unsafe guards,
exercise real PostgreSQL rollback/ownership/preservation and real connection
gating, and assert zero Clerk/R2 mutations. Existing test storage overrides may
be replaced with a controlled S3 adapter/fake for asset observations. No network
vendor calls or shared service termination in tests.

## Scope Guard and sequencing

Outcome: locally implement the guarded reset/provision operator procedure and
small baseline with the parent preservation/safety/atomicity contract.
Files: new `rehearsal` app/modules/schema migration, one repository operator
script, focused existing-style tests, base app registration, existing check/CI
script lists, Makefile command, specs and Staging runbook. No new dependency.
Proof: baseline `make api-check`, independent tests and adequacy, separate
implementer, focused checks, full `make api-check`/Semgrep, fresh spec/code reviews,
local black-box maintenance proof, doctor/diff and cleanup. Live Staging proof
passed after separately authorized fixture preparation and guarded private-network
operator execution. Normal application delivery remains separate.
No unsupported AC is represented as complete.

## Independent test-adequacy approval

Parent approved the independent author's proposed matrix on 2026-09-17, before
production implementation. All cases below are frozen acceptance/assurance scope;
unfinished proposed cases must be authored independently before final gates/review.

- AC-5: canonical typed configuration; each missing field, exact Railway IDs,
  environment/capability/UUID/endpoint/pool/media malformed inputs; actual
  endpoint/database/cluster mismatch.
- AC-1/4/5/8: sentinel/pool bindings; actual S3 HEAD/bounded read, unavailable
  object and local-storage denial; zero external mutations.
- AC-1/2/4/5: provision pre-existing non-admin identities only, no rebind/overwrite;
  atomic first-run root registration, fixed UUID collisions, root owner/UUID drift.
- AC-1..4/7/8: complete desired semantic baseline, swapped owned handles and root
  drift restoration; full User/admin/permission/migration/sentinel preservation;
  independent unowned history retained; two-run equivalence; separate unowned
  handle and crossing provenance/activation/enrollment denials; late rollback.
- AC-5..7: real dedicated PostgreSQL target gating, actual control identity and
  committed control/executor catalog observations, drain/sole executor/fresh
  connection denial; control mismatch, prepared/subscription/privilege denials;
  explicit successful resume and retained maintenance on failure.
- AC-2/5..8: CLI denial before mutation, mandatory canonical preflight, explicit
  quiesce/reset/resume/final proof inside the maintenance context, reset failure
  without resume, changed final identity and failed re-gating classifications,
  JSON allowlist and separate provision path.

AC-9 maps to this suite; AC-10 is now backed by the sanitized live proof and runbook.
Plausible mutants include global history purge, origin/runtime-only guards,
copied sentinel without database binding, uncommitted/wrong-cluster gating,
lock-only quiescence, unowned dependency adoption, non-atomic cleanup, signed-URL
asset proof, external upload/deletion, early/implicit resume and false success.
No mutation tooling/dependency is introduced.

## Parent plausible-mutant assessment

The selected assurance checks target realistic incorrect implementations rather
than a numerical mutation score. Final passing results are recorded in the parent
contract after the deterministic gate.

| Incorrect implementation | Protection |
| --- | --- |
| Purge all synthetic-looking history or Users | Independent unowned Catch/session/credential graph, complete User/admin/permission snapshots and migration history survive |
| Trust only public origin or runtime Staging claim | Mandatory preflight ordering, every missing/malformed configuration field, actual database binding and direct sentinel mismatch tests |
| Accept copied sentinel on another database/cluster | Actual connected database/cluster/endpoint mismatch denials independent of sentinel equality |
| Mutate through a wrong control database/cluster | Normal psycopg control-facts proxy denies before ALTER or backend termination |
| Drain before a committed connection gate, or use only an advisory lock | Independent control observation before drain, failed fresh target connection, existing writer termination and sole-executor proof |
| Expand ownership across a foreign or malformed dependency | Crossing Catch/activation/enrollment, all-owned incoherent Catch provenance, root owner/UUID and unowned handle conflicts deny without domain changes |
| Commit cleanup before reconstruction or skip rollback | Injected late validation failure preserves the complete previous owned domain state; integrated operator rehearsal retains maintenance |
| Treat a signed URL as asset proof or mutate external resources | Actual S3 HEAD/bounded read, unavailable/unreadable/empty/local-storage denials and read-only client rejecting uploads/deletes |
| Resume implicitly on reset failure or report false success | Real committed gate remains disabled on failure; CLI event ordering, changed final identity, interrupted final proof and failed re-gating produce fixed failures |

A duplicate inactive activation for the same fursuit/convention is an irrelevant
mutant: the existing unconditional unique constraint rejects it. Existing state
timestamp constraints and final exact-state/closure validation additionally reject
incorrect enrollment/activation status. No mutation dependency or production
testing seam was added.

The first whole-project run found the existing frozen static-analysis helper
allowlist did not yet include the approved reset script (84 failures shared that
one mismatch; all reset cases passed). Parent authorized the independent test
author to add the script to `tests/semgrep_support.py`, retain exact-scope
assertions, and extend the existing CI relevance and Make override-security
matrices for that script. These are integration contracts for the already
approved Make/CI wiring, not relaxed safety assertions or new application scope.

## Live operational adaptation and completion

The concrete platform constraint was absence of a public Staging Postgres TCP
proxy. Exact running API-instance Railway SSH supplied private-network execution;
no proxy or application deployment was created. The reviewed operator source was
copied into an isolated task directory with manifest validation, production
interpreter isolation and assertions translated to explicit fail-closed checks
in temporary orchestration. Public preflight was bound to the runtime deployment
at every CLI preflight, preserving the existing post-resume failure/re-gate path.
Actual cluster/database/endpoint pins came from independently verified resource
configuration and read-only facts. Independent transport reviews passed.

One-time fixture setup (two ordinary User bindings and one normalized persistent
image) was separately authorized and verified before registry preparation.
Only the approved registry migration ran; no sentinel was created automatically.
The explicit provision operation and two normal CLI resets then passed with
independent semantic/preservation/readiness observations. Parent completion
records, retained private operator configuration and cleanup are in the contract.
The baseline library, migration and command were not changed for live proof.

## Repository-owned SSH reset command: frozen review unit

The user authorized finishing the reusable private-network operator entry point.
Execution: STANDARD COMPACT. Assurance: SECURITY, DATA INTEGRITY, RELIABILITY,
TEST ADEQUACY. Alignment is supplied by the frozen parent boundaries and the
successful live transport proof; no additional product decisions are introduced.
Completed: focused reconnaissance, design, independent security design review
(PASS), environment readiness and independent test-matrix adequacy approval.
Completed additionally: independent tests/adequacy review, separate implementation
and parent guard remediation. Initial focused RED: 19 missing-script errors and
two expected missing Make/CI wiring failures; 33 existing checks passed. Final
focused transport/CI/command checks: 232 passed; Ruff passes; full strict Pyright
has zero errors; Semgrep nine rules/208 files has zero findings. Completed: complete
backend deterministic gate and fresh combined review (both PASS). Controlled
live command proof, completion documentation and cleanup are complete; this
review unit is finished. Git delivery remains outside this unit.

### Acceptance Contract

- SSH-1: `make api-staging-reset-ssh` runs one repository-owned operator with the
  exact reset confirmation. Its CLI accepts only `--confirm reset-tailtag-staging`
  and optional `--config PATH` (default `~/.config/tailtag/staging-reset.env`). No
  provision, migration, fixture/vendor mutation or deployment operation is added.
- SSH-2: configuration is read from a current-operator-owned regular non-symlink
  file, mode `0600`, inside an owned non-symlink `0700` directory. It contains
  exactly the nine existing `TAILTAG_STAGING_*` reset keys, once each, as literal
  assignments; blank lines/comments are permitted. Unknown/missing/duplicate/
  malformed entries fail closed. No evaluation, shell sourcing, credential field,
  runtime selector override or target URL override is accepted. Existing database/
  sentinel/fixture value validation remains authoritative in the normal reset.
- SSH-3: the real credential-free #203 canonical preflight captures the serving
  tuple. The approved Railway account (Finn the Panther / approved Finn email)
  is positively verified before external CLI work and immediately before SSH.
  Explicit fixed Staging project/environment/API/Postgres selectors are used.
  Read-only provider queries require the serving deployment's exact resource join,
  `SUCCESS`, one unambiguous RUNNING instance and the same sole active deployment.
  Malformed/mismatched/ambiguous/failing observations deny before SSH; no retry or
  alternate authentication path occurs. Selected API and PG runtime configuration
  identify the fixed resources and their database URLs must match. Only the URL's
  SHA-256 fingerprint crosses the SSH boundary, never its credential value.
- SSH-4: build a bounded code-only archive from existing first-party production
  API packages and the three reset/preflight/SSH root helpers. Exclude tests,
  dependencies, rendered configuration and other files; reject symlinks and unsafe
  paths. A per-file SHA-256 manifest covers every regular archive member. Transfer
  the archive, manifest, expected public tuple and private nine-key configuration
  through SSH stdin only, using the exact instance and `/app/.venv/bin/python -I`.
  No private value is placed in arguments, printed or persisted remotely.
- SSH-5: the isolated remote bootstrap validates the archive/manifest completely
  (bounded sizes, exact unique names, regular files only, safe first-party paths,
  matching hashes) before code execution in an exclusive private temporary root.
  It does not modify `/app`, install dependencies or submit a deployment. The
  executor positively matches immutable build SHA, actual runtime deployment/
  Staging selectors and database URL fingerprint before invoking the reset.
  It overlays only the nine reset keys onto the existing runtime environment.
- SSH-6: invoke the existing reset CLI with the exact confirmation, production
  settings and copied repository/API module paths. Its canonical helper is wrapped
  only to additionally require the pinned public tuple on every real preflight;
  both initial and post-resume checks run inside the existing failure/re-gating
  behavior. All database/sentinel/assets/quiescence/transaction guards remain in
  the existing implementation. There is no direct cleanup/reseed alternative.
- SSH-7: temporary source is removed on success and handled failure/interruption,
  and success is emitted only after cleanup is confirmed. Success output is
  allowlisted public identity, baseline version, exact semantic counts and a
  non-sensitive code-bundle fingerprint/cleanup acknowledgement. Raw provider,
  SSH, Python or configuration diagnostics never escape. Preserve the reset's
  fixed maintenance failure classifications; disconnect/timeout/untrusted response
  after SSH starts means maintenance unknown, never assumed resumption or retry.
  If process/container loss prevents cleanup, document the exact task directory
  naming and inspection procedure; never implicitly resume a retained gate.
- SSH-8: required format/lint/strict typing/Semgrep/CI relevance/Make override
  protections cover the new script. Independent offline tests reject realistic
  target, configuration, archive, runtime, output and failure mutations. The
  maintained command is then exercised twice against the already-provisioned
  Staging baseline, verifying equivalent semantics, protected state, stable media,
  final readiness and absence of retained task directories. No fixture recreation.

### Test Surface Contract

One new production module: `scripts/api_staging_reset_ssh.py`. Its normal CLI and
package-internal configuration/archive/executor helpers are intentional seams:
`main`, `_read_configuration(Path)`, `_build_bundle(Path)`, `_execute_remote(request,
root)` and `_BOOTSTRAP`. External subprocess is centralized in `_run(arguments,
input=...)`; tests may fake the existing Railway CLI and canonical HTTP helper.
Configuration returns a `dict[str, str]`; bundle construction returns the base64
archive and `dict[str, str]` member-hash manifest. The executor returns an integer
exit status and fixed safe output text for the bootstrap to publish after cleanup.
The remote bootstrap must also be exercised through a real local isolated Python
process with constructed bounded code archives, so malicious member handling,
manifest enforcement and temporary-directory cleanup are not only mocked.
Remote executor tests may control its immutable identity path constant, runtime
OS environment and the imported existing reset CLI at their normal module seams.
These are operator package internals, not new application routes or database APIs.
Test requests/configuration use fictitious sentinel values, never retained live
operator configuration. No real vendor calls or shared service termination in CI.
Existing PostgreSQL tests already cover reset invariants; do not duplicate their
whole domain matrix in this transport unit.

The independent author proposed, and parent approved, the transport mapping:
exactly `bundle` (base64 archive), `manifest` (member-to-SHA-256 mapping), `identity`
(the three-field public tuple), `database_url_fingerprint` (SHA-256 hex) and
`configuration` (the nine literal reset values). It is the sole SSH stdin JSON
document. The remote executor returns `(exit_status, safe_output)`; bootstrap imports the
copied SSH module and calls it only after whole-archive validation, then publishes
only after cleanup. `main` is the local provider/SSH orchestrator and tests observe
its external operations through `_run`; it does not call the remote executor
locally. Synthetic bootstrap test archives provide a fake remote executor in the
copied module, never a direct reset alternative in production. Successful output retains the existing reset's identity,
baseline version and exact counts, plus `bundle_fingerprint` (SHA-256 of compact
sorted manifest JSON) and `cleanup_confirmed: true`. Temporary roots use exactly
`/tmp/tailtag-staging-reset-*`. Fixed core failures remain fixed safe text; other
untrusted post-SSH outcomes are classified maintenance unknown.

Readiness evidence: locked API dependencies, Ruff 0.16.1, Pyright 1.1.411 and
pytest 9.1.1 operational; existing reset/maintenance baseline 23 tests passed.
The task-local PostgreSQL 17 container uses the preserved rehearsal-test volume
and will be stopped/removed after final checks. Installed Railway CLI 5.57.2 SSH
help and upstream CLI documentation confirm explicit instance selection and
trailing one-shot commands; the prior authorized live proof established stdin
forwarding with this installed version. No dependency change is needed.

### Scope Guard and ownership

Outcome: a maintainable safe reset command for the approved private-network
Staging runtime, reusing the parent operation and preservation boundaries.
Non-goals: automatic schema/sentinel/pool/assets preparation, online locking,
public database exposure, deployment/promotion, scheduled jobs, dependencies,
Git delivery, credentials changes and simulation population/cleanup tooling.
Files: one new root script, one new focused test module, existing Makefile/check/
CI relevance/Pyright helper lists, existing Semgrep helper and developer-command/
CI test matrices, this handoff and parent contract/Staging runbook. No core reset,
model or migration changes are planned. Production implementation owns script/
wiring; independent author owns tests; parent owns contracts and completion docs.
Proof: approved independent tests and plausible-mutant matrix, deterministic full
`make api-check`, fresh combined security/spec/code review, two maintained-command
live runs with semantic/preservation/readiness observations, doctor/diff and
confirmed task-container/temporary-source cleanup. Existing expected private
configuration, sentinel, identities, assets and baseline persist.


### Independent test adequacy and parent guard review

The independent author mapped tests to SSH-1–8 and realistic mutations. Tests use
only fictitious private values, controlled provider responses and actual isolated
Python bootstrap processes. External invocation markers survive source cleanup,
so invalid-bundle tests reject execution before full validation. Runtime/build
checks use the real remote executor and a controlled immutable artifact rather
than mutable Railway commit metadata. The post-resume case uses the actual existing
reset CLI with its normal maintenance/database seams controlled, proving second
preflight mismatch re-gates and preserves `committed maintenance retained`.
Cleanup-removal failure is injected in a real bootstrap process; no success is
claimed, and only that test's confirmed temporary root is removed afterward.

Parent review required and implementation resolved immutable-artifact absence,
in-process copied-module invocation, Path-valued bootstrap root, exact UUID SSH
selectors, complete archive validation, bounded request/member reads, duplicate
JSON denial, canonical production paths, handled SIGTERM cleanup, raw output
capture, exact failure-message allowlists and exact baseline version/counts.
Provider metadata also positively requires the Staging name on both resources
and rejects an empty or mismatched database URL before SSH. No core reset/model/
migration change or new application/testing API was introduced.


### SSH unit completion evidence

- SSH-1/2: maintained `make api-staging-reset-ssh` uses the existing private
  nine-key configuration and exact reset confirmation. No preparatory/vendor/
  deployment action is exposed or occurred during command proof.
- SSH-3/4/5/6: both live calls selected the captured canonical serving deployment
  and exact approved Staging resources/instance; verified account and provider/
  runtime/build/database fingerprints; transferred manifest-checked production
  source through stdin; and invoked the existing guarded CLI with both real
  preflights pinned. No served `/app` file or application deployment changed.
- SSH-7/8: both commands returned the same strict success receipt and bundle
  fingerprint with cleanup confirmed. Independent before/first/second read-only
  observations matched all protected-state, migration, schema, full sentinel,
  permission/identity and stable-media digests. First/second semantic digests
  matched, all three durable User rows survived, baseline counts were
  2 profiles / 1 convention / 2 fursuits / 2 enrollments / 2 activations /
  0 catches / 0 sessions / 0 credentials. Connection admission and canonical
  readiness were positively observed after each reset; no matching task temporary
  directory remained. No identities/assets/sentinel/schema were recreated.

Authoritative `make api-check` passed: 1,862 tests, 474 existing warnings; Ruff,
full strict Pyright (zero errors), Semgrep nine rules/208 files (zero findings),
Django checks, migration drift, schema and Gunicorn checks all passed. Final
focused operator/CI/command run passed 232 tests. Fresh independent combined
review passed with no material findings and independently ran 49 SSH tests.
All touched SSH-unit files satisfy the Scope Guard; no core reset/model/migration,
dependency or public application API change was required. Live failure/chaos
testing remains out of scope; negative/interruption/cleanup cases are offline.

Private configuration and receipts remain at `~/.config/tailtag` with `0700`
directory / `0600` files: `staging-reset-ssh-proof-{before,first,second}.json`,
`staging-reset-ssh-proof-command-{first,second}.json`,
`staging-reset-ssh-proof-summary.json` and captured command logs. Values are not
committed. Temporary local observation helpers were removed; remote source
absence was independently verified. Task container
`tailtag-issue-204-ssh-postgres` was stopped and removed; preserved volume
`tailtag-issue-204-postgres-data` remains reusable. No unrelated container/network
or volume was changed. The reusable Clerk/User pool, sentinel and designated
media object remain intentionally provisioned.


Final repository hygiene: `./scripts/doctor.sh` required checks passed (optional
Dev Container CLI unavailable), `git diff --check` passed, private operator files
retain required modes, task-container absence and reusable-volume presence were
verified. No commit, push, PR update, issue closure or deployment was performed.
