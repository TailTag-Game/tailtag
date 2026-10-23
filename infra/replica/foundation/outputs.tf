output "service_name" {
  value = google_cloud_run_v2_service.api.name
}

output "service_uri" {
  value = google_cloud_run_v2_service.api.uri
}

output "artifact_repository_id" {
  value = google_artifact_registry_repository.api.repository_id
}

output "deployer_email" {
  value = google_service_account.deployer.email
}

output "migrator_email" {
  value = google_service_account.migrator.email
}

output "runtime_email" {
  value = google_service_account.runtime.email
}

output "wif_provider_name" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "neon_project_id" {
  value = neon_project.replica.id
}

# Consumed only by the role script. It holds the admin password.
output "neon_admin_connection_uri" {
  value     = neon_project.replica.connection_uri
  sensitive = true
}
