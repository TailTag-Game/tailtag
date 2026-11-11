# Telemetry evidence preservation, export, and access

This runbook explains how to keep evidence of an incident after Sentry and
Render delete the underlying telemetry, how to export Render logs safely, and
how to grant or remove access to the telemetry tools.

The rules are in the
[telemetry retention and access policy](../architecture/backend/telemetry-retention-access.md).
What telemetry may contain is in the
[telemetry privacy policy](../architecture/backend/telemetry-privacy.md). How
to find one request is in [backend logging](backend-logging.md).

## Before you start

Retention as of 2026-11-04. The current figures are in
[policy section 3](../architecture/backend/telemetry-retention-access.md#3-retention-by-class).

| Source | Kept for | Who can read it today |
| --- | --- | --- |
| Render logs and HTTP request logs | 14 days | Observability owner |
| Render workspace audit log | At least 90 days | Observability owner (export is Admin-only) |
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
3. **Read Render logs, if needed.** In the Render log explorer, set the window
   and search for the `request_id` value or the event name as text.
   Render has no filter on custom JSON keys (see [backend logging](backend-logging.md)). Write down only
   allow-listed values: event names, outcomes, reasons, status codes,
   durations, counts, and correlation IDs. If you need a file to work from,
   follow [Export Render logs](#export-render-logs).

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

## Export Render logs

Exports are temporary working files. They exist only to build a record.

```bash
dir="$(mktemp -d)"
render logs --resources <service-id> \
  --start <start> --end <end> \
  --text '<request_id>' --output json > "$dir/logs.json"
```

- Always bound the export with a window and a text filter. Check
  `render logs --help` for the accepted `--start` and `--end` formats.
- The service ID starts with `srv-`. It is not a secret, but keep it out of the
  public record.
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
- Unavailable sources: <for example "Render logs expired">

**Sentry:** <issue short IDs, error types, counts, first and last seen,
route templates, trace_ids>

**Render logs:** <events, outcomes and reasons, status codes, counts,
durations, request_ids>

**Narrative:** <what happened, what was checked, what is still unknown>
```

## Simulation reports

Simulation reports, evaluations and host companions are kept in the
maintainer's private evidence archive, not in the repository.
`tools/simulator/reports/` is ignored by Git. They follow the same
must-not-contain list. Only reviewed performance baselines and thresholds are
committed, under `tools/simulator/baselines/`, and each baseline records the
SHA-256 of the archived report it came from. Telemetry a simulation produces in
Staging follows normal provider retention. Record anything worth keeping in the
report, or as closed values in an evaluation's operator context.

## Grant or remove access

Only the observability owner grants or removes access. This covers people and
integrations or tokens that can read telemetry.

1. Confirm the person needs the role, using the
   [role table](../architecture/backend/telemetry-retention-access.md#roles).
2. For Sentry, check the plan allows another user. The Developer plan does not.
   Moving to Team is a cost decision. On Team, confirm Open Membership is off.
3. For Render, give no access on the Pro plan. Pro has only the Admin and
   Developer roles, and both can see secrets. A log-only role needs the Scale
   plan, which is a cost decision.
4. Record the grant on the issue that needed it: the person's GitHub handle
   or the integration's name, the role, the tool, and the date. Do not record
   email addresses or token values.
5. Remove access when the person no longer holds the role, and record the
   removal the same way.

Never create or use a shared account.
