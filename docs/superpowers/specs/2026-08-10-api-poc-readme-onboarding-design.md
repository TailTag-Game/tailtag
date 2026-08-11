# Django API POC README Onboarding Design

## Goal

Turn `services/api-django-poc/README.md` into a short onboarding guide for TailTag
backend contributors. A new contributor should understand why the POC is a useful
Python backend example, run it locally, and know where to explore the code in roughly
ten minutes.

## Audience

Backend contributors with mixed Python and Django experience. The guide should be
welcoming to someone unfamiliar with this service without becoming a Django tutorial
or repeating the repository-wide contributor workflow.

## README structure

1. **What this is** — describe the service as a deployable Django/PostgreSQL POC and
   state clearly that it is an evaluation boundary, not the final production
   architecture.
2. **Why Django fits TailTag** — explain the fit in terms of relational domain data,
   accounts, ownership, permissions, admin workflows, migrations, API conventions,
   and contributor accessibility. Mention that ASGI/async capabilities remain
   available if future realtime workloads require them.
3. **What the POC demonstrates** — summarize the implemented security, API, data,
   operations, deployment, testing, and typing examples.
4. **Run it in ten minutes** — retain and streamline the existing prerequisite,
   dependency, PostgreSQL, migration, server, and URL instructions.
5. **Where to explore** — map the main directories and files to the concepts they
   demonstrate.
6. **What it intentionally does not decide** — call out final mobile authentication,
   gameplay models, realtime architecture, background jobs, media storage, and high
   availability as future decisions or excluded scope.
7. **Working agreements** — preserve the quality commands, PostgreSQL-only contract,
   secret-handling guidance, and links to architecture and evaluation documentation.

## Content constraints

- Keep the overview high-level and concrete; avoid marketing language.
- Describe Django as a strong current candidate, not an irrevocable architecture
  decision.
- Do not claim that the POC implements gameplay behavior or final client auth.
- Keep Railway details framed as a disposable evaluation adapter.
- Preserve accurate commands and URLs already validated during the POC evaluation.

## Success criteria

- A new contributor can explain the POC’s purpose and Django’s fit before reading code.
- A contributor can reach the local health, API docs, and admin endpoints by following
  the guide.
- The guide provides clear next files to inspect and clear boundaries around what is
  not yet decided.
- Existing validation commands and security guidance remain accurate.
