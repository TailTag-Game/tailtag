provider "google" {
  project                     = var.project_id
  region                      = var.region
  impersonate_service_account = var.tf_infra_email
}

# Reads CLOUDFLARE_API_TOKEN from the environment.
provider "cloudflare" {}

# Reads NEON_API_KEY from the environment.
provider "neon" {}
