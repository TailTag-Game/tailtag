# Backend Phase 0 onboarding validation

**Issue:** #61  
**Outcome:** Validation incomplete

## Scope

This review validates the Phase 0 backend contributor workflow: repository
diagnostics, local `.env` creation, the Compose-backed development container,
locked dependency setup, PostgreSQL, explicit migrations, Django HTTP surfaces,
and the canonical backend check suite.

It does not validate Clerk, TailTag product APIs or models, CI/CD, Railway, or
production deployment. It also does not claim that a graphical editor's Dev
Containers integration was exercised.

## Revision and environment

- Runtime revision validated: `808b43aa8fb2da49629cef4f37555d5294882f95`
  (`test/backend-onboarding-validation`).
- Baseline before validation fixes: `ff855e80c403b1677ec0fe1890deea50e4000e2c`
  (`origin/main`).
- Host: macOS on Apple Silicon; Docker Engine 29.4.0 and Docker Compose v5.1.2.
- Dev Container CLI: unavailable. VS Code CLI was available, but its Dev
  Containers extension was not installed; no editor/UI workflow was exercised.
- Host Python, host `uv`, host PostgreSQL, and host `psql` were not used for the
  primary backend checks.

## Methodology

Each validation pass used a newly cloned repository in a distinct temporary
directory. `services/api/.env` was created only by copying `.env.example` as
documented. Each Compose pass used a unique project name and newly created
`postgres_data` volume.

The documented Compose configuration could not start unchanged because an
unrelated pre-existing container occupied host port 5432. That container was
not stopped or reused. For the underlying-container fallback, a temporary,
uncommitted Compose override removed only the database host-port publication;
the API and database remained on the fresh Compose network. This validates the
container-internal workflow, but is not a pass for the exact host-port binding
or editor Dev Containers UI path.

After each in-scope repair, the prior clone was discarded and a new fresh clone
of the corrected branch was used. The final runtime pass was a fourth clean
clone at the revision above.

## Results

| Step | Result | Evidence |
| --- | --- | --- |
| Fresh clone | PASS | Final pass used a new clone of `808b43a`; no inherited `.env`, `.venv`, artifacts, or database volume. |
| Host `./scripts/doctor.sh` | PASS with expected WARN | Git, Docker, and Compose passed; absent Dev Container CLI was advisory. |
| `.env` creation | PASS | Copied from `services/api/.env.example` using the documented command. |
| Actual editor/Dev Container CLI open | NOT TESTED | Neither a Dev Container CLI nor the VS Code Dev Containers extension was available. |
| Documented Compose start with host DB port | BLOCKED | Existing unrelated host process/container occupied port 5432. |
| Fresh underlying Compose/container fallback | PASS | PostgreSQL 17 became healthy on a unique fresh volume; API development image built and joined its fresh network. |
| Locked dependency setup | PASS | `uv sync --all-groups --locked` ran inside the API container. |
| In-container `./scripts/doctor.sh` | PASS | Python 3.13, `uv`, locked dependencies, PostgreSQL, and Make commands all passed. |
| Explicit migrations | PASS | `make api-migrate` applied Django framework migrations on the fresh volume. |
| Django startup | PASS | `make api-run` served the development API from the container. |
| HTTP smoke | PASS | `make api-smoke` received HTTP 200 for `/health/live`, `/health/ready`, `/api/schema/`, and `/api/docs/`. |
| Admin reachability | PASS | `/admin/` returned HTTP 200 after its normal login redirect; no TailTag product admin behavior was inferred. |
| `make api-check` | PASS | Ruff format/lint, strict mypy, 31 pytest tests, Django checks, migration drift, OpenAPI validation, and Gunicorn configuration all passed. |
| Persistence/reopen | PASS | Normal Compose stop/start retained the named volume; a second `make api-migrate` reported no migrations to apply. |

The first smoke attempt immediately after starting Django received connection
refusals; the documented retry then passed once the server had bound its port.
This was normal startup timing, not a route failure.

## Defects found and fixed

1. The development image did not include `make`, while the documented
   devcontainer workflow requires `make api-*` commands. `145b518` installs
   `make`; a runtime-contract test asserts the dependency.
2. Devcontainer terminal commands did not inherit the Compose entrypoint's
   container-network `DATABASE_URL`, so `make api-migrate` failed despite a
   healthy database. `e3597bf` makes Django-oriented Make targets derive that
   already-approved Compose URL only when `TAILTAG_DEVCONTAINER=1`; focused
   command-contract coverage was added.
3. The new test initially needed repository formatting. `808b43a` applies the
   formatter; the final clean-clone `make api-check` includes the passing
   formatting check.

## Limitations and remaining friction

The final conclusion is **Validation incomplete**, rather than **Validated**:
the available environment could not exercise the primary editor/Dev Containers
opening path, and the exact documented database host-port binding was blocked
by unrelated active local state. The strongest available fallback did exercise
a new Compose network, fresh PostgreSQL 17 volume, the development image,
container-side commands, migrations, HTTP surfaces, and the complete check
suite.

No out-of-scope product, authentication, CI/CD, Railway, or architecture work
was performed. No follow-up issue was created: the two workflow defects were
small, in-scope repairs, while the remaining limitations are execution-host
constraints rather than repository defects.
