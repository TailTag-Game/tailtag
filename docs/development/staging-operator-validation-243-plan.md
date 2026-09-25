# #243 operator evidence recovery and bounded validation proposal

Status: **replacement-generation baseline and operator prerequisites unproven;
matrix not started**.
The old-generation
[bounded read-only result](staging-operator-validation-243-execution-attempts.md)
substantiated the old managed and limited roles only; it found no limited-role
candidate before the later old-generation provisioning. Cases 1–9 remain
`NOT_EXERCISED` on both generations. The replacement Staging handoff is recorded
in the [current public/exact-instance receipt](staging-deployments/c34c45bb-6eb8-488d-8114-d1dd931cf25e.json)
for source `fc1376e9b4387cb46e37ef3f60191b2ce7f06c68` and deployment
`c34c45bb-6eb8-488d-8114-d1dd931cf25e`. The follow-up
[replacement prerequisite readback](staging-replacement-prerequisite-attempt-2026-09-25.md)
did not return database facts. It did not inspect the #204 sentinel/fixtures or
operators, and it performed no matrix action or mutation. Thus replacement
database binding, #204 baseline, and managed/limited/emergency operator state
remain unknown.
The [dedicated limited-role contract](staging-operator-validation-243-limited-role.md)
remains authoritative; the previously established role states belonged to the
old generation and do not establish replacement roles. Fresh replacement role
inspection is required before the matrix.
No guard or matrix result is implied by that authorization. Parent evidence gap:
[#205 handoff](staging-operator-validation-205.md); readiness owner:
[#208](https://github.com/TailTag-Game/tailtag/issues/208).
The [first approved attempt](staging-operator-validation-243-attempt-2026-09-23.md)
stopped at read-only inspection before any matrix action or reset.
The later fixture-only diagnostic and its #204 ownership map are recorded in
[the focused diagnosis](staging-operator-validation-243-fixture-diagnosis.md).
Its [single live read-only result](staging-operator-validation-243-fixture-result-2026-09-23.md)
classified a preserved registry prerequisite mismatch; it did not start the
nine-case validation or reset.
The subsequent [local registry contract review](staging-operator-validation-243-registry-tooling-review-2026-09-23.md)
found that the fixture diagnostic compared the random #204 reset UUID to the
Railway environment UUID. The emitted registry classification therefore does
not establish actual sentinel drift; no further live call was made in that review.
The [repository-only correction](staging-operator-validation-243-registry-reconciliation.md)
removes that comparison and defines a separate value-free three-way check for
a future authorized read-only task. The historical fixture result is unchanged;
registry/configuration/database agreement was unverified at that review.
The later [bounded read-only registry reconciliation](staging-operator-validation-243-registry-reconciliation-result-2026-09-23.md)
found structural registry validity and equality across the private, persisted,
and connected-database authorities at its observation. It did not inspect
operators or start the nine-case matrix.
The repository-only operator-inspector correction removed the same invalid
Railway/reset UUID comparison from its fixture guard. The inspector checks the
persisted reset UUID's v4 structure, singleton key, synthetic owner/catcher
shape, the existing read-only `validate_baseline` helper, and audit-model
availability before role inspection. It does not compare private #204
configuration to the registry or claim current fixture state from earlier
point-in-time evidence. Railway environment UUID remains a runtime target
selector only. A focused audit of #204/#243 diagnostic and inspection tooling
found no other cross-namespace identifier comparison.

### Corrected read-only inspection contract

The repository-owned #243 inspector is a read-only Python entry point streamed
to an explicitly selected running `TailTag Rebuild` / `staging` `api` instance
after the separate canonical preflight and exact-deployment join. It accepts only the public
expected source SHA and deployment ID, verifies them against that instance's
build/runtime identity and the replacement selectors loaded from the owner-only
target manifest, and emits one allowlisted status. Malformed input/target identity, fixture missing,
fixture ambiguous, fixture state mismatch, managed operator missing,
managed operator ambiguous, distinct managed role-state and permission-set
mismatches, limited operator missing, limited operator ambiguous, distinct
limited role-state and permission-set mismatches, unexpected privilege, and
execution/query failure
are distinct fail-closed results. It never prints identifiers, credentials,
raw records or permission sets. The managed operator must satisfy the exact
#205 bootstrap-managed group and permission contract. The separate one-action
limited operator must have only `profiles.set_profile_enabled` and the
narrowly required `profiles.view_playerprofile` inspection permission; it
must lack `fursuits.set_fursuit_enabled` and all other sensitive permissions.
No live result follows from a local inspector test or from this contract.

For an **authorized read-only inspection**, run the replacement-aware launcher
from the reviewed #243 checkout only when its owner-only target manifest is
present and the fresh public preflight matches a current approved receipt. The
September 25 receipt above is a point-in-time handoff observation; obtain a new
preflight and exact-instance join before every invocation. Do not run a launcher
from the old main baseline or select the retired Railway project.

```sh
PYTHONPATH="$PWD" uv run --project services/api --locked --no-sync \
  python -m scripts.api_staging_operator_inspect_ssh
```

The launcher verifies approved GitHub/Railway identity, fresh canonical
preflight, the matching replacement deployment receipt, and the sole running
instance in `TailTag Rebuild` / `staging` / `api`. It repeats public preflight
before the one SSH execution. An
isolated Python bootstrap explicitly selects `/app`, verifies the exact
instance's build/runtime identity before ORM access, and runs the fixture
and role inspector inside a PostgreSQL read-only transaction. It streams
reviewed source without deploying or writing it remotely.

The result contains only a fixed classification/phase, any established public
environment/source/deployment tuple, exact-instance verification boolean and
UTC window. Transport, timeout, bootstrap, output-contract and target failures
are distinct from the existing fixture/operator classifications. Unexpected
output is rejected. The documented single-line Railway SSH key-selection
notice may accompany an otherwise valid receipt; its private payload is
discarded. Any other stderr and every nonzero transport exit fail closed.
Raw transport output and exceptions are never retained.
The launcher has no retry path. A failed read-only attempt requires diagnosis
and any necessary reviewed tooling correction before a newly preflighted
attempt under the applicable authorization. None of these inspections
establishes a #205 matrix result. Historical failures and the local startup
regression are preserved in the [execution-attempt record](staging-operator-validation-243-execution-attempts.md).

## Retained-evidence search

On 2026-09-23, read-only inspection covered current and historical repository
documentation, reachable #205 branches/commits, relevant unreachable Git
commits, Staging evidence directories, legitimately available local #204
operator receipts, [issue #205](https://github.com/TailTag-Game/tailtag/issues/205)
and its timeline/comments, and the bodies/reviews/discussions of
[PR #239](https://github.com/TailTag-Game/tailtag/pull/239) and
[PR #240](https://github.com/TailTag-Game/tailtag/pull/240). #205 has no
case-level comment; PR #239 says its live Staging matrix was pending, and PR
#240 says the remaining matrix could resume after promotion. The retained
private #204 receipts prove reset behavior only and predate the #205
operator-audit application. No authentic nine-case live receipt, validation
window, or case-level cleanup record was found. This does not establish that
the validation never occurred.

| Approved #205 case | Retained live result | Minimum missing proof |
| --- | --- | --- |
| 1. Ordinary player barred from sensitive admin browse/mutation | UNKNOWN | Actual Staging denial and unchanged target |
| 2. Staff lacking target permission denied with one audit row | UNKNOWN | Target-bound denial, exactly one `denied` row, unchanged target |
| 3. Permitted non-superuser succeeds | UNKNOWN | One permitted target transition in Staging |
| 4. One-action operator cannot cross another permission | UNKNOWN | Cross-action denial for an otherwise permitted limited operator |
| 5. Emergency superuser succeeds | UNKNOWN | Successful transition with `actor_class=emergency_superuser` |
| 6. Success has one durable audit row | UNKNOWN | Exact one-row `succeeded` evidence for the permitted transition |
| 7. Denied submission has one durable audit row | UNKNOWN | Exact one-row `denied` evidence for a submitted staff attempt |
| 8. Disable cascade has one top-level audit intent | UNKNOWN | Changed dependent state, transactionally consistent result, one top-level row |
| 9. Alternate gameplay-authority paths unavailable | UNKNOWN | Staging admin/path denials with no Catch award or other forbidden mutation |

The validation date/window and canonical source/deployment identity, audit
row survival through #204 reset, cleanup/final state, and actual limitations
are likewise UNKNOWN. `UNKNOWN` is not `FAIL` or `NOT_EXERCISED`; neither
issue closure nor deterministic tests justify a live `PASS`.

## Proposed minimum bounded validation, requiring separate approval

One approved Staging operation window can cover all nine missing cases with
**two successful sensitive operator transitions**, one staff-denied submission
serving cases 2, 4 and 7, bounded negative requests, and one guarded #204
reset after audit inspection. Do not add a new backend API, migration,
provider fixture, general test harness, or unrelated admin action. Reuse the
approved two-user, two-fursuit, one-Convention synthetic #204 baseline if it
is still exact and has no conflicting unowned dependency. Preserve unrelated
unowned state. Use only supported Django-admin and existing player flows.

### Preconditions and target binding

1. Obtain separate approval for this exact bounded live matrix, its two
   domain transitions, and the one #204 reset. Coordinate an exclusive
   Staging rehearsal window; stop if other writers or configuration/deployment
   work are active. The approval must name the operator who owns cleanup.
2. Verify the acting GitHub and Railway identities under TailTag's identity
   rule. Positively select `Finn the Panther's Projects` / `TailTag Rebuild` /
   `staging` / `api` and its environment-local `Postgres`; reject Development,
   Production, stale links, or mismatched service/volume ownership.
3. Run the repository's credential-free
   [canonical preflight](staging.md#health-and-public-staging-preflight-203)
   against exactly `https://staging.tailtag.app`. Bind its safe source SHA and
   deployment ID to the exact running replacement Railway deployment/image
   identity using
   the maintained [#201/#202 join](staging.md#immutable-build-and-deployment-identity-201).
   Capture only approved public identifiers. Repeat the preflight before the
   first mutation, before reset, and after cleanup; any tuple change stops the
   matrix as indeterminate.
4. Inspect the replacement generation's newly provisioned baseline, audit
   migration, admin permission set,
   `OperatorAuditEvent` availability, and #204 reset sentinel/configuration
   through authorized read-only surfaces. The old-generation #204 sentinel,
   fixtures, private configuration, Clerk identities, media and operator
   results are historical and must not be reused. The replacement-bound #204
   sentinel provision path is locally reviewed but has not been exercised on
   live Staging; do not start the matrix until that prerequisite has been
   safely provisioned and verified against the separate private
   `~/.config/tailtag/staging-reset-replacement.env`. Identify exactly the disposable
   profile and a distinct disposable fursuit that #204 owns. If their state
   differs from the known baseline, an unrelated dependency exists, audit
   persistence is unavailable, or reset safety cannot be proved, stop.

### Actors and fixtures

- **Ordinary player:** one existing #204 synthetic non-staff User; no admin
  elevation or credential disclosure.
- **Limited operator:** a dedicated `is_staff=True`, `is_superuser=False`
  Staging identity with exactly the needed `profiles.set_profile_enabled`
  action permission and approved inspection permission, but without
  `fursuits.set_fursuit_enabled`. Confirm effective permissions before use;
  group name alone is not authority. Retained evidence does not establish
  whether an identity with these exact permissions currently exists.
- **Managed operator:** the existing normal operator satisfying the exact #205
  managed-group and permission contract. The maintainer's current authorization
  assigns step C to this actor; step B continues to require the distinct limited
  operator.
- **Emergency superuser:** prefer an existing authorized break-glass account,
  exercised only for the one approved synthetic action. If the fresh replacement
  inspection proves that role absent, the owner-approved
  [conditional synthetic actor amendment](staging-operator-validation-243-emergency-role-proposal.md)
  permits one guarded dedicated actor with mandatory post-matrix decommission.
  It is not the normal operator. Keep credentials and session material out of
  arguments, files, logs, tickets and evidence.
- **Cascade target:** one enabled owned synthetic profile with its existing
  activation. For a meaningful session cascade, the owner may start **one**
  normal synthetic catch session using the established player flow immediately
  before the disable. Create no Catch and no arbitrary credential/history row.
  If a session cannot be established safely, document exactly which cascade
  subclaim is unavailable and stop case 8 rather than inserting database rows.
- **Emergency action target:** a distinct #204-owned synthetic fursuit that
  is enabled before the run. Its disable is the second successful transition;
  #204 reset restores the known synthetic baseline afterward.

Do not create an ad hoc staff identity or repurpose a player/superuser to fill
a missing role. If the limited operator or required fixture is unavailable,
stop and seek the separately reviewed provisioning/reset boundary. If the
existing emergency superuser is absent, follow only the conditionally approved
replacement amendment after its current-generation guards pass. An ambiguous
or mismatched emergency role still stops the matrix.

### Case sequence and expected assertions

| Step | Cases covered | Bounded action and required observation |
| --- | --- | --- |
| A | 1 | As the ordinary player, attempt the approved sensitive admin list/detail and one synthetic-target mutation. Require no inspection or state change. Do not expect a GET audit row; classify any submitted-attempt audit strictly by the documented actor contract. |
| B | 2, 4, 7 | As the limited staff operator, submit **one** `set_fursuit_enabled` attempt on the distinct synthetic fursuit, for which this actor lacks permission. Require denial before the domain handler, unchanged fursuit/dependencies, and exactly one matching `denied` `OperatorAuditEvent` with `actor_class=unauthorized_actor`. Confirm the actor still has its separate profile permission. A second staff-denied attempt is needed only if the approved case-2 role is not demonstrably the same limited operator. |
| C | 3, 6, 8 | As the permitted managed non-superuser, disable the selected synthetic profile through its per-object Django-admin action. Require committed profile disable, the expected credential/session termination where the fixture supplies those dependents, preserved relationship/integrity constraints, and exactly one top-level `set_profile_enabled` / `operator` / `succeeded` audit row. No child cascade rows or duplicate success rows. |
| D | 5 | As the emergency superuser, disable the distinct synthetic fursuit through the approved per-object action. Require the committed transition and exactly one `set_fursuit_enabled` / `emergency_superuser` / `succeeded` row. Do not use the superuser for the normal-operator cases. |
| E | 9 | On those synthetic targets, check every forbidden surface in the finite checklist below. Require each control/route unavailable or denied, synthetic state unchanged, and no Catch award or other authority mutation. Do not probe arbitrary IDs or live player data. |
| F | Audit retention and final state | Snapshot only the approved audit event counts/classes/actions and protected-state checks. Run the separately approved guarded #204 reset once, with its own target/maintenance checks. Require known synthetic baseline and readiness restored, no unrelated protected data changed, the case audit rows still present and identical, and #204 temporary-source/connection cleanup verified. |

The operator must compare pre/post audit counts in a narrowly bounded time
window and on the exact synthetic targets so pre-existing audit rows are not
mistaken for this run. Inspect audit rows through approved database/operator
procedure; Django `LogEntry` and Railway logs are not authoritative. A
submitted attempt may legitimately produce `rejected` or `failed` instead of
the expected result if preconditions drift; record the actual outcome and stop
without relabeling it.

For step E, use this finite checklist against the applicable synthetic target:
Catch add, change and bulk edit; credential add, replacement and raw edit;
session add, delete, bulk edit and history edit; activation add, delete and
reactivation; enrollment add and selection change; playable Convention
creation and deletion. Inspect each admin control and its corresponding known
route where a bounded negative request is safe. Record each as unavailable or
denied with unchanged synthetic state and no award/authority effect. If a
required surface lacks a safe owned fixture or a known no-op request, mark
that subcheck `NOT_EXERCISED` with its exact reason; case 9 cannot be called
`PASS` on the basis of that partial check. Do not improvise a fixture or
route during the window.

#### Approved bounded case-9 evidence amendments

The maintainer approved a combined evidence model for the following live
object/state-dependent subchecks that the frozen baseline cannot safely supply:

- Catch object-level change paths without an owned Catch;
- credential replacement/raw-edit paths without an owned credential;
- inactive-to-active activation reactivation without an inactive activation.

Retain each live empirical result as `NOT_EXERCISED`. Require both
exact-deployment code/control operational review and existing deterministic
tests directly proving the path unavailable or denied. Record those evidence
results separately as `PASS` or `FAIL`, and retain an explicit empirical
limitation. Do not create, deactivate, replace or otherwise mutate an object
solely to obtain this proof. An active activation's editable checkbox is not
live proof of inactive-to-active rejection.

Keep safe object-independent add/create/bulk and alternate-admin-authority
checks live, recording each actually exercised result as `PASS` or `FAIL`.
A satisfied case-level `PASS` under this amended contract requires all safe
live subchecks and all required control/deterministic evidence to pass, with
every object/state-dependent `NOT_EXERCISED` boundary explicitly listed.
It is not an undifferentiated live `PASS`.

If independent review identifies another object/state-dependent case-9 path
that cannot safely be exercised under the frozen fixtures, apply this same
principle only when deployed-code/control review and existing deterministic
tests directly substantiate that exact unavailable path. Otherwise leave the
claim unsubstantiated. Do not broaden the approved live mutation sequence,
operator authority or player flow. These approvals supersede only the earlier
partial-check prohibition for these directly substantiated boundaries.

### Evidence, cleanup, and stop conditions

Retain one sanitized record with: UTC observation window; safe source SHA,
deployment ID and environment; fixed preflight/exact-image-join outcomes;
case 1–9 `PASS`/`FAIL`/`NOT_EXERCISED` with reason; actor **class** and action
(never actor identity); target **type** and a local case label (not raw IDs);
expected/observed audit count and outcome per submitted attempt; cascade
state class; #204 reset and audit-retention result; final readiness, known
baseline and cleanup result; limitations and overall bounded result. Keep
private role/fixture-to-record bindings outside Git under the established
operator evidence handling rules. Publish no credentials, provider IDs,
emails, raw Django user IDs, tokens, request bodies, private URLs, raw logs,
database contents or screenshots containing them.

Stop before mutation on target/identity/preflight mismatch, changed D/S,
unknown fixture ownership, missing exact role permission, concurrent writer,
unhealthy readiness, audit table unavailability, or uncertain #204 reset
safety. Stop further cases on unexpected authorization, a failed/incomplete
audit insert, changed unrelated state, a cascade mismatch, cleanup failure,
or indeterminate operation result. Preserve safe identifiers and escalate to
the backend/Staging owner; do not compensate by repeating a mutation, manually
editing rows, broadening permissions, changing provider configuration, or
silently running reset. If reset itself fails or retains the maintenance gate,
use only the documented #204 control-database recovery after separate target
verification, and mark the bounded result non-PASS.

No Production access, service termination, generic chaos, new migration,
database corruption, arbitrary Catch award, alternate admin implementation,
credential rotation, or provider-breaking test is part of this proposal.
Only after a separately approved run yields retained case-level evidence
should #243 update the #205 handoff and #208's OR-6/runbook dispositions.
