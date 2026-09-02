# Product and technical specs

Use a spec for ambiguous, cross-cutting, risky, or multi-session work. A spec should state the problem, goals, non-goals, behavior, constraints, acceptance criteria, risks, and unresolved decisions.

Small, reversible changes with clear acceptance criteria do not need a spec. Specs describe what must be true; implementation sequencing belongs in `docs/plans/`.

## Current V0 specifications

- [V0 persistent fursuit identity and Convention-scoped catch credentials](2026-09-01-v0-fursuit-catch-credentials.md)
- [V0 fursuit catch sessions](2026-09-01-v0-fursuit-catch-sessions.md)
- [V0 per-Convention fursuit activation](2026-08-31-v0-fursuit-activation.md)
- [V0 fursuit domain and owner-scoped APIs](2026-08-24-v0-fursuit-domain.md)
- [V0 player onboarding and profile](2026-08-24-v0-player-profile.md)
- [V0 media storage and image-upload handling](2026-08-19-v0-media-storage.md)
- [Deterministic Semgrep validation](2026-08-19-semgrep-validation.md)
- [Deterministic Semgrep validation — final-review amendment](2026-08-19-semgrep-validation-final-review-amendment.md)
- [V0 authenticated current-user API](2026-08-18-v0-current-user-api.md)
- [Authentication test and backend developer tooling](2026-08-18-authentication-test-and-backend-developer-tooling.md)
- [Clerk identity resolution](2026-08-17-clerk-identity-resolution.md)
- [TailTag application-user identity](2026-08-17-application-user-identity.md)
- [Main-to-Railway development delivery](2026-08-16-main-to-railway-development-delivery.md)
- [Post-deploy HTTP smoke verification](2026-08-15-post-deploy-http-smoke-verification.md)
- [Replace mypy with Pyright](2026-08-13-pyright-type-checker-migration.md)

## Historical POC specifications

These documents record evaluation work and are not current V0 product
requirements:

- [Django API POC authentication and fursuit management](2026-08-04-django-api-auth-and-fursuits.md)
- [Django API POC scaffold](2026-08-04-django-api-poc-scaffold.md)
