resource "google_service_account" "tf_infra" {
  project      = google_project.replica.project_id
  account_id   = "tf-infra"
  display_name = "Terraform foundation"

  depends_on = [google_project_service.enabled]
}

# Manages secret containers and their IAM without the permissions to read or
# add secret values. This guards against accidental value access through
# Terraform. It is not a hard boundary: setIamPolicy could grant more.
resource "google_project_iam_custom_role" "secret_manager_admin_no_access" {
  project = google_project.replica.project_id
  role_id = "secretManagerAdminNoAccess"
  title   = "Secret Manager admin without value access"
  permissions = [
    "secretmanager.secrets.create",
    "secretmanager.secrets.delete",
    "secretmanager.secrets.get",
    "secretmanager.secrets.list",
    "secretmanager.secrets.update",
    "secretmanager.secrets.getIamPolicy",
    "secretmanager.secrets.setIamPolicy",
    "secretmanager.versions.list",
    "secretmanager.versions.get",
  ]

  depends_on = [google_project_service.enabled]
}

# Manages log views and their IAM for the simulator relay view (#359), without
# logging.views.access, so tf-infra cannot read logs through a view. As above,
# setIamPolicy could grant more. No predefined role fits: logging.configWriter
# lacks views.setIamPolicy and adds sinks, and logging.admin reads logs.
resource "google_project_iam_custom_role" "log_view_admin_no_access" {
  project = google_project.replica.project_id
  role_id = "logViewAdminNoAccess"
  title   = "Log view admin without log access"
  permissions = [
    "logging.views.create",
    "logging.views.delete",
    "logging.views.get",
    "logging.views.list",
    "logging.views.update",
    "logging.views.getIamPolicy",
    "logging.views.setIamPolicy",
  ]

  depends_on = [google_project_service.enabled]
}

locals {
  tf_infra_roles = {
    service_account_admin = "roles/iam.serviceAccountAdmin"
    service_account_user  = "roles/iam.serviceAccountUser"
    wif_pool_admin        = "roles/iam.workloadIdentityPoolAdmin"
    artifact_admin        = "roles/artifactregistry.admin"
    run_admin             = "roles/run.admin"
    # Lets requests made as tf-infra bill API quota to this project. Callers
    # that set a quota project need it; it grants no resource access.
    service_usage_consumer = "roles/serviceusage.serviceUsageConsumer"
    secret_manager         = google_project_iam_custom_role.secret_manager_admin_no_access.id
    log_views              = google_project_iam_custom_role.log_view_admin_no_access.id
  }
}

resource "google_project_iam_member" "tf_infra" {
  for_each = local.tf_infra_roles

  project = google_project.replica.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.tf_infra.email}"
}

resource "google_storage_bucket_iam_member" "tf_infra_state" {
  bucket = google_storage_bucket.state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.tf_infra.email}"
}

# The owner is the only identity that can impersonate tf-infra.
# The id is built from known parts so the provider id check passes before the account exists.
resource "google_service_account_iam_member" "owner_token_creator" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/tf-infra@${var.project_id}.iam.gserviceaccount.com"
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.owner_email}"

  depends_on = [google_service_account.tf_infra]
}
