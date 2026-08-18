# TailTag

TailTag is a social convention game where attendees discover and catch participating fursuit characters.

This repository contains the community-led rebuild of the TailTag platform, including the player application, backend services, administrative tools, shared packages, database changes, infrastructure configuration, and automated tests.

## Project status

TailTag is in its foundational community-rebuild phase. V0 is a controlled convention beta, and the accepted backend direction is Python, Django, Django REST Framework, PostgreSQL, Clerk authentication, a modular monolith, and Railway hosting.

The initial backend foundation is present. Client applications, TailTag-specific administrative tooling, and other V0/V1 details may continue to evolve as their issues and specifications are approved.

## Project principles

The rebuild is guided by several principles:

* Keep TailTag focused on its core identity as a convention game.
* Favor simple architecture that new contributors can understand.
* Build security, privacy, and operational reliability into the foundation.
* Document important product and technical decisions.
* Make contribution expectations explicit.
* Expand complexity only when demonstrated needs justify it.

## Repository structure

The repository is a monorepo. Current top-level areas are:

```text
docs/             Architecture and development documentation
scripts/          Repository automation and developer utilities
services/api/     TailTag V0 Django API foundation
```

Additional application and shared-package directories will be added as their scope and implementation are approved; this list describes only directories that currently exist.

## Work tracking

Actionable work is tracked through:

* [GitHub Issues](https://github.com/TailTag-Game/tailtag/issues)
* [TailTag Rebuild Project](https://github.com/orgs/TailTag-Game/projects)

Issues describe the work. Project fields describe its planning and execution state.

Discord is used for active contributor communication. Notion is used for durable product, process, and organizational documentation.

## Contributing

Contributor onboarding is currently managed in cohorts.

Accepted contributors should read [CONTRIBUTING.md](CONTRIBUTING.md) before claiming work or opening a pull request.

The normal contribution flow is:

1. Find or create an approved issue.
2. Confirm that the issue is ready to begin.
3. Create a focused branch.
4. Implement and validate the change.
5. Open a pull request linked to the issue.
6. Address automated checks and review feedback.
7. Squash-merge after all requirements pass.

Unsolicited implementation of large features may be declined when the underlying product or architecture decision has not been approved.

## Getting started

Accepted contributors should begin with the [Getting Started guide](docs/development/getting-started.md).

The guide covers repository access, cloning, Git configuration, environment verification, and the standard issue-to-pull-request workflow.

## Authenticated Development API smoke

`make api-auth-smoke` is the sole manual, interactive check of Clerk
Development authentication against `GET /api/me/`; it is excluded from normal
tests, CI, and production operations. A maintainer must first create and retain
one dedicated user in the Clerk Development instance, copy its opaque user ID
(not an email or other mutable profile attribute), and retain the corresponding
TailTag user created by the API. Configure only the non-secret
`CLERK_SMOKE_USER_ID`; the Clerk Development secret is requested invisibly on
every invocation and is never stored in configuration.

The helper always uses `http://localhost:3000` as a fixed synthetic tooling
origin. Add that exact origin to `CLERK_AUTHORIZED_PARTIES` in both local and
Railway development API settings. It does not require a frontend to be running
on port 3000, and production configuration must not gain that allowance.

Local development:

```bash
CLERK_SMOKE_USER_ID=<opaque-development-user-id> make api-auth-smoke
```

Railway development (the URL must be the exact approved API root):

```bash
API_BASE_URL=https://<exact-development-api-host> \
TAILTAG_DEVELOPMENT_API_BASE_URL=https://<exact-development-api-host> \
CLERK_SMOKE_USER_ID=<opaque-development-user-id> \
make api-auth-smoke
```

The dedicated Clerk and TailTag users are persistent test state. Each run uses
only ephemeral sign-in ticket, session, and bearer-token state, cleans up its
supported authentication resources, and reports only sanitized failure stages.
See the [API operating reference](services/api/README.md#authenticated-development-api-smoke)
for setup, target, and cleanup details. The production TailTag API verifier
itself requires no Clerk secret.

## Security

Do not disclose vulnerabilities through public issues, pull requests, Discord channels, or other public project spaces.

Follow the organization’s [Security Policy](https://github.com/TailTag-Game/.github/blob/main/SECURITY.md).

## Community standards

Participation in TailTag spaces is governed by the organization’s [Code of Conduct](https://github.com/TailTag-Game/.github/blob/main/CODE_OF_CONDUCT.md).

## License

TailTag is licensed under the [Apache License 2.0](LICENSE).

The TailTag name, logos, branding, artwork, and other non-code assets are not necessarily covered by the software license unless explicitly stated.
