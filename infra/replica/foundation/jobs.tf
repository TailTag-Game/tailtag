locals {
  # Every job shell shares one image placeholder, one command, and one limit
  # set. Only project owners can execute a job: no job IAM resource exists.
  production_job_secret_env = {
    DJANGO_SECRET_KEY               = "django-secret-key"
    MEDIA_STORAGE_ACCESS_KEY_ID     = "media-access-key-id"
    MEDIA_STORAGE_SECRET_ACCESS_KEY = "media-secret-access-key"
    CLERK_JWT_KEY                   = "clerk-jwt-key"
  }

  jobs = {
    migrate = {
      service_account = google_service_account.migrator.email
      command         = "replica_migrate"
      timeout         = "900s"
      env             = merge(local.tls_env, { DJANGO_SETTINGS_MODULE = "config.settings.migrate" })
      secret_env      = { DATABASE_URL = "migrator-database-url" }
    }
    reset = {
      service_account = google_service_account.maintainer.email
      command         = "replica_reset"
      timeout         = "900s"
      env             = local.production_env
      secret_env = merge(local.production_job_secret_env, {
        DATABASE_URL = "maintainer-database-url"
      })
    }
    fixture = {
      service_account = google_service_account.runtime.email
      command         = "replica_fixture"
      timeout         = "300s"
      env             = local.production_env
      secret_env = merge(local.production_job_secret_env, {
        DATABASE_URL = "runtime-database-url"
      })
    }
    pool = {
      service_account = google_service_account.runtime.email
      command         = "replica_pool"
      timeout         = "300s"
      env             = local.production_env
      secret_env = merge(local.production_job_secret_env, {
        DATABASE_URL = "runtime-database-url"
      })
    }
    inspect = {
      service_account = google_service_account.runtime.email
      command         = "replica_inspect"
      timeout         = "300s"
      env             = local.production_env
      secret_env = merge(local.production_job_secret_env, {
        DATABASE_URL = "runtime-database-url"
      })
    }
    registry-reconcile = {
      service_account = google_service_account.runtime.email
      command         = "replica_registry_reconcile"
      timeout         = "300s"
      env             = local.production_env
      secret_env = merge(local.production_job_secret_env, {
        DATABASE_URL = "runtime-database-url"
      })
    }
  }
}

# Terraform owns the job shape. CI owns the image after the first apply, so the
# image and client fields are ignored, as on the service.
resource "google_cloud_run_v2_job" "replica" {
  for_each = local.jobs

  name                = "tailtag-replica-${each.key}"
  location            = var.region
  deletion_protection = true

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = each.value.service_account
      max_retries     = 0
      timeout         = each.value.timeout

      containers {
        image   = "us-docker.pkg.dev/cloudrun/container/hello"
        command = ["python"]
        args    = ["manage.py", each.value.command]

        dynamic "env" {
          for_each = each.value.env

          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = var.wire_runtime_secrets ? each.value.secret_env : {}

          content {
            name = env.key

            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.app[env.value].secret_id
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_secret_manager_secret_iam_member.accessor]
}
