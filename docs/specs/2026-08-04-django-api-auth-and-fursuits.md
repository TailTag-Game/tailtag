# Django API POC authentication and fursuit management

**Issue:** [#19 — Implement authentication and fursuit management](https://github.com/TailTag-Game/tailtag/issues/19)  
**Status:** Approved for implementation

## Goal

Implement the Django POC's complete, same-origin browser workflow: account signup and session access, plus authenticated ownership-scoped fursuit management. The work evaluates Django's security defaults, relational modeling, REST API ergonomics, typing, administration, and testing; it does not establish TailTag gameplay or final mobile authentication architecture.

## Scope

The POC adds `accounts` and `fursuits` Django applications beneath `services/api-django-poc/`. It provides:

- a custom UUID-primary-key user model created in the initial `accounts` migration;
- email/password signup, login, logout, CSRF bootstrap, and current-user endpoints using Django sessions;
- a UUID-primary-key fursuit model owned by one user, with authenticated create, list, retrieve, partial-update, and hard-delete operations;
- owner-filtered querysets and object lookup, so cross-owner identifiers return `404 Not Found`;
- safe Django admin registration for users and fursuits;
- OpenAPI schema and interactive documentation routes; and
- model, migration, integration, admin-registration, type, lint, Django, and OpenAPI checks.

## Data and validation contract

### User

The user model contains `id`, `email`, `display_name`, Django-managed `password`, `is_active`, `is_staff`, `created_at`, and `updated_at`.

- `email` is required, valid, unique, and at most 254 characters.
- Email identity is canonicalized with `strip().lower()` before validation, persistence, and lookup. Only the canonical form is stored; `Alice@example.test` and `alice@example.test` are the same identity.
- `display_name` is required, trimmed, and 1–100 characters.
- Signup accepts only `email`, `display_name`, and `password`; it cannot set staff, superuser, or other privileged fields.
- Passwords use Django's default password hashing. Enable Django's user-attribute-similarity, minimum-length (12), common-password, and numeric-password validators. Validate at the API boundary before creating the user.
- User responses contain only `id`, `email`, `display_name`, `created_at`, and `updated_at`. Passwords and privilege fields are never returned or logged.

### Fursuit

The fursuit model contains `id`, `owner`, `name`, `species`, `description`, `created_at`, and `updated_at`.

- `name` and `species` are required, trimmed, and 1–100 characters.
- `description` is optional, trimmed, and at most 2,000 characters.
- Unicode values are supported. Required fields cannot be empty or whitespace-only.
- The API assigns the authenticated user as owner. It never accepts an owner identifier for create or update.
- Fursuit responses contain `id`, read-only `owner_id`, `name`, `species`, `description`, `created_at`, and `updated_at`.
- User deletion cascades to their fursuits. Fursuit deletion is a POC-only hard delete and must be revisited before promotion.

## HTTP contract

Routes are:

```text
GET    /api/auth/csrf
POST   /api/auth/signup
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me

POST   /api/fursuits
GET    /api/fursuits
GET    /api/fursuits/{id}
PATCH  /api/fursuits/{id}
DELETE /api/fursuits/{id}

GET    /api/schema/
GET    /api/docs/
```

`GET /api/auth/csrf` returns `204 No Content` and ensures the CSRF cookie is set.

Successful signup returns `201 Created`, establishes a session, and returns the public user representation. Successful login returns `200 OK`, establishes or rotates the session, and returns that same representation. `GET /api/auth/me` returns `200 OK` and the public user representation. Logout returns `204 No Content` after invalidating the active session.

Fursuit creation returns `201 Created`; list, retrieve, and partial update return `200 OK`; delete returns `204 No Content`. The list response is a plain JSON array with no pagination for this POC.

Protected endpoints use DRF session authentication and its conventional `403 Forbidden` response when no authenticated session is present. Requests for a fursuit outside the authenticated user's owner-filtered queryset return `404 Not Found`.

Invalid request data uses DRF's conventional field-error response shape. Duplicate signup email returns `400 Bad Request` with a stable `email` field error. Invalid credentials return `400 Bad Request` with the single generic message `Invalid email or password.` No response identifies whether the email or password was incorrect. No custom global error envelope is introduced.

## Session and CSRF contract

The API is same-origin for the POC. Browser clients first call `GET /api/auth/csrf`, then send the readable `csrftoken` cookie value in the `X-CSRFToken` header and use `credentials: "include"` for every unsafe request: signup, login, logout, fursuit create, update, and delete.

The session cookie is `HttpOnly`; production additionally sets `Secure` and starts with `SameSite=Lax`. The CSRF cookie remains JavaScript-readable so same-origin browser clients can submit the header. CSRF failures return JSON `403 Forbidden` with `{"detail":"CSRF validation failed."}` and do not disclose the internal reason. No endpoint is CSRF-exempt.

CORS and cross-origin cookie support are out of scope. They require an explicit future design and boundary tests.

## Administration

Use Django's `UserAdmin` password workflow rather than handling plaintext passwords in a generic admin form. User admin supports search by email and display name, filters by active and staff state, and read-only UUID and timestamp fields.

Fursuit admin displays name, species, owner, and timestamps; searches name, species, and owner email; filters by species and creation date; uses `select_related("owner")`; and keeps UUID and timestamps read-only. The owner is read-only for existing fursuits to avoid accidental reassignment.

## Non-goals

This issue does not add email verification or recovery, social login, JWTs, MFA, account linking, final mobile-token architecture, CORS, images, convention or catch behavior, QR/NFC identifiers, species taxonomy, multiple owners, transfers, moderation, audit history, rate limiting, Railway deployment, or gameplay validation.

## Acceptance and verification

Tests and checks must demonstrate:

- password hashing, password validation, canonical-email uniqueness, signup session creation, generic invalid-login failure, logout invalidation, and unauthenticated `me` rejection;
- CSRF bootstrap, accepted valid tokens, and rejection of missing/invalid tokens on all unsafe session endpoints;
- fursuit validation, authenticated-only access, owner-only list results, owned retrieve/update/delete, cross-owner `404`, and immutable API ownership;
- committed custom-user and fursuit migrations, migration consistency, model constraints, and Django admin registration;
- an OpenAPI schema that describes authentication, CSRF expectations, public representations, request bodies, success responses, and documented errors; and
- Ruff, strict mypy, PostgreSQL-backed pytest, Django checks, migration checks, and OpenAPI validation.

## Risks and future decisions

The sensitive boundaries are password handling, CSRF enforcement, session lifecycle, and non-disclosing ownership checks. Integration tests must cover each boundary rather than relying only on unit tests.

Before the POC is promoted, reconsider session/CORS and cookie settings, hard deletion and cascading user deletion, email verification and recovery, audit history, rate limiting, the final client authentication transport, and whether DRF/Gunicorn remain permanent choices.
