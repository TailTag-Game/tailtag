# Backend telemetry retention and operator access policy

**Status:** defined by [#215](https://github.com/TailTag-Game/tailtag/issues/215)

**Related:** [V0 backend observability architecture](observability.md), [ADR 0007](../../adrs/0007-v0-observability-backend.md), [telemetry privacy policy](telemetry-privacy.md), [evidence preservation runbook](../../operations/telemetry-evidence-preservation.md), [design spec](../../specs/2026-09-30-telemetry-retention-access.md)

This policy says how long each class of telemetry is kept, where it lives, who may read it, and how evidence is kept after the providers delete it. The [telemetry privacy policy](telemetry-privacy.md) still governs what telemetry may contain, including when it is exported or preserved.

## 1. Two tiers

- **Raw telemetry** stays in Sentry and Render and expires on the provider's schedule. It is not copied anywhere else, except as a temporary export while building an evidence record.
- **Preserved evidence** is a sanitized record in this repository or in a GitHub issue. The repository is public, so the record must be safe to publish (section 6).

V0 has no private evidence store. If an incident ever needs raw telemetry kept beyond the provider window, that is a new decision about where it lives and who can read it. It is not handled by copying raw data somewhere convenient.

## 2. Current plans

The maintainer confirmed the Sentry plan on 2026-09-30. [ADR 0011](../../adrs/0011-move-v0-hosting-from-railway-to-render.md) set the Render plan on 2026-10-29, and [#412](https://github.com/TailTag-Game/tailtag/issues/412) recorded it here.

| Tool | Plan | Members |
| --- | --- | --- |
| Sentry | Developer (free) | 1 |
| Render | Pro workspace | 1 |

Both members are the same person. Re-verify every figure in section 3 whenever either plan changes.

## 3. Retention by class

Sentry figures were read from Sentry documentation on 2026-09-30. Render figures were read from Render documentation on 2026-11-04. They are provider limits, not durations TailTag chose, and they can change without notice.

| Class | Where | Retention | Source |
| --- | --- | --- | --- |
| Traces (transactions and spans) | Sentry | 30 days | [Sentry data retention](https://docs.sentry.io/security-legal-pii/security/data-retention-periods/) |
| Errors | Sentry | 30 days | Same |
| Metrics | Sentry | 30 days | Same |
| Uptime check results | Sentry | 30 days | Same |
| Structured logs and HTTP request logs | Render | 14 days | [Render logging](https://render.com/docs/logging) |
| Service metrics | Render | 14 days | [Render service metrics](https://render.com/docs/service-metrics) |
| Workspace audit log | Render | At least 90 days | [Render audit logs](https://render.com/docs/audit-logs) |
| Simulation reports | Repository | While the milestone they validate is relevant | This policy, section 7 |
| Preserved incident evidence | Repository or GitHub issue | Permanent (git history and issue history) | This policy, section 6 |

Plan context for future decisions: Sentry Team keeps errors and uptime results for 90 days but spans and metrics for 30. Render Scale keeps logs and metrics for 30 days.

Sentry sets retention when data is received. A plan upgrade does not extend data already stored, so upgrading during an incident does not rescue that incident's telemetry.

Render documents one log retention figure per plan. It does not give separate figures for build or deploy logs. A plan upgrade does not bring back logs that already expired.

## 4. Retention controls TailTag owns

Neither provider offers a retention setting on the current plans. The controls TailTag owns are:

- **Trace sampling:** `SENTRY_TRACES_SAMPLE_RATE` per environment controls how many traces are stored. Unset means tracing is off.
- **Enabled datasets:** Sentry Logs stays off. Turning on any new Sentry dataset is a change to this policy.
- **Plan choice:** the only way to change provider retention. Plan changes are cost decisions made by the observability owner.

High-volume telemetry is therefore never retained indefinitely: both providers delete it, and nothing in TailTag copies it.

## 5. Access

### Roles

| Role | May | Sentry | Render |
| --- | --- | --- | --- |
| Observability owner | Query, export, preserve, grant and remove access, change plans | Owner | Workspace Admin |
| Incident responder | Query and preserve | Member, on the projects they need | None on Pro (see growth triggers) |
| Contributor | Read sanitized evidence in the repository | None | None |

Today the observability owner is the only member of either tool, and there are no incident responders. Least privilege is met by having one named account per tool.

### Rules

- Operators use their own named accounts. Shared accounts are never used.
- Sentry is the incident responder's main surface. It carries errors, traces, and metrics and holds no deployment variables. Project members can see the DSN, which only allows sending events.
- Render workspace membership is never granted only to read logs. On Pro, the only roles are Admin and Developer. A Developer can also view and change environment variables, which hold secrets, outside protected environments.
- Access is removed when a person no longer holds the role.
- Integrations and tokens that can read telemetry count as access. This includes Render API keys, Sentry auth tokens, and third-party or assistant connectors to Sentry or Render. Only the observability owner grants them, each is recorded and removed like a person's access, and each is scoped to read only what it needs.
- AI assistant connectors may read Sentry or Render only for the observability owner, read-only, under the owner's own account, and recorded like any other grant. Approved by the maintainer on 2026-09-30. What a connector returns is protected telemetry: it follows section 6 like anything else, and a connector is never used to produce public evidence directly.

### Growth triggers

- **A second person needs Sentry.** The Developer plan allows one user. Moving to Team is a cost decision for the observability owner. On Team, turn Open Membership off, so joining an access-granting team needs approval. Sentry's team-level roles need Business or above.
- **A second person needs Render logs.** On Pro, that person gets no Render access and uses Sentry. Render's Viewer role cannot read service logs, and the Contributor role, which can, needs the Scale plan. Moving to Scale is a cost decision for the observability owner.
- **Environment-level access.** Render protected environments limit secrets and changes to Admins, but they do not limit log viewing. TailTag uses separate workspaces instead (section 8).

## 6. Preserved evidence

The procedure is in the [evidence preservation runbook](../../operations/telemetry-evidence-preservation.md).

Preservation starts on the day an incident is noticed, not after it is resolved. Render's 14-day log retention is the binding limit.

An evidence record may contain:

- UTC time window and environment;
- deployment ID or `source_sha`;
- `request_id`, `edge_request_id`, and `trace_id`;
- Sentry issue short ID;
- route templates and HTTP status codes;
- bounded outcomes, reasons, and error types;
- counts, rates, and durations;
- a narrative of what happened, what was checked, and which sources had already expired.

An evidence record must not contain:

- anything in the [privacy policy's prohibited list](telemetry-privacy.md#1-prohibited-data);
- internal entity IDs, which are allowed only in protected telemetry ([privacy policy section 4](telemetry-privacy.md#4-entity-ids));
- raw log lines or exported log files;
- Sentry or Render URLs;
- exception messages or stack traces;
- screenshots that show any of the above.

## 7. Simulation reports

Simulation data is synthetic, so a simulation report may be kept as repository evidence for as long as the milestone it validates is relevant. Reports still follow section 6, because git history is permanent. They must not contain secrets, tokens, credentials, real player data, or provider URLs.

Telemetry that a simulation run produces in Staging is ordinary Staging telemetry and follows section 3. Only the report is kept longer. The report format belongs to [#199](https://github.com/TailTag-Game/tailtag/issues/199).

## 8. Environment separation

- Development and Staging share one Sentry project, separated by `environment`. This separation is a filter, not an access boundary: anyone with access to the project can read both.
- Development and Staging run in one Render workspace. Workspace access covers both.
- Local development and tests send nothing to Sentry.
- A future Production environment gets its own Sentry project and its own Render workspace if Production log access must be narrower than workspace access. That choice is made with Production.

## 9. Known limitations

- With one operator there is no independent access review.
- Render's audit log records changes and secret views, but only workspace Admins can export it.
- An incident noticed more than 14 days later has no Render logs. The evidence record says so.
- Sentry server-side scrubbing is not relied on. It is not documented for spans or metrics. Process-side redaction is the control.
- Not verified on the current plans, and not relied on: Sentry CSV export, a Sentry API export path, and Render build and deploy log retention.
