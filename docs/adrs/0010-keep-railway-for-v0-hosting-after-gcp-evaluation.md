# Keep Railway for V0 hosting after the GCP evaluation

**Status:** proposed (2026-10-22)

## Context and constraints

[ADR 0004](0004-use-railway-for-v0-hosting.md) chose Railway for V0 hosting. TailTag runs Development and Staging on Railway and has no Production environment yet. Before the project designs Production, [#338](https://github.com/TailTag-Game/tailtag/issues/338) tested Google Cloud Platform (GCP) as an alternative: Cloud Run for the API and Cloud SQL for PostgreSQL. The test used a temporary project and synthetic data only.

The [GCP hosting comparison](../specs/2026-10-22-gcp-hosting-comparison.md) holds the evidence. Its main points:

- The current API image runs on Cloud Run without application changes. One rule blocks readiness: readiness requires Railway identity variables (#346).
- Deployment, rollback, migrations as a one-time job, IAM database login, Clerk, private media, backup restore, and point-in-time recovery (PITR) all passed on GCP.
- After [#348](https://github.com/TailTag-Game/tailtag/issues/348), a revision with a wrong Cloud SQL instance name stops before it takes traffic.
- Cold starts take 6 to 15 seconds when no instance is warm.
- At matched service levels, the convention-ready month costs an estimated $27 to $64 on Railway Pro and $135 to $173 on GCP. The GCP figure includes database failover, PITR, and a Cloud SQL SLA, which Railway does not offer.
- A move needs an estimated 67 to 135 hours of one-time work. Most of it replaces delivery, promotion, restore, and reset tooling that already has proof on Railway.

## Decision

Keep Railway for V0 hosting, including the first Production design. This confirms ADR 0004. It does not supersede it.

Do not start a move to GCP. Keep the deferred portability work in #346 and #347 as migration items. Do them only if a trigger below reopens this decision.

Reopen this decision when one of these happens:

- A convention needs database failover, PITR, or a contractual SLA, and Railway cannot provide a tested equivalent.
- Railway prices, plans, or reliability change in a way that removes its cost or effort advantage.
- TailTag outgrows Railway's plan limits, or measured load shows that Railway cannot serve a convention.
- An organization, compliance, or funding need favors GCP.

## Alternatives considered

- **Move to GCP for V0.** It offers stronger recovery: database failover, PITR, and an SLA. It was not chosen, because it costs about 2 to 6 times more at the convention level, needs 67 to 135 hours of migration work, and replaces tooling with proof on Railway before any real player traffic exists.
- **Use GCP for Production only and keep Railway for Development and Staging.** It was not chosen, because environments on two hosts would split the delivery, promotion, and recovery paths. Staging would stop proving Production behavior.
- **Study another host.** It was not chosen. The evidence favors one of the two tested hosts, and #344 excludes broad research on other providers.

## Consequences and risks

- Railway has no PITR, no documented database failover, and no stated SLA. Before Production, TailTag needs a recovery plan for these gaps. One option is Railway Pro backups with a tested restore drill.
- The readiness check, build argument, and scripts keep Railway-specific names. A later move costs the work listed in the comparison.
- The cost estimates rest on assumed player numbers. Real numbers can change the cost gap.
- The GCP test project is deleted after review. A later evaluation needs a new project, and the runbook in `docs/development/gcp-hosting-test.md` describes the setup.

## Open questions

The comparison lists the [open questions](../specs/2026-10-22-gcp-hosting-comparison.md#open-questions) in full. The ones that affect this decision:

- Which Railway plan includes backups, and what they cost.
- How TailTag covers PITR and database failover on Railway before Production.
- Real beta and convention player numbers.
- PostgreSQL 18 on Cloud SQL, if GCP comes back into scope.

## Validation and rollback

The comparison records each test result, price source, and assumption. If this proposal is rejected, a new ADR records the alternative. If a trigger occurs, a new evaluation updates the comparison and a new ADR supersedes this one.
