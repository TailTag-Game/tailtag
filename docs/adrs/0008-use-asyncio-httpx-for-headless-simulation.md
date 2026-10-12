# Use asyncio and httpx for headless simulation

**Status:** accepted

## Context and constraints

#199 needs one external client that serves both small black-box acceptance runs and convention-scale simulations against Staging. The client must:

- reproduce a workload from a scenario version and seed (#224),
- drive stateful virtual users through multi-step journeys with retries, contention, and stale credentials (#221, #225, #226),
- run a few hundred concurrent users from one dedicated host (#228), not a distributed platform,
- report through TailTag's own metadata (scenario, seed, simulator SHA, backend build identity) and correctness reconciliation (#222, #229),
- stay maintainable in this Python repository and outside the Django environment.

The repository already uses httpx, Python 3.13, uv, strict Pyright, and Ruff.

## Decision

Build the harness in `tools/simulator/` as plain Python asyncio with `httpx.AsyncClient`. Each virtual user is a coroutine with its own seeded `random.Random`. Load shape, statistics, thresholds, and reports are TailTag code, added by the children that need them.

## Alternatives considered

- **Locust.** It has mature spawning, load shapes, a web UI, distributed workers, and percentile statistics. It was rejected because:
  - it has no seed option and chooses tasks through the global `random`,
  - its gevent scheduler interleaves users by I/O timing, so seeded reproducibility means working against the framework,
  - it monkey-patches networking at import, which conflicts with asyncio and httpx,
  - its built-in reports lack the run metadata and reconciliation #199 requires, so the reporting it offers would be partly duplicated anyway.
- **Molotov** (asyncio and aiohttp scenarios). Rejected because its last release was in 2022 and its Python support stops at 3.10.
- **k6.** Rejected because scenarios would be JavaScript, outside the repository's Python tooling and review practice.

## Consequences and risks

- TailTag owns spawning, ramp profiles, latency statistics, and threshold evaluation. The risk is building a weaker version of a load tool's features. #226 and #229 should keep these small and fit-for-purpose.
- A single asyncio process is bound to one CPU core. If one host cannot generate the required load, #228 can run several processes with disjoint user ranges before considering a different tool.
- Determinism covers which users exist, what each decides, and their seeded timings. Exact cross-user interleaving under real network timing is not reproducible with any tool, and reconciliation must not depend on it.

## Validation and rollback

#218 validates the package boundary with an authenticated smoke run. If #224 to #226 show that seeded scenarios or the required load cannot be achieved, a new ADR can supersede this one. The phase boundaries and target safety do not depend on the load engine, so replacing it would not affect them.
