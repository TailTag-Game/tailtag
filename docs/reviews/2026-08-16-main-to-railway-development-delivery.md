# Main-to-Railway development delivery review

Date: 2026-08-16

Issue: [#78](https://github.com/TailTag-Game/tailtag/issues/78)

## Scope

This record verifies the live controls that establish the normal contributor
delivery path for the shared Railway development API. It records configuration
and existing metadata correlation; #80 remains responsible for the final
controlled pull request through post-deploy smoke exercise.

No Railway variables, credentials, database contents, or raw secret-bearing
command output were recorded.

## GitHub protected-main gate

The active repository ruleset is Protect main, enforced for the default branch.
Its pre-existing controls remain:

- pull requests required;
- one approving review required;
- review conversations must be resolved;
- squash is the only allowed merge method;
- deletion and non-fast-forward updates are blocked.

On 2026-08-16 the ruleset received one additional rule:

~~~text
required status check: API foundation checks
strict required-status-check policy: enabled
~~~

The stable check name is unchanged. The API workflow supplies it on every pull
request: backend-relevant changes run the canonical make api-check contract,
while irrelevant changes complete the same job through its explicit successful
skip path. The workflow also now runs for pushes to main, using that same job
and command.

The repository owner retains the existing pull_request ruleset bypass. It is an
exceptional, auditable administrative/recovery override. It was retained by
explicit #78 policy and is not part of routine contributor delivery or #78/#80
validation.

## Railway development API controls

The live TailTag / development / api service was re-read after configuration:

| Setting | Verified value |
| --- | --- |
| GitHub source | TailTag-Game/tailtag |
| Trigger branch | main |
| Normal autodeploy | enabled |
| Wait for CI / check suites | enabled |
| Runtime watch paths | services/api/** |
| Root directory | /services/api |
| Pre-deploy migration | python manage.py migrate --settings=config.settings.production --noinput |
| Railway health check | /health/ready |

Before #78, the trigger had checkSuites: false and no watch paths. #78 changed
only the trigger's checkSuites flag and the API service's watchPatterns. The
Railway API re-read confirms the source repository and branch, enabled
autodeploy, migration command, and health check remain intact.

Railway documents the intended behavior: a runtime-relevant main candidate is
WAITING while GitHub workflows run; a failed workflow makes it SKIPPED;
successful workflows permit it to continue. The watch path intentionally
excludes CI-only, smoke-only, documentation, and frontend changes from API
delivery unless a later approved runtime build configuration adds a directly
consumed path.

## Verification lapse and remediation

Configuration inspection is not sufficient evidence for Wait for CI. The
first post-configuration merge, `4022f2635ce1f11f0f26493ea181cb694e5556f2`,
showed why:

| Evidence | Observed UTC time / state |
| --- | --- |
| Railway deployment `c3fe2cb6-d818-4a18-9445-c1f210481506` | `SUCCESS` at 20:04:37, duration one second |
| GitHub `API foundation checks` push job | started at 20:04:40; completed successfully at 20:05:18 |
| Railway GitHub check suite | created queued at 20:04:37 and remained queued when inspected |

The candidate therefore completed before the applicable push validation. This
does not prove the required post-merge gate and must not be cited as normal-path
evidence for either #78 or #80. The pull request also had no recorded human
approval, so it did not exercise the protected normal contributor path.

On 2026-08-16 the GitHub deployment trigger was refreshed using the same
repository, `main` branch, `/services/api` root directory, and
`checkSuites: true` setting. The refreshed trigger ID is
`4413b1bb-104e-4f50-bdcf-eb1723c570a1`. Railway source, watch path,
pre-deploy migration, and readiness configuration were re-read afterward.

Before declaring the gate effective, the next controlled normal reviewed PR
must collect the following ordered evidence for a successful candidate:

~~~text
GitHub approval and required PR check
-> squash merge SHA
-> Railway candidate SHA equals squash merge SHA; status WAITING
-> same-SHA push API foundation checks concludes SUCCESS
-> Railway SUCCESS
-> same-SHA successful deployment_status event for TailTag / development from railway-app[bot]
-> successful smoke workflow run triggered by that qualifying deployment_status event
~~~

A deliberate post-merge CI failure must instead produce Railway `SKIPPED`; no
deployment promotion, successful deployment-status event, or smoke result is
expected for that path.

The validating change is limited to the production-image label
`org.tailtag.delivery-probe=wait-for-ci-trigger-refresh-2026-08-16`. It
changes image metadata and exercises the API Docker build/watch path without
changing Django runtime behavior or adding an application version endpoint.

If Railway creates a candidate before the same-SHA push check concludes
success, it must remain `WAITING`. If it enters deployment or promotion before
that conclusion, including after the check starts but before it completes,
leave #78 open and escalate the captured SHA, Railway deployment ID, trigger
ID, and timestamps to Railway support rather than treating `checkSuites: true`
as an enforceable control.

## Existing revision-correlation evidence

The currently active Railway deployment provides a verified metadata chain for
the existing #77 post-deploy integration:

| Evidence source | Value |
| --- | --- |
| Merged main revision | a39dd0ae040bbc2d65fad073b32be02e3e0973fe |
| Railway active deployment metadata | same commit SHA; source branch main |
| Railway-created GitHub deployment | environment TailTag / development; same SHA/ref |
| Railway GitHub deployment status | success |
| #77 post-deploy verifier | [run 31897797066](https://github.com/TailTag-Game/tailtag/actions/runs/31897797066), successful; check runs use the same head SHA |

This shows the infrastructure metadata and deployment-status verifier agree on
the deployed revision. The HTTP smoke result proves the stable development
endpoint met its contract after the successful deployment; it does not
cryptographically prove each response was served by that revision.

The cited deployment predates the #78 Wait for CI setting and therefore does
not prove the new post-merge waiting/skipped behavior. It is retained as
revision-attribution evidence only.

## Remaining #80 validation

The final controlled exercise must use the normal protected path without the
owner bypass and collect:

~~~text
PR -> required API foundation checks -> approval -> squash merge
-> main push API foundation checks -> Railway WAITING
-> successful deployment and controlled migration -> readiness
-> deployment_status SHA/ref -> successful HTTP smoke
~~~

It should also capture a backend-irrelevant normal merge with no Railway API
deployment, where practical. If a subsequent deployment supersedes the
candidate before smoke requests complete, record that limitation rather than
adding application-level versioning.
