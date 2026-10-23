provider "google" {
  project = var.project_id
  region  = var.region
}

# The Budgets API needs a quota project when it runs on user credentials. The
# replica project is that quota project, so only the budget uses this alias:
# the project must exist before any request can name it.
provider "google" {
  alias                 = "billing"
  project               = var.project_id
  region                = var.region
  billing_project       = var.project_id
  user_project_override = true
}
