# Headless V0 acceptance journeys implementation plan

Spec: [headless acceptance journeys](2026-10-03-headless-acceptance-journeys.md)
(#221, acceptance contract J-1 to J-13). This plan sequences the work and fixes
interfaces. The spec stays authoritative for behavior.

## Phase ledger

- **Scope:** STANDARD EXPANDED, run as one review unit. The change is simulator-only
  and its parts are tightly coupled.
- **Assurance:** SECURITY.
- **Completed:** refinement (G1 to G12), reconnaissance, the API contract map,
  spec and plan approval (2026-10-03), independent tests, implementation, the
  deterministic gate, and one fresh review (all five verdicts PASS).
- **Current:** PR.
- **Pending:** maintainer Staging proof (J-13).

Review dispositions (no BLOCKER or HIGH):

- MEDIUM, fixed: an exception raised outside HTTP handling, such as a failed
  token refresh, escaped the journey loop as `FAIL simulation` and skipped the
  remaining journeys (J-1). `_step` now reports any send failure as that step's
  `observed=error`. A new `avatar-unexpected` failure case covers it; it fails
  without the fix.
- Test-set corrections approved by the parent:
  - The `test_smoke.py` oversized-body padding now follows `MAX_RESPONSE_BYTES`.
  - The CLI image test now filters the fixture folder by image suffix, as the
    spec says, so `.gitkeep` is not treated as an image.
- Real-API check: the generated GIF, non-image bytes, and 5001×5001 PNG are
  rejected by `media.images.normalize_image` as `unsupported_format`,
  `invalid_image`, and `too_many_pixels`. The fallback PNGs and the fixture JPEG
  are accepted.
- The J-13 Staging run is still needed to confirm these, which the review could
  not verify from the diff:
  - that Staging serves `https://` presigned URLs
  - that httpx multipart framing works against the API's closed multipart parser

## Change surface

All paths are under `tools/simulator/` unless noted.

| File | Change |
| --- | --- |
| `tailtag_simulator/client.py` | `post`, `delete`, `put_multipart`, and `post_multipart` methods. `MAX_RESPONSE_BYTES = 65536`. One shared `_send` path keeps every protection. |
| `tailtag_simulator/images.py` (new) | Stdlib-only generators: two distinct valid PNGs (the fallback), a minimal GIF, non-image bytes, and a 5001×5001 1-bit PNG. Also `load_fixture_images(directory) -> tuple[bytes, bytes]`, which returns images A and B. |
| `tailtag_simulator/journeys.py` (new) | `JourneyContext` (public clients only), the 13 journey functions, the result model, the code allowlist, and `run_journeys(...)`. |
| `tailtag_simulator/fixtures.py` | Extract the existing target, lease, provision, and release sequence of `run_fixture_smoke` into one shared helper that `run_journeys` reuses. `fixture-smoke` behavior and output must not change. |
| `tailtag_simulator/__main__.py` | A `journeys --pool` subcommand that loads the images from `REPOSITORY_ROOT/services/api/simulation_fixtures/images`. |
| `Makefile` (repo root) | A `sim-journeys` target, plus an entry in `.PHONY`. |
| `README.md` (simulator) | A "Journeys" section. |
| `tests/journey_support.py` (new) | An in-memory fake of the gameplay API. |
| `tests/test_journeys.py` (new) | Journey tests. |
| `tests/test_client.py` | Extend the existing parametrized protections to the new methods. |
| `tests/test_images.py` (new) | Image generator tests, only if they are not already covered via journeys. |
| `docs/specs/...` | Spec status updates. |

Nothing changes under `services/api/`.

## Interfaces

```python
# client.py
class ApiClient:
    async def post(self, path: str, body: Mapping[str, object] | None = None) -> Reply: ...
    async def delete(self, path: str) -> Reply: ...
    async def put_multipart(self, path: str, data: Mapping[str, str],
                            files: Mapping[str, Upload]) -> Reply: ...
    async def post_multipart(self, path: str, data: Mapping[str, str],
                             files: Mapping[str, Upload]) -> Reply: ...

@dataclass(frozen=True)
class Upload:
    filename: str
    content: bytes = field(repr=False)
    content_type: str

# journeys.py
@dataclass(frozen=True)
class JourneyImages:
    valid_a: bytes = field(repr=False)
    valid_b: bytes = field(repr=False)

@dataclass(frozen=True)
class JourneyContext:
    """All SIMULATION receives: public clients only."""
    owners: tuple[ApiClient, ApiClient]
    catchers: tuple[ApiClient, ApiClient, ApiClient, ApiClient]
    outsider: ApiClient
    anonymous: ApiClient          # no token
    malformed: ApiClient          # fixed bearer "not-a-token"
    images: JourneyImages

@dataclass(frozen=True)
class JourneyResult:
    name: str
    failed_step: str | None
    expected: str | None          # "<status>/<code>"
    observed: str | None          # "<status>/<code>" | "<status>/shape" | "error"

JOURNEY_NAMES: Final[tuple[str, ...]]   # the 13 names, in order

async def simulate_journeys(context: JourneyContext) -> tuple[JourneyResult, ...]: ...
def journey_lines(results: Sequence[JourneyResult]) -> list[str]: ...   # RECONCILIATION

async def run_journeys(pool: str, *, images: JourneyImages, prompt_secret, lease_channel,
                       fixture_channel, emit, clerk_transport=None, api_transport=None,
                       clock=time.time, run_id=None) -> int: ...
```

The anonymous and malformed clients are opened with `open_client(origin)` and
`open_client(origin, token="not-a-token")` on the same verified origin.

## Test Surface Contract

- **Seams.** These are the existing seams, nothing new:
  - the httpx transport (`api_transport`, `clerk_transport`)
  - the lease channel and fixture channel fakes (`pool_support.FakeChannel`,
    `fixture_support.FakeFixtureChannel`)
  - `emit`, `prompt_secret`, and `clock`
- **`tests/journey_support.py`.** It installs a gameplay fake as the `World`'s extra
  authenticated route, following the `FixtureState.route` pattern. It models the V0
  rules the journeys depend on, with the response shapes from the spec's Evidence
  section:
  - sessions
  - credentials, including rotation and revocation
  - activations
  - active enrollment
  - confirm precedence: already-caught first, then the catcher checks, then the
    target checks, then self catch
  - history
  - fursuit creation and photo replacement
  - avatars
  - the three image rejections, decided by inspecting the uploaded bytes
  - 401 for no token or a bad token
  - non-owner 404

  A `break_rule` hook lets a test make the fake violate exactly one rule. Every
  response carries leak sentinels: payload, URLs, names, handles, and IDs.
- **No mocks of simulator internals.** Journey functions run for real against the
  fake.

## Failure mode inventory → tests

| # | Failure mode | Test (minimum) |
| --- | --- | --- |
| FM1 | A journey accepts a wrong outcome, for example passing on 200 where 404 is expected, or a duplicate catch in history | One parametrized test: for each journey, `break_rule` makes the fake violate that journey's rule. That journey's line is a `FAIL` naming the step with the right expected/observed values. Every other journey still prints `PASS`, and the exit code is 1. |
| FM2 | A correct API is reported as failing | Happy-path run: all 13 `PASS`, `PASS journeys passed=13`, exit 0, the exact line sequence, and `provision` called once with 6 indexes while 7 were leased. |
| FM3 | Output leaks a payload, URL, name, handle, ID, or body text | Sentinel scan over the output of the happy run and of every FM1 failure run. An unknown error code from the fake is printed as `other`. |
| FM4 | SIMULATION makes privileged calls or uses the wrong identity | During journeys, the fake records no lease or fixture channel call. Each gameplay request carries the token of the identity the spec assigns, as `fixture-smoke` already checks. |
| FM5 | Image writes touch #220 fixture fursuits | The fake fails the run if any photo `PUT` targets a fixture fursuit ID. The happy run asserts that the only photo writes target the created fursuit. |
| FM6 | Client widening loses a protection | Extend the existing `test_client.py` parametrization (origin pinning, redirect, size cap, cookies, token per request) to `post`, `delete`, and the multipart methods. Add one test that the cap allows 65536 bytes and rejects 65537. |
| FM7 | The convention mismatch restore is skipped after a failure | One FM1 case where the confirm step fails asserts that the restore `PUT` was still sent. |
| FM8 | Setup or release regressions from the shared-helper extraction | Covered by the existing `test_fixture_smoke.py`, unchanged and passing. Add one journeys test where `provision` fails: there are no journey lines, `FAIL setup result=…` is printed, and the leases are released. |
| FM9 | Generated images are not what the API expects | Assert the PNG header dimensions (5001×5001) and the GIF signature. Assert that the fallback images are distinct, valid PNG signatures. Fixture folder loading cycles through sorted files and falls back when the folder is empty. |
| FM10 | CLI wiring | One test: `journeys --pool p1` reaches `run_journeys` with the pool and the loaded images. A bad pool is rejected before anything is reached. This extends the existing CLI test pattern. |

Deliberately no extra tests for: each response-shape variant, each individual output
field, or Semgrep rule changes (the rules are unchanged).

## Sequence

1. **Spec and plan approval** (maintainer).
2. **test-author** (Sonnet, high) writes `journey_support.py`, `test_journeys.py`,
   the `test_client.py` extensions, and the image tests, against the interfaces
   above. The tests fail because the code is missing. The parent then approves the
   test set.
3. **implementer** (Sonnet, high) writes the production code until `make sim-check`
   passes. It must not edit tests without parent approval.
4. **Deterministic gate.** Run `make sim-check`, `./scripts/doctor.sh`, and
   `git diff --check`.
5. **reviewer** (Opus, high) reviews the one unit and gives SPEC, QUALITY, TEST,
   SCOPE, and SECURITY verdicts.
6. **PR.** Push to `FinnThePanther` once the maintainer asks.
7. **Maintainer.** Run `make sim-journeys POOL=<fresh or readmitted pool>` on
   Staging. Record the sanitized output in the spec (J-13).
