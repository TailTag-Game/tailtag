# Hybrid replica provisioning proof (#354)

Status: offline phase complete, live phase waiting for gate G-1

Related issues: [#354](https://github.com/TailTag-Game/tailtag/issues/354) (this proof), parent [#352](https://github.com/TailTag-Game/tailtag/issues/352), contract [#353](2026-10-22-hybrid-replica-contract.md)

Runbook: [Hybrid replica provisioning](../development/hybrid-replica-provisioning.md)

This document records the evidence for each #354 acceptance criterion. Each result is PASS, FAIL or NOT_EXERCISED. NOT_EXERCISED means that the check did not run, and the reason column says why. Offline evidence proves the configuration only. It does not prove live behavior.

## Identities

| Item | Value |
| --- | --- |
| Source SHA | Recorded at the first apply |
| Terraform | 1.17.0 |
| Providers | `hashicorp/google` 8.8.0, `cloudflare/cloudflare` 5.28.1, `kislerdm/neon` 0.18.0 |
| Lock file hashes | Recorded at the first apply |
| UTC window | Recorded at the first apply |
| Resource aliases | Project `replica-project`, Cloud Run service `tailtag-api-replica`, Neon project `tailtag-replica`, R2 bucket `tailtag-replica-media` |

This document never records project IDs, billing account IDs, emails, connection strings or tokens.

## Results

| AC | Result | Evidence or reason |
| --- | --- | --- |
| AC1 | NOT_EXERCISED | Gate G-1 approval is pending. |
| AC2 | NOT_EXERCISED | Exact pins and lock files exist (offline). The Neon capability check needs a live Neon account. |
| AC3 | NOT_EXERCISED | Remote state, locking and recovery are configured and documented. Access checks need the live bucket. |
| AC4 | NOT_EXERCISED | Needs the live foundation. |
| AC5 | NOT_EXERCISED | Offline tests prove the grant mapping. The live denials in runbook step 7 are pending. |
| AC6 | NOT_EXERCISED | Needs the reviewed live plan. |
| AC7 | NOT_EXERCISED | Needs the first apply. |
| AC8 | NOT_EXERCISED | Guards are configured. The destroy-denial record and the cleanup exercise are pending. |
| AC9 | NOT_EXERCISED | Fresh creation is planned. See the reason below. |
| AC10 | NOT_EXERCISED | Bootstrap root exists. Offline tests prove the `tf-infra` role set. |
| AC11 | NOT_EXERCISED | Local PostgreSQL tests prove the role privileges. The Neon run is pending. |
| AC12 | NOT_EXERCISED | No secret version resource exists in the configuration. The live secret entry is pending. |
| AC13 | NOT_EXERCISED | The owner reports that the separate Cloudflare account exists (2026-10-22). The readback and the token scope check are pending. |
| AC14 | NOT_EXERCISED | Field ownership is configured. Runbook step 6 is pending. |
| AC15 | NOT_EXERCISED | The budget is configured. The owner reports that the Neon and Cloudflare notifications are on (2026-10-22). The readbacks are pending. |
| AC16 | NOT_EXERCISED | Guards and the cleanup toggle are configured. Runbook steps 8 and 9 are pending. |
| AC17 | NOT_EXERCISED | Offline tests prove the federation condition and grants. Live denials are pending. |
| AC18 | NOT_EXERCISED | Only empty secret containers exist for Clerk and Sentry. |
| AC19 | NOT_EXERCISED | Needs the first apply. |
| AC20 | NOT_EXERCISED | Tooling exists. The CI job result is recorded on the pull request. |
| AC21 | NOT_EXERCISED | The pin exists. The capability check and the follow-up issue are pending. |

## Approved deviations

The owner approved these differences from the AC11 text before implementation.

- `migrator` gets `USAGE` and `CREATE` on schema `public` instead of owning it. PostgreSQL 16 and later make an ownership transfer depend on role membership. The outcome is the same: `migrator` can change the schema and `runtime` cannot.
- No `neon_role` resource exists. The Neon admin role is the default role of the `neon_project` resource.
- `ALTER DEFAULT PRIVILEGES` runs while the script is connected as `migrator`, so it needs no role membership.
- The role script is `scripts/replica_neon_roles.py`, next to the other operator scripts, not in `infra/replica/`.

## Residual risks and follow-ups

- The `tf-infra` custom role cannot read or add secret values. It can still change secret IAM, and it can manage service accounts and Cloud Run. So it guards against accidental value access, not against a deliberate one. Only the owner can act as `tf-infra`.
- The GitHub federation condition names the repository, not its numeric ID. A renamed or deleted repository name can be registered again. #356 can pin `repository_id` when it first uses the federation.
- Neon accepts only plain passwords in `CREATE ROLE`, because it syncs roles to its control plane. The role script sends each password over verified TLS. A statement statistics view can keep the statement text. Only `tailtag_admin` can read the statements of other roles, and it can already reset any password.
- The API ignores the TLS settings in `DATABASE_URL`. #357 owns the fix, because it proves every connection.
- The `wire_runtime_secrets` apply waits for the Clerk value from #357 and the Sentry value from #358.
- The `kislerdm/neon` provider is archived. A follow-up issue moves the configuration to `neondatabase/neon` after Neon publishes it (AC21).

## AC9: no imported resources

Section 9 of the #353 contract records that the #338 project and its Clerk application were deleted on 2026-10-22. No earlier proof resource exists to import. #354 creates every resource fresh, and the new project ID differs from the deleted one.

## AC12: sensitive state inventory

| Value | Where | Why it is unavoidable | Control |
| --- | --- | --- | --- |
| Neon admin password | Foundation state | The `kislerdm/neon` provider stores the default role password | Only the owner and `tf-infra` can read the state bucket |
| Neon admin connection URL | Foundation state and the sensitive `neon_admin_connection_uri` output | Same as above. The role script reads the output. | Never printed. The role script captures it in memory only. |

No other secret value enters Terraform. The owner adds every secret version outside Terraform.

## AC14: Cloud Run field owners

| Field | Owner |
| --- | --- |
| Container image | Release (#356) |
| `client`, `client_version` | Release (#356) |
| Revision name | Release (#356) |
| Traffic split | Release (#356) |
| Minimum and maximum instances | Terraform capacity profile (#354, #360 adds profiles) |
| Service account, ingress, environment, secret references | Terraform (#354) |
| Deletion protection | Terraform (#354) |
| Public invocation (`invoker_iam_disabled`) | Terraform (#354). Clerk tokens guard the API, as on Staging. The deployer cannot change service IAM. |

## AC15: billing signals

| Provider | Signal | Notes |
| --- | --- | --- |
| GCP | Budget of $25 a month on the replica project. Alerts at 50%, 90% and 100% of actual spend, and 100% of forecast spend. | Credits are excluded, so the alert counts real spend. The budget sends alerts only. It does not stop spending. Billing data can lag by about one day. |
| Neon | Spending notification on the Launch plan | Alert only |
| Cloudflare | Usage notification on the replica account | Alert only |

The owner set no spending ceiling (#352).
