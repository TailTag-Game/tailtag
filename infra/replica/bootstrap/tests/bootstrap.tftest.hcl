# Offline contract test for the replica bootstrap root (#354).
# The provider is mocked and the run applies against the mock, so no cloud
# credential or network call is needed.

mock_provider "google" {}

mock_provider "google" {
  alias = "billing"
}

variables {
  project_id      = "fake-replica-project"
  billing_account = "000000-000000-000000"
  owner_email     = "owner@example.test"
}

# AC5 and AC10: tf-infra holds no role that reads or adds secret values, and
# only the owner can impersonate it.
run "tf_infra_is_least_privilege" {
  command = apply

  assert {
    condition = toset([
      for v in google_project_iam_member.tf_infra : v.role if startswith(v.role, "roles/")
      ]) == toset([
      "roles/iam.serviceAccountAdmin",
      "roles/iam.serviceAccountUser",
      "roles/iam.workloadIdentityPoolAdmin",
      "roles/artifactregistry.admin",
      "roles/run.admin",
      "roles/serviceusage.serviceUsageConsumer",
    ])
    error_message = "tf-infra must hold exactly the six predefined roles."
  }

  assert {
    condition = length(google_project_iam_member.tf_infra) == 8 && toset([
      for v in google_project_iam_member.tf_infra : v.role if !startswith(v.role, "roles/")
      ]) == toset([
      google_project_iam_custom_role.secret_manager_admin_no_access.id,
      google_project_iam_custom_role.log_view_admin_no_access.id,
    ])
    error_message = "tf-infra must hold exactly two more roles, the custom secret-manager and log view roles."
  }

  # #359: the log view role manages views and their IAM, but cannot read logs.
  assert {
    condition = toset(google_project_iam_custom_role.log_view_admin_no_access.permissions) == toset([
      "logging.views.create",
      "logging.views.delete",
      "logging.views.get",
      "logging.views.list",
      "logging.views.update",
      "logging.views.getIamPolicy",
      "logging.views.setIamPolicy",
    ])
    error_message = "The log view role must hold exactly the view and view IAM permissions, and no log access."
  }

  assert {
    condition = (
      contains(google_project_iam_custom_role.secret_manager_admin_no_access.permissions, "secretmanager.secrets.create")
      && !contains(google_project_iam_custom_role.secret_manager_admin_no_access.permissions, "secretmanager.versions.access")
      && !contains(google_project_iam_custom_role.secret_manager_admin_no_access.permissions, "secretmanager.versions.add")
    )
    error_message = "The custom role must manage secrets but never read or add secret versions."
  }

  assert {
    condition = (
      google_service_account_iam_member.owner_token_creator.role == "roles/iam.serviceAccountTokenCreator"
      && google_service_account_iam_member.owner_token_creator.member == "user:${var.owner_email}"
    )
    error_message = "Only the owner may create tokens for tf-infra."
  }
}
