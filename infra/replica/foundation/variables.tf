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

variable "enable_cleanup_exercise" {
  type    = bool
  default = false
}
