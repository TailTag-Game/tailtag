# #243 dedicated limited validation operator

Status: lifecycle command, exact-role inspector and interactive lifecycle
transport implemented and independently reviewed; the matrix and launcher
now also pass independent review after the explicit evidence-mode amendment. This
supplements the [bounded validation plan](staging-operator-validation-243-plan.md)
under the maintainer's standing authorization. Historical attempts, including
[the missing-role observation](staging-operator-validation-243-execution-attempts.md),
remain unchanged. No new normal field-beta role is introduced.

## Frozen role and lifecycle contract

The actor is staff (`is_staff=True`), never a superuser, with a usable local
administration password. Its only permissions are
`profiles.set_profile_enabled` and `profiles.view_playerprofile`. It has no
fursuit enablement, catch removal, credential revocation, session termination,
activation deactivation, enrollment removal, Convention playability, generic
change/delete, account administration or other authority. The role is materially
narrower than the existing managed operator.

Use one dedicated group, `TailTag #243 Validation Operator`, with exactly those
two permissions and exactly one member. The member has no direct permissions,
no other group, and no player profile or gameplay ownership/participation.
This fixes a narrow provisioning shape within the approved effective-permission
contract. The full managed group and bootstrap are unchanged.

The read-only inspector must verify this exact dedicated shape after
provisioning, not merely the union of effective permissions. Preserve its
existing explicit-permission candidate discovery and missing/ambiguous
classifications, also including members of the dedicated marker group even
when its permissions have drifted to empty. Then require the sole dedicated
group/member, no direct permissions, exactly
the two approved group permissions, staff/non-superuser and usable password,
and no gameplay attachments. A same-permission direct grant or unrelated group
must fail the limited-role state/permission guard. This newly frozen provisioning
shape does not retroactively change historical inspection results.

For matrix step B, the limited actor submits the one denied fursuit operation,
covering cases 2, 4 and 7. The maintainer's current instruction assigns step C
(cases 3, 6 and 8) to the existing permitted **managed** non-superuser. This
changes only the step-C actor from the earlier proposal; the same profile
transition, two successful-transition bound and other sequencing remain.
The managed actor cannot substitute for the limited actor in step B.

`OperatorAuditEvent.actor` uses `PROTECT`; preserve the actor row permanently
while audit history refers to it. After all active-role evidence is complete,
run the reviewed decommission action: set staff false, make its local password
unusable, and clear the dedicated group's permissions. Retain the empty group
and its sole member as an unambiguous synthetic lifecycle marker; retain all
audit rows and actor relationships unchanged. No deletion, audit rewrite,
provider operation or profile creation is part of either action. There is no
reactivation path in this bounded command.

## Acceptance contract

1. A dedicated `staging_validation_operator` management command exposes only
   `provision` and `decommission`. Require exactly Railway `staging` / `api`,
   a real stdin/stdout TTY, and exact action-specific confirmation. Hidden
   `getpass` prompts are the only identifier/password input. Reject CLI input
   errors without reflecting arguments. Fail closed if hidden terminal input
   is unavailable; never fall back to echoed input.
2. Provision either a previously unused dedicated identity with a new dedicated
   group, or reconcile only its already exact active shape. Reconciliation
   may update its password only. Existing ordinary players, superusers, managed
   operators, unrelated staff, group collisions, extra members/groups/direct
   permissions, missing/excess group permissions and gameplay attachments
   are refusals without mutation. No automatic adoption after an insertion race.
3. Resolve exactly both approved permissions before writing. Enclose creation,
   group membership/permission assignment and reconciliation in a transaction;
   any failure rolls everything back. User/group uniqueness and locked existing
   rows prevent duplicate ownership. Emit only fixed sanitized outcomes/errors.
4. Require a nonempty bounded identifier with no whitespace/control characters
   and a password passing the existing Django validators, entered twice through
   hidden prompts. Do not place private input in argv, environment, logs,
   exceptions, artifacts or evidence. Keep Django query debug logging from
   leaking provisioning input; do not modify global logging configuration.
5. Decommission only the exact dedicated active role, or recognize its exact
   already-decommissioned shape without further changes. Require hidden actor
   identifier and its separate exact confirmation. Refuse every ambiguous or
   drifted shape. Clear only its dedicated group's permissions, revoke its
   staff/password access, and preserve User/group membership/audit content.
   Existing admin sessions become unusable through staff/password checks.
6. The normal managed operator and its command remain unchanged. Each command
   must refuse the other's role. No changes to product authorization, public
   API, models, migrations or the eight sensitive operations.
7. The live execution is one guarded provisioning attempt, only after fresh
   approved identities, public/exact-instance tuple agreement and receipt,
   and a fresh inspector result proving managed PASS / limited MISSING.
   Perform an independently guarded post-provision inspection before the matrix.
   Any ambiguous mutation, unexpected identity collision or role verification
   failure stops execution without a retry.
8. Only the existing frozen matrix mutations and guarded #204 reset are
   authorized after all prerequisites are fresh and green. Decommission occurs
   after audit retention and final fixture evidence. Reset never repairs roles.
   Record each case independently and preserve all historical attempts.

## Test surface and scope guard

Scope: STANDARD COMPACT for the lifecycle command; SECURITY, DATA INTEGRITY,
TEST ADEQUACY and RELIABILITY assurance. The explicit maintainer specification
supplies alignment. Further execution-tool changes are separate bounded review
units with their own tests/review before use.

Expected files: the dedicated account management command and its focused tests,
this contract, the existing #243 plan/evidence, and a narrow reviewed execution
path if necessary. Reuse Django command, password-validation, transaction and
operator patterns. No new dependencies, role-management framework, schema,
product route or change to the managed bootstrap.

Tests invoke the public Django `call_command` seam against disposable local
PostgreSQL. Terminal/getpass surfaces may be replaced with controlled test
inputs; ORM identity/group/permission/transaction behavior must be real.
Force database failure through the existing test pattern or a narrow failing
ORM call after the first write, then compare complete pre/post role and audit
state. Exercise both directions of role-collision refusal against the real
managed command. A real local PTY regression verifies hidden prompt behavior
and refusal if terminal echo cannot be disabled. No test may use live Staging.

Before live use: independent test authorship and adequacy approval, separate
implementation, focused #205/#243 tests, full repository gate when practical,
static analysis, doctor, diff/link checks, and independent review of privilege
exactness, secret handling, transaction boundaries and audit preservation.

## Frozen interactive execution boundary

The narrow launcher is `scripts/api_staging_operator_lifecycle_ssh.py`, invoked
as a module with the sole positional action `provision` or `decommission`.
It accepts no identifier/password arguments, environment inputs or files.
It requires real stdin/stdout terminals before any provider call. The maintainer
enters secrets directly into hidden prompts in the real interactive terminal;
the agent never receives, forwards or stores them.

Before provisioning, run the reviewed read-only inspector with its complete
identity/preflight/receipt/exact-instance sequence and require specifically
`FAIL_LIMITED_OPERATOR_MISSING` with verified target (therefore managed PASS).
Decommission requires the inspector's exact `PASS` after approved domain reset.
Then freshly verify Railway identity, public tuple, receipt and current exact
instance again; reject any tuple change. Verify Railway identity immediately
before the interactive SSH operation. Its bootstrap again verifies exact
build/runtime identity and role prerequisites before calling the command.

Transmit only reviewed public source code and the public expected target tuple
as command data, leaving stdin/stdout inherited from the real terminal for SSH's
PTY. Do not pipe secrets or create a custom secret relay. The isolated remote
Python bootstrap loads reviewed code in memory with the established `/app`
import root; it neither deploys nor writes source files. Capture startup output
privately and reject it; sanitize exceptions to fixed failure messages. Command
output and hidden prompts contain no private values. No retry path exists.

The launcher may capture Railway stderr solely to accept the existing reviewed
key-notice contract and discard its payload. Unknown stderr, timeout,
interruption or nonzero execution fails closed as an uncertain lifecycle
operation, never an automatic retry. A zero transport exit is only
`TRANSPORT_EXITED_ZERO_UNVERIFIED`: the remote fixed completion marker must be
observed separately and independent fresh role inspection is required before
any matrix action. Railway's [version-pinned relay implementation](https://github.com/railwayapp/cli/blob/v5.57.2/src/commands/ssh/native.rs#L404-L408)
documents that zero exit alone need not prove command execution. Retain only
action, fixed phase/result, public target tuple and
UTC window. No terminal transcript or secret input is retained.

Tests use controlled provider/subprocess seams without network, check order
and failure-stop behavior, verify exact-instance command selection and source
integrity, execute the remote bootstrap locally with isolated disposable fakes
for target/role failure, and prove stdin/stdout inheritance instead of secret
capture. These tests do not establish live target or role state. The lifecycle
command's real-PTY tests separately prove non-echoing input/fail-closed fallback.

## Phase ledger

- Completed: repository contract/model inspection; role/lifecycle design;
  environment readiness; independent tests and implementation; 53 focused
  lifecycle tests; independent command review with findings resolved.
- Current: fresh live target/role guards before the first provisioning operation.
  Local full gate passed 2,504 tests; final independent execution review passed.
- Pending: guarded provisioning,
  independent role verification, bounded matrix/reset/decommission, final
  evidence review and focused PR. #208 remains open throughout this task.

The command review resolved a locked-group-name race and a disappearing-group
error path, strengthened decommission drift/rollback coverage, and verified
real-PTY no-echo and echo-disable-failure tests. The final command review found
no material issue. A wider focused operator/audit run passed 198 tests before
the final disappearing-group guard; the final command-only run passed 53 tests
after it. Subsequent matrix/launcher review resolved the distinction between
a deployed control hash match and external review/test evidence. No live
provisioning result is implied.

## Matrix feasibility review before provisioning

Repository inspection identified a case-9 evidence boundary. The
frozen #204 baseline contains no Catches or catch credentials. The approved
single owner session start creates a session, not a credential. Profile/fursuit
disable terminates sessions and revokes existing credentials without creating
a Catch or credential or deactivating the activation itself. Thus the approved
sequence supplies no Catch-change target, credential raw-edit/replacement target,
or inactive activation for a reactivation attempt.

The current matrix explicitly requires `NOT_EXERCISED` when a required surface
has no safe owned fixture or known no-op request, and forbids a case-9 `PASS`
from partial checks. Deployed-code/control review and deterministic regressions
can support those boundaries but cannot silently replace the stipulated live
subchecks. Safe Catch/credential add controls and Catch bulk denial can still
be checked without those objects. No broader fixture creation is authorized.

The maintainer approved the focused Catch/credential evidence-mode amendment
now recorded in the canonical plan: preserve those object-level live
`NOT_EXERCISED` subresults and empirical limitation, support them separately by
deployed-control review and deterministic tests, and keep safe surface checks
live. This exception does not authorize additional fixtures or apply to other
missing proof. Existing owned activations still permit inspection of their
actual admin controls; no inactive activation may be created merely for a
reactivation attempt. This finding is about plan feasibility, not an observed
product defect or a new live Staging result.
Historical role/fixture evidence remains unchanged. No provisioning, matrix
case, reset or other Staging mutation occurred during this repository review.

The exact-role inspector extension passed 44 focused tests and independent
review. It compares the two canonical `profiles.playerprofile` permission rows
by primary key; extra or replacement wrong-model permission rows are refusals.
The interactive lifecycle launcher passed 41 focused tests and independent
review, including real Django command execution options and rejection of
unexpected startup output. Neither result establishes live operator state.

Final decommission evidence requires a fresh read-only exact inactive-role
check and comparison of the retained matrix audit tuples. The ordinary
inspector's active-role state mismatch is insufficient. The matrix process
keeps its private comparison state in memory across the external decommission
step, with database connections closed, then verifies the exact inactive shape,
managed role, baseline and unchanged audit fields. No private handoff file is
created. The interactive lifecycle timeout is now bounded at 30 minutes for
direct human input; read-only inspector/provider bounds remain unchanged.
The exact inactive-role helper and timeout change passed 106 focused inspector
and lifecycle tests, plus Ruff and Pyright; independent review found no
material code issue. Its stale documentation finding was corrected.

Independent acceptance review subsequently rejected the assumption that
inspecting the active activation's checked, editable checkbox establishes
reactivation unavailability. The unchanged active submission bypasses the
inactive-to-active guard. At that point the Catch/credential-only amendment did not cover
this missing live proof. Provisioning and matrix execution stopped pending
the explicit decision in the chronological
[feasibility record](staging-operator-validation-243-execution-attempts.md#repository-only-feasibility-stop--2026-09-24-0031-utc).
No Staging mutation occurred.

## Resumed after explicit activation evidence approval

The maintainer approved the same combined-evidence treatment for activation
reactivation, retaining its empirical live result `NOT_EXERCISED` and requiring
separate deployed-control and deterministic denial evidence plus a disclosed
limitation. The earlier feasibility stop is preserved unchanged. The canonical
plan now states this amendment and the narrow direct-evidence rule for any
additional object/state-dependent case-9 boundary found by independent review.
No additional fixture or live mutation is authorized. Resume local executor
tests/implementation and all pending gates before provisioning.

The maintainer confirmed ownership of the exclusive operator window and cleanup
responsibility. The window begins immediately before the first provisioning
mutation and remains held through all matrix, reset, evidence, decommission
and final readiness/state checks. Check approved available deployment/operator
surfaces for known conflicting activity before mutation. Any conflicting writer,
deployment or configuration operation stops the sequence; uncertain cleanup
leaves the window held. The agent verifies execution cleanup; only the
maintainer confirms release. Command exit status alone cannot release it.
