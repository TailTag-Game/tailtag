resource "google_service_account" "deployer" {
  account_id   = "tt-deployer"
  display_name = "GitHub deployer"
}

resource "google_service_account" "migrator" {
  account_id   = "tt-migrator"
  display_name = "Migration job"
}

resource "google_service_account" "maintainer" {
  account_id   = "tt-maintainer"
  display_name = "Reset job"
}

resource "google_service_account" "runtime" {
  account_id   = "tt-runtime"
  display_name = "API runtime"
}

# Only the replica release workflow on main, in the approved `replica`
# environment, can impersonate the deployer (#356 AC15).
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"
  attribute_condition = join(" && ", [
    "assertion.repository == 'TailTag-Game/tailtag'",
    "assertion.ref == 'refs/heads/main'",
    "assertion.environment == 'replica'",
    "assertion.job_workflow_ref == 'TailTag-Game/tailtag/.github/workflows/replica-release.yml@refs/heads/main'",
  ])

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/subject/repo:TailTag-Game/tailtag:environment:replica"
}

resource "google_service_account_iam_member" "deployer_act_as_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# The release updates the migrate job image and runs it (#356 AC13). The
# deployer gets no right on any other job and cannot act as the maintainer.
resource "google_service_account_iam_member" "deployer_act_as_migrator" {
  service_account_id = google_service_account.migrator.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
