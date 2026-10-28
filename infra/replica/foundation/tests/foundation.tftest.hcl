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

override_resource {
  target = google_service_account.maintainer
  values = {
    name  = "projects/fake-replica-project/serviceAccounts/tt-maintainer@fake-replica-project.iam.gserviceaccount.com"
    email = "tt-maintainer@fake-replica-project.iam.gserviceaccount.com"
  }
}

override_resource {
  target = google_service_account.simrelay
  values = {
    name  = "projects/fake-replica-project/serviceAccounts/tt-simrelay@fake-replica-project.iam.gserviceaccount.com"
    email = "tt-simrelay@fake-replica-project.iam.gserviceaccount.com"
  }
}

# The deterministic Cloud Run host uses the project number, which the mock
# provider cannot invent in a recognisable form.
override_data {
  target = data.google_project.this
  values = {
    number = "123456789012"
  }
}

# The toggles are pinned so an owner's local terraform.tfvars, which terraform
# test also loads, cannot change what the default-path runs check.
variables {
  project_id            = "fake-replica-project"
  tf_infra_email        = "tf-infra@fake-replica-project.iam.gserviceaccount.com"
  cloudflare_account_id = "00000000000000000000000000000000"
  wire_runtime_secrets  = false
  wire_sentry_dsn       = false
  simrelay_token_minter = "user:owner@example.test"
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
    condition = toset([
      for k, v in google_secret_manager_secret_iam_member.accessor : split("/", k)[0]
      if v.member == "serviceAccount:${google_service_account.maintainer.email}"
      ]) == toset([
      "maintainer-database-url",
      "django-secret-key",
      "media-access-key-id",
      "media-secret-access-key",
      "clerk-jwt-key",
    ])
    error_message = "The reset identity must read exactly the maintainer URL and the four shared production secrets."
  }

  assert {
    condition = toset([
      for k, v in google_secret_manager_secret_iam_member.accessor : v.member
      if split("/", k)[0] == "sentry-dsn"
    ]) == toset(["serviceAccount:${google_service_account.runtime.email}"])
    error_message = "Only the runtime identity may read sentry-dsn."
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
    condition     = google_iam_workload_identity_pool_provider.github.attribute_condition == "assertion.repository == 'TailTag-Game/tailtag' && assertion.ref == 'refs/heads/main' && assertion.environment == 'replica' && assertion.job_workflow_ref == 'TailTag-Game/tailtag/.github/workflows/replica-release.yml@refs/heads/main'"
    error_message = "The provider condition must pin the repository, refs/heads/main, the replica environment and the release workflow."
  }

  assert {
    condition = (
      google_service_account_iam_member.deployer_wif.role == "roles/iam.workloadIdentityUser"
      && google_service_account_iam_member.deployer_wif.service_account_id == google_service_account.deployer.name
      && google_service_account_iam_member.deployer_wif.member == "principal://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/subject/repo:TailTag-Game@306886193/tailtag@1306048543:environment:replica"
    )
    error_message = "Only jobs in the replica environment of TailTag-Game/tailtag may impersonate the deployer."
  }

  assert {
    condition     = google_artifact_registry_repository.api.docker_config[0].immutable_tags == true
    error_message = "Release tags must be immutable so a source SHA tag names one digest."
  }

  # #356 AC13: the deployer updates and runs the migrate job only, as the migrator.
  assert {
    condition = (
      google_cloud_run_v2_job_iam_member.deployer_migrate.name == google_cloud_run_v2_job.replica["migrate"].name
      && google_cloud_run_v2_job_iam_member.deployer_migrate.role == "roles/run.developer"
      && google_cloud_run_v2_job_iam_member.deployer_migrate.member == "serviceAccount:${google_service_account.deployer.email}"
    )
    error_message = "The deployer must be a Cloud Run developer on the migrate job."
  }

  assert {
    condition = toset([
      for m in [
        google_service_account_iam_member.deployer_act_as_runtime,
        google_service_account_iam_member.deployer_act_as_migrator,
      ] : m.service_account_id if m.member == "serviceAccount:${google_service_account.deployer.email}" && m.role == "roles/iam.serviceAccountUser"
    ]) == toset([google_service_account.runtime.name, google_service_account.migrator.name])
    error_message = "The deployer must act as the runtime and migrator identities only."
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
# that do not exist yet. This holds for the service and for every job shell.
run "first_apply_has_no_secret_env" {
  command = apply

  assert {
    condition = length([
      for e in google_cloud_run_v2_service.api.template[0].containers[0].env : e
      if try(length(e.value_source[0].secret_key_ref) > 0, false)
    ]) == 0
    error_message = "With default variables the service must not reference any secret."
  }

  assert {
    condition = length(flatten([
      for job in google_cloud_run_v2_job.replica : [
        for e in job.template[0].template[0].containers[0].env : e.name
        if try(length(e.value_source[0].secret_key_ref) > 0, false)
      ]
    ])) == 0
    error_message = "With default variables no job may reference any secret."
  }
}

# Sentry is off unless both toggles are true, so a wired apply carries five
# secrets, and wire_sentry_dsn alone wires nothing.
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
    ])
    error_message = "Wiring must add the five runtime secret variables and leave SENTRY_DSN out by default."
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

  # Each job reads the right secret behind every variable it gets.
  assert {
    condition = alltrue([
      for family, want in {
        "migrate"            = "migrator-database-url"
        "reset"              = "maintainer-database-url"
        "fixture"            = "runtime-database-url"
        "pool"               = "runtime-database-url"
        "inspect"            = "runtime-database-url"
        "registry-reconcile" = "runtime-database-url"
        } : length([
          for e in google_cloud_run_v2_job.replica[family].template[0].template[0].containers[0].env : e
          if e.name == "DATABASE_URL"
          && try(
            contains([
              google_secret_manager_secret.app[want].secret_id,
              google_secret_manager_secret.app[want].id,
              google_secret_manager_secret.app[want].name,
            ], e.value_source[0].secret_key_ref[0].secret)
            && e.value_source[0].secret_key_ref[0].version == "latest",
            false,
          )
      ]) == 1
    ])
    error_message = "Each job must read its own database URL: migrator, maintainer, or runtime."
  }

  assert {
    condition = alltrue([
      for family in ["reset", "fixture", "pool", "inspect", "registry-reconcile"] : alltrue([
        for name, secret in {
          "DJANGO_SECRET_KEY"               = "django-secret-key"
          "MEDIA_STORAGE_ACCESS_KEY_ID"     = "media-access-key-id"
          "MEDIA_STORAGE_SECRET_ACCESS_KEY" = "media-secret-access-key"
          "CLERK_JWT_KEY"                   = "clerk-jwt-key"
          } : length([
            for e in google_cloud_run_v2_job.replica[family].template[0].template[0].containers[0].env : e
            if e.name == name
            && try(
              contains([
                google_secret_manager_secret.app[secret].secret_id,
                google_secret_manager_secret.app[secret].id,
                google_secret_manager_secret.app[secret].name,
              ], e.value_source[0].secret_key_ref[0].secret),
              false,
            )
        ]) == 1
      ])
    ])
    error_message = "Every production job must read the django, media, and clerk secrets."
  }

  assert {
    condition = alltrue([
      for family, job in google_cloud_run_v2_job.replica :
      length([
        for e in job.template[0].template[0].containers[0].env : e
        if try(length(e.value_source[0].secret_key_ref) > 0, false)
      ]) == (family == "migrate" ? 1 : 5)
    ])
    error_message = "The migrate job must hold exactly one secret and each production job exactly five."
  }
}

run "sentry_is_wired_only_under_both_toggles" {
  command = apply

  variables {
    wire_runtime_secrets = true
    wire_sentry_dsn      = true
  }

  assert {
    condition = length([
      for e in google_cloud_run_v2_service.api.template[0].containers[0].env : e
      if e.name == "SENTRY_DSN"
      && try(
        contains([
          google_secret_manager_secret.app["sentry-dsn"].secret_id,
          google_secret_manager_secret.app["sentry-dsn"].id,
          google_secret_manager_secret.app["sentry-dsn"].name,
        ], e.value_source[0].secret_key_ref[0].secret),
        false,
      )
    ]) == 1
    error_message = "With both toggles the service must reference sentry-dsn."
  }

  assert {
    condition = length(flatten([
      for job in google_cloud_run_v2_job.replica : [
        for e in job.template[0].template[0].containers[0].env : e.name
        if e.name == "SENTRY_DSN"
      ]
    ])) == 0
    error_message = "No job may ever carry SENTRY_DSN."
  }
}

run "sentry_toggle_alone_wires_nothing" {
  command = apply

  variables {
    wire_sentry_dsn = true
  }

  assert {
    condition = length([
      for e in google_cloud_run_v2_service.api.template[0].containers[0].env : e
      if try(length(e.value_source[0].secret_key_ref) > 0, false)
    ]) == 0
    error_message = "wire_sentry_dsn without wire_runtime_secrets must not reference any secret."
  }
}

# AC19 / T1: the service listens on 8000, probes /health/live, and carries the
# non-secret production settings. The host comes from the project number.
run "service_shape_and_non_secret_env" {
  command = apply

  assert {
    condition = (
      google_cloud_run_v2_service.api.template[0].containers[0].ports[0].container_port == 8000
      && google_cloud_run_v2_service.api.template[0].containers[0].startup_probe[0].http_get[0].path == "/health/live"
      && google_cloud_run_v2_service.api.template[0].containers[0].startup_probe[0].http_get[0].port == 8000
    )
    error_message = "The service must listen on 8000 and start-probe GET /health/live on 8000."
  }

  # Django refuses any Host outside ALLOWED_HOSTS, so the probe names the host.
  assert {
    condition = {
      for h in google_cloud_run_v2_service.api.template[0].containers[0].startup_probe[0].http_get[0].http_headers : h.name => h.value
      } == {
      Host = "tailtag-api-replica-123456789012.us-east4.run.app"
    }
    error_message = "The startup probe must send the deterministic run.app host as its Host header."
  }

  assert {
    condition = {
      for e in google_cloud_run_v2_service.api.template[0].containers[0].env : e.name => e.value
      if !try(length(e.value_source[0].secret_key_ref) > 0, false)
      } == {
      DJANGO_SETTINGS_MODULE       = "config.settings.production"
      DJANGO_ALLOWED_HOSTS         = "tailtag-api-replica-123456789012.us-east4.run.app,candidate---tailtag-api-replica-123456789012.us-east4.run.app"
      DJANGO_CSRF_TRUSTED_ORIGINS  = "https://tailtag-api-replica-123456789012.us-east4.run.app"
      CLERK_AUTHENTICATION_ENABLED = "true"
      CLERK_AUTHORIZED_PARTIES     = "https://accounts.replica.tailtag.app,https://simulator.replica.tailtag.app"
      MEDIA_STORAGE_ENDPOINT_URL   = "https://00000000000000000000000000000000.r2.cloudflarestorage.com"
      MEDIA_STORAGE_BUCKET_NAME    = cloudflare_r2_bucket.media.name
      MEDIA_STORAGE_REGION         = "auto"
      SSL_CERT_FILE                = "/etc/ssl/certs/ca-certificates.crt"
      GUNICORN_CMD_ARGS            = "--timeout 0"
    }
    error_message = "The service non-secret env must be exactly the production map with the host built from the project number."
  }
}

# T3: six job shells, each with the right identity, command, limits, and
# settings. Only the migrate job has an IAM binding (#356 AC13).
run "job_shells_have_the_contracted_shape" {
  command = apply

  assert {
    condition = {
      for family, job in google_cloud_run_v2_job.replica : family => job.name
      } == {
      "migrate"            = "tailtag-replica-migrate"
      "reset"              = "tailtag-replica-reset"
      "fixture"            = "tailtag-replica-fixture"
      "pool"               = "tailtag-replica-pool"
      "inspect"            = "tailtag-replica-inspect"
      "registry-reconcile" = "tailtag-replica-registry-reconcile"
    }
    error_message = "There must be exactly the six contracted jobs with their names."
  }

  assert {
    condition = {
      for family, job in google_cloud_run_v2_job.replica : family => job.template[0].template[0].service_account
      } == {
      "migrate"            = google_service_account.migrator.email
      "reset"              = google_service_account.maintainer.email
      "fixture"            = google_service_account.runtime.email
      "pool"               = google_service_account.runtime.email
      "inspect"            = google_service_account.runtime.email
      "registry-reconcile" = google_service_account.runtime.email
    }
    error_message = "Each job must run as migrator (migrate), maintainer (reset), or runtime (the rest)."
  }

  assert {
    condition = alltrue([
      for family, job in google_cloud_run_v2_job.replica : (
        jsonencode(job.template[0].template[0].containers[0].command) == jsonencode(["python", "-E", "-s", "-u", "manage.py", "replica_${replace(family, "-", "_")}"])
        && try(length(job.template[0].template[0].containers[0].args), 0) == 0
        && job.template[0].template[0].containers[0].image == "us-docker.pkg.dev/cloudrun/container/hello"
      )
    ])
    error_message = "Each job must run python -E -s -u manage.py replica_<family> with no args from the placeholder image."
  }

  assert {
    condition = alltrue([
      for family, job in google_cloud_run_v2_job.replica : (
        job.template[0].task_count == 1
        && job.template[0].parallelism == 1
        && job.template[0].template[0].max_retries == 0
        && job.template[0].template[0].timeout == ((family == "migrate" || family == "reset") ? "900s" : "300s")
      )
    ])
    error_message = "Each job must run one task, no parallelism, no retries, with a 900 s (migrate, reset) or 300 s timeout."
  }

  assert {
    condition = {
      for family, job in google_cloud_run_v2_job.replica : family => [
        for e in job.template[0].template[0].containers[0].env : e.value
        if e.name == "DJANGO_SETTINGS_MODULE"
      ]
      } == {
      "migrate"            = ["config.settings.migrate"]
      "reset"              = ["config.settings.production"]
      "fixture"            = ["config.settings.production"]
      "pool"               = ["config.settings.production"]
      "inspect"            = ["config.settings.production"]
      "registry-reconcile" = ["config.settings.production"]
    }
    error_message = "Only the migrate job may use the migrate settings module."
  }

  # The migrate job has no production non-secret map; the others share the
  # service's map exactly.
  assert {
    condition = toset([
      for e in google_cloud_run_v2_job.replica["migrate"].template[0].template[0].containers[0].env : e.name
    ]) == toset(["DJANGO_SETTINGS_MODULE", "SSL_CERT_FILE"])
    error_message = "With no wired secrets the migrate job must carry only DJANGO_SETTINGS_MODULE and SSL_CERT_FILE."
  }

  assert {
    condition = alltrue([
      for family, job in google_cloud_run_v2_job.replica : {
        for e in job.template[0].template[0].containers[0].env : e.name => e.value
        if !try(length(e.value_source[0].secret_key_ref) > 0, false)
        } == {
        for e in google_cloud_run_v2_service.api.template[0].containers[0].env : e.name => e.value
        if !try(length(e.value_source[0].secret_key_ref) > 0, false) && e.name != "GUNICORN_CMD_ARGS"
      }
      if family != "migrate"
    ])
    error_message = "Every production job must carry the service's non-secret env, minus the gunicorn setting."
  }

  assert {
    condition = (
      output.job_names == {
        "migrate"            = "tailtag-replica-migrate"
        "reset"              = "tailtag-replica-reset"
        "fixture"            = "tailtag-replica-fixture"
        "pool"               = "tailtag-replica-pool"
        "inspect"            = "tailtag-replica-inspect"
        "registry-reconcile" = "tailtag-replica-registry-reconcile"
      }
      && output.maintainer_email == google_service_account.maintainer.email
    )
    error_message = "job_names must map family to job name and maintainer_email must be the reset identity."
  }
}

# #359 AC11: the simulator relay runs and reads the pool, fixture and inspect
# jobs only, reads only their result lines, and one owner mints its tokens.
run "simrelay_is_least_privilege" {
  command = apply

  assert {
    condition = toset([
      for m in values(google_cloud_run_v2_job_iam_member.simrelay_executor) : m.name
      if m.role == "roles/run.jobsExecutorWithOverrides" && m.member == "serviceAccount:${google_service_account.simrelay.email}"
      ]) == toset([
      google_cloud_run_v2_job.replica["pool"].name,
      google_cloud_run_v2_job.replica["fixture"].name,
      google_cloud_run_v2_job.replica["inspect"].name,
    ])
    error_message = "tt-simrelay must run the pool, fixture and inspect jobs only."
  }

  assert {
    condition = toset([
      for m in values(google_cloud_run_v2_job_iam_member.simrelay_viewer) : m.name
      if m.role == "roles/run.viewer" && m.member == "serviceAccount:${google_service_account.simrelay.email}"
      ]) == toset([
      google_cloud_run_v2_job.replica["pool"].name,
      google_cloud_run_v2_job.replica["fixture"].name,
      google_cloud_run_v2_job.replica["inspect"].name,
    ])
    error_message = "tt-simrelay must view the pool, fixture and inspect jobs only."
  }

  assert {
    condition = (
      google_logging_log_view.simrelay_job_results.bucket == "projects/fake-replica-project/locations/global/buckets/_Default"
      && google_logging_log_view.simrelay_job_results.filter == "resource.type = \"cloud_run_job\" AND LOG_ID(\"run.googleapis.com/stdout\") AND (resource.labels.job_name = \"tailtag-replica-fixture\" OR resource.labels.job_name = \"tailtag-replica-inspect\" OR resource.labels.job_name = \"tailtag-replica-pool\")"
    )
    error_message = "The relay log view must show the stdout of the three relay jobs only."
  }

  assert {
    condition = (
      google_logging_log_view_iam_member.simrelay_view_accessor.name == google_logging_log_view.simrelay_job_results.name
      && google_logging_log_view_iam_member.simrelay_view_accessor.role == "roles/logging.viewAccessor"
      && google_logging_log_view_iam_member.simrelay_view_accessor.member == "serviceAccount:${google_service_account.simrelay.email}"
    )
    error_message = "tt-simrelay must read through the relay log view only."
  }

  assert {
    condition = (
      google_service_account_iam_member.simrelay_token_minter.service_account_id == google_service_account.simrelay.name
      && google_service_account_iam_member.simrelay_token_minter.role == "roles/iam.serviceAccountTokenCreator"
      && google_service_account_iam_member.simrelay_token_minter.member == "user:owner@example.test"
    )
    error_message = "Only the configured owner may mint tt-simrelay tokens."
  }
}

run "simrelay_token_minter_must_be_one_user" {
  command = plan

  variables {
    simrelay_token_minter = "serviceAccount:tt-runtime@fake-replica-project.iam.gserviceaccount.com"
  }

  expect_failures = [var.simrelay_token_minter]
}
