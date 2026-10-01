# Field-beta telemetry retention and operator access

Issue: [#215](https://github.com/TailTag-Game/tailtag/issues/215) (OB-7).
Parent: #198. Architecture: [ADR 0007 and the observability boundary](../architecture/backend/observability.md) (#209).
Builds on: #211 ([telemetry privacy policy](../architecture/backend/telemetry-privacy.md)).
Consumers: #216 (dashboard and alert access), #199 (simulation reports), #217 (final validation).

## Status and phase ledger

Execution: STANDARD COMPACT, documentation only. Assurance: SECURITY
(operator access and what may leave the protected tools).
Completed: scope review, uncertainty review, provider research
(2026-09-30), maintainer confirmation of current plans and of the
no-private-store decision (2026-09-30), maintainer approval of the design
below (2026-09-30), policy and runbook documentation.
Completed additionally: `./scripts/doctor.sh`, `git diff --check`, and a
relative link check passed. Independent review: SPEC, QUALITY, TEST, SCOPE,
and SECURITY passed, with one MEDIUM and three LOW findings, remediated by the
parent:

- M1 (MEDIUM): integrations and tokens that can read telemetry count as access
  (D6, policy section 5, runbook).
- L1 (LOW): D8 lists `railway_request_id`, error types, and rates, matching
  the policy.
- L2 (LOW): Production's Railway separation is a project or workspace, decided
  with Production, as in ADR 0007.
- L3 (LOW): Sentry holds no deployment variables; members can see the DSN.

Completed additionally: maintainer approval of owner-only, read-only assistant
connector access (2026-09-30).
Current: commit and pull request.

## Problem

Telemetry now flows to two providers with different retention and access
models, and nothing says how long each class is kept, who may read it, or how
an operator keeps evidence of an incident after the providers expire it. The
repository is public, so the obvious evidence location is also the least
private one.

## Evidence

Provider facts below were read from provider documentation on 2026-09-30.
They are point-in-time observations, not guarantees, and are re-verified on any
plan change.

Current plans (maintainer, 2026-09-30): Sentry Developer (free), one member.
Railway Hobby, one member. Both are the same person.

| Fact | Source |
| --- | --- |
| Sentry retention is set by plan and fixed when data is received; a later plan change affects only new data. No per-project or per-dataset retention setting or retention add-on is documented below Enterprise. | [Sentry data retention](https://docs.sentry.io/security-legal-pii/security/data-retention-periods/) |
| Sentry Developer: errors, spans, application metrics, uptime results, and attachments 30 days. Team: errors, uptime, attachments 90 days; spans and metrics 30 days. | Same |
| Sentry Developer allows one user; Team allows unlimited users. Team-level roles are Business and above. Open Membership is on by default. | [Sentry pricing](https://sentry.io/pricing/), [Sentry membership](https://docs.sentry.io/organization/membership/) |
| Railway logs: Hobby 7 days, Pro 30, Enterprise up to 90. Not customer-configurable. No log drain. | [Railway logging](https://docs.railway.com/reference/logging) |
| Railway audit log: Hobby 48 hours, Pro 30 days. Admin-only. | [Railway audit logs](https://docs.railway.com/enterprise/audit-logs) |
| Railway workspace Member can read logs and change variables; Deployer cannot read logs. Project Viewer cannot see variables. Environment-level access control needs committed spend. | [Railway teams](https://docs.railway.com/reference/teams), [project members](https://docs.railway.com/projects/project-members), [environment RBAC](https://docs.railway.com/enterprise/environment-rbac) |
| `railway logs` supports `--json`, `--since`, `--until`, `--filter`, and for HTTP logs `--request-id`. | [Railway CLI logs](https://docs.railway.com/cli/logs) |

Unverified, and not relied on: whether a Railway project Viewer can read logs;
whether Sentry Discover CSV export is available on Developer or Team; whether
Sentry server-side scrubbing covers spans and metrics. Railway
`@request_id:<id>` filtering on structured logs was verified by #210
([D-1](../operations/backend-logging.md)).

## Decisions

**D1 Two tiers, no private store.** Raw telemetry stays in Sentry and Railway
and expires on the provider's schedule. Preserved evidence is a sanitized
record in the public repository or an issue. V0 introduces no private evidence
store, and no raw telemetry outlives the provider window. A future need to keep
raw data longer is a new decision, not an improvised copy.

**D2 Retention is provider-determined.** The policy records provider retention
as limits, not chosen durations. The controls TailTag owns are the trace sample
rate per environment (`SENTRY_TRACES_SAMPLE_RATE`), which datasets are enabled
(Sentry Logs stays off), and plan choice. Because retention is fixed at
receipt, a plan upgrade cannot rescue data from an incident already underway.

**D3 Preservation works inside the shortest window.** Railway Hobby log
retention (7 days) is the binding limit, so preservation starts on the day an
incident is noticed, not after it is resolved.

**D4 Roles, not people.** The policy defines roles and records who holds them.

| Role | May | Sentry | Railway |
| --- | --- | --- | --- |
| Observability owner | Query, export, preserve, grant and remove access, change plans | Owner | Workspace Admin |
| Incident responder | Query and preserve | Member, on the projects they need | Project Viewer only if it can read logs; otherwise none |
| Contributor | Read sanitized evidence in the repository | None | None |

Today the owner holds every role and there are no responders. Least privilege
is met by having one account per tool.

**D5 Sentry is the responder's surface.** Sentry carries errors, traces, and
metrics and holds no deployment variables; members can see the DSN, which
only allows sending events. A Railway workspace Member can change variables,
so Railway workspace membership is never granted just to read logs.

**D6 Growth triggers.** A second person who needs Sentry access requires the
Team plan (a cost decision, reviewed when it arises) and Open Membership off. A
second person who needs Railway logs requires first confirming that project
Viewer can read logs. Access is removed when the person no longer holds the
role. Shared accounts are never used. Integrations and tokens that can read
telemetry count as access: only the observability owner grants them, and they
are recorded and removed like a person's access. AI assistant connectors may
read telemetry only for the observability owner, read-only, under the owner's
account, and never to produce public evidence directly (maintainer approval,
2026-09-30).

**D7 Environment separation follows ADR 0007.** Development and Staging share
one Sentry project, separated by `environment`; that separation is a filter,
not an access boundary. Railway environments sit in one project. Local
development and tests send nothing. A future Production environment gets its
own Sentry project and its own Railway project or workspace, decided with
Production, which is how Production access is narrowed without
environment-level access control.

**D8 The evidence record is public-safe.** It may contain: UTC time window,
environment, deployment ID or `source_sha`, `request_id`,
`railway_request_id`, `trace_id`, Sentry issue short ID, route template,
status codes, bounded outcomes, reasons, and error types, counts, rates,
durations, and a narrative. It must not contain: anything prohibited by
the [privacy policy](../architecture/backend/telemetry-privacy.md#1-prohibited-data),
internal entity IDs (allowed only in protected telemetry), raw log lines,
Sentry or Railway URLs, exception messages, or screenshots that show any of
these.

**D9 Exports are temporary.** A Railway export is a bounded
`railway logs --json` window written outside the repository, read to build the
record, then deleted. Raw exports are never committed, attached to issues, or
pasted into other services. Sentry evidence is gathered by viewing it in
Sentry; V0 adds no CSV export dependency and no Sentry API token.

**D10 Simulation reports.** Simulation data is synthetic, so reports may be
kept as repository evidence for as long as the milestone they validate is
relevant. They follow D8 anyway, because git history is permanent. Telemetry a
simulation produces in Staging follows normal provider retention. The report
format belongs to #199.

## Scope

### In scope

- A retention and access policy covering traces, structured logs, metrics,
  uptime results, simulation reports, and preserved incident evidence.
- An operations runbook for preserving incident evidence and exporting logs.
- Updating the observability architecture to point to the policy.

### Out of scope

- Any private evidence store, plan upgrade, or access change.
- Application code, Sentry or Railway configuration changes.
- Dashboards and alerts (#216); simulation tooling and report format (#199).
- Compliance or legal retention, product analytics, BI.

## Acceptance Contract

**AC-1 Classes.** The policy gives each class (traces, errors, structured logs,
metrics, uptime results, Railway audit log, simulation reports, preserved
incident evidence) its location, retention, and source of that retention.

**AC-2 No invented durations.** Every provider figure cites its source and
review date, and the policy states it is re-verified on plan change.

**AC-3 Bounded retention.** High-volume telemetry has only provider-bounded
retention; nothing copies it elsewhere beyond a temporary export.

**AC-4 Environments.** Environment separation and its limits match D7.

**AC-5 Access.** Roles, current holders, permitted actions, and growth
triggers match D4–D6.

**AC-6 Preservation.** A maintainer can follow the runbook to produce an
evidence record that satisfies D8, starting inside the D3 window, without
needing knowledge outside the repository.

**AC-7 Limits recorded.** Known limitations and unverified provider behavior
are stated as such.

**AC-8 Boundaries.** No private store, analytics retention, permanent
high-volume store, or compliance program is introduced.

## Design

- New `docs/architecture/backend/telemetry-retention-access.md`: the policy
  (D1–D8, D10, AC-1–AC-5, AC-7).
- New `docs/operations/telemetry-evidence-preservation.md`: the runbook (D3,
  D8, D9, AC-6).
- `docs/architecture/backend/observability.md`: section 5 and the #215 handoff
  in section 7 point to the policy.
- `docs/specs/README.md`: list this spec.

## Test surface

Documentation only. NO NEW TEST REQUIRED. Validation is `./scripts/doctor.sh`
and `git diff --check`.

## Risks

- **Provider drift.** Retention and roles change without notice. Mitigated by
  dated figures and re-verification on plan change.
- **Late preservation.** An incident noticed after 7 days has no Railway logs.
  Sentry keeps 30 days; the record says which sources were unavailable.
- **Over-sharing in public evidence.** Mitigated by the D8 allow-list and the
  runbook's review step.

## Known limitations

- With one operator there is no independent access review; the 48-hour Railway
  audit log gives almost no access history.
- Sentry `environment` separation is not an access boundary.
- Server-side Sentry scrubbing is not relied on; process-side redaction is the
  control.
