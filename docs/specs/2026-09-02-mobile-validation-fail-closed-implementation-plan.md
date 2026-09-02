# Fail-closed Mobile Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the always-reported `Mobile validation` check fail closed, prove
its event and failure matrix, and then require it in the active `Protect main`
ruleset.

**Architecture:** Preserve the current four-job GitHub Actions workflow. Pass
the `changes` job result into the final validation step and check it before the
change-detection output; do not add scripts, dispatch inputs, or testing-only
production seams. Use local extraction of the committed shell block for the
fast result matrix and real GitHub Actions runs for orchestration proof.

**Tech Stack:** GitHub Actions YAML, Bash, Ruby/Psych/Open3 for local workflow
inspection, GitHub CLI, GitHub repository rulesets.

## Global Constraints

- The approved design and contracts are in
  `docs/specs/2026-09-02-mobile-validation-fail-closed.md`.
- The final implementation diff modifies only
  `.github/workflows/mobile-build-test.yml` and the approved design/plan
  artifacts.
- Preserve Android, iOS, trigger, permissions, and path-filter behavior outside
  the approved fail-closed change.
- Do not introduce permanent simulation inputs, a repository test harness, new
  dependencies, or a production API for testing.
- Temporary fault commits used for live verification must not remain in the
  final file tree.
- Do not push, open/close a pull request, merge, delete a remote branch, or
  mutate the ruleset without the user's applicable explicit authorization.
- Do not add the required check until all pre-merge workflow behavior has been
  demonstrated. Preserve every existing rule and required check.

---

### Task 1: Independently approve the verification matrix

**Files:**

- Read: `docs/specs/2026-09-02-mobile-validation-fail-closed.md`
- Read: `.github/workflows/mobile-build-test.yml`
- Create/modify: none

**Interfaces:**

- Consumes: the frozen Acceptance Contract and Test Surface Contract.
- Produces: an acceptance-item-to-evidence map and exact local/live checks for
  the implementer; it must not propose production implementation.

- [ ] **Step 1: Dispatch a fresh `test_author` context**

  Give it the design artifact and current workflow, but no proposed
  implementation. Require every proposed check to map to Acceptance Contract
  items 1-8 or the RELIABILITY/TEST ADEQUACY modifiers.

- [ ] **Step 2: Require plausible-mutant analysis**

  At minimum, assess whether the checks reject these incorrect behaviors:

  - an unset `mobile` output is treated as an irrelevant change after the
    `changes` job fails;
  - Android failure is ignored;
  - iOS failure is ignored;
  - an irrelevant pull request incorrectly requires platform jobs;
  - push or manual dispatch incorrectly skips platform jobs; and
  - the ruleset update replaces an existing required check.

- [ ] **Step 3: Parent-review test adequacy and scope**

  Approve only checks using the Test Surface Contract. Reject any proposal for
  permanent workflow controls, new application interfaces, unrelated mobile
  tests, or a committed general-purpose workflow harness.

### Task 2: Implement and locally prove the fail-closed gate

**Files:**

- Modify: `.github/workflows/mobile-build-test.yml`
- Test: the extracted `mobile-validation` shell block in the same workflow

**Interfaces:**

- Consumes: `needs.changes.result`, `needs.changes.outputs.mobile`,
  `needs.android.result`, and `needs.ios.result`.
- Produces: the stable `Mobile validation` check with ordered fail-closed
  decisions; no new external interface.

- [ ] **Step 1: Run the approved local result-matrix check before editing**

  Run this command against the shell stored in the workflow:

  ```bash
  ruby -ryaml -ropen3 -e '
  workflow = YAML.safe_load(File.read(ARGV.fetch(0)), aliases: true)
  script = workflow.fetch("jobs").fetch("mobile-validation").fetch("steps").fetch(0).fetch("run")
  cases = [
    ["change detection failure", {"CHANGES_RESULT"=>"failure", "MOBILE_CHANGED"=>"", "ANDROID_RESULT"=>"skipped", "IOS_RESULT"=>"skipped"}, 1],
    ["irrelevant change", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"false", "ANDROID_RESULT"=>"skipped", "IOS_RESULT"=>"skipped"}, 0],
    ["relevant success", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"success", "IOS_RESULT"=>"success"}, 0],
    ["Android failure", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"failure", "IOS_RESULT"=>"success"}, 1],
    ["iOS failure", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"success", "IOS_RESULT"=>"failure"}, 1]
  ]
  failures = cases.count do |name, env, expected|
    stdout, stderr, status = Open3.capture3(env, "bash", "-c", script)
    actual = status.exitstatus
    puts "#{name}: expected=#{expected} actual=#{actual}"
    warn stdout unless actual == expected
    warn stderr unless actual == expected
    actual != expected
  end
  exit failures.zero? ? 0 : 1
  ' .github/workflows/mobile-build-test.yml
  ```

  The matrix encoded by the command is:

  | Changes result | Mobile | Android | iOS | Expected exit |
  | --- | --- | --- | --- | --- |
  | `failure` | empty | `skipped` | `skipped` | 1 |
  | `success` | `false` | `skipped` | `skipped` | 0 |
  | `success` | `true` | `success` | `success` | 0 |
  | `success` | `true` | `failure` | `success` | 1 |
  | `success` | `true` | `success` | `failure` | 1 |

  Expected result before implementation: the first case unexpectedly exits 0
  and prints `No mobile app changes.`, reproducing the defect.

- [ ] **Step 2: Make the smallest workflow edit**

  Add this environment mapping to the existing `Validate build status` step:

  ```yaml
  CHANGES_RESULT: ${{ needs.changes.result }}
  ```

  Add this as the first branch of its shell script:

  ```bash
  if [ "$CHANGES_RESULT" != "success" ]; then
    echo "Mobile change detection failed."
    exit 1
  fi
  ```

  Remove the existing trailing spaces after `outputs:`, both affected `steps:`
  and `env:` keys, `needs:`, and the whitespace-only line after the
  `Skip mobile app change detection` step.

- [ ] **Step 3: Run the approved local result-matrix check after editing**

  ```bash
  ruby -ryaml -ropen3 -e '
  workflow = YAML.safe_load(File.read(ARGV.fetch(0)), aliases: true)
  script = workflow.fetch("jobs").fetch("mobile-validation").fetch("steps").fetch(0).fetch("run")
  cases = [
    ["change detection failure", {"CHANGES_RESULT"=>"failure", "MOBILE_CHANGED"=>"", "ANDROID_RESULT"=>"skipped", "IOS_RESULT"=>"skipped"}, 1],
    ["irrelevant change", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"false", "ANDROID_RESULT"=>"skipped", "IOS_RESULT"=>"skipped"}, 0],
    ["relevant success", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"success", "IOS_RESULT"=>"success"}, 0],
    ["Android failure", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"failure", "IOS_RESULT"=>"success"}, 1],
    ["iOS failure", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"success", "IOS_RESULT"=>"failure"}, 1]
  ]
  failures = cases.count do |name, env, expected|
    stdout, stderr, status = Open3.capture3(env, "bash", "-c", script)
    actual = status.exitstatus
    puts "#{name}: expected=#{expected} actual=#{actual}"
    warn stdout unless actual == expected
    warn stderr unless actual == expected
    actual != expected
  end
  exit failures.zero? ? 0 : 1
  ' .github/workflows/mobile-build-test.yml
  ```

  Expected result: all five rows return their expected exit code. Confirm the
  change-detection failure is evaluated before the no-mobile branch.

- [ ] **Step 4: Parse the workflow YAML**

  Run:

  ```bash
  ruby -ryaml -e 'YAML.safe_load(File.read(ARGV.fetch(0)), aliases: true)' .github/workflows/mobile-build-test.yml
  ```

  Expected result: exit 0 with no parse error.

- [ ] **Step 5: Check the focused diff**

  Run:

  ```bash
  git diff --check
  git diff -- .github/workflows/mobile-build-test.yml
  ```

  Expected result: no whitespace errors and only the approved guard/environment
  mapping plus removal of existing trailing whitespace.

- [ ] **Step 6: Commit the implementation**

  ```bash
  git add .github/workflows/mobile-build-test.yml
  git commit -m "fix(ci): make mobile validation fail closed"
  ```

### Task 3: Run deterministic gates and independent review

**Files:**

- Read: all changes relative to `origin/main`
- Create/modify: none unless a required review finding maps to the contract

**Interfaces:**

- Consumes: the committed Task 2 implementation and approved contracts.
- Produces: deterministic evidence, plausible-mutant conclusions, and one fresh
  STANDARD COMPACT reviewer verdict.

- [ ] **Step 1: Run repository and whitespace checks**

  ```bash
  ./scripts/doctor.sh
  git diff --check origin/main...HEAD
  ```

  Expected result: required doctor checks pass, with only the existing optional
  Dev Container CLI warning permitted; no diff whitespace errors.

- [ ] **Step 2: Run the repository Semgrep gate**

  ```bash
  make api-semgrep-check
  ```

  Expected result: rule-contract tests and the repository-owned scan pass. This
  is the required STANDARD deterministic Semgrep gate even though its targets
  do not include the mobile workflow.

- [ ] **Step 3: Re-run YAML parsing and the approved result matrix**

  ```bash
  ruby -ryaml -e 'YAML.safe_load(File.read(ARGV.fetch(0)), aliases: true)' .github/workflows/mobile-build-test.yml
  ruby -ryaml -ropen3 -e '
  workflow = YAML.safe_load(File.read(ARGV.fetch(0)), aliases: true)
  script = workflow.fetch("jobs").fetch("mobile-validation").fetch("steps").fetch(0).fetch("run")
  cases = [
    ["change detection failure", {"CHANGES_RESULT"=>"failure", "MOBILE_CHANGED"=>"", "ANDROID_RESULT"=>"skipped", "IOS_RESULT"=>"skipped"}, 1],
    ["irrelevant change", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"false", "ANDROID_RESULT"=>"skipped", "IOS_RESULT"=>"skipped"}, 0],
    ["relevant success", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"success", "IOS_RESULT"=>"success"}, 0],
    ["Android failure", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"failure", "IOS_RESULT"=>"success"}, 1],
    ["iOS failure", {"CHANGES_RESULT"=>"success", "MOBILE_CHANGED"=>"true", "ANDROID_RESULT"=>"success", "IOS_RESULT"=>"failure"}, 1]
  ]
  failures = cases.count do |name, env, expected|
    stdout, stderr, status = Open3.capture3(env, "bash", "-c", script)
    actual = status.exitstatus
    puts "#{name}: expected=#{expected} actual=#{actual}"
    warn stdout unless actual == expected
    warn stderr unless actual == expected
    actual != expected
  end
  exit failures.zero? ? 0 : 1
  ' .github/workflows/mobile-build-test.yml
  ```

  Expected result: YAML parsing exits 0 and every approved matrix row passes.

- [ ] **Step 4: Inspect the complete branch diff**

  ```bash
  git diff --stat origin/main...HEAD
  git diff origin/main...HEAD
  ```

  Expected result: only the workflow and approved design/plan artifacts differ.
  No temporary faults, debug output, scratch files, dead scope, or unrelated
  cleanup appears.

- [ ] **Step 5: Dispatch one fresh `reviewer` context**

  Require specification compliance, correctness, test adequacy, code quality,
  scope discipline, RELIABILITY review, and plausible-mutant assessment. Resolve
  all Acceptance Contract, BLOCKER, and HIGH findings. The parent decides
  whether any MEDIUM finding belongs to the approved scope.

- [ ] **Step 6: Re-run affected deterministic checks after any correction**

  Do not rely on earlier evidence after an edit. Commit approved corrections
  with a message describing the corrected behavior.

### Task 4: Obtain live pre-merge GitHub Actions evidence

**Files:**

- Final branch tree: no additional files
- Temporary verification commits: workflow-only deliberate faults that are
  reverted before final review

**Interfaces:**

- Consumes: the fixed branch and existing `pull_request`/`workflow_dispatch`
  triggers.
- Produces: GitHub Actions run URLs and per-job conclusions for Acceptance
  Contract items 1-6, except the post-merge push run.

- [ ] **Step 1: Obtain explicit authorization for remote actions**

  Confirm permission to push the branch, open a draft pull request, create and
  revert temporary fault commits, run manual dispatch, create/close a temporary
  stacked irrelevant-path pull request, and delete its remote branch.

- [ ] **Step 2: Verify the GitHub account and push the clean branch**

  ```bash
  gh auth status
  git push -u origin fix/160-mobile-validation-fail-closed
  ```

  The active account must be `FinnThePanther`.

- [ ] **Step 3: Open a draft pull request for issue 160**

  Use a `fix(ci): ...` title, include `Closes #160`, summarize the fail-closed
  decision order, and keep a run-evidence table in the PR body.

- [ ] **Step 4: Record the relevant-pull-request success path**

  On the clean implementation commit, require `Detect mobile changes`, Android,
  iOS, and `Mobile validation` all to conclude `success`. Record the run URL.

- [ ] **Step 5: Record manual-dispatch behavior**

  Dispatch `mobile-build-test.yml` on the issue branch. Require Android, iOS,
  and `Mobile validation` all to run and conclude `success`. Record the run URL.

- [ ] **Step 6: Record change-detection failure behavior**

  In a temporary commit, replace the pinned `dorny/paths-filter` ref with an
  invalid full SHA so `Detect mobile changes` fails to resolve. Push it and
  require Android/iOS to skip and `Mobile validation` to conclude `failure`.
  Record the run URL, then revert the temporary commit and push the revert.

- [ ] **Step 7: Record Android failure behavior**

  In a temporary commit, replace the Android `Java sanity check` command with
  `exit 1`. Push it and require Android and `Mobile validation` to conclude
  `failure`. Record the run URL, then revert the temporary commit and push the
  revert.

- [ ] **Step 8: Record iOS failure behavior**

  In a temporary commit, replace the iOS `Build App` command with `exit 1`.
  Push it and require iOS and `Mobile validation` to conclude `failure`. Record
  the run URL, then revert the temporary commit and push the revert.

- [ ] **Step 9: Record irrelevant-pull-request behavior**

  Create a temporary branch from the clean issue branch, add a harmless
  documentation-only commit, and open a stacked pull request targeting
  `fix/160-mobile-validation-fail-closed`. Require `Detect mobile changes` and
  `Mobile validation` to succeed while Android and iOS are skipped. Record the
  run URL, then close the temporary PR and delete its remote branch.

- [ ] **Step 10: Re-establish and review the clean final branch**

  Require the latest issue-PR commit to contain the intended final tree and a
  fully successful relevant workflow run. Re-run Task 3 deterministic checks,
  inspect the diff, and update the PR evidence table.

### Task 5: Verify the post-merge push and require the stable check

**Files:**

- Repository files: none
- External configuration: active `Protect main` ruleset

**Interfaces:**

- Consumes: issue 160 merged into `main`, its resulting push workflow run, and
  the current ruleset returned by the GitHub API.
- Produces: a successful full-suite push run and a ruleset that additionally
  requires `Mobile validation`.

- [ ] **Step 1: Wait for an authorized squash merge**

  Do not merge unless the user explicitly requests it. After merge, confirm the
  resulting `main` commit contains the fail-closed guard.

- [ ] **Step 2: Verify the post-merge push run**

  Require Android, iOS, and `Mobile validation` to run and conclude `success`
  for the merge commit's `push` event. Record the run URL.

- [ ] **Step 3: Read and save the current ruleset semantics**

  Use `gh api` to confirm the active `Protect main` ruleset ID and record its
  conditions, bypass actors, pull-request parameters, and required checks. It
  must still include `API foundation checks` and `Repository policy`.

- [ ] **Step 4: Obtain explicit authorization for the ruleset mutation**

  Present the exact before/after required-check list. Do not infer this
  authorization from permission to push or open a pull request.

- [ ] **Step 5: Add only `Mobile validation` to required status checks**

  Build the update payload from a fresh API response. Preserve `name`, `target`,
  `enforcement`, `bypass_actors`, `conditions`, every rule and parameter, and
  every existing required check. Append `{ "context": "Mobile validation" }`
  only if it is absent, then update the same ruleset through `gh api`.

- [ ] **Step 6: Read the ruleset back and compare it**

  Confirm `Mobile validation`, `API foundation checks`, and `Repository policy`
  are all required and that no unrelated ruleset field changed.

- [ ] **Step 7: Perform final authoritative verification**

  Account for every Acceptance Contract item with deterministic output or a
  live run/API URL, confirm all BLOCKER/HIGH findings are resolved, and report
  the rollback order: remove the required check first, then revert the workflow
  through a pull request.
