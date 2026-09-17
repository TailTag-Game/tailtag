# Backend build and deployment identity

Issue: #201. Parent: #197. Deployment workflow: #202.

## Status and phase ledger

Scope: STANDARD COMPACT. Assurance: SECURITY and TEST ADEQUACY.
The user-approved identity contract and implementation design are frozen below.
The focused Staging experiment passed. Independent acceptance tests are frozen
and approved; production implementation and local verification are complete.
Final deployed acceptance passed against the exact implementation deployment.

Completed: repository reconnaissance, upstream documentation research, live
Railway schema and target inspection, authorized probe publication, exact-SHA
Staging experiment, design freeze, environment baseline (`make api-check`:
1,500 tests passed), independent test authorship and test-adequacy approval.
Completed additionally: production implementation, parent deterministic gate
(`make api-check`: 1,529 tests passed), final image artifact readback and
permission checks, independent Compact review and scoped re-review. The MEDIUM
hard-coded-fixture test gap was resolved with a second valid source/deployment
pair and exact query-variable assertions (AC-1/2/6/7); no findings remain open.
Completed additionally: authorized implementation publication, exact-SHA Staging
deployment, actual-instance identity readback, repository-owned exact-D join,
Finn-verified GitHub commit resolution, and existing HTTP smoke.
Completed additionally: final evidence documentation, `./scripts/doctor.sh`
and `git diff --check`. Required documentation checks passed; the optional
Dev Container CLI remains unavailable.
Current: final evidence handoff. No merge or Production action is authorized.

## Acceptance Contract

1. Source identity is the full immutable Git SHA of the source built into the
   backend image. A branch, label, timestamp, runtime variable, local checkout,
   or current repository head must never replace it.
2. Declare `ARG RAILWAY_GIT_COMMIT_SHA` in the production Docker stage and persist
   only that validated SHA in image-local metadata. Runtime application code
   consumes this artifact as its single canonical source identity.
3. Read `RAILWAY_DEPLOYMENT_ID` and `RAILWAY_ENVIRONMENT_NAME` at runtime. Never
   bake deployment identity into the image. Canonical rehearsal targets Staging.
4. `deployment_timestamp` is the exact deployment record's `createdAt`, obtained
   from Railway's control plane using the runtime deployment ID. No build,
   startup, restart, query-time, or activation timestamp may substitute for it.
5. Expose identity through a reusable backend component and an operator command,
   with no public API endpoint and no arbitrary configuration/environment dump.
6. Proof joins baked SHA S, runtime deployment D and environment `staging` to
   Railway record D with source S and timestamp T, and GitHub commit S in
   `TailTag-Game/tailtag`.
7. Always query captured D, never the latest deployment as a substitute.
   Superseding deployments do not invalidate historical evidence for D. A
   current-serving claim requires a separate active-deployments comparison.
8. Missing or malformed required Staging identity fails clearly. Safe output
   contains only explicitly allowlisted identity fields. Process clocks and
   restarts cannot generate or replace identity fields.
9. If the manual explicit-SHA deployment lacks a correct build-time Railway SHA,
   stop. Record a precise #202 dependency for explicit source-SHA injection;
   do not add a fallback or absorb the controlled deployment workflow.

## Research evidence

Installed Railway CLI: 5.57.2. The live schema inspected on 2026-09-16 exposes
`serviceInstanceDeployV2(serviceId, environmentId, commitSha): String!`, returning
a deployment ID; `Deployment.createdAt: DateTime!`; and
`ServiceInstance.activeDeployments`, explicitly describing running deployments.
The approved `TailTag` project has `staging` and `development` environments and
`api` and `Postgres` services. Only allowlisted operational fields were rendered;
no secret values were retained or reported.

Upstream references:

- [Docker build variables](https://docs.railway.com/builds/dockerfiles): declare
  variables with `ARG` in the stage that consumes them.
- [Explicit-commit deployment](https://github.com/railwayapp/docs/blob/main/content/docs/integrations/api/manage-services.md):
  the deployment API accepts an explicit commit and returns deployment identity.
- [Deployment lookup](https://github.com/railwayapp/docs/blob/main/content/docs/integrations/api/manage-deployments.md):
  query a deployment by ID, including `createdAt` and source metadata.
- [Git variables](https://github.com/railwayapp/docs/blob/main/content/docs/variables/reference.md):
  documents Git-triggered SHA injection, but does not independently prove the
  manual explicit-SHA Docker-build case.

## Focused experiment

The existing Dockerfile declares no Git SHA argument. An unchanged deployment
cannot prove build-time injection. Publish one temporary probe commit containing
only the following production-stage addition after its `FROM` instruction:

```dockerfile
ARG RAILWAY_GIT_COMMIT_SHA
RUN python -c 'import os,re; from pathlib import Path; s=os.environ.get("RAILWAY_GIT_COMMIT_SHA", ""); assert re.fullmatch("[0-9a-f]{40}", s), "missing or malformed Railway build SHA"; Path("/opt/tailtag-source-sha-probe").write_text(s + "\n")'
```

The probe is an experiment, not the final identity implementation. It persists
only a safe SHA and fails the build if injection is absent or malformed. Do not
add a configured SHA, runtime override, local Git lookup, or secret handling.

Before publishing, verify Git author/committer are exactly the approved Finn
identity, verify GitHub account `FinnThePanther`, and obtain push authorization.
Resolve the published probe SHA through that verified GitHub identity. Before
deployment, verify approved identity and exact Staging API target, disabled
autodeploy, connected repository, Dockerfile/root path, and no pending unrelated
configuration changes. Inspect current source metadata through a local allowlist;
do not print raw deployment metadata or variables.

Invoke `serviceInstanceDeployV2` once with explicit probe SHA and Staging/API
selectors. Capture returned D. Poll D specifically. Do not retry a failed
authenticated operation or switch identities. Once running, read the probe file
and only runtime deployment ID/environment through remote execution. Assert the
runtime D matches the mutation result; query D for source SHA and `createdAt`;
assert all source identities match. Run existing credential-free Staging HTTP
smoke. Record only allowlisted evidence. Do not claim #201 completion from this
probe. Remove probe code from the implementation diff; retaining the probe
deployment until replaced avoids adding a rollback experiment or #202 flow.

## Frozen implementation design

Use root-owned `/opt/tailtag/build-identity.json`, generated before switching to
the application user in the production Docker stage. The only stored field is
`source_sha`. Accept exactly 40 lowercase hexadecimal characters. An empty build
argument creates explicit null identity for existing local production-image
builds; a nonempty malformed argument fails the build. It never invents a SHA.
Development-stage image builds remain unchanged.

`services/api/config/build_identity.py` is the sole application identity source.
It reads the fixed artifact path and the two explicit runtime Railway values.
There is no runtime SHA fallback or production path override. Execute
`python -m config.build_identity` inside the selected running deployment instance
to emit JSON with exactly `source_sha`, `deployment_id`, and `environment`.
Missing local identity remains explicit null. In `staging`, missing/malformed
source SHA or deployment ID causes the operator command to fail with a sanitized
message and no successful tuple. Validate deployment IDs as UUIDs and environments
as bounded safe names. This does not introduce new startup or readiness gates.

A maintainer-side `scripts/api_deployment_identity.py` consumes the exact
three-field JSON through stdin and queries exact D through authenticated Railway
CLI/API. It targets the canonical Staging project and API service, validates the
input as Staging identity, and rejects extra input keys. The backend has no Railway credentials,
control-plane network dependency, or generated deployment timestamp. The joined
operator result adds `deployment_timestamp` from `createdAt` only after validating
record ID, target project/environment/service, and source equality using Railway
deployment metadata field `commitHash`. Its successful JSON output contains
exactly `source_sha`, `deployment_id`, `environment`, and `deployment_timestamp`.
Validate `createdAt` as a timezone-aware timestamp and preserve its original
value. Control-plane failure
produces a clear failure rather than a fabricated complete tuple. Omit the
optional release label initially; it adds no required evidence.

Alternative runtime-only SHA is rejected by the approved artifact-binding
contract. Embedding the full deployment tuple in the image is rejected because
deployment instances differ from source artifacts.

## Test Surface Contract

Approved parsing interfaces: backend `_load_identity(metadata_path: Path,
environment: Mapping[str, str])` returns a three-field dictionary of string/null
values; `get_identity()` binds the fixed artifact path and actual runtime
environment; `main()` renders safe JSON or a sanitized error and returns an
exit code. The operator script's `join_deployment(identity, record)` validates
and returns the four-field tuple; `main()` consumes stdin, invokes Railway once
for exact D, renders the tuple or sanitized failure, and returns an exit code.
Use existing subprocess mocking patterns; do not add test-only APIs.

Tests exercise the identity module through its intended package interface, using
temporary artifact files and controlled runtime mappings at the internal parsing
seam. The production entry point fixes the actual artifact path. Operator output
is tested as parsed JSON and checked against the exact key allowlist. Fake
Railway CLI responses exercise record joining, mismatched IDs/source/environment,
and missing timestamps without contacting Railway. Tests do not need a public
API, database, Railway credentials, new injection API, or new test infrastructure.

Required coverage: full SHA accepted; missing/malformed required Staging values
rejected; environment accurate; runtime deployment ID distinct from baked SHA;
runtime SHA cannot override artifact SHA; arbitrary environment keys never
appear in output; clock/process-start changes cannot alter identity; joining
queries exact D and rejects mismatches; timestamp equals record `createdAt`.

## Scope Guard and proof boundary

Security assumptions: immutable identity means image-local, root-owned metadata
that the ordinary application user cannot replace; it is not protection against
host/platform administrators or compromised build infrastructure. Source SHA is
public metadata, but arbitrary deployment `meta`, CLI stderr, configuration and
environment values are not approved output. Treat control-plane responses and
stdin as untrusted: validate structure, source, exact deployment, target and
timestamp before rendering allowlisted fields. Never invoke a shell with input
values. The backend performs no control-plane queries and receives no Railway
credentials. Operator credentials retain their existing Railway scope; no new
secret, credential storage, public route, or authentication mechanism is added.

Expected implementation surface: `services/api/Dockerfile`,
`services/api/config/build_identity.py`, `scripts/api_deployment_identity.py`,
`services/api/tests/test_build_identity.py`,
`services/api/tests/test_api_deployment_identity.py`, this specification,
`docs/development/staging.md`, and existing Makefile verification lists so the
new maintainer script participates in formatting/linting/type checking.
`services/api/pyproject.toml` owns the Pyright include list. Register the new
script in `scripts/backend_ci_relevance.py` and add its row to the existing
`services/api/tests/test_backend_ci_relevance.py` path matrix so script-only
changes receive the same authoritative CI gate. These are existing verification
registries for the approved script, not a new deployment workflow.
The shared exact-scan helper registry in `services/api/tests/semgrep_support.py`
must also include the new script; preserve its exact-scope assertions. The full
suite exposed this required registry update after initial implementation.

Use
`make api-check` (including existing Semgrep), focused pytest, existing Docker
production build checks, `./scripts/doctor.sh`, and `git diff --check`.
No dependencies, database
schema, public API, readiness behavior, logging implementation, Production,
promotion automation, or unrelated cleanup.

Deterministic tests prove repository-owned parsing, output, and joining logic.
The final live Staging proof must exercise the implemented baked artifact and
operator command, exact Railway deployment lookup, and GitHub commit resolution.
Railway's metadata is trusted platform evidence, not cryptographic image
attestation. A historical proof does not establish which deployment serves now.
The maintainer join script validates supplied identity against Railway; it does
not attest where stdin originated. Live acceptance must capture stdin from the
selected running instance's backend command, not manually invent the tuple.

## 2026-09-16 focused Staging experiment evidence

Authorized probe commit:
`c070f413eec1518459f1fef21b471642765a54e9`, resolved by GitHub in
`TailTag-Game/tailtag`. It was pushed to `docs/201-build-identity-design`; no
change was pushed to `main`. The exact-SHA manual API operation returned
deployment `93de11d6-714f-405a-b931-a9b567d5ec1e` with Staging autodeploy disabled
(no deployment triggers). Existing source/root remained the connected repository
and `/services/api`; no service configuration or secrets were changed.

The deployment reached `SUCCESS`. Remote execution against its explicitly
selected running instance read the image-local probe artifact and reported:

```json
{
  "source_sha": "c070f413eec1518459f1fef21b471642765a54e9",
  "deployment_id": "93de11d6-714f-405a-b931-a9b567d5ec1e",
  "environment": "staging"
}
```

Exact control-plane deployment lookup independently reported matching source
`commitHash`, deployment ID, and Staging/API/project ownership, and supplied
`createdAt = 2026-09-17T00:16:10.526Z`. That is deployment-record creation time,
not a lifecycle activation timestamp. Successful reading of the file created
only by the Docker probe establishes build-time ARG availability and equality
for this deployment mechanism, without relying on runtime SHA.

The temporary probe is removed from the local implementation/design diff after
the experiment. The separately authorized final implementation deployment
recorded below replaced the probe. This is feasibility evidence, not final
#201 acceptance: the reusable component, operator join script, deterministic
tests, and final implementation proof are established separately below. No
fallback or #202 SHA injection dependency was needed for the tested mechanism.

The existing credential-free HTTP smoke passed for `/health/live`,
`/health/ready`, `/api/schema/`, and `/api/docs/` with HTTP 200. This confirms
the shared endpoint's smoke contract after the probe deployment; it does not
bind individual HTTP responses to the deployment or assert ongoing serving
identity. Artifact identity evidence came from the explicitly selected instance.

## Implementation plan

Goal: implement the frozen identity primitive and exact-deployment lookup with
no new dependencies or behavior outside the operator surface.

- [x] Establish `make api-check` baseline with locked existing dependencies and
  existing local PostgreSQL. Preserve lockfiles and unrelated work.
- [x] Independent test author adds scoped tests against the parsing/CLI seams,
  maps cases to acceptance items, and proves expected preimplementation failure.
  Parent reviews adequacy including override, allowlist, exact-D and timestamp
  mutants before dispatching implementation.
- [x] Independent implementer adds the backend module and maintainer script.
  `get_identity()` fixes the artifact path; `main()` renders using `json.dumps`.
  Do not import Django. Query `deployment(id: $id)` via `railway api` with typed
  variables and `subprocess.run` without a shell. Capture both output streams,
  never emit raw CLI errors, validate input before invoking Railway, and fail
  on GraphQL errors or identity/target mismatch.
- [x] Add Docker `ARG`, validate nonempty SHA, and write root-owned one-field
  JSON (mode 0444) before `USER tailtag`. Missing local build SHA remains null.
  Add the script to existing Makefile and Pyright verification lists, including
  Semgrep targets. No dependency changes.
- [x] Document exact-instance lookup, stdin join, Finn-verified GitHub commit
  resolution, timestamp meaning, historical vs current-serving evidence, and
  limitations in the existing Staging runbook.
- [x] Run focused tests, `make api-check`, production Docker build and command
  readback with a valid SHA, and absent-SHA local build compatibility. Check
  ownership/mode and inability of the application user to alter the artifact.
- [x] Fresh Compact reviewer checks contract, code, security, test adequacy and
  scope. Resolve acceptance and BLOCKER/HIGH findings.
- [x] Prepare reviewed commit for separately authorized implementation push and
  final Staging deployment. Capture exact-instance output, join D, resolve S in
  GitHub, run existing HTTP smoke, and retain sanitized evidence.
- [x] Final authoritative verification and acceptance accounting. No merge or
  Production action.

## Local implementation verification

Fresh parent `make api-check` completed with 1,529 tests passed, Ruff format/lint,
strict Pyright, nine Semgrep rule fixtures, zero Semgrep findings, Django checks,
no migration drift, schema validation, and Gunicorn configuration validation.
Local checks used temporary host configuration against the existing contributor
PostgreSQL container; no repository environment file or lockfile was changed.
Existing missing-collected-staticfiles warnings remain unchanged from baseline.

Focused identity and CI classification tests passed 58 cases. Adding the new
operator script to the exact Semgrep test registry resolved the full-suite
registry failures while preserving all exact-scope assertions; all 144 affected
developer-command/Semgrep tests passed.

Production image builds passed with a valid fixture SHA and with no SHA for
local use; malformed nonempty SHA failed at artifact generation. Final-image
readback confirmed the baked SHA despite a conflicting runtime SHA. The image
ran as a non-root user, with root-owned directory 0755 and file 0444; attempted
write and unlink both raised permission errors. Local absent identity rendered
explicit null fields and the same absent-SHA image failed Staging lookup.
These are local component/image checks, not deployed revision evidence.

Independent review found no correctness/security blockers. Its one MEDIUM
test-adequacy gap was resolved by independently authored second-identity cases
and parsed query-variable assertions, then scoped re-review confirmed addressed
with no new findings. Plausible-mutant analysis covered SHA fallback/validation,
allowlists, target/source mismatches, exact-D propagation, timestamp substitution,
and sanitized errors. No mutation framework was introduced.

Application API, database schema/data behavior, authentication, readiness,
deployment/migration flow, and dependencies are unchanged. The only runtime
addition is safe image metadata and its explicit operator reader. Any rollout
or recovery procedure remains separately authorized and belongs to the existing
deployment work, not new automation in this issue. Live acceptance cannot use
the probe as a substitute for the final implemented identity surface.

## Final Staging acceptance evidence

The authorized manual deployment of the published implementation commit returned
exact deployment `bd411e7e-cbc9-4c3e-b332-9f7e522b4b72`. Its control-plane status
was `SUCCESS`. The exact-record instance lookup selected a `RUNNING` instance;
SSH used that explicit instance selector to execute
`uv run --locked --no-sync python -m config.build_identity`.
The actual three-field stdout was retained and passed unchanged as stdin to
`scripts/api_deployment_identity.py`. The repository-owned lookup queried the
captured deployment ID and validated source, environment, project and service.
Its successful allowlisted output was:

```json
{
  "source_sha": "84237fd2e8db35ecf06c33a8eb09d104858195ff",
  "deployment_id": "bd411e7e-cbc9-4c3e-b332-9f7e522b4b72",
  "environment": "staging",
  "deployment_timestamp": "2026-09-17T01:04:22.773Z"
}
```

`deployment_timestamp` is this exact Railway record's `createdAt`, preserved
without translating lifecycle or process timestamps. GitHub resolved the
reported full SHA in `TailTag-Game/tailtag`, immediately after verifying the
acting account as `FinnThePanther`. Staging autodeploy remained disabled and the
source repository and Docker root were unchanged. No secrets or service
configuration were modified.

The existing `API_BASE_URL=https://staging.tailtag.app make api-smoke` passed
all four endpoints with HTTP 200. This shared-URL smoke is separate from the
exact-instance proof; neither asserts that the captured deployment remains
currently serving after future deployments. No latest-active lookup is needed
for this historical acceptance evidence.

Acceptance accounting: AC-1/2 are established by artifact tests, non-root image
readback and the actual deployed artifact; AC-3 by runtime tests and deployed
readback; AC-4 by exact-record timestamp tests and the live join; AC-5 by the
three/four-field allowlists and scoped review; AC-6 by the complete live tuple
and GitHub resolution; AC-7 by exact-D queries and second-identity tests; AC-8
by validation/allowlist/clock cases within the 58 focused tests and the
1,529-test deterministic gate; AC-9 by the focused feasibility experiment and
final explicit-SHA deployment, both supplying the correct build-time SHA. No
contract item remains unverified. There is no new public API, database migration,
dependency, or complete deployment
workflow. #202 retains controlled deployment/rollback ownership.

This evidence is a documentation-only follow-up to deployed source
`84237fd2e8db35ecf06c33a8eb09d104858195ff`. The evidence commit's own SHA does
not substitute for the source SHA of the captured deployment.
