# The simulator relay identity (#359 AC11). It runs and reads only the pool,
# fixture and inspect jobs, and it has no key: the owner mints a short-lived
# token for one attended session by impersonation. Runs with overrides can
# change the job environment, so a token holder can act as tt-runtime. The
# trust runbook records the controls and the compromise steps.
locals {
  simrelay_jobs = toset(["pool", "fixture", "inspect"])

  # The relay reads each job's one result line from stdout. The view shows all
  # stdout of those three jobs, including Django logs, and nothing else.
  simrelay_log_filter = join(" AND ", [
    "resource.type = \"cloud_run_job\"",
    "LOG_ID(\"run.googleapis.com/stdout\")",
    "(${join(" OR ", [
      for job in sort(tolist(local.simrelay_jobs)) :
      "resource.labels.job_name = \"${google_cloud_run_v2_job.replica[job].name}\""
    ])})",
  ])
}

resource "google_service_account" "simrelay" {
  account_id   = "tt-simrelay"
  display_name = "TailTag replica simulator relay"
}

resource "google_cloud_run_v2_job_iam_member" "simrelay_executor" {
  for_each = local.simrelay_jobs

  name     = google_cloud_run_v2_job.replica[each.key].name
  location = google_cloud_run_v2_job.replica[each.key].location
  role     = "roles/run.jobsExecutorWithOverrides"
  member   = "serviceAccount:${google_service_account.simrelay.email}"
}

# The relay polls its own executions, which needs run.executions.get.
resource "google_cloud_run_v2_job_iam_member" "simrelay_viewer" {
  for_each = local.simrelay_jobs

  name     = google_cloud_run_v2_job.replica[each.key].name
  location = google_cloud_run_v2_job.replica[each.key].location
  role     = "roles/run.viewer"
  member   = "serviceAccount:${google_service_account.simrelay.email}"
}

# A view on the existing _Default bucket. Terraform does not manage the bucket,
# so its retention stays as it is.
resource "google_logging_log_view" "simrelay_job_results" {
  name        = "simrelay-job-results"
  bucket      = "projects/${var.project_id}/locations/global/buckets/_Default"
  description = "Stdout of the pool, fixture and inspect jobs for tt-simrelay"
  filter      = local.simrelay_log_filter
}

resource "google_logging_log_view_iam_member" "simrelay_view_accessor" {
  parent   = google_logging_log_view.simrelay_job_results.parent
  location = google_logging_log_view.simrelay_job_results.location
  bucket   = google_logging_log_view.simrelay_job_results.bucket
  name     = google_logging_log_view.simrelay_job_results.name
  role     = "roles/logging.viewAccessor"
  member   = "serviceAccount:${google_service_account.simrelay.email}"
}

# Exactly one owner principal can mint relay tokens.
resource "google_service_account_iam_member" "simrelay_token_minter" {
  service_account_id = google_service_account.simrelay.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = var.simrelay_token_minter
}
