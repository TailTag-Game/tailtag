# Replacement Development and Staging API launch

Status: approved paired first-activation contract. The new APIs remain
source-free until the preparation gate below passes. This is the first usable
environment milestone; it does not close [#243](https://github.com/TailTag-Game/tailtag/issues/243)
or [#208](https://github.com/TailTag-Game/tailtag/issues/208).

## Prepare both environments

Before connecting the shared `api` service to `TailTag-Game/tailtag` on
`main`, verify the approved GitHub and Railway identities, the exact pinned
replacement project and its Development/Staging API and PostgreSQL instances,
and the old Development automatic-delivery hold. Freeze one CI-accepted merged
source SHA and keep a no-push window through first deployment and Staging
trigger control.

Configure and read back **both** new API instances while source-free:

- environment-local `${{Postgres.DATABASE_URL}}` reference to the selected
  PostgreSQL service, distinct volume and actual database/cluster identity;
- production Django settings, host and CSRF origins, separate Django secret,
  the correct Clerk public key and authorized origin from each new Clerk
  instance, and bucket-scoped R2 credentials for each distinct private bucket;
- `services/api` Dockerfile build context, exact
  `python -m config.replacement_migrate` pre-deploy command with a bounded
  timeout, and the required PostgreSQL service selector and Staging phase.

The pre-deploy wrapper checks code-pinned API and PostgreSQL targets, the baked
source SHA and runtime deployment identity, and the actual connected database
name/cluster before calling Django migrations on that same connection. A
failure or ambiguous migration stops deployment and requires independent
reconciliation before another attempt. The wrapper does not choose whether a
syntactically valid source SHA was approved; the host launch must establish
that provenance separately.

## Activate and verify

Connect the repository **once** after both configurations pass. Initial
deployments in both configured environments are intentional. Read back each
effective source, build and pre-deploy setting; join the accepted SHA to each
provider deployment/instance, guarded migration result, and public identity.
Stop on an unexpected target, extra deployment, incomplete configuration or
ambiguous write. Disable and verify Staging's automatic GitHub trigger before
ending the no-push window. Enable only the intended Development delivery path.

On the candidate domains, check identity/readiness, a fresh Clerk login and
authenticated API request in each environment, cross-environment token
rejection, and a disposable upload/read/delete through each environment's R2
binding. Prove the two database and credential bindings remain distinct.

Quiesce old writers and direct routes before moving canonical API, Clerk and
DNS bindings. After the handoff, repeat identity/readiness, authentication,
cross-environment rejection and disposable media checks at the final public
endpoints. Retain old resources as isolated recovery surfaces until separate
retirement authorization and verification.

Fresh #204 reset, #243 operator matrix, #208 readiness reconciliation and
new-database restore evidence follow the usable-environments milestone. Old
target receipts remain historical evidence; they do not substantiate the new
Staging generation.

## Acceptance and test surface

The IDs cited by the focused tests retain these approved meanings:

| ID | Required observable result |
| --- | --- |
| T-1 | Replacement project/environment/service tuples match code-owned commitments; swaps and malformed selectors fail. |
| T-2 | Missing, malformed, edited or incorrectly protected private selector files cannot redirect a pinned target. |
| T-3 | Provider, public and in-image identities must join; old and replacement generations remain distinct. |
| T-4 | Candidate and canonical origins are finite; candidate evidence cannot authorize canonical mutation. |
| T-5 | Railway identity, #204 reset identity and actual PostgreSQL identity use their separate authorities. |
| T-6 | Old or delayed Development deployment events cannot acquire replacement delivery attribution. |
| T-8 | Guards and evidence expose only fixed sanitized classifications. |
| C-1 | Only the pinned candidate Staging hostname and selector produce a candidate origin. |
| C-2 | Staging readiness requires its exact phase, target, host, CSRF and Clerk origin sets. |
| C-3 | Candidate preflight reads only the pinned HTTPS origin and returns explicitly candidate-only evidence. |
| C-4 | Candidate evidence cannot satisfy the canonical matrix or reset boundary. |
| D-1 | Only the pinned Development hostname and selector produce its public origin. |
| D-2 | Development readiness requires the replacement target, complete runtime identity and exact origins. |
| D-3 | Development event attribution requires the pinned provider tuple and complete successful event binding. |
| D-4 | Attributed smoke requires the pinned origin and stable identity/readiness/source join; manual smoke is unattributed. |
| D-5 | Provider readback must join the Development deployment, source, instance and public identity before delivery resumes. |
| M-1 | Wrong API/runtime identity, PostgreSQL selector, source, settings or Staging phase fails before Django setup or migration. |
| M-2 | The configured default database and actual connected name/cluster are checked against independent code-owned commitments. |
| M-3 | Wrong database or failed identity query stops before migration. |
| M-4 | A matching database migrates once on the verified physical connection; loss or uncertain partial writes stop without retry. |
| M-5 | Migration wrapper output and failures remain sanitized. |
| M-6 | Both APIs have complete, distinct database bindings and guarded pre-deploy configuration before source attachment. |

T-7 (complete helper bundles in #204/#243 SSH launchers) belongs to the
subsequent canonical Staging validation work; this focused launch does not
change those bundles or claim that result.

Tests use pure selector/digest functions with synthetic identities, the
existing HTTP/preflight transport seam, synthetic production settings,
controlled provider/event inputs, and disposable local PostgreSQL for Django's
real default-connection migration path. Provider readback, actual launch and
public API/auth/media checks remain live gates. This change does not alter
gameplay, operator permissions, audit behavior, the old-generation promoter,
schema migrations or #204 reset semantics.
