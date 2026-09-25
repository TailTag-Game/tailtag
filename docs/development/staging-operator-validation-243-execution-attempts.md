# #243 read-only operator execution attempts

These records preserve the chronological pre-mutation evidence. They do not
substantiate any of the nine #205 live matrix cases.

## Stopped attempt: 2026-09-23 23:27:33–23:27:40 UTC

- Retained result: `FAIL_EXECUTION_OR_TARGET`.
- Phase: `exact_instance_inspector`.
- Approved GitHub/Railway identity, fresh canonical public preflight, approved
  deployment receipt and exact running-instance selection passed beforehand.
- The fresh public source/deployment tuple was checked internally but was not
  retained in the failure output. The earlier tuple must not be substituted.
- The execution did not return an accepted inspector classification. Raw
  stdout/stderr were not retained. Transport, startup and output-contract
  failure cannot be distinguished from this record.
- Managed and limited operator state: unknown. Neither a role `PASS` nor a
  role mismatch can be inferred.
- Matrix cases 1–9: `NOT_EXERCISED`; reset/provisioning: not invoked;
  Staging mutation: none. No retry occurred in that attempt.
- No restoration was needed because no mutation began. No fresh fixture or
  operator final-state assertion is supported.

## Subsequent local diagnosis

Streaming the inspector with `python -` at filesystem root reproducibly raises
`IndexError` in the module-level repository-path calculation before the
sanitized guard. Streaming the same source from a nested working directory
returns the intended fixed invalid-input classification. This is a proven
startup defect and a missing execution-mode regression; the retained prior
attempt does **not** prove its remote working directory or root cause.

The correction makes stdin startup independent of directory depth. A bounded
runner uses the established isolated-Python transport pattern, explicitly
sets the application import root, validates exact-instance identity before
ORM inspection and enforces a PostgreSQL read-only transaction. Its fixed
execution phases and strict output schema preserve failure categories and
any established public tuple without retaining raw diagnostics. Managed and
limited role contracts are unchanged. Local tests cannot establish live
operator state.

## Local correction verification

Before a new live attempt, the startup regression and runner acceptance tests
passed, as did 330 focused #204/#205/#243 tests. The final `make api-check`
passed all 2,213 tests, formatting, lint, strict types, Semgrep, Django checks,
migration-drift check, schema validation and Gunicorn configuration. Explicit
Ruff/Pyright and Semgrep checks also covered the new launcher; Semgrep found
no findings. Doctor, local documentation links and diff checks passed.

Independent review found and resolved a fail-closed CLI exit-status defect:
non-`PASS` receipts now exit nonzero, with a regression proving the behavior.
The final review found no material issue and approved bounded read-only use.
These are local verification facts, not live #205 acceptance evidence.

## Read-only attempt: 2026-09-23 23:41:54.260518–23:42:00.810085 UTC

The reviewed launcher at `3d87bad` made one newly preflighted attempt:

| Fact | Observed result |
| --- | --- |
| Public environment | `staging` |
| Public source SHA | `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a` |
| Public deployment ID | `cbe83780-0256-49c2-b026-34709ddb69b0` |
| Identity, public preflight, approved receipt, running-instance selection | Passed before SSH |
| Launcher result / phase | `FAIL_TRANSPORT` / `exact_instance_inspector` |
| Accepted exact-instance verification | Not established by the retained result |
| Managed / limited roles | Unknown / unknown |
| Cases 1–9 | `NOT_EXERCISED` |
| Reset / provisioning / Staging mutation | None |

The raw transport streams were discarded. This classification alone cannot
establish whether the remote inspector ran or which role state it observed.
The submitted program contained only target checks and read-only inspection;
no mutation sequence started and no restoration was needed. No final live
operator-state assertion is supported.

### Subsequent transport-contract diagnosis

Railway CLI version `5.57.2` writes a key-selection announcement to stderr
even when an already registered key is selected successfully. This is
explicit in the [version-pinned upstream implementation](https://github.com/railwayapp/cli/blob/v5.57.2/src/commands/ssh/native.rs#L128-L139).
The launcher incorrectly required completely empty stderr. Local tests can
therefore reproduce rejection of a valid, target-verified inspector receipt
accompanied by this normal notice. The retained attempt does not prove that
this was its sole failure, and no historical role result can be recovered
from discarded output.

The bounded correction recognizes only that documented one-line notice and
never retains its identity/path payload. A nonzero transport exit, any other
stderr, extra stdout or invalid inspector receipt still fails closed. This
does not change identity selection, credentials, target guards or role rules.

The notice correction passed 58 focused inspector tests and the full
`make api-check` gate (2,220 tests). Explicit launcher Ruff/Pyright and
Semgrep checks, doctor, local documentation links and diff checks passed.
Independent review approved the narrow exception with no material finding.
It authorizes no inference about the discarded prior remote result.

## Substantiated precondition result: 2026-09-23 23:46:56.246313–23:47:02.191628 UTC

**Overall: `LIMITED_OPERATOR_REMEDIATION_REQUIRED`; #243 remains blocked
before mutation.** The reviewed launcher at `9d4e420` executed once under
the bounded autonomous authorization. Its sanitized receipt established:

| Fact | Result |
| --- | --- |
| Environment | `staging` |
| Source SHA | `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a` |
| Deployment ID | `cbe83780-0256-49c2-b026-34709ddb69b0` |
| Approved identities, fresh/repeated public preflight, receipt and sole running-instance selection | `PASS` |
| Exact-instance build/runtime identity agreement | `PASS` (`target_verified=true`) |
| Phase | `exact_instance_inspector` |
| Inspector result | `FAIL_LIMITED_OPERATOR_MISSING` |
| Bounded fixture prerequisite | `PASS` (the inspector reached both role checks) |
| Managed operator | `PASS` for the exact frozen managed group, staff/non-superuser, credential shape, direct-permission and group-permission contract |
| Limited operator | `MISSING` through the approved independent candidate lookup |

The inspector returns at the first failed guard. Reaching the limited-role
lookup therefore supports the preceding fixture and managed-role results.
`MISSING` means no candidate was found outside the managed group with either
of the two approved profile permissions. It does **not** distinguish a
nonexistent underlying User from an existing identity without those
permissions, and does not justify guessing an identity or granting access.
No identity values, role memberships or permission snapshots were retained.

This fixture result covers only the inspector's maintained baseline/structure
checks. It does not replace the earlier 17-invariant fixture observations or
refresh the separate private-config/registry/database reconciliation.

### Nine-case disposition

| #205 case | Result | Supported limitation |
| --- | --- | --- |
| 1. Ordinary-player denial | `NOT_EXERCISED` | Live matrix stopped at missing limited-role prerequisite |
| 2. Staff-without-target-permission denial | `NOT_EXERCISED` | Required distinct limited role unavailable |
| 3. Permitted non-superuser success | `NOT_EXERCISED` | Required distinct limited role unavailable |
| 4. Cross-permission denial | `NOT_EXERCISED` | Required distinct limited role unavailable |
| 5. Emergency-superuser success/classification | `NOT_EXERCISED` | Matrix not started; emergency identity not inspected in this attempt |
| 6. Exactly one successful top-level audit event | `NOT_EXERCISED` | No successful action submitted |
| 7. Exactly one denied-submission audit event | `NOT_EXERCISED` | No denied action submitted |
| 8. Representative cascade/top-level intent | `NOT_EXERCISED` | No cascade action or session preparation performed |
| 9. Forbidden alternate authority paths | `NOT_EXERCISED` | Finite matrix checks not started |

Success/denial audit outcomes, emergency-superuser classification, cascade
behavior, forbidden paths, and #204 reset/audit-retention interaction are
unsubstantiated by this attempt. No reset, operator provisioning, credential
change, fixture preparation, audit-row creation or Staging mutation occurred.
The read-only process exited; no remote source files were written and no
restoration was required. No additional live call followed this result.

### Required decision and repair boundary

The approved plan explicitly stops when the separate limited role is
unavailable and requires a separately reviewed fixture plan. The existing
`bootstrap_staging_operator` establishes the full managed permission set;
it cannot supply this one-action role unchanged. Reusing that managed actor,
stripping its authority, elevating a player or manually granting permissions
would cross the approved boundary.

The smallest next task is to approve a guarded provisioning/fixture plan for
a **separate** staff, non-superuser identity with only
`profiles.set_profile_enabled` and `profiles.view_playerprofile`, including
its credential-handling and cleanup boundary. Provisioning would mutate
Staging and needs explicit authorization after that plan is reviewable.
No such provisioning was implemented or executed in this task.

[#243](https://github.com/TailTag-Game/tailtag/issues/243) remains the owner of
this missing live evidence and its precondition handoff. #208 OR-6 remains
`BLOCKING` and #208 remains open at NO-GO. #205's historical closure, #207's
restore evidence and #241's non-blocking limitation are unchanged.

Local test cleanup: the task's disposable PostgreSQL container was stopped
and removed, with no task container or custom network left running. The
initial anonymous test volume was preserved under the repository's data
preservation policy; the final test container used temporary memory storage.

Final independent evidence review passed with no material finding. The
record preserves both failed attempts, the supported role result and the
unexercised matrix boundary. Local documentation links and diff checks passed.


## Repository-only feasibility stop — 2026-09-24 00:31 UTC

Classification: `BLOCKED_BEFORE_MUTATION` / `PLAN_CONTRACT_GAP`.
This is a local planning/review result, not an authenticated Staging attempt.
No fresh target tuple was established; the earlier observations above remain
point-in-time historical evidence. Cases 1–9 remain `NOT_EXERCISED`.

The maintainer authorized a narrow limited-role provisioning path and then
approved mixed evidence for absent Catch/credential object-level case-9
checks. That amendment expressly excludes other missing live proof.
Independent acceptance review found another unresolved boundary:

- The frozen #204 baseline has active FursuitActivation records.
- The approved profile and fursuit disables terminate sessions/revoke existing
  credentials, but do not make those activation records inactive.
- The real activation admin form exposes an editable, checked `is_active`
  checkbox on the active owned record. An active-to-active submission does
  not exercise the inactive-to-active rejection in `save_model`.
- Local deterministic tests and exact-deployment control review can support
  that rejection, but cannot replace its missing live proof under the current
  plan's Catch/credential-only exception. Calling this subcheck live `PASS`
  or merely calling its control unavailable would overstate the evidence.

Accordingly, no limited operator was provisioned and no live matrix started.
No authenticated Staging call, reset, fixture change, operator change, audit
write or other Staging mutation occurred during this repository work.
No Staging restoration is required by this work; current live state was not
reinspected. Prior fixture, registry and operator observations are unchanged.

The smallest decision is an explicit evidence-mode amendment for activation
reactivation: retain its live empirical result `NOT_EXERCISED`, separately
record the observed active form/control, exact-deployed-code review and
existing deterministic inactive-to-active denial tests, and disclose the
limitation in any satisfied case-level result. This would authorize no new
fixture, deactivation/reactivation transition or gameplay object. Without
that amendment, case 9 remains incomplete; no final #243 PASS is available.
No such amendment is inferred or applied by this record.

Local work remains in progress on the isolated #243 branch. The limited-role
command (53 focused tests), active-role inspector (44 focused tests) and
interactive lifecycle transport (41 focused tests) passed their bounded
reviews. Matrix executor/launcher tests are unfinished acceptance work with
production entry points absent; their expected red state is not a completed
repository gate. The proposed exact decommission proof also remains pending.
No final full-suite, execution or evidence approval is claimed.

#243 remains open and #208 remains NO-GO / OR-6 `BLOCKING`. #205's historical
closure, #207's restore GO and #241's non-blocking limitation remain unchanged.

Local cleanup after this stop: the task-owned temporary-memory PostgreSQL
container `tailtag-243-limited-tests` was stopped and removed. A subsequent
container listing confirmed it absent. No unrelated containers, persistent
volumes or reusable images were removed.

## Provisioning input guard stop — 2026-09-24 00:57–00:59 UTC

Reviewed tooling commit: `1468cc7`. Attempt window:
`2026-09-24T00:57:45.524105Z`–`2026-09-24T00:59:37.756849Z`.
Fresh registry reconciliation passed all structural and equality checks before
this attempt. The lifecycle launcher's provider identities, canonical preflight,
approved receipt, exact running instance and remote role/target guards passed
before the interactive confirmation prompt. The prerequisite remained managed
operator valid and limited operator absent at that inspection.

- Environment: `staging`.
- Source: `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`.
- Deployment: `cbe83780-0256-49c2-b026-34709ddb69b0`.
- Retained remote output: `FAIL_LIFECYCLE_UNCERTAIN`.
- Retained launcher result: `FAIL_TRANSPORT_UNCERTAIN`;
  phase: `interactive_ssh`.
- Last observed input boundary: public confirmation. The maintainer's retained
  account shows the public phrase split across lines. No identifier/password
  prompt or secret entry was observed or reported. No completion marker appeared.
- Supported attempt disposition: `BLOCKED_BEFORE_MUTATION`. The command requires
  successful confirmation and all hidden credential inputs before entering its
  provisioning transaction. None of those credential inputs was supplied.
  A multiline confirmation is the apparent input failure; the sanitized wrapper
  does not independently distinguish rejected confirmation from early hidden-input
  setup failure. No operator-state mismatch is inferred from this failure.
- Cases 1–9: `NOT_EXERCISED`. Provisioning, reset, decommission and matrix mutations
  did not begin. No Staging restoration is required by this attempt. The operator
  window is not declared released; release remains the maintainer's responsibility.

Do not treat the transport classification as success or overwrite it. A new
attempt must repeat all fresh target/role gates. The exact public confirmation
may be entered by the executing agent under the existing explicit authorization;
all identifiers/passwords still require the maintainer's direct hidden-TTY input.
No guard is weakened and no credential transport changes.

## Maintainer-requested safe pause — 2026-09-24 01:03 UTC

After the preceding input-guard stop, an independent source review confirmed
that no write was reachable without the missing hidden credential inputs.
A second guarded launch was initiated under the standing authorization. Its
bounded observation window falls after `2026-09-24T00:59:37.756849Z` and ends at
`2026-09-24T01:03:47Z`. No new target/role receipt, confirmation prompt, hidden
credential prompt or completion marker was retained from that launch. The
agent's conditional public-confirmation entry did not run because its required
prompt was not observed. No secret input was supplied or reported.

The maintainer requested a safe pause. Delivery of a terminal interrupt could
not be confirmed because the selected terminal surface was no longer available.
A subsequent local process inspection found no matching lifecycle executor or
SSH/Railway lifecycle transport. No new authenticated Staging observation was
made to reconstruct the missing launch result.

- Disposition: `PAUSED_NO_COMPLETION_RECEIPT`, before any established provisioning
  mutation. The command's mandatory confirmation/credential gates were not
  completed in the retained interaction; do not infer a successful provision.
- Fresh target tuple and exact guard phase for this second launch: not established
  by retained output. The preceding attempt's tuple remains historical evidence.
- Cases 1–9: `NOT_EXERCISED`; no reset, decommission or matrix action ran.
- Local test cleanup: task-owned disposable PostgreSQL container stopped,
  removed and verified absent. No matching local execution/transport remains.
- No Staging repair or follow-on inspection was attempted after the pause request.
  The exclusive window is not declared released; that decision remains with the
  maintainer. Resume only on instruction, with fresh guards and no inferred result
  from the missing receipt.

## Resumed provisioning input stop — 2026-09-24 02:04–02:05 UTC

Window: `2026-09-24T02:04:30.776190Z`–`2026-09-24T02:05:11.837540Z`.
Reviewed source remains `1468cc7`; repository unchanged apart from evidence.
Fresh approved identities, registry reconciliation, canonical preflight,
approved deployment receipt, running-instance join and role guards passed.
Environment `staging`; source `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`;
deployment `cbe83780-0256-49c2-b026-34709ddb69b0`.

The executing agent entered the exact public confirmation. The hidden identifier
prompt then appeared. The attempt subsequently ended with
`FAIL_LIFECYCLE_UNCERTAIN` and launcher `FAIL_TRANSPORT_UNCERTAIN` at
`interactive_ssh`. No password prompt, password input or completion marker was
observed. No entered identifier or secret is retained. The maintainer reported
confusion between the public confirmation and the subsequent identifier input.
The retained output establishes the identifier-input/validation boundary, not
an underlying operator-state failure.

Disposition: `BLOCKED_BEFORE_MUTATION`. The command cannot enter its write
transaction before both hidden password prompts and password validation.
Provisioning did not begin; cases 1–9 remain `NOT_EXERCISED`, and no reset or
matrix action ran. No restoration is required by this attempt. Any new attempt
must repeat fresh guards; clarify the existing input sequence without weakening
validation or changing the hidden-TTY boundary. The exclusive window is not
released by this record.

## Provisioning hard stop after hidden inputs — 2026-09-24 02:06 UTC

Window: `2026-09-24T02:06:10.429341Z`–`2026-09-24T02:06:48.117701Z`.
Reviewed command and transport: `1468cc7`.
The freshly guarded launcher reached the interactive command after approved
provider identity, public preflight, approved receipt, exact running-instance
and remote target/role checks. Before the command, the managed role was valid
and the limited role was specifically absent. These are pre-operation facts.

- Environment: `staging`.
- Source: `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`.
- Deployment: `cbe83780-0256-49c2-b026-34709ddb69b0`.
- Observed prompt progression: public confirmation, hidden identifier, hidden
  password, hidden password confirmation. The maintainer confirmed entering a
  new identifier and password. Input values were not observed or retained.
- Remote fixed result: `FAIL_LIFECYCLE_UNCERTAIN`.
- Launcher result: `FAIL_TRANSPORT_UNCERTAIN`; phase `interactive_ssh`.
- Neither a creation/reconciliation success message nor the fixed lifecycle
  completion marker was observed.

Disposition: `HARD_STOP_PROVISIONING_OUTCOME_UNCERTAIN`. Unlike the preceding
input stops, the full credential-prompt sequence was reached. The sanitized
wrapper does not distinguish input/password validation, a refused existing
state, transaction failure, or failure after a possible commit. Do not infer
which occurred. Mutation may have begun; actual provisioning outcome and the
current limited-operator state are unknown. No retry or post-failure authenticated
inspection was performed.

Cases 1–9 remain `NOT_EXERCISED`. No matrix action, reset, decommission or cleanup
mutation was invoked. No credential, identifier, permission dump or raw exception
is retained. The exclusive Staging window remains held; cleanup/final operator
state is not declared verified. #243 is incomplete and #208 remains NO-GO.

Smallest next decision: separately authorize one fresh, exact-target, read-only
operator inspection to establish whether provisioning committed and whether both
roles remain exact, alongside repository-only diagnosis of the overly broad
lifecycle failure classification. Do not authorize a provisioning retry or repair
from this receipt alone. Preserve this outcome even if later evidence clarifies
current state.

## Authorized read-only reconciliation — 2026-09-24 02:08 UTC

After the maintainer authorized another attempt, the reviewed read-only operator
inspector ran first, without provisioning or credentials. Window:
`2026-09-24T02:08:45.083854Z`–`2026-09-24T02:08:51.537255Z`.

- Fresh verified environment: `staging`.
- Source: `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`.
- Deployment: `cbe83780-0256-49c2-b026-34709ddb69b0`.
- Phase: `exact_instance_inspector`; target verified: true.
- Result: `FAIL_LIMITED_OPERATOR_MISSING`. The prior fixture and managed-role
  guards passed; no limited-role candidate was present at this observation.
- No write, provisioning retry, matrix case, reset or decommission occurred.

This establishes current inspected role absence; it does not recover the cause
of the earlier command failure or rewrite its uncertain transport receipt.
Before another provisioning attempt, the bounded repository correction in the
[limited-role contract](staging-operator-validation-243-limited-role.md#focused-lifecycle-failure-reporting-correction)
will preserve fixed known refusal classifications instead of suppressing every
command error into uncertainty. Unknown errors remain fail-closed.

## Provisioning completion marker with uncertain transport — 2026-09-24 02:17–02:18 UTC

Window: `2026-09-24T02:17:54.140857Z`–`2026-09-24T02:18:58.280920Z`.
Reviewed tooling: `8ad4b15`. The reporting correction passed 63 focused tests,
the full 2,525-test repository gate, static analysis and independent review.
The task-owned disposable test database was stopped, removed and verified absent
before this attempt.

A fresh guarded registry reconciliation passed all three structural checks and
all 12 equality checks. The lifecycle launcher independently passed its approved
identity, canonical preflight, approved deployment receipt, running-instance,
exact-instance target and role checks before displaying the public confirmation.
Its required pre-operation role result establishes managed PASS / limited MISSING
at that time, not after provisioning.

- Environment: `staging`.
- Source: `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`.
- Deployment: `cbe83780-0256-49c2-b026-34709ddb69b0`.
- Public confirmation was entered by the executing agent. The maintainer entered
  the identifier/password/password confirmation directly through the hidden TTY.
  No entered value was observed or retained.
- Remote fixed output observed: `Validation operator created.` followed by
  `TAILTAG_LIFECYCLE_COMMAND_COMPLETED`. No fixed lifecycle refusal was observed.
- Local launcher: `FAIL_TRANSPORT_UNCERTAIN`, phase `interactive_ssh`.

Disposition: `HARD_STOP_TRANSPORT_UNCERTAIN_AFTER_COMPLETION_MARKER`. The remote
output supports command completion and an intended committed creation; the
launcher did not accept the transport result. Its sanitized output does not
distinguish nonzero transport exit from rejected stderr. Do not infer the cause,
declare the whole operation successful, or retry provisioning. Actual current
role state and cleanup remain independently unverified. Treat a Staging mutation
as having potentially committed; this is not a before-mutation stop.

The sequence stopped without post-operation authenticated inspection, matrix,
reset, decommission or other mutation. Cases 1–9 remain `NOT_EXERCISED`.
A local process check found no matching lifecycle executor or Railway lifecycle
transport. No terminal transcript, credential, private identity, raw stderr or
database content is retained. The exclusive Staging window remains held.

Smallest next decision: authorize one newly preflighted, exact-instance,
read-only operator inspection to determine whether both roles are exact, plus
repository-only diagnosis of the transport-result handling. Do not retry
provisioning or perform cleanup based solely on this receipt. Preserve both
the remote completion evidence and the contradictory uncertain transport result.
#243 remains incomplete; #208 remains NO-GO.

## Independent postcondition inspection — 2026-09-24 02:26 UTC

The single newly authorized read-only operator inspection ran after fresh
approved GitHub and Railway identity checks. Its own credential-free public
preflight, approved deployment receipt, exact running-instance selection,
identity readback and repeated public preflight agreed. Window:
`2026-09-24T02:26:41.715725Z`–`2026-09-24T02:26:47.890031Z`.

- Verified environment: `staging`.
- Source: `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`.
- Deployment: `cbe83780-0256-49c2-b026-34709ddb69b0`.
- Exact-instance inspector result: `PASS`; target verified: true.
- Managed operator: `PASS` against the frozen #205 role contract.
- Dedicated limited operator: `PASS` against the exact #243 group, staff,
  nonsuperuser, password, permission and attachment contract.
- Overall role disposition: `LIMITED_OPERATOR_READY`.

This independently establishes the expected post-provision role state at the
inspection time. The preceding `FAIL_TRANSPORT_UNCERTAIN` receipt remains the
historical result of the earlier attempt; this later inspection does not change
its missing transport facts or prove why the launcher rejected the transport.
No operator, fixture, audit or other Staging state was mutated by this inspection.

Local transport diagnosis: the lifecycle launcher inherits stdout, so the
remote creation message and completion marker were visible outside the
launcher. It returns the same uncertain classification on a nonzero Railway
SSH exit, unallowlisted captured stderr, or execution interruption/timeout.
The earlier receipt retained neither the actual exit code nor stderr category.
Controlled local subprocess doubles reproduced both marker-then-nonzero-exit
and marker-then-extra-stderr rejection; they cannot determine which occurred
in the historical attempt. Railway CLI `5.57.2` passes the native SSH process's
exit status and streams through to the caller. The strict rejection matches
the reviewed fail-closed contract; independent review found no proven tooling
defect or matrix safety blocker requiring a change before the approved matrix.
The 172 focused lifecycle/matrix launcher tests passed. A terminal display
truncation could limit human observation, but cannot affect the launcher's
classification because it does not parse inherited stdout.

Cases 1–9 remain `NOT_EXERCISED` at this point. Reset and decommission have not
run. The exact limited operator is now active; the approved post-validation
decommission and audit-preserving final checks remain cleanup obligations.
The exclusive Staging window remains held through the bounded matrix, reset,
decommission and final state verification.

## Matrix authentication stop — 2026-09-24 02:27–02:29 UTC

The matrix launcher used fresh approved provider identity, credential-free
canonical preflight, approved deployment receipt, exact running-instance,
value-free #204 registry reconciliation and read-only exact operator inspection
before starting the remote matrix program. The maintainer entered the dedicated
limited and managed credentials only through their separate hidden Terminal
prompts. The public exclusive-window confirmation was entered under its
existing authorization. No credential or identifier is retained.

- Remote matrix window: `2026-09-24T02:27:42.880194Z`–
  `2026-09-24T02:29:39.627353Z`.
- Environment: `staging`.
- Source: `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`.
- Deployment: `cbe83780-0256-49c2-b026-34709ddb69b0`.
- Remote fixed classification: `FAIL_AUTHENTICATION`.
- Launcher: `FAIL_TRANSPORT_UNCERTAIN`, phase `interactive_ssh`, window
  `2026-09-24T02:27:23.306629Z`–`2026-09-24T02:29:39.978689Z`. This
  transport result is expected for a nonzero remote failure, but the retained
  receipt does not prove its specific exit/stderr details.
- The limited admin identifier/password prompts and the managed admin
  identifier/password prompts were reached. The emergency-superuser and owner
  Clerk prompts were not reached. Reaching the managed prompt implies the
  limited-role authentication step returned, but does not prove why the
  managed step failed.
- Remote `mutation_may_have_begun=false`; cases 1–9 all `NOT_EXERCISED`;
  audit event summary empty; reset and decommission `NOT_EXERCISED`.
  No approved case submission, domain transition or #204 reset ran. The
  completed limited admin login may have created an ordinary session; the
  sanitized result makes no claim that all application writes were absent.

The managed role had passed exact read-only state inspection immediately before
the matrix, but that does not establish credential correctness or HTTP login
success. The remote result does not distinguish an invalid managed identifier
or password, a local password check, an HTTP/CSRF/login failure, or a later
authentication guard. No cause is inferred and no alternate identity, account,
secret transport or authenticated retry was used. This is a hard stop under
the approved authentication boundary; no matrix result may be inferred.

The dedicated limited operator remains active according to the immediately
preceding read-only PASS, with no later lifecycle action. Its current state has
not been re-inspected after the failed authentication. The approved
audit-preserving decommission and final fixture/readiness checks remain pending.
The exclusive Staging window remains held and has not been released by this
record. #243 remains incomplete and #208 remains NO-GO. A new separately
authorized access/credential diagnosis and an explicit decision about cleanup
or a newly guarded matrix attempt are required before further live work.

## Managed authentication diagnosis stop — 2026-09-24 03:01–03:02 UTC

This is a new, separate read-only attempt after the historical matrix
`FAIL_AUTHENTICATION`; it does not reclassify that earlier result. The reviewed
diagnostic at `da11788` ran after local validation and independent review. The
approved GitHub/Railway identities, fresh canonical public preflight,
deployment receipt, unique running instance, and repeated public tuple passed.
The diagnostic launcher's independent exact-instance inspector was required to
return `PASS` for both managed and limited roles before the remote credential
prompt could start. The remote exact target and read-only role/fixture
preconditions passed before the two hidden prompts.

- Launcher window: `2026-09-24T03:01:36.878480Z`–
  `2026-09-24T03:02:19.967161Z`; phase `exact_instance_auth_diagnosis`;
  `FAIL_TRANSPORT_EXIT_STATUS`. A nonzero SSH exit is expected for the fixed
  remote failure; the launcher does not infer a credential result from exit
  status alone.
- Remote window: `2026-09-24T03:01:47.424189Z`–
  `2026-09-24T03:02:19.641681Z`; `IDENTITY_MISMATCH`. The successful remote
  completion marker was absent.
- Both retained results report the same public tuple: `environment=staging`,
  source `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, deployment
  `cbe83780-0256-49c2-b026-34709ddb69b0`. The local launcher's
  `target_verified=false` is intentional because it does not parse inherited
  remote stdout; the remote target checks passed before prompting.
- The entered identifier did not select the sole exact managed operator. The
  diagnostic intentionally does not distinguish a mistyped/missing identifier
  from one selecting another User. It did not establish whether the managed
  operator's stored password matches the entered password or whether the
  Django-admin HTTP login would succeed. No identifier, password, hash or
  account detail was retained.
- The diagnostic performed read-only queries only. No matrix case was
  submitted; cases 1–9 remain `NOT_EXERCISED`. No domain transition, audit
  mutation, #204 reset, credential reconciliation or limited-operator
  decommission occurred in this attempt. The limited validation operator was
  still exact and active at the pre-prompt inspection; no later lifecycle
  action was taken. Its current post-attempt state was not re-inspected.

This is an identity hard stop, not proof of an application authorization or
password defect. Do not retry the failed authentication, switch accounts,
rotate a credential, start the matrix or decommission on this evidence. The
exclusive Staging window remains held, and the approved audit-preserving
limited-operator decommission and final readiness checks remain pending. A
separately authorized task must establish the intended exact managed-operator
identifier through the existing private operator boundary and freshly repeat
the target and role guards before any new authentication attempt.

## Managed-login replacement transport stop — 2026-09-24 04:15 UTC

The reviewed repository-only managed-login recovery at `c5942bb` was invoked
once from a real interactive Terminal after the previously documented
managed-only scope decision. Its launcher had passed the exact managed+limited
inspector, #204 registry reconciliation, fresh public target checks, approved
deployment receipt, and unique running-instance guard before starting the
interactive SSH phase. This is a separate attempt; the earlier managed-auth
`IDENTITY_MISMATCH` remains historical.

- Launcher window: `2026-09-24T04:15:25.205728Z`–
  `2026-09-24T04:15:54.875802Z`; phase `interactive_ssh`;
  `FAIL_TRANSPORT_UNCERTAIN`.
- Public target: `environment=staging`, source
  `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, deployment
  `cbe83780-0256-49c2-b026-34709ddb69b0`.
- The public confirmation and hidden new-identifier prompt appeared. The
  retained sanitized output includes `FAIL_MANAGED_REPLACEMENT_UNCERTAIN`.
  Neither `PREPARED`, `POSTCONDITION_PASS`, nor the remote completion marker
  was witnessed. The maintainer separately confirmed that neither the new
  identifier nor password was entered before the failure. The reviewed command
  cannot enter its write transaction without both inputs, so this attempt did
  **not** transfer the managed role. The launcher still remains historically
  `FAIL_TRANSPORT_UNCERTAIN`; its output alone does not establish the cause of
  the remote/transport stop. No credential or identifier value was retained.
- A fresh, independently guarded, read-only exact-instance operator
  inspection at `2026-09-24T04:16:30.121910Z`–
  `2026-09-24T04:16:36.112003Z` returned `PASS`, `target_verified=true`,
  against the same public target. It establishes that the managed and limited
  roles were exact at that observation. It does not identify a User; the
  pre-write input boundary above establishes that this attempt did not create
  a replacement or retire the predecessor.
- No #205 matrix case, #204 reset, or limited-operator decommission was
  invoked in this attempt; cases 1–9 remain `NOT_EXERCISED`. No final cleanup
  or readiness check ran. The limited operator remains active at the read-only
  inspection. Its approved decommission and final-state checks remain pending.

Do not blindly retry replacement or begin the matrix based on this result.
Diagnose the pre-input stop and use a new fully guarded attempt only after its
interactive path is reviewed. The exclusive Staging window remains held. The
new managed credentials cannot be used for the matrix until a future completed
replacement postcondition and fresh authentication check establish them.

## Managed-login replacement input stop — 2026-09-24 04:20–04:22 UTC

A new, fully guarded interactive recovery attempt used the unchanged reviewed
launcher after the preceding attempt's no-write boundary was established. This
second attempt remains a separate historical launcher result.

- Launcher window: `2026-09-24T04:20:48.886399Z`–
  `2026-09-24T04:22:03.326722Z`; phase `interactive_ssh`;
  `FAIL_TRANSPORT_UNCERTAIN`.
- Public target: `environment=staging`, source
  `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, deployment
  `cbe83780-0256-49c2-b026-34709ddb69b0`.
- The public confirmation and hidden new-identifier prompt appeared. The
  retained output includes `FAIL_MANAGED_REPLACEMENT_UNCERTAIN`. Neither
  `PREPARED`, `POSTCONDITION_PASS`, nor the completion marker was witnessed.
  The maintainer confirmed that only an identifier was entered, no password
  was entered, and the identifier did not satisfy the reviewed
  `staging_managed_`-prefixed format. The actual identifier was not retained.
- The command requires both hidden identifier and password inputs before its
  write transaction. Thus this attempt did **not** transfer the managed role.
  The nonconforming identifier is a demonstrated input-contract mismatch; the
  generic launcher result alone does not prove which remote/transport failure
  path ended the process. No fresh post-attempt role inspection was performed.
- No #205 matrix case, #204 reset, or limited-operator decommission ran;
  cases 1–9 remain `NOT_EXERCISED`. The limited-operator decommission and final
  readiness checks remain pending. The exclusive Staging window remains held.

Before any new attempt, the maintainer must choose an unused local username
that meets the existing exact prefix and 1–64 lowercase letter, digit, or
underscore suffix rule. No Clerk identity is created or required for this
synthetic managed-login replacement. A future attempt must independently
repeat every target and operator guard; this
record does not authorize inferring current role state or bypassing them.

## Managed-login replacement postcondition — 2026-09-24 04:24–04:25 UTC

A subsequent, freshly guarded managed-only replacement attempt used a new
unused local identifier satisfying the reviewed reserved format. The
maintainer entered the identifier and password through separate hidden TTY
prompts. No value was retained. The launcher passed its read-only managed and
limited role guard, #204 registry reconciliation, public target/approved
receipt/unique-instance guards, and remote exact-instance guard before the
interactive mutation. The preceding stopped attempts remain unchanged.

- Launcher window: `2026-09-24T04:24:03.852642Z`–
  `2026-09-24T04:24:41.210309Z`; phase `interactive_ssh`;
  `FAIL_TRANSPORT_UNCERTAIN`. This is the historical SSH/launcher result and
  is **not** rewritten as transport success.
- Public target: `environment=staging`, source
  `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, deployment
  `cbe83780-0256-49c2-b026-34709ddb69b0`.
- The maintainer witnessed fixed `PREPARED`, `POSTCONDITION_PASS`, and
  `TAILTAG_MANAGED_REPLACEMENT_COMMAND_COMPLETED` markers. The reviewed remote
  command emits `POSTCONDITION_PASS` only after its committed transfer passes
  a separate read-only check of old-login retirement, exact new managed role,
  unchanged limited role, unchanged managed Group permissions, and unchanged
  historical operator-audit rows. The final completion marker follows the
  command's successful return.
- A fresh independent exact-instance operator inspection at
  `2026-09-24T04:24:56.844660Z`–`2026-09-24T04:25:02.886489Z` returned
  `PASS`, `target_verified=true` at the same approved public target. Both the
  current managed and limited roles were exact at this observation. This
  inspection alone does not identify the predecessor; the remote witnessed
  postcondition supplies the retirement proof.
- No #205 matrix case, #204 reset, or limited-operator decommission ran in
  this replacement attempt. Cases 1–9 remain `NOT_EXERCISED`. The limited
  operator remains active; final cleanup and readiness checks remain pending.

Do not repeat replacement. The next required guard is a separate hidden-TTY
read-only authentication check of the **new** managed credentials, followed by
the bounded matrix's real Django-admin login before any case submission. The
exclusive Staging window remains held.

## New managed-login authentication mismatch — 2026-09-24 04:25–04:27 UTC

The separate reviewed authentication diagnostic ran once after the witnessed
replacement postcondition and fresh independent managed+limited role PASS.
Its launcher repeated the approved identity, public target, receipt,
exact-instance and read-only operator guards before hidden credential input.
The maintainer entered an identifier and password only through the hidden
Terminal prompts; neither value was retained.

- Launcher window: `2026-09-24T04:25:54.835353Z`–
  `2026-09-24T04:27:30.922781Z`; phase `exact_instance_auth_diagnosis`;
  `FAIL_TRANSPORT_EXIT_STATUS`, `target_verified=false` in the launcher
  receipt. A nonzero remote exit is expected for the remote fixed failure;
  the launcher does not parse the inherited remote output.
- Remote window: `2026-09-24T04:26:05.185479Z`–
  `2026-09-24T04:27:30.612044Z`; `IDENTITY_MISMATCH`.
- Both receipts identify `environment=staging`, source
  `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, deployment
  `cbe83780-0256-49c2-b026-34709ddb69b0`. The remote target and role
  preconditions passed before prompting. The entered identifier did not
  select the sole exact current managed operator. The password was not
  classified as accepted or rejected. The maintainer could not confirm from
  private notes whether the identifier matched the one entered during the
  successful replacement.
- This diagnostic performed read-only database queries only. No #205 case,
  #204 reset, managed credential change, limited-operator decommission, or
  other Staging mutation occurred in this attempt. Cases 1–9 remain
  `NOT_EXERCISED`; final cleanup/readiness checks remain pending.

This is an unresolved managed-login access boundary, not evidence of a
password or application-authorization defect. Do not start the matrix or
replace/delete identities based only on this result. The exclusive Staging
window remains held while a bounded private recovery is designed and
reviewed. The prior witnessed replacement postcondition remains historical
evidence; this failed credential check does not undo it.

## Managed-password rotation postcondition — 2026-09-24 05:10–05:11 UTC

The repository-only password recovery at `7aa5cbb` passed the full local
backend gate and independent specification, code, and security review before
this new guarded attempt. The exact managed and limited roles and the #204
registry reconciliation passed a fresh read-only check before rotation. The
maintainer entered the new password and confirmation through hidden TTY
prompts; no credential or operator identifier was retained.

- Launcher window: `2026-09-24T05:10:03.335971Z`–
  `2026-09-24T05:10:56.331296Z`; phase `interactive_ssh`;
  `FAIL_TRANSPORT_UNCERTAIN`. Preserve this launcher result as issued; do not
  relabel the SSH transport as successful.
- Public target: `environment=staging`, source
  `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, deployment
  `cbe83780-0256-49c2-b026-34709ddb69b0`.
- The maintainer witnessed fixed `PREPARED`, `POSTCONDITION_PASS`, and
  `TAILTAG_MANAGED_PASSWORD_ROTATION_COMPLETED` markers. The reviewed remote
  command emits `POSTCONDITION_PASS` after a separate read-only postcommit
  check verifies the same managed User, identifier, group and permissions,
  unchanged limited-role state, unchanged audit snapshot, and the committed
  password hash against the entered password without a setter.
- A fresh independent exact-instance operator inspection at
  `2026-09-24T05:11:12.341275Z`–`2026-09-24T05:11:19.027210Z` returned
  `PASS`, `target_verified=true` at that same public target. This independently
  establishes exact current managed and limited role state; it does not test
  the entered password. A separate read-only authentication check remains
  required before any matrix attempt.
- No #205 matrix case, #204 reset, or limited-operator decommission ran in
  this rotation attempt. Cases 1–9 remain `NOT_EXERCISED`; final cleanup and
  readiness checks remain pending. The exclusive Staging window remains held.

Do not repeat the rotation. Preserve the launcher uncertainty separately from
the witnessed remote postcondition and the independent role inspection.

## Managed-password authentication proof — 2026-09-24 05:12 UTC

The reviewed read-only authentication diagnostic ran once with the newly
saved password entered through a hidden TTY prompt. It privately selected the
sole exact managed operator, rechecked the target and pinned role after input,
and verified the stored password hash without a setter. No identifier or
credential value was retained.

- Remote window: `2026-09-24T05:12:33.256844Z`–
  `2026-09-24T05:12:43.709520Z`; fixed classification
  `CREDENTIAL_ACCEPTED` at `environment=staging`, source
  `856a43863ec4e8f2f68cc2a6aaf5b333e8299a7a`, deployment
  `cbe83780-0256-49c2-b026-34709ddb69b0`. The remote completion marker
  `TAILTAG_MANAGED_AUTH_DIAGNOSIS_COMPLETED` was witnessed.
- Launcher window: `2026-09-24T05:12:19.654862Z`–
  `2026-09-24T05:12:44.066355Z`; phase `exact_instance_auth_diagnosis`;
  `FAIL_TRANSPORT_STDERR`, `target_verified=false` in its conservative
  transport receipt. The captured stderr was not retained or classified;
  do not relabel the launcher receipt as PASS. The fixed remote classification
  and completion marker separately establish that the exact-instance
  read-only password check completed and accepted the credential.
- No #205 matrix case, #204 reset, decommission, or Staging mutation occurred
  in this authentication check. Cases 1–9 remain `NOT_EXERCISED`; the limited
  operator remains active, final cleanup remains pending, and the exclusive
  Staging window remains held.

The next bounded matrix attempt must independently rerun every target and
role guard and prove real Django-admin HTTP login before case submission.

## Matrix attempt stopped at limited-operator prompt — after 2026-09-24 05:12 UTC

The maintainer confirmed that the subsequent matrix Terminal stopped while
waiting for the limited admin identifier. The exact attempt window and a final
launcher receipt were not retained, so no fresh target tuple or completed
target/role guard result is attributed to this attempt. Earlier successful
inspections remain point-in-time evidence only.

- Fixed outcome for this attempt: `STOPPED_BEFORE_CASE_SUBMISSION`.
- The limited identifier/password, managed password, emergency credentials and
  synthetic Clerk token were not established as accepted by this attempt.
- Cases 1–9: `NOT_EXERCISED`; no case submission or domain transition occurred.
- #204 reset and limited-operator decommission: not invoked.
- No Staging mutation occurred in this matrix attempt. Prior operator
  provisioning/replacement/rotation remain separate historical operations.
- The limited operator was last independently verified active before this
  attempt. Its decommission and final cleanup/readiness checks remain pending;
  current live operator state has not been reinspected after the stop.
- The exclusive #243 operator window remains held until its owner explicitly
  hands it off or a reviewed cleanup/retirement procedure establishes final
  state. This stopped prompt does not prove #243 cleanup or release.

The decision to plan a clean-slate replacement preserves this attempt as
historical Staging evidence. It does not turn any #205 case into a PASS or
erase the outstanding limited-role cleanup obligation on the old stack.

## Replacement promotion preflight blocked — 2026-09-25

After #248 merged, a read-only promotion configuration preflight stopped
before any deployment submission with fixed result
`staging configuration invalid`. The exact attempt timestamps were not
retained. The fresh credential-free canonical preflight reported
`environment=staging`, source
`fc1376e9b4387cb46e37ef3f60191b2ce7f06c68`, and deployment
`c34c45bb-6eb8-488d-8114-d1dd931cf25e`; the approved replacement
receipt and exact active-instance check passed. Approved GitHub and Railway
identity checks and replacement target pins also passed.

A subsequent separately authorized, sanitized read-only comparison found
the service binding, environment binding, repository source, null image
source, and readiness path all `PASS`; only the promotion script's
pre-deploy-command comparison was `MISMATCH`. A focused equality check
confirmed the live setting was the approved replacement
`python -m config.replacement_migrate` wrapper. The promoter still expected
the retired direct Django migration command. This is a repository tooling
contract mismatch, not evidence that the Staging migration configuration
drifted. No raw provider configuration was retained.

No promotion submission, #205 matrix case, #204 reset, operator provisioning,
or Staging mutation occurred. Cases 1–9 remain `NOT_EXERCISED` on the
replacement generation. This preflight result remains historical; a corrected
promoter requires its own reviewed repository change and fresh target gates
before any later live attempt.

## Replacement promotion and prerequisite readback — 2026-09-25

The reviewed #202 promoter on merged `main` submitted one eligible accepted
source, `99e6466e1bd5432025c085134e72c2c46eb92dbc`, after approved
GitHub/Railway identity, canonical public target, replacement pins, approved
handoff receipt, exact running-instance readback, guarded migration-command
configuration, disabled autodeploy, and an exclusive operator window passed.
The exact-SHA successful push workflow was run `36095037272`, attempt 1.
The sanitized [deployment receipt](staging-deployments/2adc748c-ee54-4446-958c-f49a384925be.json)
records deployment `2adc748c-ee54-4446-958c-f49a384925be` as `SUCCEEDED`
and `ACTIVE`, including migration, startup, readiness, identity, and public
smoke. Fresh canonical public and exact-instance readback then agreed on
`environment=staging` and the same source/deployment tuple. No second
promotion submission occurred.

The fresh replacement operator inspector returned `FAIL_FIXTURE_MISSING`
with exact-instance target verification `true`; it stopped before managed or
limited operator checks. A bounded separate read-only check on that same
current target established API/PostgreSQL service binding `PASS`, #204 reset
registry `MISSING`, and ordinary Clerk-bound TailTag User count category `ONE`.
The independently retained private replacement reset configuration was also
absent at the local ownership/mode check. These observations do not establish
the state of the managed, limited, or emergency roles, the designated media,
or the rest of the #204 fixture baseline. No sentinel provision, reset,
operator change, or #205 matrix action occurred. Cases 1–9 remain
`NOT_EXERCISED`; the exclusive window remains held pending prerequisite work.

## Replacement ordinary identity preparation — 2026-09-25

Window: approximately 12:54–14:09 UTC. The approved replacement Staging
Clerk application initially had one synthetic account. A second, separately
designated synthetic catcher account was created through the Clerk form; the
maintainer entered its password and new-device code privately. Its signed-in
account page was observed without retaining an identifier or credential.

Before the normal API call, approved GitHub and Railway identities passed,
canonical credential-free preflight observed `environment=staging`, source
`99e6466e1bd5432025c085134e72c2c46eb92dbc`, and deployment
`2adc748c-ee54-4446-958c-f49a384925be`, matching the approved promotion
receipt. The reviewed exact-instance inspector returned
`FAIL_FIXTURE_MISSING` with `target_verified=true`, as expected while the
#204 sentinel is absent. A one-use, independently reviewed client compared
the normal session token's subject with the separately copied subject from
the signed-in catcher session before sending one authenticated `/api/me/`
request. Its fixed result was `PASS_CATCHER_API_AUTH`; that line alone was
not treated as proof of the database binding. The token and subject were
transferred through hidden TTY prompts with clipboard clearing and were not
retained.

A separate independently reviewed exact-instance reconciliation reran the
identity, receipt, active-instance and public preflight guards. In one
repeatable-read, read-only database transaction, it required exactly two
distinct ordinary, non-staff, non-superuser Users bound to the exact privately
supplied approved owner and catcher subjects, with unusable local passwords
and no group or direct-user permissions; it also required the #204 registry
to remain absent. Its maintainer-reported fixed result was `PASS`. A prior
read-only binding check on the same replacement generation established that
the API was attached to the approved PostgreSQL service; this identity
postcondition does not independently re-prove the database name or cluster
identifier needed before #204 provision.

The replacement Staging R2 bucket was separately observed empty. Thus
designated media and the new private #204 reset configuration remain missing;
sentinel provisioning, reset/reseed, operator-role checks, and cases 1–9 were
not run. This preparation created the designated Clerk account and invoked
its normal TailTag User resolution once. It did not invoke a #204 fixture,
operator, audit, or gameplay action; those domain tables were not independently
reread in this postcondition. The exclusive Staging window remains held.

## Replacement designated media preparation — 2026-09-25

The replacement Staging R2 bucket was observed empty before the action. The
maintainer approved one upload of a 256×256 synthetic rehearsal PNG normalized
by TailTag's image code. The local candidate used one valid opaque `images/`
key. The Cloudflare upload flow was submitted once; its immediate browser
response did not report completion, so no second upload was submitted. A fresh
read-only bucket inventory then showed exactly one `image/png` object under
`images/`, with the expected 2.87 KB displayed size. A value-free comparison
also matched its opaque filename to the one locally prepared candidate. No
old-generation media was copied and no additional object was observed in that
inventory.

This establishes bucket presence at that observation time, not application
readability or an exact #204 media binding. Those remain pending fresh guarded
verification before sentinel provisioning. No #204 provision/reset, operator
action, or #205 matrix case occurred; the exclusive Staging window remains held.

## Replacement #204 private prerequisite check — 2026-09-25

Window: approximately 14:18–14:22 UTC. A separately reviewed, one-use
read-only check first verified approved GitHub/Railway identities, the canonical
public Staging tuple, approved deployment receipt, exact running API instance,
and matching API/PostgreSQL service `DATABASE_URL` binding. It observed source
`99e6466e1bd5432025c085134e72c2c46eb92dbc` and deployment
`2adc748c-ee54-4446-958c-f49a384925be` throughout its guarded execution.
The maintainer supplied the two already approved Clerk subjects through
separate hidden TTY prompts. On the exact instance, a read-only transaction
required the two exact ordinary, nonstaff, nonsuperuser User bindings, absent
#204 sentinel, zero prepared transactions and subscriptions, a superuser
database executor, and actual connected database facts. A separate storage
read required the designated replacement R2 object to match the locally
prepared image's SHA-256. The fixed result was
`PASS_MEDIA_READ_DATABASE_BINDING_AND_PRIVATE_CONFIG`.

The check created only the independent owner-only local replacement #204
expected-configuration file. A separate local read verified its nine-key
schema, owner, parent-directory mode `0700`, and file mode `0600` without
rendering values. The random reset identity, database values, Clerk subjects,
and media key remain private. The clipboard was cleared after subject transfer.
No Staging database, fixture, operator, audit, or gameplay state was changed.
The sentinel is still absent and the #204 baseline remains unproven. Cases
1–9 remain `NOT_EXERCISED`; the exclusive Staging window remains held.

## Replacement #204 sentinel and baseline — 2026-09-25

After fresh approved GitHub/Railway identity checks and canonical public
preflight, the reviewed replacement-bound `api-staging-reset-provision-ssh`
command was invoked once. It observed source
`99e6466e1bd5432025c085134e72c2c46eb92dbc` and deployment
`2adc748c-ee54-4446-958c-f49a384925be`. Its sentinel-only receipt reported
`provision_postcondition=PASS` and `cleanup_confirmed=true`. The subsequent
value-free, read-only three-way check reported `PASS`: registry singleton,
structure, and root completeness passed, and all 12 private-configuration /
registry / connected-database equality checks matched.

The guarded `api-staging-reset-ssh` command then ran once against the same
public tuple. Its sanitized receipt reported `baseline_version=1`, two
profiles, one Convention, two Fursuits, two enrollments, two activations, zero
Catches, zero sessions, zero credentials, and `cleanup_confirmed=true`. A
separate read-only three-way reconciliation again returned `PASS`, including
root completeness and all 12 equalities. The first exact-instance #243
operator inspector reached the role phase with `target_verified=true` and
reported `FAIL_MANAGED_OPERATOR_MISSING`; it stopped before limited-role
inspection. No operator account was provisioned by #204. No #205 matrix case
has run; cases 1–9 remain `NOT_EXERCISED`. The exclusive Staging window remains
held while the missing role is handled through its separate approved boundary.

## Replacement managed-operator creation and postcondition — 2026-09-25

Window: approximately 14:31–14:33 UTC. The first replacement role inspection
had established `FAIL_MANAGED_OPERATOR_MISSING` with the #204 baseline guard
and exact target verified. A separately reviewed creation-only launcher
rechecked the managed-role absence, #204 three-way reconciliation, approved
GitHub/Railway identities, public source/deployment tuple, approved receipt,
exact running instance, and matching API/PostgreSQL database binding. The
maintainer entered a new unused dedicated local operator identifier and
password through the real hidden TTY; no Clerk identity was created. The
remote command displayed the fixed `Staging operator created.` and completion
markers, while the SSH launcher returned `FAIL_TRANSPORT_UNCERTAIN`. Preserve
that launcher result as uncertain; it is not a transport PASS and the mutation
was not retried.

A new independent, freshly preflighted, read-only exact-instance operator
inspection then reported `FAIL_LIMITED_OPERATOR_MISSING` with
`target_verified=true` against source
`99e6466e1bd5432025c085134e72c2c46eb92dbc` and deployment
`2adc748c-ee54-4446-958c-f49a384925be`. The inspector reaches that result
only after the replacement #204 baseline and exact managed-role checks pass.
This separately establishes the managed operator's required state and the
dedicated limited role's absence; it does not imply emergency-role readiness.
No matrix case or cleanup reset ran. The managed account remains active for
the approved matrix, and the exclusive Staging window remains held.

## Replacement limited-operator creation and postcondition — 2026-09-25

Window: approximately 14:34–14:36 UTC. The reviewed lifecycle launcher
freshly required the managed-role PASS / dedicated limited-role MISSING
classification, approved target, and #204 registry reconciliation. The
maintainer entered a new unused dedicated limited local operator identifier
and password through real hidden TTY prompts. The remote command displayed
its fixed creation and completion markers, while the launcher returned
`FAIL_TRANSPORT_UNCERTAIN`. Preserve that transport classification; no
provisioning retry occurred.

A separate freshly preflighted read-only exact-instance operator inspection
then reported `PASS` with `target_verified=true` against source
`99e6466e1bd5432025c085134e72c2c46eb92dbc` and deployment
`2adc748c-ee54-4446-958c-f49a384925be`. This independently establishes
that the managed and dedicated limited roles both meet their exact frozen
contracts, including the limited role's narrow permission shape. Emergency
role state is still uninspected. No #205 matrix case, #204 cleanup reset, or
role decommission ran. Both synthetic operator rows remain active for the
approved validation; the exclusive Staging window remains held.

## Replacement emergency-role inspection — 2026-09-25

After managed and limited roles independently passed, a new read-only check
reverified approved GitHub/Railway identities, the current public source and
deployment, approved receipt, exact running instance, full #204 three-way
reconciliation, and exact managed/limited inspector PASS. The existing
reviewed emergency-state check ran only on that instance and returned
`ABSENT`; a repeated public preflight retained the same tuple. The
conditionally approved dedicated synthetic emergency actor is therefore
needed for Case 5. No emergency provisioning, #205 matrix action, or cleanup
ran in this read-only inspection. The exclusive Staging window remains held.

## Replacement emergency creation input stop — 2026-09-25

Window: 14:38–14:39 UTC. The reviewed emergency launcher passed its prior
read-only guards and reached the real interactive SSH command. After the
confirmation phrase, the command displayed the hidden operator-identifier
prompt and then fixed `FAIL_EMERGENCY_COMMAND`; no password prompt or creation
completion marker was observed. The launcher classified the transport
`FAIL_TRANSPORT_UNCERTAIN`. The specific prompt failure is not established by
that generic marker, and no retry was submitted.

A separate freshly guarded, read-only exact-instance check then required
the current public tuple, approved receipt, #204 three-way reconciliation,
and exact managed/limited operator PASS. The emergency state was `ABSENT`
and the public tuple remained source
`99e6466e1bd5432025c085134e72c2c46eb92dbc`, deployment
`2adc748c-ee54-4446-958c-f49a384925be`. This establishes no emergency
account survived the attempt; it does not identify whether input format,
hidden-input availability, or transport caused the prompt failure. No matrix
case or cleanup reset ran. The exclusive Staging window remains held.
The maintainer subsequently confirmed that the entered identifier lacked the
required `staging_emergency_` prefix. This explains the command's documented
identifier rejection; the original generic failure and uncertain transport
receipt remain historical. The separate `ABSENT` postcondition supports a new
fully guarded attempt without treating the failed attempt as a live PASS.

## Replacement emergency creation and postcondition — 2026-09-25

Window: approximately 14:42–14:45 UTC. After the prior `ABSENT`
postcondition and the corrected identifier format, the reviewed emergency
launcher repeated its target, #204 registry, managed/limited-role, database,
and emergency-absence guards. The maintainer entered one new dedicated
synthetic emergency local identifier and password through real hidden TTY
prompts. The remote command displayed its fixed creation and completion
markers, while the launcher returned `FAIL_TRANSPORT_UNCERTAIN`; that
transport classification remains unchanged, and no provisioning retry was
submitted.

A separate freshly guarded read-only exact-instance check then required the
same canonical source `99e6466e1bd5432025c085134e72c2c46eb92dbc` and
deployment `2adc748c-ee54-4446-958c-f49a384925be`, approved receipt,
matching #204 private/registry/database facts, and exact managed and limited
operator PASS. The reviewed emergency-state check returned `READY`, and a
repeat public preflight retained the same tuple. This independently
establishes the emergency actor's exact approved synthetic state. No matrix
case, cleanup reset, or operator decommission has run. All three operator
actors remain active for the bounded matrix; the exclusive Staging window
remains held.

## Replacement matrix confirmation stop — 2026-09-25

Window: approximately 14:46–14:48 UTC. The reviewed matrix launcher passed
its target, registry, exact-instance operator, and deployed-control guards.
The remote matrix then requested the exact exclusive-window confirmation. The
maintainer's entered text omitted the word `window`; the bounded result was
`FAIL_CONFIRMATION`, `mutation_may_have_begun=false`, empty audit-event
evidence, and Cases 1–9 all `NOT_EXERCISED`. No credential prompt, case
submission, #204 cleanup reset, or decommission was reached. The outer SSH
launcher returned `FAIL_TRANSPORT_UNCERTAIN`; preserve that transport result
separately from the remote confirmation classification. Do not infer a matrix
PASS from reaching the remote command.

A fresh independent read-only guard then required the same canonical source
and deployment, approved receipt, #204 private/registry/database agreement,
synthetic baseline, exact managed/limited roles, and emergency state `READY`.
It returned `POST_CONFIRMATION_GUARDS_PASS`. The exclusive Staging window
remains held; a new matrix attempt must begin from Case 1 with the full exact
confirmation phrase.

## Replacement matrix limited-authentication stop — 2026-09-25

Remote matrix window: 14:50:16–14:51:29 UTC. After the prior independent
read-only guards passed, the maintainer entered the exact exclusive-window
confirmation and reached the hidden limited-operator identifier and password
prompts. The remote matrix classified the attempt `FAIL_AUTHENTICATION`, with
`mutation_may_have_begun=false`, no audit events, and Cases 1–9 all
`NOT_EXERCISED`. The source was
`99e6466e1bd5432025c085134e72c2c46eb92dbc`; the deployment was
`2adc748c-ee54-4446-958c-f49a384925be`. No owner session prompt, case
submission, #204 cleanup reset, or operator decommission was reached. The
launcher separately classified SSH transport `FAIL_TRANSPORT_UNCERTAIN` for
14:49:35–14:51:30 UTC; this does not change the remote pre-mutation result.

The maintainer reported that the dedicated limited operator's saved local
identifier and password may have been lost. This is an input uncertainty, not
proof of Staging role drift or an application authentication defect. The
limited account was previously proven exact by independent read-only
inspection, but its current post-attempt state has not yet been freshly
rechecked. No credential was retained in this evidence. The exclusive Staging
window remains held. Recovery requires a separately validated exact-account
credential path and new preflight; do not blindly retry the matrix or
provision another limited account.

## Replacement limited-password recovery — 2026-09-25

Repository-only recovery at commit `b547218` added a password-only action for
the existing exact synthetic limited account and removed the matrix's need
for its identifier. The independent review found no remaining material issue;
the full backend gate passed 3,210 tests, Ruff, Pyright, Semgrep, Django,
migration, OpenAPI and Gunicorn checks. Doctor, changed-document links and
`git diff --check` passed. These are local tooling results, not live matrix
evidence.

Immediately before recovery, fresh read-only #204 three-way registry
reconciliation returned `PASS` on all structural and equality checks. The
read-only exact-instance operator inspector returned `PASS` with
`target_verified=true` at source
`99e6466e1bd5432025c085134e72c2c46eb92dbc`, deployment
`2adc748c-ee54-4446-958c-f49a384925be` during 15:07:39–15:07:47 UTC.
The reviewed lifecycle launcher then repeated its own current-target,
receipt, exact-instance and role guards. The maintainer entered a new limited
password twice through the real hidden terminal. The remote command printed
`Validation operator password rotated.` and
`TAILTAG_LIFECYCLE_COMMAND_COMPLETED`; the outer launcher returned
`FAIL_TRANSPORT_UNCERTAIN` for 15:08:59–15:09:49 UTC. Preserve that transport
classification and do not retry the rotation.

A new independent read-only exact-instance operator inspection at
15:10:09–15:10:16 UTC returned `PASS`, `target_verified=true` at the same
source/deployment. This independently establishes that managed and limited
role state remains exact after the attempted rotation; it cannot by itself
prove which password is accepted. The next newly guarded matrix must prove
limited authentication before any case submission. Cases 1–9 remain
`NOT_EXERCISED`; #204 cleanup reset and both decommissions remain pending.
The exclusive Staging window remains held.

## Replacement matrix emergency-authentication stop — 2026-09-25

The newly guarded matrix attempt used the exact confirmation phrase and the
password-only limited, managed and dedicated emergency prompts. The remote
matrix returned `FAIL_AUTHENTICATION` for 15:45:44–15:46:06 UTC at canonical
source `99e6466e1bd5432025c085134e72c2c46eb92dbc` and deployment
`2adc748c-ee54-4446-958c-f49a384925be`. Because the emergency prompt was
reached after the sequential limited and managed logins, those two
authentication paths completed during this attempt. The emergency path did
not complete; this result alone does not distinguish a rejected password,
actor-state drift, admin-login response failure, or execution error.

The remote result reports `mutation_may_have_begun=false`, empty audit-event
evidence, and Cases 1–9 all `NOT_EXERCISED`. The owner Clerk token prompt,
case submissions, #204 reset and both decommissions were not reached. The
launcher separately returned `FAIL_TRANSPORT_UNCERTAIN` for
15:45:14–15:46:07 UTC; preserve both classifications. No matrix retry or
Staging remediation has been submitted. All three synthetic operators remain
subject to fresh state inspection; cleanup is pending and the exclusive
Staging window remains held.

## Replacement emergency password diagnosis — 2026-09-25

A separate reviewed, one-use read-only diagnosis checked the saved emergency
password on the exact replacement Staging instance. Its remote fixed result was
`CREDENTIAL_REJECTED` during 15:52:05–15:53:55 UTC at source
`99e6466e1bd5432025c085134e72c2c46eb92dbc` and deployment
`2adc748c-ee54-4446-958c-f49a384925be`. The check required the dedicated
emergency actor to be `READY`, pinned its identity and password hash across the
hidden prompt, and compared the entered password without a write. This proves
only that the password entered for this diagnosis did not match that actor's
current stored hash. It does not prove why the user-held value differed, nor
does it test the later admin HTTP login path. The outer Railway launcher
separately returned `FAIL_TRANSPORT_UNCERTAIN`; preserve that transport result
without rewriting the remote classification or the earlier matrix attempt.

No matrix case, reset, provisioning, decommission, fixture write, or audit write
occurred during this diagnosis. Cases 1–9 remain `NOT_EXERCISED`; the managed,
limited, and emergency actors' active state requires fresh verification before
any further action. The approved emergency bootstrap is an absent-role creation
path, not a password-rotation path. Restoring usable emergency access would
require a separately reviewed, exact-actor, password-only remediation with its
own authorization and guards. No such remediation was run. The exclusive
Staging window remains held and matrix/cleanup obligations remain pending.
