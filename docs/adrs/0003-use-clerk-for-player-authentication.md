# Use Clerk for player authentication

**Status:** accepted

## Context and constraints

Player authentication is a security-sensitive boundary. TailTag should avoid owning routine credential storage and authentication lifecycle concerns while retaining stable domain relationships inside its backend.

## Decision

Use Clerk as the authentication authority for players. TailTag will maintain its own internal application user identity, separate from Clerk, and use that identity for domain relationships and server-side authorization.

## Alternatives considered

Build and operate authentication in Django, use another hosted identity provider, or use Clerk identifiers directly as all application foreign keys.

## Consequences and risks

Clerk reduces credential-management scope, but creates an integration and account-linking boundary. TailTag must define subject verification, provisioning/linking, lifecycle changes, failure behavior, and privacy rules before implementation.

## Validation and rollback

Phase 0/1 must validate the authentication boundary with explicit positive, negative, and account-linking tests. A provider change would require a migration of external identities and a reviewed user-identity compatibility plan.
