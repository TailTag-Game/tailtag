# #243 managed-operator login recovery contract

The later owner-approved [three-operator restart](staging-operator-validation-243-operator-restart.md)
supersedes this document only for the single coordinated replacement of all
three current synthetic replacement-Staging logins. The managed-only recovery
rules below remain historical and do not authorize a separate concurrent
replacement.

Status: repository design for a separately guarded Staging recovery operation.
The last managed-auth diagnosis remains `IDENTITY_MISMATCH`. No matrix case,
reset, or decommission ran in that attempt. The exclusive #243 Staging window
remains held.

## Scope and identity boundary

The maintainer requested a fresh managed-operator login. The existing
`bootstrap_staging_operator` command can rotate a password for the exact
existing login, but cannot replace its identifier while the managed group
exists. Reusing that command with a different identifier is unsafe.

Create one new local managed-operator User and retire the old local login in
**one transaction**. Do not rename or delete the old User: `clerk_user_id` is
also the Clerk-subject lookup key, and historical `OperatorAuditEvent.actor`
references must remain attached to their original User. Preserve the old
identifier and User row solely as a retired identity. Preserve the existing
managed Group and its exact #205 permission set. Do not touch the #243 limited
operator, emergency superuser, #204 identity bindings, player fixtures, or
historical audit rows.

The repository-owned command is `replace_staging_managed_operator`, with the
exact public confirmation `replace Railway Staging managed operator`.

The new identifier is entered only through a hidden, non-echoing real TTY.
Require a new, unused, bounded ASCII `staging_managed_` identifier. Refuse
every collision, including ordinary, limited, retired, and managed Users.
The prefix reserves a local administrative namespace; it is not a Clerk user
ID. The password and confirmation use separate hidden prompts and the existing
Django password policy. No identifier, credential, hash, or private row value
may enter argv, environment variables, files, logs, evidence, or command
output. No provider user is created or modified.

## Acceptance contract

1. The operation is available only for the approved Railway Staging API,
   through the verified exact running deployment instance, after a fresh
   GitHub/Railway identity check, public preflight, approved receipt join,
   exact-instance readback, fixture/registry prerequisites, and read-only
   managed+limited operator inspection. A real TTY, exact public confirmation,
   disabled query/debug logging, and no query wrappers are mandatory.
   The launcher must invoke the existing reviewed #204 three-way private
   configuration/registry/connected-database reconciliation and require its
   complete fixed `PASS` before mutation transport. A subsequent public
   preflight must still match the inspected deployment tuple.
2. Before input, privately pin the sole exact existing managed User. Inside
   the transaction, lock and revalidate that same User and Group, exact group
   membership/permissions, staff/non-superuser status, no direct permissions,
   and unchanged current target. Any drift or ambiguity refuses with zero
   writes. The new identifier must be unused at commit; a uniqueness race
   rolls back, never adopting the colliding account.
   Refuse if the predecessor is linked to a player profile, owned fursuit,
   convention enrollment, Catch, or #204 owner/catcher binding; this recovery
   may not demote an ordinary or reset-bound account.
   After the hidden new identifier is checked as unused and distinct, and
   before collecting the password or writing, emit only a fixed `PREPARED`
   marker. If that marker is not witnessed, a later transport failure cannot
   establish that a newly authenticated operator is a replacement; stop with
   the result uncertain rather than inferring success.
3. The transaction creates one new staff/non-superuser User with a usable
   password; moves the sole existing managed Group membership to it; and
   sets the old User to nonstaff with an unusable password and no managed or
   direct permissions. The Group permission rows do not change. The old User
   retains its identifier, PK, domain references, and audit references.
4. A failed input, target check, role check, database write, or commit leaves
   the previous managed login intact and emits only a fixed sanitized result.
   A transport failure after possible commit is `UNCERTAIN`; never retry the
   mutation until an independent read-only postcondition has resolved it.
5. The remote process retains only in-memory predecessor/new, limited-role,
   and operator-audit comparisons. After commit, it opens a **separate read-only
   transaction**, rechecks the exact target, and proves the new exact managed
   role, old login retirement, unchanged limited role, and unchanged audit
   rows. It emits a fixed `POSTCONDITION_PASS` marker only after those checks.
   If this proof is lost or fails, the mutation outcome remains uncertain and
   the command is never blindly retried. A fresh independent operator
   inspection and new local-authentication check must then pass. Real
   Django-admin HTTP login must succeed before the #243 matrix restarts at
   case 1. A successful password check alone is insufficient.

## Test surface and proof

Use the real TailTag User, Group, Permission, audit, and Django session models
against disposable local PostgreSQL. Fake only interactive terminal input and
the external Railway/SSH transport in launcher tests. Tests must reject
collisions, privilege/group drift, stale pinned predecessor, wrong target,
non-TTY/echo fallback, query logging/wrappers, partial-write failure, and
transport uncertainty. They must prove exact authority transfer, old-session
rejection, preserved audit attribution, unchanged limited role, sanitized
output, and no unrelated data write. Run focused #204/#205/#243 suites,
repository gates, static analysis, and independent security/data review before
any live attempt.

If the operation is used, do it once within the held exclusive #243 window.
Never treat a command's exit status alone as postcondition proof. The
subsequent live read-only reconciliation and admin-login check are separate
gates before any matrix mutation. The previous failed attempts stay historical.

## Bounded execution and evidence

From the reviewed #243 worktree in a real interactive terminal, run:

```sh
services/api/.venv/bin/python -m scripts.api_staging_managed_operator_replace_ssh
```

The launcher requires an exact managed+limited inspector `PASS`, a fresh
complete #204 private-config/registry/connected-database `PASS`, an approved
deployment receipt, and a unique current instance. The remote side rechecks
that target before reading the database or prompting. The maintainer enters
the public confirmation and then the new identifier/password at separate
hidden prompts. `PREPARED` means only that the new identifier was unused at
that point; it does not mean a write occurred. `POSTCONDITION_PASS` means the
committed transfer passed the separate read-only old/new/limited/audit check.
The final completion marker and a zero SSH exit still require fresh
independent verification.

After the attempt, keep the exclusive window held. Run a new fully guarded
read-only operator inspection; require managed and limited `PASS` at the same
approved deployment. Diagnose the **new** managed credentials through the
existing separate hidden-TTY read-only authentication tool and require
`CREDENTIAL_ACCEPTED`. The bounded matrix executor then authenticates the
new managed login through real Django-admin HTTP before any case submission;
require that login to succeed before treating the replacement as ready for
case 1. No old identifier is needed or retained in evidence.

If the replacement transport or postcondition is uncertain, do not run the
replacement again. Preserve only the public target tuple, fixed markers
actually witnessed, fixed failure classification, and known mutation boundary.
Fresh inspector/authentication checks can corroborate the new current role,
but they cannot identify the retired predecessor if `POSTCONDITION_PASS` was
not witnessed. In that case stop with the exclusive window held and report
the remaining uncertainty and cleanup obligation. Never infer rollback from
an SSH exit status.

## Current managed-login access recovery amendment — 2026-09-24

The later replacement attempt witnessed `PREPARED`, `POSTCONDITION_PASS`, and
the remote completion marker; a separate exact-instance inspector returned
managed and limited `PASS`. Its launcher retained `FAIL_TRANSPORT_UNCERTAIN`.
The subsequent read-only credential check returned `IDENTITY_MISMATCH` before
testing the password, and the maintainer cannot recover the exact entered
identifier or password. These remain distinct chronological observations in
the [execution record](staging-operator-validation-243-execution-attempts.md).

The normal managed operator is not the disposable #243 limited operator.
Preserve its current User row, identifier, group/permissions, and audit actor
relationship. Do not delete, rename, replace, or decommission it to solve a
manual credential handoff. The maintainer will generate and retain one final
password in a password manager and enter it only through real hidden TTY
prompts. No credential is printed, accepted through argv/environment/files,
or retained in repository evidence. The exclusive Staging window remains held.

### Acceptance contract

1. A narrow Staging-only command rotates **only the password** of the sole
   exact current managed operator. Before any write, require approved
   GitHub/Railway identity, fresh public and exact-instance target agreement,
   approved deployment receipt, full #204 private-config/registry/database
   reconciliation, managed+limited inspector `PASS`, a real TTY, exact public
   confirmation, and disabled query/debug logging. Never select an ordinary
   player, retired predecessor, limited operator, or superuser as a fallback.
   The repository command is `rotate_staging_managed_password`, launched only
   by `scripts.api_staging_managed_password_rotate_ssh`; its public
   confirmation is `rotate Railway Staging managed operator password`.
2. Pin the sole exact managed User and group before hidden input; inside one
   transaction, lock and revalidate the same User, target, group, permissions,
   limited role, and historical audit snapshot. Validate the new password with
   Django's existing operator policy, and update only that User's password.
   Any drift or write failure rolls back. A separate read-only postcommit
   check must prove the same User/identifier/group/permission/limited/audit
   state and a committed password hash that verifies the newly entered
   password without invoking a setter. Fixed completion markers may report that
   proof; an uncertain SSH result is never retried blindly.
   `PREPARED` means only that the pre-write guards passed before password
   input. `POSTCONDITION_PASS` and
   `TAILTAG_MANAGED_PASSWORD_ROTATION_COMPLETED` report the remote
   postcommit proof and successful command return, respectively.
3. The read-only managed-auth diagnostic privately selects the sole exact
   managed User before its hidden password prompt. After input, recheck the
   target and pin; classify the password without an identifier prompt or
   output, any setter, session creation, or audit write. The diagnostic must
   check only the pinned managed User's hash; a distinct other actor password
   must not pass.
4. The #243 matrix privately selects that same exact managed actor and asks
   only for its password. It must submit the actual stored identifier and
   entered password through the existing CSRF-protected Django-admin HTTP
   login, verify the resulting admin session and actor, and stop before case
   submission on failure. The limited, emergency, and owner credential
   boundaries remain separate and unchanged. No `force_login`, synthetic
   session, authorization bypass, or direct service invocation substitutes
   for the real login.
5. The matrix's nine cases, two successful domain transitions, one denied
   submission, Case 9 combined-evidence limitations, #204 reset interaction,
   limited-operator decommission, and final-state assertions remain the
   previously approved bounded sequence. No new domain fixture or product
   authorization behavior is introduced.

### Test surface and scope guard

Use disposable local PostgreSQL with the real TailTag User, Group,
Permission, session, and audit models. Fake only real-TTY input and the
external Railway/SSH boundary. Tests must prove exact role selection,
pre/post-input drift rejection, atomic password-only writes, unchanged audit
and limited state, old-session invalidation, privacy-safe outputs, no write
from read-only diagnosis, and actual Django-admin HTTP login before the
matrix's first case. Exercise the real source-bundle path against the current
deployed module boundary. Relevant full repository and static gates plus
independent security/code review precede any new live rotation.

This amendment changes #243 **tool input and credential recovery only**. It
does not change application authentication/authorization, #205 permissions,
the #204 reset contract, the limited operator lifecycle, the live case
sequence, or #208 readiness criteria. Stop if a different product behavior,
new secret transport, account deletion, or an unapproved mutation becomes
necessary.
