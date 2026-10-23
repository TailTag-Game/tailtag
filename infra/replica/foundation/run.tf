locals {
  capacity_profiles = {
    idle = { min_instances = 0, max_instances = 2 }
  }
  capacity = local.capacity_profiles[var.capacity_profile]

  # env var name => runtime secret id
  runtime_secret_env = {
    DJANGO_SECRET_KEY               = "django-secret-key"
    DATABASE_URL                    = "runtime-database-url"
    MEDIA_STORAGE_ACCESS_KEY_ID     = "media-access-key-id"
    MEDIA_STORAGE_SECRET_ACCESS_KEY = "media-secret-access-key"
    CLERK_JWT_KEY                   = "clerk-jwt-key"
    SENTRY_DSN                      = "sentry-dsn"
  }
}

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
