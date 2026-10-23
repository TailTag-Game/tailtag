# The bucket and impersonate_service_account come from -backend-config.
terraform {
  backend "gcs" {
    prefix = "foundation"
  }
}
