# V0 convention enrollment and active-convention selection

**Issue:** [#116 — Implement convention enrollment and active-convention selection](https://github.com/TailTag-Game/tailtag/issues/116)

**Parent:** [#111 — Establish V0 participation and catchability domains](https://github.com/TailTag-Game/tailtag/issues/111)

**Status:** Approved for implementation

## Goal

Allow an onboarded authenticated user to explicitly participate in a Convention and select their active Convention. At completion, an eligible player can enroll in any active Convention, list their own enrollments, activate a valid enrolled Convention as their current active gameplay context, or clear their active Convention. Operators can inspect and moderate enrollments via the Django admin.

## Existing contracts

- Clerk remains the external authentication authority.
- `accounts.User.id` remains the canonical TailTag application identity. Enrollment records never store or expose a Clerk identifier.
- The profile-owned participation predicate (`profiles.eligibility.is_participation_eligible`) is required for enrollment and active convention selection: the user must be authenticated, onboarding completed, and profile enabled.
- `/api/` remains the unversioned V0 product namespace.
- Convention operational lifecycle (`conventions.ConventionStatus`) governs convention eligibility (`ACTIVE` is playable).

## Scope

Issue #116 owns:

- The durable `ConventionEnrollment` model and migration under `conventions`.
- `UniqueConstraint` on `(user, convention)` ensuring a user can enroll in a convention at most once.
- Partial `UniqueConstraint` on `user` where `is_active=True`, ensuring at most one active convention enrollment per user at the database level.
- Owner-scoped list, enroll, get-active, set-active, and clear-active APIs under `/api/conventions/`.
- Domain services in `conventions.services` managing atomic state changes and validation.
- Profile-level participation write eligibility enforcement (HTTP 403 `PermissionDenied` when ineligible).
- Operator inspection via `conventions.admin.ConventionEnrollmentAdmin`.
- Database constraints, OpenAPI schemas (`drf-spectacular`), and comprehensive automated tests.

Issue #116 does not own:

- GPS or location detection;
- Clerk Organizations or third-party registration/ticketing integrations;
- Per-convention fursuit activation (owned by child issue #117);
- Catch mechanics and QR validation.

## Domain Model: `ConventionEnrollment`

Create `conventions.ConventionEnrollment` with this persistence contract:

| Field | Persistence contract |
| --- | --- |
| `id` | Default `BigAutoField`; stable internal primary key |
| `user` | Required `ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name="convention_enrollments")` |
| `convention` | Required `ForeignKey("conventions.Convention", on_delete=PROTECT, related_name="enrollments")` |
| `is_active` | Required `BooleanField(default=False)`; indicates active selection for gameplay |
| `created_at` | Required server-controlled creation timestamp (`auto_now_add=True`) |
| `updated_at` | Required server-controlled mutation timestamp (`auto_now=True`) |

### Database Constraints & Indexes

1. `conventions_enrollment_user_convention_unique`: `UniqueConstraint(fields=["user", "convention"])`
2. `conventions_enrollment_user_single_active`: `UniqueConstraint(fields=["user"], condition=Q(is_active=True))`
3. Ordering: `["-created_at", "id"]`

## Business Logic & Service Invariants

### 1. Eligibility Check
Any mutation (enrolling, selecting active convention, clearing active convention) checks `profiles.eligibility.is_participation_eligible(user)`. If false, raises `PermissionDenied` (HTTP 403).

### 2. Convention Enrollment (`enroll_in_convention`)
- Verifies convention exists (raises 404 if missing) and is currently `ACTIVE` (raises validation error if `status != ACTIVE`).
- Idempotent: If enrollment already exists for `(user, convention)`, returns existing enrollment without raising an error.
- Supports optional `set_active=True`: atomically clears any prior active enrollment and sets `is_active=True` on the enrollment.

### 3. Active Convention Selection (`set_active_convention`)
- Atomically selects the specified convention for the user.
- Target convention must already be enrolled by the user.
- Target convention must currently be in `ACTIVE` status.
- Atomically deactivates any existing active enrollment for that user and sets `is_active=True` on the target enrollment.

### 4. Clear Active Convention (`clear_active_convention`)
- Atomically sets `is_active=False` on all enrollments for the user.

### 5. Inactive / Ended Convention Handling
- If a convention is moved from `ACTIVE` to `PAUSED`, `COMPLETED`, or `CANCELLED` by an operator, existing enrollment rows remain intact with `is_active=True` in the database.
- Read operations expose the latest convention `status` (which reflects whether the convention is active and playable).
- Attempting to *select* or *enroll* into a non-active convention is rejected.

## API Contracts

### Endpoints Overview

| Method | Path | Summary | Description |
| --- | --- | --- | --- |
| `GET` | `/api/conventions/enrollments/` | List user enrollments | List all conventions the user is enrolled in |
| `POST` | `/api/conventions/enrollments/` | Enroll in convention | Enroll authenticated user in an active convention |
| `GET` | `/api/conventions/active/` | Get active convention | Retrieve the user's current active convention enrollment |
| `PUT` | `/api/conventions/active/` | Select active convention | Select an enrolled active convention as current |
| `DELETE` | `/api/conventions/active/` | Clear active convention | Clear active convention selection |

### Payload Schemas

#### Enrollment Representation (`ConventionEnrollmentSerializer`)
```json
{
  "id": 1,
  "convention": {
    "id": 10,
    "name": "Anthrocon 2026",
    "status": "active",
    "start_date": "2026-07-02",
    "end_date": "2026-07-05"
  },
  "is_active": true,
  "created_at": "2026-08-25T16:00:00Z"
}
```

#### Enroll Request (`ConventionEnrollRequestSerializer`)
```json
{
  "convention_id": 10,
  "set_active": false
}
```

#### Select Active Request (`SelectActiveConventionRequestSerializer`)
```json
{
  "convention_id": 10
}
```

#### Get Active Response (`ActiveConventionResponseSerializer`)
```json
{
  "enrollment": { ... } | null
}
```

## Django Admin

Register `ConventionEnrollment` with:
- `list_display = ("id", "user", "convention", "is_active", "created_at")`
- `list_filter = ("is_active", "convention__status", "convention", "created_at")`
- `search_fields = ("user__clerk_user_id", "convention__name")`
- `raw_id_fields = ("user", "convention")`
- `readonly_fields = ("created_at", "updated_at")`
