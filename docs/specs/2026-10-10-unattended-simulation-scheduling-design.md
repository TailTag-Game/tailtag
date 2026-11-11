# Unattended convention-simulation scheduling — design for decision

Issue: [#230](https://github.com/TailTag-Game/tailtag/issues/230) (AC14).
Status: **decision input only. Nothing in this document is implemented.**
Today, simulation runs on the external host are attended:

- `--unattended` is refused;
- no host scheduler launches workloads;
- no Railway or Clerk credential is stored on the host.

The [operator guide](../operations/simulation-operations.md) describes the
attended cadence that #230 delivers. Enabling anything below needs maintainer
approval of a direction, then a separately approved follow-up issue.

## Why scheduling is not a small change

A run needs three kinds of authority. Today, only the maintainer's machine
holds two of them.

| Authority | Today | Where it lives |
| --- | --- | --- |
| Public gameplay over HTTPS | Container on the host | Short-lived Clerk session tokens minted during SETUP |
| Clerk Backend API (sign-in tickets for pool identities) | Hidden interactive prompt | Typed by the maintainer for each run; never stored |
| Privileged Staging fixtures, pool and inspection | Maintainer bridge over reverse SSH sockets | `railway ssh` into the pinned Staging instance, using the maintainer's personal Railway login |

These trust facts constrain every option:

- **The relays are bound to a personal account.** They refuse unless
  `railway whoami` returns the maintainer's personal account
  (`scripts/api_staging_reset_ssh.py:188-194`).
- **Narrow Railway tokens cannot drive `railway ssh`.** A Railway project
  token (`RAILWAY_TOKEN`) can be scoped to one environment, but SSH key
  management is not supported with project tokens
  ([Railway CLI ssh](https://docs.railway.com/cli/ssh)). `railway ssh` needs
  a workspace or account token. Such a token reaches every environment in the
  workspace, including Production. No token expiry is documented.
- **The Clerk secret cannot be narrowed.** Clerk instance secret keys have no
  documented scopes, expiry or IP allow-list. Several keys can exist at once
  for rotation ([Clerk key rotation](https://clerk.com/docs/guides/secure/rotate-api-keys)).
  The Staging Clerk instance is separate from Production's, so a leaked key
  can affect Staging users only.

## Options

### A. Host-resident credentials

**Design.** A workspace-scoped Railway token and the Staging Clerk secret are
stored on the host as root-owned systemd credentials (`LoadCredential=`). A
host-side bridge replaces the maintainer's bridge, and a systemd timer starts
a oneshot unit.

**Threat model.** The host is an internet-facing VPS. Its SSH access is
limited to approved addresses, but it runs a container that processes network
responses. Compromising the host or its owner account would expose:

- a Railway token that can read secrets, deploy, or open a shell in
  **Production**;
- the Staging Clerk secret.

The Production blast radius is the deciding concern. The relay identity check
would also have to change from a personal account to a token. That makes it a
security-assumption change to #217/#220-era tooling.

**Verdict.** Not recommended unless Railway gains SSH support for
environment-scoped tokens.

### B. Maintainer-armed bridge

**Design.** A launchd agent on the maintainer's Mac holds the reverse SSH
sockets open during a configured window. It supplies the Clerk secret from the
macOS Keychain instead of the hidden prompt. A host systemd timer starts runs
only while a fresh armed bridge is present. Railway credentials never leave
the maintainer's machine.

**Threat model.** Credentials stay where they are today. The new exposures
are:

- a long-lived Keychain item;
- a background agent that can trigger privileged Staging operations without a
  human at the keyboard.

Production is not reachable through this path, because the relays still pin
Staging.

**Costs.** Runs happen only while the Mac is awake, online and logged in. The
agent needs its own disable switch and audit trail. It is the most moving
parts of any option.

**Verdict.** This is the recommended direction if unattended runs are wanted
before a backend-side path exists.

### C. Backend-side privileged path

**Design.** Fixture, pool and inspection operations move behind a Staging-only
privileged API that uses its own narrowly scoped service credential, kept on
the host. `railway ssh` is no longer needed.

**Threat model.** The blast radius is bounded by the API: Staging only, and
only the closed operations. This option, however:

- introduces a new authorization boundary;
- adds API behavior;
- needs its own SECURITY design and review.

The parent epic excludes new API behavior that exists only for the simulator.

**Verdict.** This is the cleanest long-term option. It is out of #199 scope
and would need product approval.

## Mechanics common to any option

- **Overlap.** A systemd timer does not start a unit that is still active
  ([systemd.timer](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)),
  and the host runner already holds an exclusive whole-host lock. Use a
  oneshot service started by a timer with `Persistent=false`, so missed
  windows are skipped rather than replayed.
- **Holds.** An unresolved recovery hold refuses admission, as it does today.
  A scheduled run that finds a hold exits nonzero without starting work, and
  reports `held`. Holds are never resolved automatically.
- **Disable.** `systemctl disable --now` stops the timer. An owner-only
  sentinel file, `/srv/tailtag-simulator/schedule-disabled`, is checked before
  each scheduled prepare, so a timer that is enabled by mistake still refuses
  to start.
- **Notification.** Use Sentry Cron check-ins, which need only the DSN:
  - `in_progress` at start, and `ok` or `error` at the end;
  - missed or failed check-ins create an issue routed to the existing
    `Staging field beta: email observability owner` alert;
  - the Developer (free) plan includes one cron monitor
    ([Sentry Crons HTTP](https://docs.sentry.io/product/crons/getting-started/http/)).
  - The DSN is a low-sensitivity key, but it is still configuration and not
    for the repository.
- **Aborts.** The existing automatic guardrails stay the abort policy. No
  backend resource monitoring is added.
- **Release.** A schedule runs only the currently selected approved release.
  Updates still go through `install-runtime`.

## Recommended follow-up issue

Title: *Establish maintainer-armed unattended simulation scheduling.*

**Scope:**

- option B;
- the launchd armed bridge with a Keychain-sourced Clerk secret;
- a host systemd timer and oneshot unit, with sentinel disable;
- held-run refusal;
- a Sentry Cron monitor;
- an unattended variant of the nightly cadence.

**Non-goals:** host-resident Railway credentials, option C, and any change to
host ceilings.

**Assurance:** SECURITY review of the armed-bridge trust boundary.

The maintainer decides whether to open this issue. Until then, the
[attended cadence](../operations/simulation-operations.md) is the operating
model, and #199's host-scheduling criterion is met only in its attended form.

Update (#316): attended runs can also run from the host in a
[host operator session](../operations/simulation-host.md#host-operator-session).
A Railway login and an SSH key then exist on the host for the length of one
session only. Unattended scheduling stays deferred. Before Production shares
the Railway workspace, the workload container must run as a separate Linux
user.
