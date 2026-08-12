# Use a modular monolith for V0

**Status:** accepted

## Context and constraints

V0 has a small team, evolving requirements, and no demonstrated need for independently deployed services. The architecture should keep domain ownership and operational work understandable.

## Decision

Use a modular monolith backend in the monorepo for V0. Explicitly reject premature microservices; create separate services only after an approved requirement demonstrates a real boundary in ownership, scaling, deployment, or reliability.

## Alternatives considered

Premature microservices, a loosely structured single application, or multiple deployable backends before domain boundaries are understood.

## Consequences and risks

The monolith simplifies local development, transactions, deployment, and contribution. It requires disciplined module boundaries and may need later extraction if scale or ownership makes that worthwhile.

## Validation and future migration

Phase 0 validates module boundaries through the promoted `services/api` foundation and behavior-level tests. A future extraction should preserve contracts, data ownership, observability, and a reversible migration path.
