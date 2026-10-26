resource "google_artifact_registry_repository" "api" {
  repository_id = "tailtag-api"
  location      = var.region
  format        = "DOCKER"

  # A release tags each image with its source SHA. Immutable tags make that
  # tag name one digest for good (#356 AC1).
  docker_config {
    immutable_tags = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_artifact_registry_repository_iam_member" "deployer_writer" {
  repository = google_artifact_registry_repository.api.name
  location   = google_artifact_registry_repository.api.location
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}
