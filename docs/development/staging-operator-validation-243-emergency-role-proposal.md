# #243 replacement Staging emergency actor proposal

Status: **proposed; not authorized for live provisioning or decommission**. The frozen
[#243 matrix](staging-operator-validation-243-plan.md) requires an existing
authorized break-glass superuser for Case 5 and directs the operator to stop if
that actor is unavailable. The replacement environment has not yet been
inspected for this role. No result from the retired Staging generation proves a
replacement role exists.

## Decision boundary

First inspect the fresh replacement target through a reviewed, read-only path.
If one existing authorized break-glass actor satisfies the frozen plan, use that
actor and do not create another. If no suitable actor exists, stop the matrix.
The alternative below requires separate approval before any live mutation.

## Proposed synthetic actor if the role is absent

- Create at most one dedicated replacement-Staging `staging_emergency_...` User.
  It is staff and superuser, has a usable local password, no group or direct
  permission grants, and no gameplay attachments. It must not adopt or change
  an ordinary player, the managed operator, or the limited operator.
- Use only the exact-instance guarded interactive launcher, after the current
  public tuple, approved deployment receipt, Railway instance, private #204
  configuration, persisted reset registry, and actual connected PostgreSQL
  binding agree. The managed and limited roles must independently pass their
  exact read-only checks. Use the separate replacement private configuration
  at `~/.config/tailtag/staging-reset-replacement.env`, never the retired file.
  Require a real hidden TTY for all credentials.
- The bootstrap write must independently require the pinned Railway staging/API
  runtime and the same connected database name/cluster as the persisted #204
  singleton, within the creation transaction. Uncertain transport or commit
  status stops the run; establish the postcondition read-only before any next
  mutation. Never blindly retry or create a second superuser.
- Exercise the actor only for the one approved Case 5 fursuit action. Require
  `actor_class=emergency_superuser` and exactly one successful top-level audit
  intent. No extra action is authorized by provisioning the role.
- After Case 5, #204 reset, and audit-retention checks, preserve the User row
  referenced by durable `OperatorAuditEvent` records. A separately reviewed
  exact-instance guarded decommission action must remove staff and superuser authority and
  make the local password unusable, without deleting or rewriting audit rows.
  The repository-only decommission command and launcher have been implemented
  with local tests; their live use remains pending this amendment and final
  independent review. Require the read-only `DECOMMISSIONED` classification
  on the exact running instance, not merely a successful SSH exit status.
  Verify the retained actor classification, disabled access, managed/limited
  role state, and final fixture/readiness state before releasing the exclusive
  window. Do not provision until this decommission path is approved, tested,
  and reviewed against the complete #243 procedure.

If the fresh read-only result is ambiguous, another superuser exists, target
binding fails, or decommission cannot be proven safe, stop. This proposal does
not change the two successful-transition limit, Case 9 evidence model, or any
product authorization rule.
