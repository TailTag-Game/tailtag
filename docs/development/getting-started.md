# Getting Started

This guide takes an accepted TailTag contributor from repository access to a
usable V0 backend development environment. For the detailed backend operating
reference—including configuration, database lifecycle, commands, and
troubleshooting—see the [API README](../../services/api/README.md).

For the Flutter app at `apps/mobile/`, see [Mobile contributor
environment](mobile.md): host-side `task mobile-setup`, `task mobile-check`,
`task mobile-doctor`, and `task mobile-run DEVICE=<id>`, plus configuration and
Local/Railway Development connectivity. The backend flow below is separate and
runs in the devcontainer.

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

On the host, doctor checks the repository, Docker, Compose, and an optionally
detectable Dev Container CLI. It does not require PostgreSQL or a project
environment. It is a Python script: `./scripts/doctor.sh` (macOS and Linux)
runs it with `uv` when installed, else `python3` 3.9 or newer, and otherwise
prints an install hint. If go-task and `uv` are installed, `task doctor` runs
the same checks on any host, including native Windows. `FAIL` identifies a
required condition that prevents the intended workflow; `WARN` is advisory.
Doctor diagnoses the environment only—it does not install dependencies, start
services, or repair configuration.

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
task doctor
```

Then use the canonical repository-root commands to prepare and verify the API:

```bash
task api-migrate
task api-run
```

Leave `task api-run` running. In another devcontainer terminal, verify the
running service:

```bash
task api-smoke
```

During development, run:

```bash
task api-test
```

Before opening or updating a pull request, run:

```bash
task api-check
```

Migrations are always explicit; neither opening the devcontainer nor running
`task doctor` applies them. The [Devcontainer](../../services/api/README.md#recommended-devcontainer-workflow),
[HTTP surfaces](../../services/api/README.md#http-surfaces), and [canonical
commands](../../services/api/README.md#canonical-backend-commands) sections
explain the expected outcomes and operating details.

## Secondary supported path: native Django with Compose PostgreSQL

The supported native alternative is deliberately narrow: host Python 3.13,
`uv`, and [go-task](https://taskfile.dev), plus Docker with the Compose plugin. PostgreSQL 17 is supplied by this
repository's Compose `db` service; Django runs on the host and consumes
`services/api/.env`.

Start the database service, then use the same root `task api-*` commands shown
above:

```bash
docker compose -f services/api/compose.yaml up -d db
task api-setup
task api-migrate
task api-run
```

This is not support for host-installed PostgreSQL, SQLite, other Python
versions, or arbitrary environment managers. See [Supported native
workflow](../../services/api/README.md#supported-native-workflow) for the
configuration and lifecycle details.

### Native Windows

The same native path works from PowerShell on Windows, with no Git Bash or
other POSIX shell. Install `uv`, go-task 3.53.1, and Docker Desktop, then run
the same commands from the repository root:

```powershell
docker compose -f services/api/compose.yaml up -d db
task api-setup
task api-check
```

The local API commands (`api-migrate`, `api-migrations`, `api-run`,
`api-shell`, and `api-smoke`) work the same way, as do the offline simulator
commands: `sim-setup`, `sim-check`, `sim-report-validate`, and
`sim-report-trend`. `task doctor` and the mobile commands (`mobile-setup`,
`mobile-check`, and `mobile-doctor`) also run natively; the mobile commands
need FVM and the pinned Flutter SDK (see [Mobile contributor
environment](mobile.md)), and iOS targets still need macOS with Xcode. CI runs
`mobile-setup`, `mobile-check`, and `mobile-doctor` natively on Windows on every
pull request, with no device attached. `task doctor`'s host checks and
`mobile-run` are covered by tests rather than run as commands there.
`sim-report-evaluate` and `sim-baseline-promote` also run natively;
CI exercises their code through the simulator tests rather than as commands,
because they need a real archived run report. `sim-smoke` should also work,
but it has not yet been run against a live API on Windows.

A few checks differ visibly on Windows:

- `api-gunicorn-check` prints a `SKIP` line, because Gunicorn runs only on
  Unix. CI checks the production Gunicorn configuration on Linux.
- `sim-host-bootstrap-check`, part of `sim-check`, prints a `SKIP` line,
  because `bootstrap.sh` provisions an Ubuntu host and its syntax check needs
  bash. CI checks it on Linux.
- `api-test` and the simulator tests do not collect the POSIX-only operator
  and host tooling modules (pty and termios sessions, SSH relays, owner-and-mode
  checks). The pytest header lists them. A few individual tests are skipped
  with a stated reason.

The Staging operator tasks and the simulator's Staging and host operations (`sim-pool-*`,
`sim-fixture-smoke`, `sim-journeys`, `sim-convention`, `sim-cleanup`,
`sim-retained`, `sim-host-*`, and `sim-image`) still need macOS or Linux.
Native Windows support for them is in progress (#315).

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
