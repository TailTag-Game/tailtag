# Terraform creates the containers only. Operators add versions by hand so no
# secret value ever enters state.
locals {
  secret_ids = toset([
    "django-secret-key",
    "runtime-database-url",
    "migrator-database-url",
    "media-access-key-id",
    "media-secret-access-key",
    "clerk-jwt-key",
    "sentry-dsn",
  ])

  runtime_secret_ids = [
    "django-secret-key",
    "runtime-database-url",
    "media-access-key-id",
    "media-secret-access-key",
    "clerk-jwt-key",
    "sentry-dsn",
  ]

  secret_readers = merge(
    { for id in local.runtime_secret_ids : "${id}/runtime" => {
      secret_id = id
      member    = "serviceAccount:${google_service_account.runtime.email}"
    } },
    { "migrator-database-url/migrator" = {
      secret_id = "migrator-database-url"
      member    = "serviceAccount:${google_service_account.migrator.email}"
    } },
  )
}

resource "google_secret_manager_secret" "app" {
  for_each = local.secret_ids

  secret_id = each.key

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = local.secret_readers

  secret_id = google_secret_manager_secret.app[each.value.secret_id].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}
