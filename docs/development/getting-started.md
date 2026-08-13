# Getting Started

This guide takes an accepted TailTag contributor from repository access to a
usable V0 backend development environment. For the detailed backend operating
reference—including configuration, database lifecycle, commands, and
troubleshooting—see the [API README](../../services/api/README.md).

The Django/DRF service at `services/api` is a minimal V0 foundation. Historical
Django POC documents are evaluation evidence, not current setup instructions or
the V0 product/API contract.

## Prerequisites

All contributors need:

- Git
- a GitHub account with secure two-factor authentication
- an editor with Git support

For the **recommended devcontainer workflow**, also install Docker Desktop (or
another Docker Engine with the Compose plugin) and use a devcontainer-capable
editor. Host Python, `uv`, and PostgreSQL are not required for this workflow.

GitHub CLI is recommended for contribution work, but it is not required to open
the devcontainer.

## Clone and diagnose the repository

Clone with SSH:

```bash
git clone git@github.com:TailTag-Game/tailtag.git
cd tailtag
```

Or clone with HTTPS:

```bash
git clone https://github.com/TailTag-Game/tailtag.git
cd tailtag
```

Run the host diagnostic before opening the backend environment:

```bash
./scripts/doctor.sh
```

On the host, `doctor.sh` checks the repository, Docker, Compose, and an
optionally detectable Dev Container CLI. It does not require host Python, `uv`,
or PostgreSQL. `FAIL` identifies a required condition that prevents the intended
workflow; `WARN` is advisory. The script diagnoses the environment only—it does
not install dependencies, start services, or repair configuration.

## Configure the backend environment

Create your local-only backend environment file before starting either supported
workflow:

```bash
cp services/api/.env.example services/api/.env
```

The copied file contains safe local defaults. It is ignored by Git: never
commit it or share its contents. See [Local configuration in the API
README](../../services/api/README.md#local-configuration) for the contract and
safe handling of environment values.

## Recommended: open the devcontainer

Open the repository root in your devcontainer-capable editor and choose its
**Reopen in Container** action. The devcontainer provides Python 3.13, `uv`,
locked dependencies, and the Compose-backed PostgreSQL 17 service. Its
post-create setup synchronizes dependencies but does not apply migrations.

Inside the devcontainer, confirm the backend environment:

```bash
./scripts/doctor.sh
```

Then use the canonical repository-root commands to prepare and verify the API:

```bash
make api-migrate
make api-run
```

Leave `make api-run` running. In another devcontainer terminal, verify the
running service:

```bash
make api-smoke
```

During development, run:

```bash
make api-test
```

Before opening or updating a pull request, run:

```bash
make api-check
```

Migrations are always explicit; neither opening the devcontainer nor running
`doctor.sh` applies them. The [Devcontainer](../../services/api/README.md#recommended-devcontainer-workflow),
[HTTP surfaces](../../services/api/README.md#http-surfaces), and [canonical
commands](../../services/api/README.md#canonical-backend-commands) sections
explain the expected outcomes and operating details.

## Secondary supported path: native Django with Compose PostgreSQL

The supported native alternative is deliberately narrow: host Python 3.13 and
`uv`, plus Docker with the Compose plugin. PostgreSQL 17 is supplied by this
repository's Compose `db` service; Django runs on the host and consumes
`services/api/.env`.

Start the database service, then use the same root `make api-*` commands shown
above:

```bash
docker compose -f services/api/compose.yaml up -d db
make api-setup
make api-migrate
make api-run
```

This is not support for host-installed PostgreSQL, SQLite, other Python
versions, or arbitrary environment managers. See [Supported native
workflow](../../services/api/README.md#supported-native-workflow) for the
configuration and lifecycle details.

## Contribute changes

Configure the name and email recorded in your commits if needed:

```bash
git config user.name "Your Name"
git config user.email "your-github-email@example.com"
```

Then follow the repository workflow:

1. Select an approved issue with Project status `Ready` and coordinate ownership.
2. Create a focused branch from the latest `main`.
3. Make and validate the change with the checks appropriate to its scope.
4. Open a draft pull request and link the issue with `Closes #123`.
5. Address checks and review feedback before marking the pull request ready.

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the complete contribution
policy.

## Getting help

When requesting help, include the issue or pull-request link, operating system,
command, complete sanitized error, and what you already attempted. Never publish
passwords, tokens, private keys, `.env` contents, or user data.

These instructions describe the implemented Phase 0 workflow. Independent
clean-environment onboarding validation is tracked separately and may lead to
documentation corrections.
