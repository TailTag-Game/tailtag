variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east4"
}

variable "tf_infra_email" {
  type = string
}

variable "cloudflare_account_id" {
  type = string
}

variable "neon_region" {
  type    = string
  default = "aws-us-east-1"
}

variable "service_name" {
  type    = string
  default = "tailtag-api-replica"
}

variable "capacity_profile" {
  type    = string
  default = "idle"

  validation {
    condition     = contains(keys(local.capacity_profiles), var.capacity_profile)
    error_message = "capacity_profile must be a key of local.capacity_profiles."
  }
}

# Set true only after the operator has entered every runtime secret version.
variable "wire_runtime_secrets" {
  type    = bool
  default = false
}

# Wires SENTRY_DSN into the service only, and only together with
# wire_runtime_secrets. Set true after the operator has entered a sentry-dsn
# secret version.
variable "wire_sentry_dsn" {
  type    = bool
  default = false
}

# The one owner account that may mint tt-simrelay tokens (#359 AC11), for
# example "user:<owner email>". Keep it in the gitignored terraform.tfvars.
variable "simrelay_token_minter" {
  type = string

  validation {
    condition     = can(regex("^user:[^@\\s]+@[^@\\s]+$", var.simrelay_token_minter))
    error_message = "simrelay_token_minter must be one user principal, user:<email>."
  }
}

variable "enable_cleanup_exercise" {
  type    = bool
  default = false
}
