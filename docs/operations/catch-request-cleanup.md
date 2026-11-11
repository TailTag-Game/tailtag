# Catch request cleanup

This runbook covers the daily job that deletes catch request history after each convention's review deadline. The [catch request contract](../specs/2026-11-09-reusable-tailtag-catch-request-contract.md#privacy-and-retention) sets the rule. [ADR 0013](../adrs/0013-run-catch-request-cleanup-as-render-cron-jobs.md) records the scheduler decision. [#507](https://github.com/TailTag-Game/tailtag/issues/507) built it.

## Terms

- A request is one catch attempt that waits for, or got, an owner decision.
- A block is an owner's refusal of one player for one suit at one convention.
- The review deadline is the instant when the owner review window closes for a convention.
- Cleanup is the `cleanup_catch_requests` management command.
- A check-in is a run report that the job sends to the Sentry Crons monitor.

## What cleanup does

For each convention whose stored `review_deadline_at` is at or before the database time, cleanup deletes:

- every `CatchRequest` row, in any state, and
- every `CatchBlock` row.

Cleanup never changes or deletes a catch. A catch keeps `caught_at` and `approved_at`. Cleanup skips a convention with an open window or with no time zone.

Each convention runs in one transaction. Cleanup locks the convention row first, so it waits for any request action in flight. After the deadline, no action can write, so the delete is final.

Cleanup runs whatever the `CATCH_REQUESTS_ENABLED` gate value is. With no history, it deletes nothing.

## Retention boundaries

| Data | Rule |
| --- | --- |
| Request rows and blocks | Hidden from players and owners at the deadline. Deleted by the first successful run after the deadline. |
| Operators | Can inspect rows in the admin until cleanup deletes them. |
| Catches | Kept. Cleanup never touches them. |
| Operator audit rows | Kept with no expiry. An `invalidate_catch_request` row keeps the request ID after the request is gone. The ID holds no personal content. |
| Render PITR (point-in-time recovery) history | Deleted rows stay recoverable for up to 7 days. The owner accepted this exposure (#502 G8). |
| Metrics | Counts only, with no player, suit, convention, request, or token ID. |

## Schedule

| Environment | Render service | Schedule | Deploys |
| --- | --- | --- | --- |
| Development | `tailtag-cleanup-dev` | 10:00 UTC daily | After the GitHub checks pass on `main` |
| Staging | `tailtag-cleanup-stg` | 10:00 UTC daily | At the promoted commit, by the [promotion step](#deploy-the-staging-cron-job) |

Render runs one run at a time. If a run is still active at the next scheduled time, Render delays the next run until the active one finishes. Render stops a run after 12 hours.

## Signals

### Sentry Crons monitor

The command reports to the monitor `catch-request-cleanup`. It sends `in_progress` at the start, then `ok` or `error`. The command sets the monitor schedule from code: daily at 10:00 UTC, a 60-minute check-in margin, and a 30-minute maximum run time. One failed or missed check-in opens a Sentry issue.

Sentry gives each environment its own monitor environment. A cron job without a [pin](#pin-the-cron-services) reports as environment `unknown`. Then an `ok` check-in from one environment can hide a missed run in the other, so pin a new cron job soon after it is created.

### Outcome signal

Each run records `tailtag.catches.request_cleanup` on the usual domain outcome channels, a Sentry count and one INFO log line. See [backend domain outcomes](backend-domain-outcomes.md#catch-request-cleanup).

| Outcome | Reason | Count | Meaning |
| --- | --- | --- | --- |
| `deleted` | `expired`, `approved`, `declined`, `withdrawn`, or `invalidated` | Rows deleted in that state | A pending row counts as `expired`. |
| `succeeded` | | 1 | Every closed convention was cleaned. |
| `failed` | | 1 | At least one convention failed, or the run stopped. |

A failure for one convention writes one ERROR log line with `error_type` only, and the run continues with the next convention. The run then exits with status 1.

Render also emails a failed run when failure notifications are on for the service.

## Provisioning

These steps are separate authorized owner actions. The #507 pull request does none of them.

1. In the Render dashboard, sync the Blueprint. Make sure that the sync creates `tailtag-cleanup-dev` and `tailtag-cleanup-stg`.
2. At the sync prompt, enter the `sync: false` values for each cron job. Copy `SENTRY_DSN` and the four media storage values from the web service of the same environment.
3. A Blueprint sync deploys the latest `main` commit to every service, even with auto-deploy off. Promote the intended Staging commit again with `scripts/api_staging_render_promote.py`. See [deploys outside the promotion](../development/staging.md#deploys-outside-the-promotion).
4. [Deploy the Staging cron job](#deploy-the-staging-cron-job) at the same commit.
5. In Sentry, after the first check-in creates the monitor, create one alert for the `catch-request-cleanup` monitor. Send it to the owner.
6. Send the two cron job IDs (`crn-…`) for the [pin pull request](#pin-the-cron-services).
7. Make sure that the first scheduled run in each environment shows an `ok` check-in and a `succeeded` outcome.

The cron job gets only the variables that production settings need. Clerk stays off. The hosts values are placeholders, because the job serves no HTTP traffic. Production settings require the media storage values at startup, so the job holds them but never uses them.

## Deploy the Staging cron job

The Staging cron job has auto-deploy off. After each Staging promotion:

1. Open `tailtag-cleanup-stg` in the Render dashboard.
2. Choose **Manual Deploy**, then **Deploy a specific commit**.
3. Choose the commit that the promotion deployed to `tailtag-api-stg`.

If you skip this step, the cron job keeps its older image. The command touches only `CatchRequest`, `CatchBlock`, and `Convention`, so an older image still deletes the right rows.

## Pin the cron services

A cron job is its own Render service, with a `crn-` ID. Web services have `srv-` IDs. Build identity names the environment only for a pinned service, and the web pins do not match the cron jobs.

The pins were added on 2026-11-11 for `tailtag-cleanup-dev` (`crn-dbqbhkbl550s73emiqn0`) and `tailtag-cleanup-stg` (`crn-dbqbhkbl550s73emiqug`). If a cron job is created again, it gets a new ID. Pin it again:

1. Compute the digest from the repository root:

   ```bash
   uv --directory services/api run --locked --no-sync python -c "from config.replacement_target_binding import fingerprint_render_cron_job as f; print(f('staging', input('Cron job ID: ')))"
   ```

   Use `development` instead of `staging` for the Development cron job.
2. Put the value in `_EXPECTED_RENDER_CLEANUP_DIGESTS` in `services/api/config/replacement_target_binding.py`, and change the cron job IDs in `services/api/tests/test_build_identity.py`, in a pull request.
3. After the merge, make sure that the Development cron job redeployed. Promote Staging, and deploy the Staging cron job at that commit.
4. Trigger one run of each cron job. Make sure that its outcome log line shows its environment and release.

The cron pins widen build identity only. `validate_runtime_target`, the Staging reset, migrations, and the operator commands accept only the web pins.

## Retry a failed run

The next scheduled run retries every convention that still has history. To retry sooner:

1. Read the Sentry issue and the Render log of the failed run. The ERROR line names only `error_type`.
2. Fix the cause, if it is not temporary.
3. Open the cron job in the Render dashboard and choose **Trigger Run**. A manual trigger cancels a run that is still active.
4. Make sure that the new run shows an `ok` check-in.

## After a database restore

A PITR restore can bring back request rows that cleanup already deleted. Run cleanup against the restored database before it serves traffic.

1. Restore the database, as in [Restore the database with PITR](../development/staging.md#restore-the-database-with-pitr).
2. Copy the internal URL of the restored database from **Connect > Internal**. Note its host.
3. Open a shell on the web service of the same environment with `render ssh`. That service still uses the live database, so point this one shell at the restored database. Paste the URL at the hidden prompt:

   ```bash
   read -rs DATABASE_URL && export DATABASE_URL
   ```

4. Print the database host that Django will use:

   ```bash
   python manage.py shell -c "from django.db import connection; print(connection.settings_dict['HOST'])"
   ```

   If the host is not the restored database host from step 2, stop. Do not run cleanup.
5. Run cleanup, then run it again:

   ```bash
   python manage.py cleanup_catch_requests
   python manage.py cleanup_catch_requests
   ```

   Make sure that both runs exit with status 0, and that the second run prints `Deleted 0 catch requests and 0 blocks.`
6. Run `unset DATABASE_URL` and close the shell.
7. Only then move traffic to the restored database. Moving Staging to a restored database needs its own reviewed plan.

A manual run also sends check-ins to the `catch-request-cleanup` monitor.

A manual database export holds request history too. Run cleanup on any database restored from it before that database serves traffic.
