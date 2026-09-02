# Fail-closed mobile validation

Issue: [#160](https://github.com/TailTag-Game/tailtag/issues/160)

## Outcome

Make the always-reported `Mobile validation` GitHub Actions check safe to
require on `main`. The check must distinguish a successfully detected
irrelevant pull request from a failed change-detection job and must fail closed
when change detection or either platform build fails.

## Design

Keep the existing workflow structure and add one input to the final validation
step: `needs.changes.result`. The validation script checks that result before it
interprets `needs.changes.outputs.mobile`.

The ordered decision logic is:

1. If change detection did not finish with `success`, fail `Mobile validation`.
2. If change detection succeeded and reported no mobile changes, succeed while
   Android and iOS remain skipped.
3. If mobile changes were reported, require both Android and iOS to have
   finished with `success`; otherwise fail.
4. If both platform jobs succeeded, succeed.

Push and manual-dispatch runs continue to set `mobile=true`, so they continue to
execute both platform jobs. No new dispatch inputs, repository scripts, or
testing-only production seams are introduced.

## Acceptance Contract

1. A failed `Detect mobile changes` job causes `Mobile validation` to fail.
2. An irrelevant pull request skips Android and iOS and reports successful
   `Mobile validation`.
3. A relevant pull request reports successful `Mobile validation` only when
   both Android and iOS succeed.
4. Push and manual-dispatch runs execute and validate both Android and iOS.
5. An Android failure causes `Mobile validation` to fail.
6. An iOS failure causes `Mobile validation` to fail.
7. The final repository diff has no whitespace errors.
8. After the workflow behavior is demonstrated, the active `Protect main`
   ruleset requires `Mobile validation` without removing its existing required
   checks.

## Test Surface Contract

Tests and verification observe the existing GitHub Actions job graph and job
conclusions. Approved observation points are:

- `Detect mobile changes`, `Android Build Test`, `iOS Build Test`, and
  `Mobile validation` job conclusions;
- the `mobile` change-detection output and existing `needs.<job>.result`
  contexts inside the final validation job;
- workflow runs for pull request, push, and manual-dispatch events; and
- the repository ruleset returned by the GitHub API.

Temporary commits may deliberately break change detection or one platform job
to obtain failure evidence, but those faults must not remain in the final diff.
An irrelevant-path pull request may be used after the fixed workflow is present
on its base branch. No public or package-internal application API, permanent
simulation input, or new repository test harness is approved.

## Scope Guard

- **Outcome:** implement the Acceptance Contract above.
- **Non-goals:** mobile application changes, build-contract changes, dependency
  changes, signing or distribution, unrelated workflow refactoring, and broader
  issue #133 work.
- **Expected repository files:**
  `.github/workflows/mobile-build-test.yml` plus this approved design artifact.
  The pre-existing `AGENTS.md` branch commit is preserved but is not part of
  issue #160 implementation.
- **External configuration:** add `Mobile validation` to the existing required
  checks in `Protect main` only after verification.
- **Proof:** deterministic syntax/whitespace checks, independent test-adequacy
  and implementation review, live GitHub Actions conclusions covering the
  acceptance paths, and a final GitHub API read of the ruleset.

## Sequencing and rollback

The workflow fix is verified before the required-check ruleset is changed. The
ruleset update preserves `API foundation checks`, `Repository policy`, and all
other current protection parameters.

If the workflow change must be rolled back, first remove `Mobile validation`
from the required-check list so pull requests are not blocked by an unavailable
or unsafe check, then revert the workflow change through a pull request.

