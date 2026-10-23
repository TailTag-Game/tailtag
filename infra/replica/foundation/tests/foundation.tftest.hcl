# Offline contract tests for the replica foundation root (#354).
# Providers are mocked and every run applies against the mocks, so computed
# values exist and no cloud credential or network call is needed.

mock_provider "google" {}
mock_provider "cloudflare" {}
mock_provider "neon" {}

# The google provider checks the format of service_account_id, so each mocked
# service account needs a real-looking name and a distinct email.
override_resource {
  target = google_service_account.deployer
  values = {
    name  = "projects/fake-replica-project/serviceAccounts/tt-deployer@fake-replica-project.iam.gserviceaccount.com"
    email = "tt-deployer@fake-replica-project.iam.gserviceaccount.com"
  }
}

override_resource {
  target = google_service_account.migrator
  values = {
    name  = "projects/fake-replica-project/serviceAccounts/tt-migrator@fake-replica-project.iam.gserviceaccount.com"
    email = "tt-migrator@fake-replica-project.iam.gserviceaccount.com"
  }
}

override_resource {
  target = google_service_account.runtime
  values = {
    name  = "projects/fake-replica-project/serviceAccounts/tt-runtime@fake-replica-project.iam.gserviceaccount.com"
    email = "tt-runtime@fake-replica-project.iam.gserviceaccount.com"
  }
}

variables {
  project_id            = "fake-replica-project"
  tf_infra_email        = "tf-infra@fake-replica-project.iam.gserviceaccount.com"
  cloudflare_account_id = "00000000000000000000000000000000"
}

# AC17 and the #344 regression: every identity reads only the secrets it needs.
run "secret_access_is_least_privilege" {
  command = apply

  assert {
    condition = toset([
      for k, v in google_secret_manager_secret_iam_member.accessor : split("/", k)[0]
      if v.member == "serviceAccount:${google_service_account.migrator.email}"
    ]) == toset(["migrator-database-url"])
    error_message = "The migrator must read exactly migrator-database-url."
  }

  assert {
    condition = toset([
      for k, v in google_secret_manager_secret_iam_member.accessor : split("/", k)[0]
      if v.member == "serviceAccount:${google_service_account.runtime.email}"
      ]) == toset([
      "django-secret-key",
      "runtime-database-url",
      "media-access-key-id",
      "media-secret-access-key",
      "clerk-jwt-key",
      "sentry-dsn",
    ])
    error_message = "The runtime identity must read exactly the six runtime secrets."
  }

  assert {
    condition = length([
      for v in google_secret_manager_secret_iam_member.accessor : v
      if v.member == "serviceAccount:${google_service_account.deployer.email}"
    ]) == 0
    error_message = "The deployer must not read any secret."
  }

  assert {
    condition = alltrue([
      for v in google_secret_manager_secret_iam_member.accessor :
      v.role == "roles/secretmanager.secretAccessor"
    ])
    error_message = "Every secret grant must use roles/secretmanager.secretAccessor."
  }
}

# AC17: GitHub federation is pinned to this repository and main, and the
# deployer holds only publish, deploy, and act-as-runtime rights.
run "deployer_federation_and_grants" {
  command = apply

  assert {
    condition     = google_iam_workload_identity_pool_provider.github.attribute_condition == "assertion.repository == 'TailTag-Game/tailtag' && assertion.ref == 'refs/heads/main'"
    error_message = "The provider condition must pin the repository and refs/heads/main."
  }

  assert {
    condition = (
      google_service_account_iam_member.deployer_wif.role == "roles/iam.workloadIdentityUser"
      && google_service_account_iam_member.deployer_wif.service_account_id == google_service_account.deployer.name
      && google_service_account_iam_member.deployer_wif.member == "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/TailTag-Game/tailtag"
    )
    error_message = "Only the TailTag-Game/tailtag repository may impersonate the deployer."
  }

  assert {
    condition = (
      google_artifact_registry_repository_iam_member.deployer_writer.role == "roles/artifactregistry.writer"
      && google_artifact_registry_repository_iam_member.deployer_writer.member == "serviceAccount:${google_service_account.deployer.email}"
    )
    error_message = "The deployer must be an Artifact Registry writer, not an admin."
  }

  assert {
    condition = (
      google_cloud_run_v2_service_iam_member.deployer_developer.role == "roles/run.developer"
      && google_cloud_run_v2_service_iam_member.deployer_developer.member == "serviceAccount:${google_service_account.deployer.email}"
    )
    error_message = "The deployer must be a Cloud Run developer, not an admin."
  }

  assert {
    condition = (
      google_service_account_iam_member.deployer_act_as_runtime.role == "roles/iam.serviceAccountUser"
      && google_service_account_iam_member.deployer_act_as_runtime.service_account_id == google_service_account.runtime.name
      && google_service_account_iam_member.deployer_act_as_runtime.member == "serviceAccount:${google_service_account.deployer.email}"
    )
    error_message = "The deployer must be able to act as the runtime identity only."
  }
}

# AC14 bootstrap ordering: the first apply cannot reference secret versions
# that do not exist yet.
run "first_apply_has_no_secret_env" {
  command = apply

  assert {
    condition = length([
      for e in google_cloud_run_v2_service.api.template[0].containers[0].env : e
      if try(length(e.value_source[0].secret_key_ref) > 0, false)
    ]) == 0
    error_message = "With default variables the service must not reference any secret."
  }
}

run "wired_apply_references_runtime_secrets" {
  command = apply

  variables {
    wire_runtime_secrets = true
  }

  assert {
    condition = toset([
      for e in google_cloud_run_v2_service.api.template[0].containers[0].env : e.name
      if try(length(e.value_source[0].secret_key_ref) > 0, false)
      ]) == toset([
      "DJANGO_SECRET_KEY",
      "DATABASE_URL",
      "MEDIA_STORAGE_ACCESS_KEY_ID",
      "MEDIA_STORAGE_SECRET_ACCESS_KEY",
      "CLERK_JWT_KEY",
      "SENTRY_DSN",
    ])
    error_message = "Wiring must add exactly the six runtime secret variables."
  }

  assert {
    condition = length([
      for e in google_cloud_run_v2_service.api.template[0].containers[0].env : e
      if e.name == "DATABASE_URL"
      && try(
        contains([
          google_secret_manager_secret.app["runtime-database-url"].secret_id,
          google_secret_manager_secret.app["runtime-database-url"].id,
          google_secret_manager_secret.app["runtime-database-url"].name,
        ], e.value_source[0].secret_key_ref[0].secret)
        && e.value_source[0].secret_key_ref[0].version == "latest",
        false,
      )
    ]) == 1
    error_message = "DATABASE_URL must reference the latest runtime-database-url secret, never the migrator URL."
  }
}
