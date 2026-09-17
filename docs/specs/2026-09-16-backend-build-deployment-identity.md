# Backend build and deployment identity

Issue: #201. Parent: #197. Deployment workflow: #202.

## Status and phase ledger

Scope: STANDARD COMPACT. Assurance: SECURITY and TEST ADEQUACY.
The user-approved identity contract is frozen below. The proposed implementation
design is conditional on the focused Staging experiment; build-time SHA injection
has not yet been validated live. No production implementation has begun.

Completed: repository reconnaissance, upstream documentation research, live
Railway schema and target inspection. Current: experiment preparation.
Pending: authorized probe publication, Staging experiment, final design freeze,
environment baseline, independent test authorship, implementation, deterministic
checks, independent review, exact-deployment live proof, final verification.

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
`api` and `Postgres` services. No configuration values were queried.

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
only the following production-stage addition after `WORKDIR /app`:

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

## Proposed implementation design

Use a root-owned metadata file outside writable application paths for baked SHA.
Generate it in the production Docker stage from the declared argument. One small
Python identity module reads this fixed artifact path and explicitly reads the
two runtime Railway values. No runtime SHA fallback or selectable production
metadata path. Local development may report absent identity explicitly; it must
not fabricate a full Staging identity. Final build/local behavior must preserve
existing contributor image builds and will be specified after the experiment.

A backend operator command renders source SHA, deployment ID, and environment.
A maintainer-side lookup script consumes this safe output and queries exact D
through authenticated Railway CLI/API. The backend has no Railway credentials,
control-plane network dependency, or generated deployment timestamp. The joined
operator result adds `deployment_timestamp` from `createdAt` only after validating
record ID, target environment/service, and source equality. Control-plane failure
produces a clear failure rather than a fabricated complete tuple. Omit the
optional release label initially; it adds no required evidence.

Alternative runtime-only SHA is rejected by the approved artifact-binding
contract. Embedding the full deployment tuple in the image is rejected because
deployment instances differ from source artifacts.

## Test Surface Contract

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

Expected implementation surface: existing production Dockerfile, one backend
identity module and operator entry point, one maintainer lookup script, relevant
existing test locations, and identity/Staging documentation. Final paths and
baseline checks will be frozen after the probe passes. No dependencies, database
schema, public API, readiness behavior, logging implementation, Production,
promotion automation, or unrelated cleanup.

Deterministic tests prove repository-owned parsing, output, and joining logic.
The final live Staging proof must exercise the implemented baked artifact and
operator command, exact Railway deployment lookup, and GitHub commit resolution.
Railway's metadata is trusted platform evidence, not cryptographic image
attestation. A historical proof does not establish which deployment serves now.
