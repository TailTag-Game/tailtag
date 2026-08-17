# Replace mypy with Pyright

## Status

Approved for implementation.

## Outcome

Pyright becomes TailTag API's only authoritative static type checker. It must
run in strict mode locally and in CI, replacing mypy without changing the
canonical contributor interfaces: `make api-type-check` and `make api-check`.

## Scope

- Replace the mypy development dependency, mypy configuration, and
  mypy-specific Django/DRF plugin configuration with Pyright and its strict
  configuration.
- Update the committed `uv.lock` resolution for the new toolchain.
- Make the existing Make target and GitHub Actions type-check step run the
  equivalent Pyright command.
- Update command-contract tests and current contributor and architecture
  documentation to name Pyright and describe strict type checking accurately.
- Resolve every new Pyright diagnostic in production code and tests. A
  suppression requires a specific, documented framework limitation; broad
  relaxations and baseline suppressions are out of scope.

## Compatibility boundary

The migration must validate strict Pyright behavior for the API's Django and
DRF usage, including ORM models and managers, settings imports, configured
Django application discovery, DRF serialization/view code if present, and the
pytest suite. Mypy plugin behavior is not itself a compatibility requirement;
the requirement is a sound, strict, passing Pyright result for the current V0
foundation.

## Non-goals

- Running mypy and Pyright concurrently.
- Changing application behavior, runtime dependencies, database schema,
  deployment configuration, or authentication behavior.
- Revising historical POC documentation to imply Pyright was used during that
  evaluation.

## Acceptance criteria

1. `mypy` and its plugin-only configuration are absent from the active API
   dependency and validation path.
2. Pyright runs in strict mode through `make api-type-check` and the API CI
   workflow.
3. The lockfile, contributor guidance, architecture document, and
   command-contract tests agree on the Pyright command.
4. Strict Pyright has no unsuppressed diagnostics in its configured scope.
5. The complete backend validation suite remains green.

## Verification

During implementation, run the Pyright target while iterating, then run
`make api-check`, `./scripts/doctor.sh`, and `git diff --check`. Report any
environmental inability to run the PostgreSQL-backed checks rather than
substituting a lighter result.
