# Telemetry evidence preservation, export, and access

This runbook explains how to keep evidence of an incident after Sentry and
Railway delete the underlying telemetry, how to export Railway logs safely, and
how to grant or remove access to the telemetry tools.

The rules are in the
[telemetry retention and access policy](../architecture/backend/telemetry-retention-access.md).
What telemetry may contain is in the
[telemetry privacy policy](../architecture/backend/telemetry-privacy.md). How
to find one request is in [backend logging](backend-logging.md).

## Before you start

Retention as of 2026-09-30. The current figures are in
[policy section 3](../architecture/backend/telemetry-retention-access.md#3-retention-by-class).

| Source | Kept for | Who can read it today |
| --- | --- | --- |
| Railway logs | 7 days | Observability owner |
| Railway audit log | 48 hours | Observability owner |
| Sentry errors, traces, metrics, uptime | 30 days | Observability owner |

Start on the day the incident is noticed. Do not wait for it to be resolved.
Evidence that is not recorded inside these windows is gone, and a plan upgrade
does not bring it back.

The record you produce is public. If something would be unsafe on a public
issue, it does not go in the record.

## Preserve incident evidence

1. **Fix the window.** Note the environment, the UTC start and end of the
   incident, and the deployment ID or `source_sha` that was serving. Note
   which sources are already past their retention.
2. **Read Sentry.** Filter by the environment and window. From the issue,
   trace, and metrics views, write down only: the issue short ID, error type,
   event count, first and last seen, affected route templates, `trace_id`
   values worth keeping, and counts by outcome and reason. Do not copy
   exception messages, stack traces, or URLs.
3. **Read Railway logs, if needed.** In the Railway log view, filter with
   `@request_id:<id>` or `@event:<event>` for the window. Write down only
   allow-listed values: event names, outcomes, reasons, status codes,
   durations, counts, and correlation IDs. If you need a file to work from,
   follow [Export Railway logs](#export-railway-logs).

   The observability owner may use an approved, read-only assistant connector
   for steps 2 and 3. Treat its output like the tools themselves: write the
   record by hand from allow-listed values, never by pasting connector output.
4. **Write the record** using the [template](#record-template), as an issue
   comment or in the repository evidence location for the work.
5. **Check the record** against the
   [must-not-contain list](../architecture/backend/telemetry-retention-access.md#6-preserved-evidence)
   before posting it. In particular, remove internal entity IDs (convention,
   user, fursuit, activation, session, catch), which are allowed only inside
   the protected tools.
6. **Delete any export** and confirm with `git status` that nothing raw is in
   the working tree.

If the incident seems to need raw telemetry kept beyond the provider window,
stop at step 4. Record that need in the issue and leave the decision to the
observability owner. Do not keep a raw copy in the meantime.

## Export Railway logs

Exports are temporary working files. They exist only to build a record.

```bash
dir="$(mktemp -d)"
railway logs --environment <environment> --service api \
  --since <start> --until <end> \
  --filter '@request_id:<id>' --json > "$dir/logs.json"
```

- Always bound the export with a window and a filter. Check
  `railway logs --help` for the accepted `--since` and `--until` formats.
- Write the file outside the repository, as above.
- Never commit it, attach it to an issue, or paste it into another service,
  chat, or tool.
- Delete it when the record is written: `rm -r "$dir"`.

Sentry data is read in Sentry. V0 does not use Sentry CSV export or a Sentry
API token for export.

## Record template

```markdown
### Telemetry evidence: <short title>

- Environment: <Development | Staging>
- Window (UTC): <start> to <end>
- Deployment: <deployment ID or source_sha>
- Recorded: <date>, <n> days after the incident started
- Unavailable sources: <for example "Railway logs expired">

**Sentry:** <issue short IDs, error types, counts, first and last seen,
route templates, trace_ids>

**Railway logs:** <events, outcomes and reasons, status codes, counts,
durations, request_ids>

**Narrative:** <what happened, what was checked, what is still unknown>
```

## Simulation reports

Simulation reports are kept in the repository like evidence records and follow
the same must-not-contain list. Telemetry a simulation produces in Staging
follows normal provider retention, so record anything worth keeping from it in
the report.

## Grant or remove access

Only the observability owner grants or removes access. This covers people and
integrations or tokens that can read telemetry.

1. Confirm the person needs the role, using the
   [role table](../architecture/backend/telemetry-retention-access.md#roles).
2. For Sentry, check the plan allows another user. The Developer plan does not.
   Moving to Team is a cost decision. On Team, confirm Open Membership is off.
3. For Railway, invite to the project, never to the workspace, and only as
   Viewer. First confirm that Viewer can read logs. If it cannot, give no
   Railway access.
4. Record the grant on the issue that needed it: the person's GitHub handle
   or the integration's name, the role, the tool, and the date. Do not record
   email addresses or token values.
5. Remove access when the person no longer holds the role, and record the
   removal the same way.

Never create or use a shared account.
