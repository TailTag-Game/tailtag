# #243 replacement Staging operator restart

Status: **approved objective, design and execution pending**. The owner asked to
retire the three current synthetic Staging operator logins and create fresh
managed, limited and emergency logins, with generated local usernames and
password-only hidden prompts. This amends only #243's operator prerequisite
lifecycle. Cases 1–9 remain `NOT_EXERCISED`; the exclusive Staging window stays
held. Preserve the earlier `CREDENTIAL_REJECTED` and transport-uncertain
attempts in the chronological [evidence record](staging-operator-validation-243-execution-attempts.md).

## Acceptance contract

1. Operate only on the positively identified replacement Railway Staging API
   and its exact running instance. Before mutation, require approved GitHub and
   Railway identities, canonical public preflight, approved deployment receipt,
   current instance readback, private #204 configuration / registry / connected
   database agreement, intact #204 fixtures, and exact managed, limited and
   dedicated emergency roles. Require that these are the only current staff
   Users; an additional staff or superuser identity is outside this bounded
   restart and stops the run. Any drift or other Staging writer stops the run.
2. The command generates three unused local-only identifiers with exact
   `staging_managed_`, `staging_validation_` and `staging_emergency_` prefixes.
   The existing limited actor may have an older arbitrary local identifier and
   is selected by its exact dedicated group; its old name is not renamed. The
   maintainer enters only three new role-specific passwords and confirmations
   through a real non-echoing TTY. Require an exact public confirmation phrase
   and the existing Django password policy. Require the three passwords to be
   distinct so one disclosed credential cannot authenticate every role. Never
   put a username, password or
   password hash in argv, environment variables, logs, receipts or chat.
   The phrase is `restart Railway Staging validation operators`.
3. In one guarded database transaction, retain all three old User rows and
   their audit relationships, remove their staff/superuser/group authority and
   make their passwords unusable. Create exactly one new actor for each role:
   managed staff/non-superuser with the frozen full managed group; limited
   staff/non-superuser with only the frozen two-permission limited group; and
   dedicated staff/superuser with no group or direct permissions. Do not touch
   ordinary players, #204 owner/catcher identities, domain fixtures, audit
   rows, group permission definitions, Clerk, R2 or Railway configuration.
4. The operation is atomic and fail closed on an unexpected current role,
   identity collision, extra superuser, audit drift, target/database drift,
   password-policy failure or write failure. A timeout or lost SSH completion
   after possible mutation is `UNCERTAIN`; never repeat the write blindly.
   Keep the predecessor identities and bounded audit snapshot only in the
   remote process's memory, never in output or a file. In a separate read-only
   transaction after commit, compare those pinned facts and emit a fixed
   `POSTCONDITION_PASS` marker only if they still match. A fresh exact-instance
   inspection corroborates the new roles. If the marker or its continuity is
   lost, a healthy-looking role inspection alone is insufficient: stop with
   the restart outcome uncertain rather than infer which old actors retired.
   A zero Railway SSH transport exit alone is unverified and must not be a
   successful launcher result. The maintainer must witness both fixed remote
   markers, then complete a fresh exact-instance managed/limited inspection
   and emergency `READY` readback before any matrix case. An absent marker or
   failed readback keeps the restart outcome uncertain with no write retry.
5. The postcommit check proves the new three-role contract, retired old access,
   unchanged audit rows and unchanged #204 baseline at the postcommit read
   within the exclusive Staging writer window. Update
   the emergency inspector and matrix selection narrowly to preserve the
   initial singleton `READY` state and recognize two new lifecycle states:
   `READY` with one active dedicated actor and one exact retired predecessor;
   `DECOMMISSIONED` after the matrix with both dedicated rows retired. Two
   active actors, a third dedicated row, an unrelated
   superuser or an abnormal retired row still fail closed. Existing bootstrap
   must not adopt or reactivate a retired actor. The final decommission launcher
   must accept the exact two-retired-row postcondition without relaxing its
   old audit-retention checks.
6. After fresh independently guarded target/role inspection, test each new
   password through its role's real Django-admin login before any #205 case
   submission. Only then restart the bounded matrix at Case 1. Preserve the
   approved Case 9 combined-evidence boundaries and final #204 reset,
   audit-retention, decommission and readiness checks.

## Test surface and scope

Use real TailTag User, Group, Permission, session and OperatorAuditEvent models
with disposable local PostgreSQL. Fake only hidden terminal input and the
external provider/SSH boundary. Tests must reject unauthorized target or role,
unexpected group/direct permissions, extra superusers, username collisions,
echoed or missing TTY input, partial writes, audit changes and transport
uncertainty. Prove that old sessions lose admin access and that the new limited
   role cannot gain managed or emergency authority. Existing #204/#205 behavior
   and product authorization rules are unchanged.

## Rollout gate

The current deployed image still assumes one dedicated emergency row. Review,
test and merge the replacement command **and every consuming inspector, matrix
and decommission helper** before the restart write. Promote the accepted code
through the existing guarded #202 path within the exclusive operator window,
then freshly prove the canonical public/exact-instance tuple and full #204
binding. Do not run a source-bundled replacement command against an old image
whose later matrix or decommission path cannot interpret the retained actor.
If promotion or target evidence is ambiguous, do not start the restart write.

The generated identifiers are not evidence and need not be remembered by the
maintainer. The matrix and lifecycle tooling must select the sole exact actor
for each role, and prompts must identify the role whose password is requested.
The maintainer should keep three passwords privately labeled **managed**,
**limited** and **emergency**; no value enters this repository.

The intended narrow repository seams are the Django management command
`restart_staging_validation_operators` and its exact-instance launcher
`scripts.api_staging_operator_restart_ssh`. The launcher and command must not
expose a generalized account-management API.
