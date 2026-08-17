# Use Railway for V0 hosting

**Status:** accepted

## Context and constraints

V0 needs a straightforward hosted environment for the backend and PostgreSQL, suitable for a small contributor team and early operational learning.

## Decision

Use Railway for V0 backend hosting, including the shared development environment established in Phase 1. This is a V0 platform choice, not an irreversible lifetime commitment.

## Alternatives considered

Other managed application platforms, self-managed infrastructure, or postponing the hosting decision until after backend implementation.

## Consequences and risks

Railway accelerates initial deployment and environment setup, but introduces platform-specific configuration, cost, availability, and portability considerations.

## Validation and rollback

Phase 1 will validate deployment, secrets/configuration boundaries, migrations, health checks, logs, and recovery procedures. Moving platforms later requires an infrastructure and data migration plan with a tested rollback path.
