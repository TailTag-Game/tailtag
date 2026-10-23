# Hybrid replica provisioning proof (#354)

Status: live phase complete on 2026-10-23. AC21 waits for its follow-up issue.

Related issues: [#354](https://github.com/TailTag-Game/tailtag/issues/354) (this proof), parent [#352](https://github.com/TailTag-Game/tailtag/issues/352), contract [#353](2026-10-22-hybrid-replica-contract.md)

Runbook: [Hybrid replica provisioning](../development/hybrid-replica-provisioning.md)

This document records the evidence for each #354 acceptance criterion. Each result is PASS, FAIL or NOT_EXERCISED. NOT_EXERCISED means that the check did not run, and the reason column says why.

## Identities

| Item | Value |
| --- | --- |
| Source SHA | Bootstrap first applied from `e873706`. The `tf-infra` quota role and the foundation were applied from `522b095`. The role script and every proof ran from `88fd189`. |
| Terraform | 1.17.0 |
| Providers | `hashicorp/google` 8.8.0, `cloudflare/cloudflare` 5.28.1, `kislerdm/neon` 0.18.0 |
| Lock file hashes (SHA-256 prefix) | Bootstrap `3f01edb591b822bc`, foundation `8d5c6a2e276edf77` |
| UTC window | 2026-10-23T15:07Z to 2026-10-23T17:11Z |
| Resource aliases | Project `replica-project`, Cloud Run service `tailtag-api-replica`, Neon project `tailtag-replica`, R2 bucket `tailtag-replica-media` |

This document never records project IDs, billing account IDs, emails, connection strings or tokens.

## Results

| AC | Result | Evidence or reason |
| --- | --- | --- |
| AC1 | PASS | The owner approved gate G-1 on 2026-10-23 before the first apply. The approval is recorded on #354. Credits and billing lag are in the AC15 section. |
| AC2 | PASS | Exact pins and committed lock files. The first Neon apply was the capability check. It found that the API key belonged to a Free organization, which caps history at 6 hours. The owner upgraded the organization to Launch. Launch then accepted PostgreSQL 18, a protected default branch, 1 day of history, 0.25 to 2 CU and a 300 second suspend timeout. Import was not exercised, because no resource needed import (AC9). |
| AC3 | PASS | State is in a versioned bucket with uniform access and enforced public access prevention. Google encrypts it at rest. The `gcs` backend locks it. The runbook gives the recovery steps. Readback: only the owner and `tf-infra` can read the bucket. The Neon admin password is the only secret in state. |
| AC4 | PASS | The project, identities, Artifact Registry, Secret Manager, Cloud Run, Neon project and R2 bucket exist under replica-only names. Cross-environment access is denied: see AC13 and AC17. |
| AC5 | PASS | Live checks in AC11 and AC17 |
| AC6 | PASS | The owner and the agent reviewed each plan before apply. Every resource was in the replica project, the replica Cloudflare account or the replica Neon project. No plan named Railway, Development or Staging. |
| AC7 | PASS | Bootstrap: 26 added, then 1 added for the quota role. Foundation: 27 added over two applies. Each later plan shows no changes. See AC19 for reproducibility. |
| AC8 | PASS | See AC16 |
| AC9 | PASS | Fresh creation. See the reason below. |
| AC10 | PASS | The bootstrap state moved into the bucket. Foundation runs as `tf-infra` through impersonation. `tf-infra` holds no billing account role. The owner is its only token creator. |
| AC11 | PASS | On Neon, `migrator` created a table. `runtime` got SQLSTATE 42501 for `CREATE TABLE`. `runtime` inserted, updated, selected and deleted rows, and it used the sequence. Neither role is a superuser or a member of `neon_superuser`, and neither can create databases or roles or bypass row security. The stored URLs require `verify-full` TLS. The probe table was dropped. |
| AC12 | PASS | Terraform made empty secrets. The owner added the Django key and both R2 keys through standard input, one version each. The role script added both database URLs. `clerk-jwt-key` and `sentry-dsn` have no version. |
| AC13 | PASS | The Terraform Cloudflare token sees exactly one account, the replica account. The runtime R2 token is an Object Read & Write token on the replica bucket only. |
| AC14 | PASS | `gcloud run deploy` redeployed the placeholder by digest as a new revision. The next Terraform plan showed no changes. The field owner table is below. |
| AC15 | PASS | Budget readback: $25 USD, credits excluded, one project, alerts at 50%, 90% and 100% of actual spend and 100% of forecast. The owner reports that the Neon and Cloudflare spending notifications are on. |
| AC16 | PASS | Destroy plans were refused. Bootstrap: `Instance cannot be destroyed` for the state bucket. Foundation: 10 refusals for the 7 secrets, the Artifact Registry repository, the Neon project and the R2 bucket. Nothing was destroyed. Cleanup exercise: one plan added only the disposable Neon branch and secret. The next plan destroyed only those two. The final plan shows no changes. |
| AC17 | PASS | Policy Troubleshooter found that no allow policy grants these permissions: `tt-migrator` reading the Django key or either media key, `tt-runtime` reading the migrator URL or creating Cloud Run services, `tt-deployer` reading any secret or setting service or project IAM. The expected grants show as granted. The overall result reads unknown only because the owner cannot read organization deny policies. |
| AC18 | PASS | `clerk-jwt-key` and `sentry-dsn` exist with no versions. Only `tt-runtime` can read them. |
| AC19 | PASS | A fresh clone at `88fd189` with the committed lock files planned no changes for both roots. The cleanup exercise destroyed and made the disposable resources again. |
| AC20 | PASS | Tooling and CI shipped in #363. The CI job passed. |
| AC21 | NOT_EXERCISED | The pin and the capability check passed. The follow-up issue for `neondatabase/neon` is not filed yet. |

## Live findings

- Neon refused a 1 day history on the Free plan. The owner upgraded the organization to Launch, as gate G-1 approved.
- Neon accepts only plain passwords in `CREATE ROLE`. #367 changed the role script.
- The owner's credentials named the deleted #338 project as their quota project. `tf-infra` needed `roles/serviceusage.serviceUsageConsumer` (#366). The owner set the replica project as the quota project.
- Google put the new project in the owner's organization. The organization ID is in the private variables file.
- Policy Troubleshooter needs the project number, not the project ID, in secret resource names.

## Approved deviations

The owner approved these differences from the AC11 text before implementation.

- `migrator` gets `USAGE` and `CREATE` on schema `public` instead of owning it. PostgreSQL 16 and later make an ownership transfer depend on role membership. The outcome is the same: `migrator` can change the schema and `runtime` cannot.
- No `neon_role` resource exists. The Neon admin role is the default role of the `neon_project` resource.
- `ALTER DEFAULT PRIVILEGES` runs while the script is connected as `migrator`, so it needs no role membership.
- The role script is `scripts/replica_neon_roles.py`, next to the other operator scripts, not in `infra/replica/`.

## Residual risks and follow-ups

- The state bucket keeps the default project owner, editor and viewer bindings. Today only the owner holds a basic role. A future project viewer can read the state, which holds the Neon admin password. Removing the viewer bindings is a later hardening step.
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
