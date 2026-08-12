# Use Django and DRF for the backend

**Status:** accepted

## Context and constraints

TailTag needs a contributor-friendly Python backend with relational data, a conventional HTTP API, strong server-side validation, and a practical foundation for V0. The completed Django POC evaluated these concerns but included deliberately temporary product behavior.

## Decision

Use Python, Django, and Django REST Framework for the V0 backend. Phase 0 will preserve useful engineering foundation from the POC while resetting POC-only product behavior and promoting the result into `services/api`. The POC is not wholesale production code.

## Alternatives considered

Keep evaluating another framework, use a different Python web framework, or promote the POC unchanged.

## Consequences and risks

Django and DRF provide a coherent ORM, API, administration, and testing foundation. The team must define V0 contracts separately and avoid carrying temporary POC choices forward by accident.

## Validation and future migration

Phase 0 validates the promoted foundation and local workflow. A future framework change remains possible if approved requirements or contributor experience show that Django/DRF no longer fits.
