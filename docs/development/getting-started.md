# Getting Started

This guide verifies that you can access, clone, and contribute to the TailTag repository.

The Django/DRF backend is now available as the minimal `services/api` V0 foundation. This guide covers the repository workflow that applies today; the devcontainer and canonical contributor environment are still being established in subsequent Phase 0 work.

## Prerequisites

Install:

- Git
- A GitHub account with secure two-factor authentication
- GitHub CLI, recommended
- An editor with Git support

The active service README is [`services/api/README.md`](../../services/api/README.md). Historical Django POC material remains evaluation evidence and is not a V0 setup contract.

## Clone the repository

Using SSH:

```bash
git clone git@github.com:TailTag-Game/tailtag.git
cd tailtag
```

Using HTTPS:

```bash
git clone https://github.com/TailTag-Game/tailtag.git
cd tailtag
```

## Verify the remote

```bash
git remote -v
```

The remote should point to:

```text
TailTag-Game/tailtag
```

## Run the repository checks

```bash
./scripts/doctor.sh
```

## Configure Git

Set the name and email that should appear on your commits:

```bash
git config user.name "Your Name"
git config user.email "your-github-email@example.com"
```

You may use GitHub's private no-reply email if you do not want your personal email address included in commits.

## Contribution workflow

1. Select an issue with Project status `Ready`.
2. Assign yourself to the issue.
3. Move it to `In progress`.
4. Create a branch from the latest `main`.
5. Make and validate the change.
6. Open a draft pull request.
7. Link the issue using `Closes #123`.
8. Mark the pull request ready for review.
9. Address checks and review feedback.
10. Squash-merge after all requirements pass.

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the complete workflow.

## Getting help

Include the following when requesting help:

- The issue or pull-request link
- Your operating system
- The command you ran
- The complete sanitized error
- What you already attempted

Never publish passwords, tokens, private keys, `.env` contents, or user data.
