# #243 bounded matrix executor contract

Status: resumed after explicit activation-reactivation evidence amendment;
implementation, independent review and local verification complete; live
execution pending. No live matrix result is claimed. The earlier local
[feasibility stop](staging-operator-validation-243-execution-attempts.md#repository-only-feasibility-stop--2026-09-24-0031-utc)
remains historical evidence.
This implements only the [approved matrix](staging-operator-validation-243-plan.md)
and its explicit object/state-dependent case-9 evidence amendments. Historical evidence
is unchanged. No live result follows from this document.

## Scope and execution surface

STANDARD COMPACT review unit with SECURITY, DATA INTEGRITY, RELIABILITY and
TEST ADEQUACY assurance. Add only a bounded remote Python entry point
`scripts/api_staging_operator_matrix.py`, its exact-instance interactive launcher
`scripts/api_staging_operator_matrix_ssh.py`, and focused local tests. Reuse the
reviewed preflight/identity/SSH transport and inspector patterns. No product
authorization change, new API, generic test harness or fixture creation path.

Public command: `python -m scripts.api_staging_operator_matrix_ssh` in a real
interactive terminal from the reviewed checkout. No credential arguments or
configuration files. The local launcher verifies approved provider identities,
canonical preflight, approved deployment receipt and exact running instance.
Require a fresh registry/configuration/database reconciliation and a fresh
exact operator/fixture PASS before the matrix. The remote bootstrap verifies
the public tuple against the instance before Django reads or authentication.
Private reset configuration remains inside its existing reviewed comparison
path; the matrix command does not read or alter it.

The operator confirms an exclusive validation window and cleanup responsibility
with an exact non-secret phrase before authentication. Failure or concurrent
activity stops execution. Deployment work and other Staging writers remain
excluded for the entire window. This is procedural coordination, not a new
maintenance flag or infrastructure feature.

## Authentication and transport

Use actual HTTPS requests to `https://staging.tailtag.app` with redirects and
proxies disabled, finite timeouts and bounded response bodies. Never use Django
test Client, `force_login`, RequestFactory, direct service mutations or invented
sessions for live evidence. Keep cookie jars, CSRF values, form bodies, private
fixture bindings and returned pages solely in memory. Do not log raw requests,
responses, URLs with object paths, exceptions or authentication material.

The maintainer supplies the existing synthetic owner's ordinary Clerk token
through its hidden real-TTY prompt. For inspected singleton managed and limited
operators, the matrix derives each existing local identifier from its exact
role state and prompts separately for passwords only. When the dedicated
`staging_emergency_` actor is exactly `READY`, it likewise derives that
identifier and prompts only for its password; an existing non-synthetic
break-glass actor still requires a hidden identifier and password pair. No
echoed fallback or automated secret relay. Confirm each actor privately
against the exact inspected role and the
real HTTP authenticated session. The synthetic owner's authenticated `/api/me/`
must match the preserved ordinary #204 owner. Clerk-backed admin sign-in is not
part of #205: case 1 proves this verified player's Bearer token grants no admin
session/access, with valid CSRF so rejection is not merely a CSRF failure.
Never print or retain secret values, private user/object IDs or provider claims.

Authenticate/check the three admin principals in separate hidden prompt events
before the first matrix submission. Obtain the owner token after those prompts
so their duration does not consume its short validity window. Before sending a
player request, use the existing unchanged offline `ClerkSessionVerifier` and
require its verified subject to match the preserved owner; a valid token for
another user must never reach `/api/me/` and materialize an unrelated identity.
This precheck does not replace the actual HTTP API/admin evidence.

Any authentication/access failure stops immediately without retry or another
identity. If a short-lived player token expires before its approved session
step, stop before that request; do not manufacture provider credentials. The
owner may obtain a fresh ordinary token through the same existing signed-in
browser and enter it at the designated prompt before that step.

## Frozen observations and mutations

Read the registered #204 root bindings privately. Only those exact profiles,
two fursuits, Convention, enrollments, activations and their bounded dependent
state may be inspected. Reject ambiguous/missing/foreign closure state. Use
short PostgreSQL read-only transactions for snapshots and audit assertions;
close connections before waiting for external reset. No ORM writes exist in
the matrix tool. The only domain writes are the approved real HTTP requests.

1. **A / case 1:** verified ordinary player makes the specified sensitive list,
   detail and one CSRF-valid profile mutation attempt. Require admin login
   denial, identical bounded domain state and no operator audit row.
2. **B / cases 2, 4, 7:** authenticate the exact limited operator; submit one
   fursuit disable attempt on the distinct second fursuit. Require 403,
   unchanged state, exactly one denied/unauthorized_actor/set_fursuit_enabled
   audit event matching that actor and target. No retry.
3. **Session prerequisite:** through the verified owner's supported player API,
   start one catch session for the first registered fursuit/Convention. Require
   exactly one active session and no Catch or credential creation. This step
   supplies the meaningful session-disable cascade; no arbitrary history row.
4. **C / cases 3, 6, 8:** authenticate the exact managed non-superuser and disable
   the owner profile through its admin change form. Require its committed
   transition, termination of that session, preserved fixture relationships,
   no unexpected transition and exactly one operator/set_profile_enabled/
   succeeded top-level event. There are no credential rows to revoke; retain
   that subclaim as unexercised rather than inventing one.
5. **D / case 5:** separately authenticate an existing authorized staff
   emergency superuser; disable the second registered fursuit. Require exactly
   one emergency_superuser/set_fursuit_enabled/succeeded event and the expected
   fursuit transition, with no extra success rows.
6. **E / case 9:** use only the finite operator/admin checklist from the plan.
   Inspect actual safe controls/routes on existing owned objects and exercise
   safe object-independent add/bulk/create rejection paths. Required controls
   must be unavailable or constrained as specified; verify bounded state and
   audit invariants after negative requests. Preserve Catch/credential absent-object and inactive-activation reactivation
   live subchecks as NOT_EXERCISED, with separately identified
   exact-deployment control review and deterministic evidence. Never create
   another gameplay object to complete the checklist or call normal owner
   credential/award routes as though they were forbidden admin paths.
7. **F:** keep exact case audit records and bounded state in process memory,
   close database connections, and emit only a fixed reset-ready marker. The
   maintainer/agent invokes the existing separately guarded #204 reset launcher
   once after its independent current target/database/maintenance checks.
   The matrix process remains alive with its private comparison state; resume
   only after a successful sanitized reset receipt. Recheck public/instance
   identity, `validate_baseline`, and byte-for-byte field equality of retained
   case audit records. No private record is written to a handoff file. This is a manual
   acknowledgement boundary: the parent/maintainer must observe the separately
   produced successful sanitized receipt before entering the fixed acknowledgement.
   The matrix does not parse that external receipt; its subsequent state/audit
   checks independently establish the resulting state.

Recheck the canonical public/exact-instance tuple before each mutating request,
before the reset handoff and after reset. Never retry an ambiguous mutation.
Missing/duplicate/privacy-unsafe audit evidence, unexpected state changes,
target drift, unavailable credentials or a required failure stops the sequence.
The tool never compensates with extra writes or silently invokes reset.

After matrix/reset evidence completes, keep the comparison process alive.
If Case 5 used the separately approved dedicated synthetic emergency actor,
the matrix first emits `TAILTAG_MATRIX_EMERGENCY_DECOMMISSION_READY`. While the
limited operator is still active, invoke the separately reviewed emergency
decommission launcher in a separate terminal. Retain its successful sanitized
receipt and exact `DECOMMISSIONED` postcondition. Enter the emergency-specific
fixed acknowledgement only after observing both; the matrix independently
checks the same retained actor's disabled state and unchanged audit rows.
If Case 5 used an existing authorized break-glass actor, the synthetic
emergency decommission handoff is skipped.

The matrix then emits `TAILTAG_MATRIX_DECOMMISSION_READY`. Use the separately
reviewed limited lifecycle command in a separate terminal. Close database
connections while waiting. Retain its separate successful sanitized receipt;
enter the limited-specific fixed acknowledgement only after observing it.
The matrix does not parse either external receipt. Perform a fresh target
readback and read-only exact decommissioned-role check: sole
dedicated group/member, nonstaff/nonsuperuser, unusable password, zero direct
and group permissions, no other groups or gameplay attachments. Reuse the
inspector helper; an ordinary active-role mismatch is not proof of this state.
Compare retained audit tuples again in memory and require the managed role and
fixture baseline still valid. Only then emit
`LIVE_SEQUENCE_COMPLETE_PENDING_CASE9_EVIDENCE`. This confirms the bounded
sequence and cleanup, not complete #243 acceptance. The matrix never
deletes identities, changes permissions or writes audit rows.

## Evidence and tests

Output only fixed step/case/subcheck classifications, allowlisted audit
action/class/outcome/count facts, public environment/SHA/deployment tuple and
UTC windows. Cases begin NOT_EXERCISED and advance only when every required
assertion succeeds. On interruption, retain only established facts and whether
mutation may have begun. No snapshots, identities, raw rows or responses are
printed. Successful sequence completion is unavailable before reset, audit
retention and decommission verification. The executor reports only
`deployed_control_hash_match=PASS` for matching control files. It leaves
`case9_control_review`, `case9_deterministic_evidence` and case 9 itself
`NOT_EXERCISED`: those proofs require the parent to review the actual deployed
controls and cite fresh, directly relevant deterministic results. The final
durable artifact may then reconcile case 9 under the approved combined model,
retaining all four live subchecks and their empirical limitations. Neither
matching hashes nor a completed command alone establishes #243 PASS.

Freeze tests against a public `run(expected_identity)` entry point and bounded
internal HTTP/snapshot seams. Use real Django ORM with disposable PostgreSQL
for fixture/audit/state comparisons. Exercise actual local HTTP/session/CSRF
behavior against a disposable server where feasible; controlled transport
responses may cover stop-on-failure and privacy cases. No network to Staging or
Clerk in tests. Existing deterministic admin/domain tests supply the behavior
under test; the executor tests prove correct sequence, actor separation,
target checks, exact audit/state assertions, no extra requests, no retries,
redaction and failure evidence. Independent review must approve the executor
and complete evidence model before any live matrix or provisioning attempt.

### Direct evidence required for the four combined subchecks

Local control review identifies the following exact controls and tests. The
fresh final prelaunch `make api-check` run passed all 2,504 tests, including these
existing tests. This is local deterministic evidence only. The final artifact
must additionally cite the live deployed-file hash comparison before using
this review for the observed Staging deployment.

| Live subcheck retained as `NOT_EXERCISED` | Control reviewed locally | Existing direct deterministic evidence |
| --- | --- | --- |
| `catch_change` | `CatchAdmin.has_change_permission` returns false for every actor; all object fields are read-only. | `test_catch_admin_permissions_and_bulk_delete_denial` checks unconditional refusal, including superuser and explicit generic change permission; `test_catch_admin_configuration_and_immutability` checks all fields remain read-only. |
| `credential_replacement` | `CatchCredentialAdminForm` exposes only `revoke`; `FursuitCatchCredentialAdmin.save_model` permits only that transition, and add is unavailable. | `test_credential_admin_is_staff_only_safe_history_with_exact_search_and_no_mutation_paths` checks no replacement/rotation control on a real existing credential, including emergency authority. |
| `credential_raw_edit` | Credential identity, activation and history are read-only; token is absent from the form; no broad save path exists. | The same credential test checks token and raw mutable fields are absent on a real object and only terminal revocation changes state. |
| `activation_reactivation` | `FursuitActivationAdmin.save_model` rejects a changed `is_active=True` value; only active-to-inactive transition is delegated. | `test_activation_view_is_read_only_and_reactivation_has_no_alternate_authority_path` verifies an inactive-to-active POST is denied and remains inactive; `test_activation_admin_only_allows_active_to_inactive_and_preserves_timestamps_on_noop` also covers emergency authority. |

The live executor does not run these tests and must not label their outcome
from a file hash. The parent reconciles these distinct evidence sources in the
durable result after the live sequence. No additional gameplay objects or
activation changes are authorized by this table.

## Prelaunch verification

- Focused matrix: 48 tests passed; launcher: 109 tests passed.
- Inspector/lifecycle integration: 106 tests passed; limited lifecycle command:
  53 tests passed, including real-PTY non-echoing and fail-closed input tests.
- Final `make api-check`: 2,504 tests passed; Ruff, strict Pyright, Semgrep
  (9 rules, zero findings), Django checks, migration drift, OpenAPI and
  Gunicorn configuration passed. Separate changed-script Ruff/Pyright and
  Semgrep checks passed (3 scripts, 9 rules, zero findings).
- `./scripts/doctor.sh`, `git diff --check` and local documentation-link checks
  passed. Doctor notes the absent optional Dev Container CLI and uncommitted
  changes at check time. Tests retain existing missing-staticfiles and
  controlled test-setting/PTY warnings.
- Independent final review: PASS after correcting the HIGH evidence-labeling
  finding. Hash correlation no longer claims review or deterministic PASS.
  The reviewer confirmed scope, fail-closed behavior, credential handling,
  exact audit/cleanup assertions and the manual receipt handoff.
- No application authorization/domain behavior, migration, fixture, operator,
  or Staging configuration was changed during this local work. Live target
  verification, provisioning, matrix, reset and decommission remain pending.
