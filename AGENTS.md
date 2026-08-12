# TailTag agent guidance

TailTag is a social convention game where attendees discover and catch participating fursuit characters. This repository is the community-led rebuild, currently preparing the controlled-convention V0 foundation.

## Source of truth

Use this hierarchy when sources disagree:

1. The current approved issue or spec for the task
2. Current approved architecture and product documentation
3. `CONTRIBUTING.md` and repository conventions
4. Current production-intent code
5. Historical POC, prototype, evaluation, and archive material

Inspect the relevant issue and spec before editing. Do not invent product or architecture decisions. Historical POC documents are evidence, not current V0 requirements.

## Accepted V0 backend direction

- Python, Django, and Django REST Framework
- PostgreSQL as the primary application database
- Clerk as the player authentication authority
- A TailTag-owned internal application user identity, separate from Clerk
- A modular monolith backend in the monorepo
- Railway as the V0 backend hosting platform
- Backend Phase 0 promotes and resets the POC into a clean `services/api` foundation and establishes the local contributor environment.
- Backend Phase 1 establishes CI/CD and the shared Railway development environment.

The completed Django POC remains historical evaluation evidence. Its POC-only routes, session/CSRF behavior, fursuit fields, deletion behavior, and other experimental choices are not authoritative V0 requirements.

## Contribution expectations

Work on a focused branch and follow `CONTRIBUTING.md`. Keep business rules server-controlled, avoid premature microservices and unnecessary abstractions, and do not broaden an issue’s scope. Preserve unrelated work. Do not modify application behavior when the task is documentation-only.

Run the narrowest relevant checks while working and the repository’s required validation before completion. For documentation changes, run `./scripts/doctor.sh` and `git diff --check`, and report any unavailable checks. Never expose secrets or personal data.
