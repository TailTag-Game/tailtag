# Django API POC README Onboarding Implementation Plan

> **For agentic workers:** Execute this plan inline with review checkpoints.

**Goal:** Turn the Django API POC README into a concise onboarding guide that explains the POC, Django’s fit for TailTag, local setup, code tour, boundaries, and working agreements.

**Architecture:** Modify only `services/api-django-poc/README.md`; keep implementation details in the existing service docs and architecture report. Add the approved design spec and implementation plan as durable project documentation.

**Tech Stack:** Markdown, Django, PostgreSQL, `uv`, Docker Compose, Railway.

## Global Constraints

- Keep the POC described as an evaluation boundary, not a final production architecture.
- Preserve the PostgreSQL-only contract and validated commands.
- Keep Railway framed as disposable evaluation infrastructure.
- Do not claim final mobile authentication, gameplay behavior, or realtime architecture.
- Do not alter application code or infrastructure configuration.

---

### Task 1: Add the onboarding overview and Django-fit explanation

**Files:**
- Modify: `services/api-django-poc/README.md`

- [ ] **Step 1: Add the orientation sections**

Add `What this is`, `Why Django is a good fit for TailTag`, and `What this POC demonstrates` before the prerequisite/setup instructions. Cover relational domain data, accounts, ownership, permissions, admin, migrations, DRF/OpenAPI, contributor familiarity, and future ASGI/async options without presenting Django as a final architecture decision.

- [ ] **Step 2: Review the copy for scope accuracy**

Confirm the new text explicitly says the service is a framework evaluation and does not claim gameplay, final mobile authentication, or production launch.

### Task 2: Add a ten-minute code tour and boundaries

**Files:**
- Modify: `services/api-django-poc/README.md`

- [ ] **Step 1: Add the local quickstart framing**

Add a short `Run it in ten minutes` introduction immediately before the existing prerequisites and setup commands, preserving those commands and URLs.

- [ ] **Step 2: Add the code-tour map**

Add a `Where to explore` section mapping `config/settings/`, `accounts/`, `fursuits/`, `health/`, `tests/`, `railway.toml`, and `Dockerfile` to the concepts they demonstrate.

- [ ] **Step 3: Add intentional boundaries and working agreements**

Add sections covering excluded final decisions, PostgreSQL-only development, secrets, validation commands, Railway’s disposable adapter role, and links to `docs/architecture.md` and the issue evaluation report.

### Task 3: Verify and publish the documentation update

**Files:**
- Test: `README.md` rendering/content through repository checks

- [ ] **Step 1: Run documentation verification**

Run `./scripts/doctor.sh` from the repository root and `git diff --check`. Confirm the README contains all approved headings and no stale claims.

- [ ] **Step 2: Commit the documentation set**

Stage the README, design spec, and implementation plan, then commit with:

```bash
git add services/api-django-poc/README.md docs/superpowers/specs/2026-08-10-api-poc-readme-onboarding-design.md docs/superpowers/plans/2026-08-10-api-poc-readme-onboarding.md
git commit -m "docs: add Django API POC onboarding guide"
```

- [ ] **Step 3: Push the current branch**

```bash
git push origin feat/issue-20-local-setup
```
