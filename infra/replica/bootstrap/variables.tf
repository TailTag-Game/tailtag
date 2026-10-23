variable "project_id" {
  type = string
}

variable "billing_account" {
  type = string
}

variable "owner_email" {
  type = string
}

variable "org_id" {
  type    = string
  default = null
}

variable "folder_id" {
  type    = string
  default = null
}

variable "region" {
  type    = string
  default = "us-east4"
}

variable "budget_amount_usd" {
  type    = number
  default = 25
}
