locals {
  capacity_profiles = {
    idle = { min_instances = 0, max_instances = 2 }
  }
  capacity = local.capacity_profiles[var.capacity_profile]

  # env var name => runtime secret id. SENTRY_DSN is wired only when both
  # toggles are on, and no job ever carries it.
  runtime_secret_env = merge(
    {
      DJANGO_SECRET_KEY               = "django-secret-key"
      DATABASE_URL                    = "runtime-database-url"
      MEDIA_STORAGE_ACCESS_KEY_ID     = "media-access-key-id"
      MEDIA_STORAGE_SECRET_ACCESS_KEY = "media-secret-access-key"
      CLERK_JWT_KEY                   = "clerk-jwt-key"
    },
    var.wire_sentry_dsn ? { SENTRY_DSN = "sentry-dsn" } : {},
  )

  # Cloud Run's deterministic URL is built from the project number, so the
  # service and its jobs know the host before the first revision exists.
  service_host = "${var.service_name}-${data.google_project.this.number}.${var.region}.run.app"

  # Non-secret production settings shared by the service and every job except
  # the migrate job.
  production_env = {
    DJANGO_SETTINGS_MODULE       = "config.settings.production"
    DJANGO_ALLOWED_HOSTS         = local.service_host
    DJANGO_CSRF_TRUSTED_ORIGINS  = "https://${local.service_host}"
    CLERK_AUTHENTICATION_ENABLED = "true"
    CLERK_AUTHORIZED_PARTIES     = "https://accounts.replica.tailtag.app"
    MEDIA_STORAGE_ENDPOINT_URL   = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com"
    MEDIA_STORAGE_BUCKET_NAME    = cloudflare_r2_bucket.media.name
    MEDIA_STORAGE_REGION         = "auto"
  }
}

data "google_project" "this" {}

# Terraform owns the service shape. CI owns the image and traffic after the
# first apply, so those fields are ignored.
resource "google_cloud_run_v2_service" "api" {
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true
  # The API is public like Staging: Clerk tokens, not Cloud Run IAM, guard it.
  # Disabling the invoker check needs no allUsers binding, and the deployer
  # cannot change service IAM, so Terraform owns this field.
  invoker_iam_disabled = true

  template {
    service_account = google_service_account.runtime.email

    scaling {
      min_instance_count = local.capacity.min_instances
      max_instance_count = local.capacity.max_instances
    }

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      ports {
        container_port = 8000
      }

      startup_probe {
        http_get {
          path = "/health/live"
          port = 8000
        }
      }

      dynamic "env" {
        for_each = local.production_env

        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.wire_runtime_secrets ? local.runtime_secret_env : {}

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

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      template[0].revision,
      traffic,
    ]
  }

  depends_on = [google_secret_manager_secret_iam_member.accessor]
}

resource "google_cloud_run_v2_service_iam_member" "deployer_developer" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deployer.email}"
}
