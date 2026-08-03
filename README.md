# TailTag

TailTag is a social convention game where attendees discover and catch participating fursuit characters.

This repository contains the community-led rebuild of the TailTag platform, including the player application, backend services, administrative tools, shared packages, database changes, infrastructure configuration, and automated tests.

## Project status

TailTag is currently in its foundational rebuild phase.

The contributor team is establishing:

* The product direction and V1 scope
* Technical architecture
* Development and review workflows
* Contributor onboarding
* The initial application structure
* Testing and deployment foundations

The repository may change significantly while these decisions are being made.

## Project principles

The rebuild is guided by several principles:

* Keep TailTag focused on its core identity as a convention game.
* Favor simple architecture that new contributors can understand.
* Build security, privacy, and operational reliability into the foundation.
* Document important product and technical decisions.
* Make contribution expectations explicit.
* Expand complexity only when demonstrated needs justify it.

## Repository structure

The final monorepo structure has not yet been established.

Likely top-level areas include:

```text
apps/             Deployable user and administrative applications
services/         Backend services and APIs
packages/         Shared libraries, types, validation, and configuration
database/         Schema, migrations, seeds, and database tooling
infrastructure/   Deployment and infrastructure configuration
docs/             Architecture and development documentation
scripts/          Repository automation and developer utilities
```

Directories will be added only after the relevant architecture decisions are approved.

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

## Security

Do not disclose vulnerabilities through public issues, pull requests, Discord channels, or other public project spaces.

Follow the organization’s [Security Policy](https://github.com/TailTag-Game/.github/blob/main/SECURITY.md).

## Community standards

Participation in TailTag spaces is governed by the organization’s [Code of Conduct](https://github.com/TailTag-Game/.github/blob/main/CODE_OF_CONDUCT.md).

## License

TailTag is licensed under the [Apache License 2.0](LICENSE).

The TailTag name, logos, branding, artwork, and other non-code assets are not necessarily covered by the software license unless explicitly stated.
