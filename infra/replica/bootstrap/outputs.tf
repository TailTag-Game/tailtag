output "project_id" {
  value = google_project.replica.project_id
}

output "state_bucket" {
  value = google_storage_bucket.state.name
}

output "tf_infra_email" {
  value = google_service_account.tf_infra.email
}

output "region" {
  value = var.region
}
