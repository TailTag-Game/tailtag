# Architecture

Status: foundational; no application runtime stack has been approved.

## Current repository

The repository currently contains contributor documentation, GitHub policy files, and shell-based repository checks. It does not yet contain application code, a package manifest, a database schema, infrastructure configuration, or a selected monorepo tool.

That absence is intentional. The candidate top-level areas in `README.md` are a direction for discussion, not an approved architecture.

## Architectural constraints

- Keep the system understandable to a mixed-experience contributor community.
- Prefer the simplest deployable shape that satisfies approved product requirements.
- Treat security, privacy, accessibility, and operational recovery as design inputs.
- Keep domain language in `CONTEXT.md`; keep hard-to-reverse decisions in `docs/adrs/`.
- Avoid framework, database, hosting, and monorepo commitments until the relevant requirements and alternatives are documented.
- Design stable interfaces around product behavior. Add boundaries only where behavior, ownership, deployment, or data responsibility genuinely differs.

## Candidate areas, not decisions

The README anticipates player and administrative applications, backend capabilities, shared packages, database changes, infrastructure, and tests. Before creating those areas, an approved spec and any necessary ADR should establish:

1. the user-visible behavior and trust boundaries;
2. data ownership, retention, and privacy requirements;
3. deployment and operational constraints;
4. interface and failure behavior;
5. verification strategy and rollback path.

## Verification architecture

`scripts/doctor.sh` is the current repository check. It validates the local Git/GitHub setup, repository location, remote, branch, and working-tree state. As application code and a runtime stack are added, evolve the doctor script and CI together to cover the new checks.

## Decision log

No technical ADRs have been accepted yet. See `docs/adrs/README.md` for the decision threshold and format.
