# Hybrid replica provisioning runbook

This runbook provisions the persistent core of the hybrid replica with Terraform. The hybrid replica is an isolated copy of Staging on Cloud Run, Neon, Cloudflare R2 and a separate Clerk application. The work item is [#354](https://github.com/TailTag-Game/tailtag/issues/354). The parent is [#352](https://github.com/TailTag-Game/tailtag/issues/352). The approved contract is [the #353 contract](../specs/2026-10-22-hybrid-replica-contract.md).

[ADR 0010](../adrs/0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) stays in force. This runbook does not approve a hosting move.

## Boundaries

- The replica uses synthetic data and replica-only credentials. Never copy a Railway secret or player data.
- Nothing in this runbook changes Railway Development or Staging, or their R2 buckets.
- Only the owner workstation runs `terraform apply`. CI only checks formatting, validation and offline tests.
- No secret value goes into a Terraform variable, a `.tfvars` file, a plan file or an output that a person reads.
- The owner approves gate G-1 in the contract before the first apply.
- Never destroy a persistent resource without gate G-4 approval. Persistent resources are the project, state bucket, Artifact Registry repository, secrets, Neon project and R2 bucket.

## Layout

| Path | Purpose |
| --- | --- |
| `infra/replica/bootstrap` | Terraform root for the project, APIs, state bucket, `tf-infra` identity and budget. It runs with owner credentials. |
| `infra/replica/foundation` | Terraform root for the service identities, GitHub federation, Artifact Registry, secrets, Cloud Run service, Neon project and R2 bucket. It runs as `tf-infra`. |
| `scripts/replica_neon_roles.py` | Makes the Neon `migrator` and `runtime` roles and writes their connection URLs into Secret Manager |

A Terraform root is one directory with its own state. `task replica-tf-check` runs the offline checks for both roots.

## Placeholders

Replace each placeholder with the value from the owner-private setup record. Never commit real values.

| Placeholder | Meaning |
| --- | --- |
| `<PROJECT_ID>` | Replica GCP project ID. It has a random suffix and differs from the deleted #338 project. |
| `<BILLING_ACCOUNT_ID>` | Billing account that pays for the replica |
| `<OWNER_EMAIL>` | Google account of the owner |
| `<STATE_BUCKET>` | `<PROJECT_ID>-tfstate` |
| `<TF_INFRA_EMAIL>` | `tf-infra@<PROJECT_ID>.iam.gserviceaccount.com` |
| `<CLOUDFLARE_ACCOUNT_ID>` | ID of the separate replica Cloudflare account |
| `<SERVICE_NAME>` | Cloud Run service name. The default is `tailtag-api-replica`. |

Region pair: Cloud Run and the other GCP resources use `us-east4`. Neon uses `aws-us-east-1`.

## Prerequisites

1. Terraform 1.17. Make sure that `terraform version` prints 1.17.
2. The Google Cloud CLI. Sign in with `gcloud auth login`. Then run `gcloud auth application-default login`. Terraform uses the second sign-in.
3. Billing Account Administrator rights for the owner on `<BILLING_ACCOUNT_ID>`.
4. A Neon account on the Launch plan, with a spending notification.
5. A separate Cloudflare account for the replica, with R2 turned on and a usage notification. Never use the Development and Staging Cloudflare account.
6. go-task and uv, as in [Getting started](getting-started.md).
7. Gate G-1 approval from the owner, recorded on #354.

## 1. Bootstrap the project

1. Create `infra/replica/bootstrap/terraform.tfvars`. Git ignores this file.

   ```hcl
   project_id      = "<PROJECT_ID>"
   billing_account = "<BILLING_ACCOUNT_ID>"
   owner_email     = "<OWNER_EMAIL>"
   ```

   If the owner account belongs to a Google Cloud organization, also set `org_id` or `folder_id`. Find the organization with `gcloud organizations list`. Google puts a new project in the organization anyway. Without `org_id`, the next plan tries to move the project out.

2. The state bucket does not exist yet, so the first apply uses local state. Create `infra/replica/bootstrap/backend_override.tf`. Git ignores this file.

   ```hcl
   terraform {
     backend "local" {}
   }
   ```

3. Plan and apply:

   ```sh
   terraform -chdir=infra/replica/bootstrap init
   terraform -chdir=infra/replica/bootstrap plan -out=bootstrap.tfplan
   terraform -chdir=infra/replica/bootstrap apply bootstrap.tfplan
   ```

   Before the apply, read the plan. Make sure that every resource is in `<PROJECT_ID>` or is the replica budget.

4. Make the new project the quota project of your Application Default Credentials. A quota project is the project that pays for API quota. If the credentials name a deleted project, every later step fails.

   ```sh
   gcloud auth application-default set-quota-project <PROJECT_ID>
   ```

5. Move the bootstrap state into the state bucket. Delete `backend_override.tf`. Then run this command and answer `yes`:

   ```sh
   terraform -chdir=infra/replica/bootstrap init -migrate-state -backend-config=bucket=<STATE_BUCKET>
   ```

6. Make sure that `terraform -chdir=infra/replica/bootstrap plan` shows no changes. Then delete the local `terraform.tfstate`, `terraform.tfstate.backup` and `bootstrap.tfplan` files in that directory.

## 2. Apply the foundation

1. Create `infra/replica/foundation/terraform.tfvars`. Git ignores this file.

   ```hcl
   project_id            = "<PROJECT_ID>"
   tf_infra_email        = "<TF_INFRA_EMAIL>"
   cloudflare_account_id = "<CLOUDFLARE_ACCOUNT_ID>"
   ```

2. Create two provider tokens. Make each one right before use.

   - Neon: an API key from the Neon console. Terraform needs it to create the project.
   - Cloudflare: an API token on the replica account only, with the Workers R2 Storage Edit permission.

3. Open a separate terminal for the tokens, because a hidden prompt needs a real terminal. Enter each token without echo:

   ```sh
   read -rs NEON_API_KEY && export NEON_API_KEY
   read -rs CLOUDFLARE_API_TOKEN && export CLOUDFLARE_API_TOKEN
   ```

4. In the same terminal, initialize, plan and apply as `tf-infra`:

   ```sh
   terraform -chdir=infra/replica/foundation init -backend-config=bucket=<STATE_BUCKET> -backend-config=impersonate_service_account=<TF_INFRA_EMAIL>
   terraform -chdir=infra/replica/foundation plan -out=foundation.tfplan
   terraform -chdir=infra/replica/foundation apply foundation.tfplan
   ```

5. Before the apply, review the plan against AC6:

   - Every Google resource is in `<PROJECT_ID>`.
   - The only Cloudflare resource is the replica R2 bucket in `<CLOUDFLARE_ACCOUNT_ID>`.
   - The only Neon resource is the replica project.
   - No resource names Railway, Development or Staging.

6. Delete `foundation.tfplan` after the apply. A plan file can hold sensitive values.

## 3. Add the secret values

Terraform makes empty secrets. The owner adds each value from the separate terminal. The value goes through standard input and never appears on screen.

1. Django secret key:

   ```sh
   python3 -c 'import secrets, sys; sys.stdout.write(secrets.token_urlsafe(50))' | gcloud secrets versions add django-secret-key --project=<PROJECT_ID> --data-file=-
   ```

2. R2 keys. In the replica Cloudflare account, create an R2 API token with Object Read & Write on the `tailtag-replica-media` bucket only. Cloudflare shows the keys once. Enter each key without echo:

   ```sh
   read -rs VALUE && printf '%s' "$VALUE" | gcloud secrets versions add media-access-key-id --project=<PROJECT_ID> --data-file=- && unset VALUE
   read -rs VALUE && printf '%s' "$VALUE" | gcloud secrets versions add media-secret-access-key --project=<PROJECT_ID> --data-file=- && unset VALUE
   ```

3. Clerk and Sentry values come later. #357 adds `clerk-jwt-key`. #358 adds `sentry-dsn`.

## 4. Make the Neon roles

The script makes two login roles with SQL. Roles from the Neon API or Terraform join `neon_superuser`, so the script does not use them.

- `migrator` can change the schema.
- `runtime` can read and write rows, but it cannot change the schema.

Run it in the terminal that ran the foundation apply:

```sh
task replica-neon-roles -- --project <PROJECT_ID>
```

The script reads the admin connection URL from the foundation Terraform output. It writes `migrator-database-url` and `runtime-database-url` into Secret Manager. The script verifies the Neon server certificate on its own connections. A second run changes nothing. To make new passwords, add `--rotate`.

Each stored URL asks for TLS with server identity checks. The API does not apply the TLS settings in `DATABASE_URL` yet. #357 owns that fix.

## 5. Connect the runtime secrets

The Cloud Run service starts from the Google placeholder image without secrets. A revision that references a secret with no version fails to start.

Set `wire_runtime_secrets = true` in the foundation `terraform.tfvars` only after every runtime secret has a version. Then plan and apply again. The runtime secrets are `django-secret-key`, `runtime-database-url`, `media-access-key-id`, `media-secret-access-key`, `clerk-jwt-key` and `sentry-dsn`.

The Clerk and Sentry values come from #357 and #358. So the wiring apply happens after those issues, not in #354.

## 6. Prove field ownership on Cloud Run

Terraform ignores the image, client, revision and traffic fields of the Cloud Run service. A release owns those fields. To prove this, deploy the placeholder image by digest. Then make sure that Terraform plans no change.

```sh
DIGEST="$(gcloud artifacts docker images describe us-docker.pkg.dev/cloudrun/container/hello --format='value(image_summary.digest)')"
gcloud run deploy <SERVICE_NAME> --project=<PROJECT_ID> --region=us-east4 --image="us-docker.pkg.dev/cloudrun/container/hello@${DIGEST}"
terraform -chdir=infra/replica/foundation plan
```

The expected result is `No changes`. Record the result in the proof document.

## 7. Check identity denials

Policy Troubleshooter reads the IAM policy and answers whether a principal has a permission. It changes nothing. For each row, the expected access state is not granted.

| Principal | Permission | Resource |
| --- | --- | --- |
| `tt-migrator` | `secretmanager.versions.access` | `django-secret-key`, `media-access-key-id`, `media-secret-access-key` |
| `tt-runtime` | `secretmanager.versions.access` | `migrator-database-url` |
| `tt-runtime` | `run.services.create` | the project |
| `tt-deployer` | `secretmanager.versions.access` | each runtime secret |
| `tt-deployer` | `run.services.setIamPolicy` | the service |

Example:

```sh
gcloud policy-intelligence troubleshoot-policy iam //secretmanager.googleapis.com/projects/<PROJECT_ID>/secrets/django-secret-key --principal-email=tt-migrator@<PROJECT_ID>.iam.gserviceaccount.com --permission=secretmanager.versions.access
```

## 8. Run the cleanup exercise

The cleanup exercise proves that Terraform can remove disposable resources and leave persistent resources alone. It uses a Neon child branch and an empty secret.

1. Plan and apply with the exercise on:

   ```sh
   terraform -chdir=infra/replica/foundation plan -var=enable_cleanup_exercise=true -out=exercise.tfplan
   terraform -chdir=infra/replica/foundation apply exercise.tfplan
   ```

   Make sure that the plan adds exactly two resources and changes nothing else.

2. Plan and apply with the exercise off:

   ```sh
   terraform -chdir=infra/replica/foundation plan -out=exercise.tfplan
   terraform -chdir=infra/replica/foundation apply exercise.tfplan
   ```

   Make sure that the plan destroys exactly the same two resources and changes nothing else. Then delete `exercise.tfplan`.

## 9. Record the destroy denial

This step proves that the guards block destruction. It deletes nothing.

1. Run a destroy plan in each root:

   ```sh
   terraform -chdir=infra/replica/bootstrap plan -destroy
   terraform -chdir=infra/replica/foundation plan -destroy
   ```

   Each plan must fail with `Instance cannot be destroyed` for the persistent resources. Never run `terraform destroy`.

2. Read back each guard outside Terraform:

   - State bucket: `gcloud storage buckets describe gs://<STATE_BUCKET>` shows versioning, uniform access and enforced public access prevention.
   - Neon: the default branch shows as protected in the Neon console.
   - Cloud Run: the service shows deletion protection in the Cloud Run console.

## 10. Prove reproducibility

1. Make sure that `terraform plan` shows no changes in both roots. If a plan shows drift, record each item and its cause.
2. Clone the repository into a new directory at the same commit. Git ignores the `terraform.tfvars` files, so copy each one into the clone. Initialize both roots with the same backend settings. Make sure that each plan shows no changes.
3. The cleanup exercise in step 8 is the recreation proof for disposable resources.
4. Record the Terraform version, the provider versions, the SHA-256 hash of each `.terraform.lock.hcl` file and the source SHA.

Never rebuild the persistent core to prove reproducibility.

## State recovery and locking

- The `gcs` backend locks the state during each operation. If a run stops and leaves a lock, make sure that no other run is active. Then use `terraform force-unlock` with the lock ID from the error.
- The state bucket keeps old object versions. To recover a damaged state, list the versions with `gcloud storage ls --all-versions gs://<STATE_BUCKET>/<ROOT>/`. Then copy the last good generation over the current object.
- Only the owner and `tf-infra` can read the state bucket. The foundation state holds the Neon admin password and connection URL, because the Neon provider stores them. No other secret value is in state.

## What never to do

- Never commit `.tfvars` files, state files, plan files, `backend_override.tf` or `backend.hcl`.
- Never put a token or password in a Terraform variable or on a command line.
- Never print the `neon_admin_connection_uri` output.
- Never run `terraform destroy` on either root.
- Never use the Development and Staging Cloudflare account for the replica.
