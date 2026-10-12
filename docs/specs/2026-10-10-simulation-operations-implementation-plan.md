# V0 convention simulation operations — implementation plan

Contract: [implementation contract](2026-10-10-simulation-operations.md).
Issue: [#230](https://github.com/TailTag-Game/tailtag/issues/230). Branch:
`feat/230-simulation-operations`.

## Global constraints

- Stay within the contract's change surface. Add no dependencies, backend
  changes or unattended execution.
- Widen privileged allow-lists only by exact closed shapes. Prefer explicit
  refusal to permissive defaults.
- Tests use real admission, bridge and host-directory code. Fake only
  `ssh`, `scp`, Docker, relays and time at process or provider boundaries,
  following existing host test patterns.
- Before review, each unit passes:
  - its focused tests;
  - `make sim-format-check`, `make sim-lint-check` and `make sim-type-check`;
  - Semgrep, with `git add -N` for new modules, because Semgrep skips
    untracked files;
  - ruff with `--no-cache`, because a stale cache hides first-party import
    findings.
- The parent runs `make sim-check`, `./scripts/doctor.sh` and
  `git diff --check` on the integrated branch.

## Unit order

1. **Code unit A — admission, profiles and journeys host execution** (contract
   U1 and U2). Admission and the bridge partition are coupled through
   `validate_manifest`, so they share one review.
2. **Code unit B — inventory and collect** (contract U3). Depends on nothing in
   unit A, but runs after it to keep the diffs reviewable.
3. **Documentation unit C** (contract U4). The parent writes it after A and B,
   so the text matches the implemented commands.
4. **Whole-change review**, then parent verification.

Each code unit follows the same sequence:

1. The test-author writes tests from the frozen test map and records the RED
   evidence.
2. The parent approves the test set.
3. The implementer makes the tests pass without editing them, unless the parent
   approves a test change.
4. A fresh reviewer reviews the unit.

### Code unit A

- `host_protocol.py`:
  - journeys and expiration-tier shapes;
  - the persona-sum branch;
  - refusal of `expired` under the standard tier.
- `host_operator.py` `prepare`: dispatches journeys configuration validation.
- `host_runner.py`: builds the container command from the scenario.
- `__main__.py`:
  - host flags and the host branch for journeys;
  - channel wrapping when the host is bound.
- `host_bridge.py`:
  - the journeys partition;
  - the provision acknowledgement;
  - `inspect` and its closed response validator;
  - cross-scenario operation refusal;
  - the separate heartbeat budget.
- `tools/simulator/host/`: the eight new committed files listed in the
  contract.
- Stop condition: if the journeys fixture images are not in the immutable
  image, stop and replan.

### Code unit B

- `host_runner.py` `inventory` subcommand, plus any read-only helpers in
  `host_artifacts.py`.
- `host_operator.py`:
  - `collect`;
  - a bounded stdout-capturing SSH helper;
  - `scp` retrieval;
  - verification, atomic rename and evaluation.
- Root `Makefile`: `sim-host-collect`, added to `.PHONY`.

### Documentation unit C

- `docs/operations/simulation-operations.md`
- `docs/specs/2026-10-10-unattended-simulation-scheduling-design.md`
- `tools/simulator/README.md`
- `docs/operations/simulation-host.md`

### Live proof (deferred)

Each of these needs separate explicit authorization:

- AC26 smoke, nightly cycle and weekend runs;
- the pool expansion to 50 identities;
- the AC25 expiration run;
- the AC20 baseline promotions;
- the AC23/AC26 proof document.
