# Disposable resources for the destroy-and-recreate exercise. No
# prevent_destroy, no versions, no IAM.
resource "neon_branch" "cleanup_exercise" {
  count = var.enable_cleanup_exercise ? 1 : 0

  project_id = neon_project.replica.id
  name       = "cleanup-exercise"
}

resource "google_secret_manager_secret" "cleanup_exercise" {
  count = var.enable_cleanup_exercise ? 1 : 0

  secret_id = "cleanup-exercise"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}
