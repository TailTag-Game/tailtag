# The bucket comes from -backend-config. The first apply uses a local override.
terraform {
  backend "gcs" {
    prefix = "bootstrap"
  }
}
