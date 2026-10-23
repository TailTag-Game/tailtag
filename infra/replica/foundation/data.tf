resource "neon_project" "replica" {
  name                      = "tailtag-replica"
  region_id                 = var.neon_region
  pg_version                = 18
  history_retention_seconds = 86400
  default_branch_protected  = true

  branch {
    name          = "main"
    role_name     = "tailtag_admin"
    database_name = "tailtag"
  }

  primary_compute {
    autoscaling_limit_min_cu = 0.25
    autoscaling_limit_max_cu = 2
    suspend_timeout_seconds  = 300
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "cloudflare_r2_bucket" "media" {
  account_id = var.cloudflare_account_id
  name       = "tailtag-replica-media"
  location   = "enam"

  lifecycle {
    prevent_destroy = true
  }
}
