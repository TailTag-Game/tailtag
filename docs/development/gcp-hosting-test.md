# GCP hosting test runbook

This runbook sets up a temporary project on Google Cloud Platform (GCP) for the TailTag hosting test. GCP is a cloud host from Google. The test compares GCP with the accepted Railway hosting. It does not approve a move to GCP. The parent research issue is #338. This setup issue is #339.

## Boundaries

- The test uses synthetic data and test credentials only.
- The test does not change Railway Development or Staging.
- The test does not use real player data or production credentials.
- Make sure that every command targets the test project. Make sure that the project ID is correct before each change.

## Placeholders

This runbook uses placeholders for values that stay private. Replace each placeholder with the value from the private setup record. Do not commit real values.

| Placeholder | Meaning |
| --- | --- |
| `<PROJECT_ID>` | Project ID of the test project |
| `<PROJECT_NUMBER>` | Numeric project number |
| `<BILLING_ACCOUNT_ID>` | Billing account that pays for the test |
| `<OPERATOR_EMAIL>` | Google account of the operator |
| `<BUDGET_ID>` | ID of the spend budget |

The region for every resource is `us-central1`.

## Prerequisites

1. A Google account with 2-step verification turned on. This account is the operator.
2. A billing account with a payment method. Make sure that the operator is an admin of this billing account.
3. The Google Cloud CLI (`gcloud`) installed on the operator machine.
4. Sign in with `gcloud auth login`. Then run `gcloud config set account <OPERATOR_EMAIL>`.

## Setup

### 1. Create and link the project

```bash
gcloud projects create <PROJECT_ID> --name="TailTag Hosting Test"
gcloud billing projects link <PROJECT_ID> --billing-account=<BILLING_ACCOUNT_ID>
gcloud config set project <PROJECT_ID>
```

You cannot change a project ID after you create the project. Google does not reuse a deleted project ID. Choose the ID with a random suffix.

### 2. Enable the approved APIs

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com sqladmin.googleapis.com logging.googleapis.com monitoring.googleapis.com secretmanager.googleapis.com iam.googleapis.com billingbudgets.googleapis.com --project=<PROJECT_ID>
```

| API | Purpose in this test |
| --- | --- |
| `run.googleapis.com` | Cloud Run, which runs the API container |
| `artifactregistry.googleapis.com` | Artifact Registry, which stores container images |
| `sqladmin.googleapis.com` | Cloud SQL Admin, which manages the PostgreSQL database |
| `logging.googleapis.com` | Cloud Logging |
| `monitoring.googleapis.com` | Cloud Monitoring |
| `secretmanager.googleapis.com` | Secret Manager, which stores runtime secrets |
| `iam.googleapis.com` | IAM, which creates service accounts |
| `billingbudgets.googleapis.com` | Cloud Billing Budget API, which creates the spend budget |

### 3. Disable unrelated default APIs

GCP enables some APIs when it creates a project. Disable the ones this test does not use. Disable a service before the service it depends on. If a command fails with a dependency error, disable the service that the error names first. CAUTION: Do not use a force flag. It can disable services that other services depend on.

```bash
gcloud services disable cloudapis.googleapis.com --project=<PROJECT_ID>
gcloud services disable apptopology.googleapis.com telemetry.googleapis.com cloudtrace.googleapis.com pubsub.googleapis.com containerregistry.googleapis.com datastore.googleapis.com dataplex.googleapis.com dataform.googleapis.com analyticshub.googleapis.com --project=<PROJECT_ID>
gcloud services disable bigquerystorage.googleapis.com bigqueryconnection.googleapis.com bigquerydatapolicy.googleapis.com bigquerydatatransfer.googleapis.com bigquerymigration.googleapis.com bigqueryreservation.googleapis.com --project=<PROJECT_ID>
gcloud services disable bigquery.googleapis.com --project=<PROJECT_ID>
```

These platform services stay enabled. The approved APIs or gcloud need them:

- `cloudresourcemanager.googleapis.com`, which gcloud uses to read and change project IAM
- `iamcredentials.googleapis.com`
- `servicemanagement.googleapis.com`
- `serviceusage.googleapis.com`
- `sql-component.googleapis.com`
- `storage-api.googleapis.com`
- `storage-component.googleapis.com`
- `storage.googleapis.com`

### 4. Create the spend budget

```bash
gcloud billing budgets create --billing-account=<BILLING_ACCOUNT_ID> --display-name="TailTag hosting test cap" --budget-amount=50USD --filter-projects=projects/<PROJECT_NUMBER> --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```

The budget sends email to billing admins at $25, $45, and $50. A budget only sends alerts. It does not stop spending.

Make sure that the budget exists with this command:

```bash
gcloud billing budgets list --billing-account=<BILLING_ACCOUNT_ID>
```

The list must show a budget of 50 USD with thresholds 0.5, 0.9, and 1.0. Google does not guarantee that a real alert fires during the test. If no alert fires, record that result as NOT EXERCISED, with the reason.

### 5. Review the project access

```bash
gcloud projects get-iam-policy <PROJECT_ID>
```

Make sure that the operator holds `roles/owner` on the project only. Make sure that the default service account of Compute Engine does not hold `roles/editor`. If it does, remove that role:

```bash
gcloud projects remove-iam-policy-binding <PROJECT_ID> --member=serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com --role=roles/editor
```

Do not run workloads as the default service account of Compute Engine. That account is outside the least-privilege design.

### 6. Create the workload service accounts

A service account is an identity that a workload uses. Create two accounts.

```bash
gcloud iam service-accounts create tt-deployer --display-name="TailTag deployer"
gcloud iam service-accounts create tt-runtime --display-name="TailTag runtime"
```

Bind the deployer roles:

```bash
gcloud projects add-iam-policy-binding <PROJECT_ID> --member=serviceAccount:tt-deployer@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/run.developer
gcloud iam service-accounts add-iam-policy-binding tt-runtime@<PROJECT_ID>.iam.gserviceaccount.com --member=serviceAccount:tt-deployer@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser
```

Bind the runtime roles:

```bash
gcloud projects add-iam-policy-binding <PROJECT_ID> --member=serviceAccount:tt-runtime@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/cloudsql.client
gcloud projects add-iam-policy-binding <PROJECT_ID> --member=serviceAccount:tt-runtime@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/logging.logWriter
gcloud projects add-iam-policy-binding <PROJECT_ID> --member=serviceAccount:tt-runtime@<PROJECT_ID>.iam.gserviceaccount.com --role=roles/monitoring.metricWriter
```

Give the deployer `roles/artifactregistry.writer` on the repository after the repository exists. Give the runtime account `roles/secretmanager.secretAccessor` on each named secret after the secret exists. Do not give the runtime account a project-wide secret role.

Before each binding, make sure that the role ID exists with `gcloud iam roles describe <ROLE_ID>`.

### 7. Record the setup

Write the real values in the private setup record. The record holds the project ID, project number, billing account ID, budget ID, operator email, and resource names. This runbook must not hold those values.

## Cloud SQL Auth Proxy sidecar

The API reaches Cloud SQL through the Cloud SQL Auth Proxy. The proxy runs as a second container, a sidecar, in the Cloud Run service. #348 tested this setup.

The proxy container uses these arguments:

```text
--port=5432
--auto-iam-authn
--health-check
--http-address=0.0.0.0
--http-port=9090
--run-connection-test
<PROJECT_ID>:us-central1:<INSTANCE_NAME>
```

- The database listener stays on `127.0.0.1:5432`. Do not bind it to another address. With IAM login, any client that reaches the listener connects without a password.
- The health server listens on `0.0.0.0:9090`. Cloud Run probes cannot reach a server that listens only on `localhost`. Cloud Run sends outside requests only to the API container port.
- The connection test makes the proxy exit if it cannot reach the instance. A wrong instance name then stops the revision before it takes traffic.

Give the proxy container a startup probe:

```yaml
startupProbe:
  httpGet:
    path: /startup
    port: 9090
  periodSeconds: 2
  failureThreshold: 15
  timeoutSeconds: 1
```

Name the containers `api` and `cloud-sql-proxy`. Make the API container start after the proxy. Add this annotation to the revision template:

```yaml
run.googleapis.com/container-dependencies: '{"api":["cloud-sql-proxy"]}'
```

A revision deployed with no traffic does not start an instance. Cloud Run marks it ready without running the startup probe. To test a new revision, send it traffic or a tag. If a test revision fails, delete it. A failed revision can keep starting new instances until it is deleted. Cloud Run does not delete the latest created revision. In that case, deploy a good revision first, and then delete the failed one.

## Spend review

The operator reviews spend at least once each week during the test:

1. Open the Billing reports page for the billing account in the Google Cloud console.
2. Filter the report to the test project.
3. Compare the month total with the $50 budget.

If the month total reaches $45, the operator stops new test work and tells the owner before continuing. Billing data can lag behind real usage, so use the budget alerts as a second signal.

## Cleanup

Remove resources in this order. Each step targets only the test project. If a resource was never created, skip its step.

1. Delete the Cloud Run services and jobs. The tests created a migration job and two check jobs:

   ```bash
   gcloud run services delete <SERVICE_NAME> --region=us-central1 --project=<PROJECT_ID>
   gcloud run jobs delete <JOB_NAME> --region=us-central1 --project=<PROJECT_ID>
   ```

2. If the Cloud SQL instance has deletion protection, remove that protection first. Then delete the instance. This also deletes its automated backups:

   ```bash
   gcloud sql instances delete <INSTANCE_NAME> --project=<PROJECT_ID>
   ```

3. Deactivate and delete the media HMAC key. Then delete the media bucket and its objects:

   ```bash
   gcloud storage hmac update <HMAC_ACCESS_ID> --deactivate --project=<PROJECT_ID>
   gcloud storage hmac delete <HMAC_ACCESS_ID> --project=<PROJECT_ID>
   gcloud storage rm --recursive gs://<BUCKET_NAME>
   ```

4. Delete the Artifact Registry repository:

   ```bash
   gcloud artifacts repositories delete <REPOSITORY_NAME> --location=us-central1 --project=<PROJECT_ID>
   ```

5. Delete each Secret Manager secret:

   ```bash
   gcloud secrets delete <SECRET_NAME> --project=<PROJECT_ID>
   ```

6. Delete the service accounts:

   ```bash
   gcloud iam service-accounts delete tt-runtime@<PROJECT_ID>.iam.gserviceaccount.com --project=<PROJECT_ID>
   gcloud iam service-accounts delete tt-deployer@<PROJECT_ID>.iam.gserviceaccount.com --project=<PROJECT_ID>
   gcloud iam service-accounts delete tt-migrate@<PROJECT_ID>.iam.gserviceaccount.com --project=<PROJECT_ID>
   ```

7. Delete the budget:

   ```bash
   gcloud billing budgets delete <BUDGET_ID> --billing-account=<BILLING_ACCOUNT_ID>
   ```

8. Unlink the billing account from the project to stop new charges:

   ```bash
   gcloud billing projects unlink <PROJECT_ID>
   ```

9. After the owner approves, delete the project:

   ```bash
   gcloud projects delete <PROJECT_ID>
   ```

   Google keeps a deleted project for 30 days, and an owner can restore it in that time. Google does not reuse a deleted project ID.

Then make sure that the project state is `DELETE_REQUESTED`:

```bash
gcloud projects describe <PROJECT_ID> --format="value(lifecycleState)"
```

Record the cleanup result in the private setup record.

## Evidence

Each test result is PASS, FAIL, or NOT EXERCISED. A NOT EXERCISED result must give the reason. The issue receives a status summary. The summary must not contain project IDs, billing account IDs, emails, or resource names.
