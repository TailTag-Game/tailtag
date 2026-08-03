# Founding Cohort GitHub Onboarding Workflow

Use one parent issue to track cohort-wide onboarding and one sub-issue for each accepted contributor.

## Parent issue

### Suggested title

```text
[Work]: Onboard the founding contributor cohort
```

### Suggested body

```markdown
## Objective

Verify that every founding-cohort contributor can access the organization, use the TailTag Rebuild Project, clone the repository, follow the contribution workflow, and complete a reviewed pull request.

## Acceptance criteria

- [ ] Every accepted contributor has an onboarding sub-issue
- [ ] Every contributor can access the TailTag organization
- [ ] Every contributor can access the main repository
- [ ] Every contributor can update the TailTag Rebuild Project
- [ ] Every contributor has completed the clone and environment checks
- [ ] Every contributor has opened a linked pull request
- [ ] Every contributor has completed the review and merge workflow
- [ ] Access or documentation problems discovered during onboarding are tracked
```

### Suggested metadata

- Type: `Task`
- Status: `In progress`
- Priority: `P1 — High`
- Phase: `1 — Foundation`
- Effort: `L`
- Cohort: `Foundational`
- Label: `area: community`

## Contributor onboarding sub-issue

### Suggested title

```text
[Work]: Complete GitHub onboarding — GITHUB_USERNAME
```

### Suggested body

```markdown
## Objective

Complete the TailTag GitHub and repository onboarding workflow.

This task validates access and provides a low-risk introduction to the same process used for normal project work.

## Steps

### Organization and Project

- [ ] Confirm access to the `TailTag-Game` organization
- [ ] Confirm access to the `TailTag Rebuild` Project
- [ ] Open the `Ready to claim` and `Current work` views
- [ ] Assign this issue to yourself
- [ ] Move this issue from `Ready` to `In progress`

### Local repository

- [ ] Clone `TailTag-Game/tailtag`
- [ ] Run `./scripts/doctor.sh`
- [ ] Read `README.md`
- [ ] Read `CONTRIBUTING.md`
- [ ] Read `docs/development/getting-started.md`

### Contribution

- [ ] Create a branch named `docs/onboard-GITHUB_USERNAME`
- [ ] Add yourself to `docs/community/founding-cohort.md`
- [ ] Commit the change
- [ ] Push the branch
- [ ] Open a draft pull request
- [ ] Include `Closes #ISSUE_NUMBER` in the pull request
- [ ] Confirm the `Repository policy` check passes
- [ ] Mark the pull request ready for review
- [ ] Address review feedback
- [ ] Complete the squash-merge workflow

### Completion

- [ ] Confirm the issue closed automatically when the pull request merged
- [ ] Confirm its Project status changed to `Done`
- [ ] Report any unclear or broken onboarding instructions

## Acceptance criteria

- The contributor can access all required GitHub resources.
- `./scripts/doctor.sh` completes without required failures.
- The contributor has completed a linked, reviewed pull request.
- The contributor understands how issues, Project status, branches, pull requests, checks, and reviews fit together.
- Any onboarding defect is documented in a separate issue.
```

### Suggested metadata

- Type: `Task`
- Status: `Ready`
- Priority: `P2 — Normal`
- Phase: `1 — Foundation`
- Effort: `XS`
- Cohort: `Foundational`
- Labels:
  - `area: community`
  - `good first issue`
- Assignee: the individual contributor

## Project view fields

Add these built-in fields to the `All work` view:

- `Parent issue`
- `Sub-issue progress`

This lets the parent issue show cohort onboarding completion directly in the Project.
