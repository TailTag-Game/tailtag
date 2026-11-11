# Run catch request cleanup as Render cron jobs

**Status:** accepted (2026-11-11)

This ADR makes the separate decision that [ADR 0011](0011-move-v0-hosting-from-railway-to-render.md) asks for before TailTag uses Render cron jobs. A Render cron job is a Render service that runs one command on a schedule. The rest of ADR 0011 and [ADR 0012](0012-run-staging-and-production-in-render-virginia.md) stay in force.

## Context and constraints

The [catch request contract](../specs/2026-11-09-reusable-tailtag-catch-request-contract.md#privacy-and-retention) says that a scheduled job deletes every catch request and every block for a convention within 24 hours after its review deadline. The review deadline is the instant when the owner review window closes. The job retries daily, and its failures must be visible. [#507](https://github.com/TailTag-Game/tailtag/issues/507) builds that job.

TailTag had no scheduler. The V0 backend is one web service and one database per environment, with no worker. ADR 0011 allowed Render one-off jobs for restore and reset, and Render cron jobs only after a separate decision.

Constraints:

- A job must not need an account-wide credential outside Render.
- A missed run must be visible, not only a failed run.
- A late run must not expose history. Reads already hide closed-window requests, so a late run only keeps hidden rows longer.

## Decision

Each environment gets one Render cron job in `render.yaml`:

| Environment | Service | Region | Deploys |
| --- | --- | --- | --- |
| Development | `tailtag-cleanup-dev` | Oregon | After the GitHub checks pass on `main` (`checksPass`) |
| Staging | `tailtag-cleanup-stg` | Virginia | Only by the promotion checklist step, at the promoted commit |

Each job runs `python manage.py cleanup_catch_requests` at 10:00 UTC each day, on the `0.5c-512mb` plan, from the same Dockerfile as the web service. 10:00 UTC is after local midnight in every US time zone, so a deadline at local midnight is cleaned within about 10 hours.

The command reports to one Sentry Crons monitor, `catch-request-cleanup`. Sentry Crons is the Sentry feature that alerts on a failed or missed scheduled run. The command creates and updates the monitor schedule from code. The owner creates one Sentry alert for the monitor. Render failure email is a second signal.

A cron job is its own Render service, so it has its own service ID. The web service pins in `config/replacement_target_binding.py` do not match it. A separate cron pin map lets build identity name the environment for logs and Sentry. Guarded operator paths keep accepting only the web pins. The cron pins start empty, and a follow-up pull request adds them after the Blueprint sync.

## Alternatives considered

| Option | Why not |
| --- | --- |
| A GitHub Actions schedule that starts a Render one-off job | It needs a Render API key in GitHub. A classic Render key can act on every workspace of the account. GitHub schedules can also run late or skip a run. |
| A schedule inside the web service | The web service has no worker. Gunicorn workers restart and scale, so one run per day is hard to promise. |
| A third-party scheduler | It adds a vendor and a credential for one daily command. |

## Consequences and risks

- Cost: Render bills cron jobs per second of run time, with a minimum of 1 USD a month per cron job ([Render cron jobs](https://render.com/docs/cronjobs), read 2026-11-11). Two jobs cost about 2 USD a month. Sentry includes one cron monitor on each plan.
- The cron job needs the variables that production settings require. That includes the media storage credentials, because settings load them at startup. The job never uses them. Clerk stays off.
- The Staging cron job can run an older commit than the web service if the promotion step is skipped. The command touches only `CatchRequest`, `CatchBlock`, and `Convention`, which no planned migration drops.
- A Blueprint sync deploys the latest `main` commit to every service in the environment. After the sync that creates the cron jobs, the owner promotes the intended Staging commit again.
- Until the cron pin pull request lands, the job reports to Sentry with environment `unknown`.

## Validation and rollback

- Validation: the first scheduled run in each environment shows an `ok` check-in in Sentry and a `tailtag.catches.request_cleanup` `succeeded` outcome in the Render logs.
- Rollback: suspend or delete the cron job in the Render dashboard, and remove it from `render.yaml`. Request history then stays hidden but is not deleted, against the contract. A replacement scheduler needs a new ADR.

## Provisioning

The decision does not provision anything. The owner runs these steps as separate authorized actions, listed in the [cleanup runbook](../operations/catch-request-cleanup.md#provisioning):

1. Sync the Render Blueprint to create the two cron jobs.
2. Promote the intended Staging commit again, and deploy the Staging cron job at that commit.
3. Create the Sentry alert for the `catch-request-cleanup` monitor.
4. Send the two cron service IDs for the pin pull request.
