# Contributing to TailTag

Thank you for contributing to the TailTag rebuild.

This project is being developed by a community with a wide range of experience levels and availability. Our process is designed to keep work visible, decisions understandable, and contributions reviewable.

## Before contributing

All participants must follow the TailTag Code of Conduct.

Accepted contributors should also complete the current contributor onboarding process before requesting repository access or claiming internal work.

Before beginning an issue:

1. Read the issue, linked documentation, and acceptance criteria.
2. Confirm its Project status is `Ready`.
3. Check that it is not already assigned.
4. Assign yourself or coordinate ownership in the relevant Discord channel.
5. Ask for clarification before implementation when requirements remain ambiguous.

Do not begin substantial implementation from an unapproved Discord discussion, draft proposal, or general feature idea.

## Finding work

The primary sources of actionable work are:

* The `Ready to claim` Project view
* Issues labeled `good first issue`
* Issues labeled `help wanted`
* Work assigned through an active squad or project discussion

A `good first issue` should be narrow, documented, and achievable without extensive knowledge of the system.

`help wanted` means maintainers are actively seeking a contributor, but the issue may still require meaningful project context.

## Issue types

TailTag uses these organization issue types:

* `Bug` — unexpected or incorrect behavior
* `Feature` — a new capability or meaningful behavior change
* `Task` — defined engineering, design, documentation, research, testing, or operational work

Use the repository’s issue forms rather than opening an unstructured issue whenever possible.

Do not report security vulnerabilities through public issues. Follow the Security Policy.

## Planning fields

Issues may use the following planning metadata:

* `Status` — current workflow state
* `Priority` — relative importance
* `Phase` — rebuild phase
* `Effort` — estimated size and uncertainty
* `Cohort` — contributor intake grouping where relevant
* `Type` — Bug, Feature, or Task

Only maintainers and authorized project contributors should reprioritize work or move it into `Ready`.

## Branches

Create a separate branch for each issue or coherent change.

Use a concise branch name with a category prefix:

```text
feat/convention-enrollment
fix/duplicate-catch
docs/local-development
test/catch-service
chore/update-dependencies
```

Recommended prefixes:

* `feat/` — new product behavior
* `fix/` — bug fixes
* `docs/` — documentation
* `test/` — tests and testing infrastructure
* `refactor/` — internal restructuring without intended behavior changes
* `chore/` — maintenance, tooling, or configuration
* `spike/` — time-boxed investigation or prototype

Do not work directly on `main`.

## Scope

Keep each pull request focused on one coherent change.

A pull request should normally:

* Address one issue or tightly related set of acceptance criteria
* Avoid unrelated cleanup
* Avoid reformatting unaffected files
* Include tests where behavior changes
* Update relevant documentation
* Identify follow-up work instead of expanding indefinitely

Large issues should be divided before implementation when they cannot be reviewed safely as one change.

## Commits

Write commit messages that describe the intent of the change.

Examples:

```text
feat(mobile): add convention enrollment screen
fix(api): prevent duplicate catches
docs: document local database setup
test(auth): cover expired session handling
chore: update development dependencies
```

Branch commit history may be iterative. Pull requests are squash-merged, so the pull-request title must clearly describe the final change.

## Pull requests

Open a draft pull request when early feedback would materially reduce risk. Mark it ready for review only when:

* The intended scope is implemented
* The branch is reasonably clean
* Relevant tests pass
* Documentation is updated
* The pull-request template is completed
* Known limitations are disclosed

Link the relevant issue using a supported closing keyword:

```text
Closes #123
```

Pull-request titles should follow approximately the same convention as commit messages:

```text
feat(mobile): add convention enrollment flow
fix(api): reject duplicate catches
docs: add contributor environment guide
```

## Validation

Every pull request must explain how the change was validated.

Depending on the work, validation may include:

* Automated tests
* Type checking
* Linting
* Build validation
* Manual application testing
* Device or browser testing
* Database migration checks
* Screenshots or recordings
* Documentation review
* Accessibility review
* Security analysis

Do not state that a change is tested without describing what was run or inspected.

## Review

Reviewers should evaluate:

* Correctness
* Alignment with the linked issue
* Test coverage
* Security and privacy implications
* User experience
* Maintainability
* Documentation
* Scope discipline

Review feedback should be specific and actionable.

Contributors should either implement requested changes or explain why a different approach is preferable. Resolve conversations only after the underlying concern has been addressed.

## Merging

The `main` branch is protected.

Changes must be merged through pull requests using squash merge. Direct pushes, force pushes, and deletion of `main` are blocked.

During the founding stage, the repository may allow pull requests with zero required approvals because the project currently has one maintainer. Required code-owner review will be enabled when another reliable maintainer is available.

A pull request must still satisfy all enabled repository rules and automated checks before merging.

## Documentation and decisions

Use:

* GitHub Issues for actionable work
* Pull requests for implementation and review
* Discord for active discussion and coordination
* Notion for durable product, process, and organizational documentation
* Repository documentation for technical information that must remain synchronized with the code

Significant architectural decisions should be documented through the project’s approved decision process before implementation.

## Getting help

Accepted contributors should ask questions in the appropriate TailTag Discord help or squad channel.

When asking for help, include:

* The issue or pull-request link
* What you are trying to accomplish
* What you already attempted
* Relevant errors or sanitized logs
* The specific point where you are blocked
