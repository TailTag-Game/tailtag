# Django API Proof of Concept

**Status:** Draft  
**Related issue:** [#17 — Define the Django API POC](https://github.com/TailTag-Game/tailtag/issues/17)  
**Parent issue:** [#16 — Evaluate Django as TailTag’s backend framework](https://github.com/TailTag-Game/tailtag/issues/16)  
**Blocks:** [#18 — Scaffold the Django API POC](https://github.com/TailTag-Game/tailtag/issues/18)

## 1. Purpose

This document defines a limited, production-shaped Django API proof of concept for the TailTag rebuild.

The POC is intended to answer:

> Is Django a suitable primary backend framework for TailTag, particularly for contributor productivity, strict typing, API development, authentication, relational modeling, automated testing, internal administration, and deployment?

The POC is not intended to select TailTag’s complete backend architecture or validate unresolved gameplay rules.

The result should support one of three recommendations:

- **Promote:** Continue from the POC as the foundation of TailTag’s backend.
- **Revise:** Django remains promising, but identified problems must be addressed before promotion.
- **Reject:** Django introduces unacceptable friction or risk for TailTag’s needs.

## 2. Feature scope

The POC will implement one complete but narrow workflow:

1. A user signs up with an email address and password.
2. The user logs in.
3. The user retrieves their current account.
4. The user creates a fursuit profile.
5. The user lists their own fursuit profiles.
6. The user retrieves one owned fursuit profile.
7. The user edits one owned fursuit profile.
8. The user deletes one owned fursuit profile.
9. The user logs out.
10. Users cannot view or modify fursuits owned by another user.
11. Authorized staff can inspect users and fursuits through Django admin.

This scope is intentionally small enough to implement and evaluate quickly while still exercising Django’s major application-development features.

## 3. Included capabilities

### Authentication

The POC includes:

- A custom Django user model
- Email-and-password signup
- Login
- Logout
- Current-user retrieval
- Django password hashing
- Cookie-based sessions
- CSRF protection
- Duplicate-email handling
- Invalid-credential handling
- Authentication tests

### Fursuit management

The POC includes:

- Create a fursuit
- List the current user’s fursuits
- Retrieve an owned fursuit
- Partially update an owned fursuit
- Delete an owned fursuit
- Enforce ownership on every operation
- Register fursuits in Django admin
- Search and filter fursuits in Django admin

### Engineering foundation

The POC includes:

- PostgreSQL
- Django REST Framework
- OpenAPI schema generation
- Interactive API documentation
- Strict static type checking
- Formatting and linting
- Automated tests
- Database migrations
- Docker-based local development
- A production application server
- Health endpoints
- Railway deployment
- Documented setup and validation commands

## 4. Explicit exclusions

The following are outside the POC:

- Convention records
- Convention enrollment
- Catch creation or validation
- QR or NFC identifiers
- Achievements
- Tasks
- Leaderboards
- Image uploads
- Object storage
- Species taxonomy
- Multiple fursuit owners
- Fursuit transfers
- Moderation workflows
- Audit history
- Email verification
- Password recovery
- Social login
- Multifactor authentication
- JWT access or refresh tokens
- Final mobile authentication design
- Background jobs
- Redis
- Celery or another worker system
- Notifications
- Rate-limiting architecture
- Production analytics
- Full observability infrastructure
- Performance or load benchmarking

These exclusions prevent the POC from committing the project to product rules or infrastructure that have not yet been approved.

## 5. Repository placement

The proposed location is:

```text
services/
└── api-django-poc/
```

The supporting design and evaluation documentation will live under:

```text
docs/
└── architecture/
    └── backend/
        └── django-api-poc.md
```

No unrelated top-level directories should be added as part of this work.

The outer service directory explicitly identifies the implementation as a POC. Internal Python and Django names should remain neutral so the service can be promoted without renaming application packages or changing migration identities.

Proposed internal layout:

```text
services/api-django-poc/
├── config/
├── accounts/
├── fursuits/
├── tests/
├── manage.py
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── .env.example
└── README.md
```

If Django is selected, the outer directory may later be renamed from `services/api-django-poc/` to `services/api/`.

## 6. Proposed technology stack

The initial technology choices are:

- Python
- Django
- Django REST Framework
- PostgreSQL
- `uv` for dependency management and locking
- Ruff for formatting and linting
- mypy for authoritative static type checking
- `django-stubs`
- `djangorestframework-stubs`
- pytest
- pytest-django
- drf-spectacular
- Gunicorn
- Docker
- Railway

### Version-selection policy

Exact versions will not be pinned in this design issue.

Issue #18 must:

1. Verify currently supported stable Python and Django versions.
2. Verify compatibility across Django REST Framework, typing stubs, pytest tooling, OpenAPI tooling, the PostgreSQL driver, and the production server.
3. Select stable compatible version ranges in `pyproject.toml`.
4. Generate and commit `uv.lock`.
5. Record any compatibility compromise in the POC README or pull request.

The current proposal is to use Python 3.13 and Django 6.0 if the complete dependency set supports them without workarounds.

The service will initially be an independent uv project with its own `pyproject.toml` and `uv.lock`. A root uv workspace is unnecessary while the repository contains only one Python project. uv workspaces can be introduced later if the monorepo gains multiple related Python packages.

### Type checker decision

Mypy will be the authoritative CI type checker for the POC because the Django and DRF stub ecosystems provide framework-specific mypy integration.

Astral’s `ty` may be evaluated separately, but it will not replace mypy during this POC unless it demonstrates equivalent Django ORM and framework coverage.

## 7. Application boundaries

The POC will contain two domain-oriented Django applications.

### `accounts`

Responsible for:

- The custom user model
- User creation
- Email normalization
- Signup
- Login
- Logout
- Current-user responses
- User administration

### `fursuits`

Responsible for:

- The fursuit model
- Fursuit validation
- Fursuit CRUD endpoints
- Owner-based query scoping
- Ownership enforcement
- Fursuit administration

### `config`

Responsible for:

- Django settings
- Root URL routing
- WSGI and ASGI entry points
- OpenAPI configuration
- Health endpoints
- Environment configuration

No generic `api`, `core`, or `common` application should be created without a concrete responsibility.

## 8. User model

A custom user model must be created in the initial `accounts` migration.

Proposed fields:

| Field | Description |
|---|---|
| `id` | UUID primary key |
| `email` | Unique login identifier |
| `display_name` | User-facing name |
| `password` | Django-managed password hash |
| `is_active` | Whether the account may authenticate |
| `is_staff` | Whether the account may access Django admin |
| `created_at` | Creation timestamp |
| `updated_at` | Last-update timestamp |

Decisions:

- Email is the authentication identifier.
- A separate username is not required.
- Email is normalized consistently before persistence and comparison.
- Email uniqueness is enforced by the database.
- Public signup cannot set staff, superuser, or other elevated fields.
- Passwords are never stored or logged in plain text.
- The custom user model must exist before fursuit migrations depend on it.

## 9. Fursuit model

Proposed fields:

| Field | Description |
|---|---|
| `id` | UUID primary key |
| `owner` | Required foreign key to the user |
| `name` | Required display name |
| `species` | Required free-text species value |
| `description` | Optional free-text description |
| `created_at` | Creation timestamp |
| `updated_at` | Last-update timestamp |

Decisions:

- Fursuit names are not globally unique.
- Species remains free text for the POC.
- Field-length limits must be explicit.
- The API does not accept an owner ID during creation or update.
- The authenticated user is assigned as owner by the backend.
- User deletion cascades to their fursuits for the POC.
- Fursuit deletion is a hard delete for the POC.

Hard deletion is temporary. Before promotion, the project must revisit whether fursuits associated with catches, conventions, moderation actions, or audit requirements should instead be archived.

## 10. API contract

The proposed API surface is:

```http
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

GET    /health/live
GET    /health/ready
```

Route naming may change during scaffolding if a clearer repository-wide convention is adopted, but the supported operations should remain equivalent.

### Response behavior

- Successful signup returns the created user representation.
- Successful fursuit creation returns `201 Created`.
- Successful deletion returns `204 No Content`.
- Unauthenticated protected requests return `401` or the framework-standard equivalent selected and documented by the implementation.
- Invalid request data returns field-level validation errors.
- Requests for a fursuit not owned by the current user return `404 Not Found`.
- The owner field is read-only.
- User and fursuit UUIDs are exposed as opaque identifiers.
- Password fields are write-only and never returned.

The POC will initially retain DRF’s conventional validation-error format unless evaluation demonstrates a need for a custom error envelope.

## 11. Authentication and CSRF behavior

The POC will use Django session authentication.

This choice is intended to evaluate Django’s integrated account, session, permission, and administrative capabilities. It is not a decision about TailTag’s final mobile authentication transport.

### Cookie behavior

Production session cookies should be:

- `HttpOnly`
- `Secure`
- Configured with an appropriate `SameSite` policy
- Scoped as narrowly as practical

The initial assumption is `SameSite=Lax` while the API and test client are same-site.

### CSRF behavior

Unsafe session-authenticated requests must require valid CSRF protection.

This includes:

- Signup
- Login
- Logout
- Fursuit creation
- Fursuit updates
- Fursuit deletion

The implementation must document how a client obtains and submits the CSRF token.

Login and signup must use Django’s normal CSRF protections rather than assuming DRF session authentication alone protects unauthenticated requests.

### CORS

CORS middleware should not be added by default.

It should be introduced only if the deployed POC uses a browser client on a different origin. Any cross-origin cookie configuration must be explicitly documented and tested.

## 12. Authorization and ownership

The central authorization rule is:

> A user may only list, retrieve, update, or delete fursuits they own.

This rule will be enforced through:

1. Querysets scoped to the authenticated user.
2. Authentication requirements on all fursuit endpoints.
3. Read-only ownership fields.
4. Tests covering cross-user access.
5. Django admin permissions for staff-only administrative access.

The API should return `404 Not Found` when a user attempts to access another user’s fursuit. This avoids revealing whether an object owned by another user exists.

The POC should not introduce a generalized policy or authorization framework unless the implementation demonstrates a concrete need.

## 13. HTTP and application structure

Django REST Framework will handle:

- HTTP request parsing
- Runtime request validation
- Authentication integration
- Serialization
- Response generation
- Endpoint routing
- OpenAPI integration

For straightforward CRUD, DRF views, serializers, and Django models are sufficient.

The POC should not introduce:

- A generic repository abstraction over the Django ORM
- A command bus
- A mediator
- Domain events
- A dependency-injection framework
- A service layer for trivial one-line operations

Logic should be extracted into typed functions or services when it represents a meaningful workflow, is reused, or becomes difficult to test inside a view or serializer.

Critical behavior must not be hidden in Django signals or model `save()` overrides.

## 14. Static typing

Strict typing is a primary evaluation target.

The POC must configure:

```text
mypy --strict
```

with:

- `django-stubs`
- `djangorestframework-stubs`
- The appropriate Django and DRF mypy plugins

Requirements:

- TailTag-owned functions and methods are annotated.
- Public functions declare return types.
- Core code does not rely on broad `Any`.
- Untyped decorators are avoided or isolated.
- `# type: ignore` must include a narrow error code.
- Non-obvious suppressions must include an explanation.
- Type checking is a blocking CI check.
- Type-related shortcuts must be documented in the final evaluation.

Ruff should enforce formatting, linting, import rules, and selected annotation-related rules that complement mypy.

The POC should prefer ordinary typed Python constructs such as:

- Dataclasses
- Enums
- Typed dictionaries where dictionaries are appropriate
- Explicit return types
- Typed querysets and managers

It should not add artificial layers solely to increase the number of typed abstractions.

## 15. Django admin

Django admin is part of the evaluation, not incidental tooling.

### User administration

The admin should support:

- Search by email and display name
- Filtering by active and staff state
- Safe password creation and changes
- Read-only UUID and timestamps
- Prevention of accidental plain-text password handling

### Fursuit administration

The admin should support:

- Search by fursuit name
- Search by species
- Search by owner email
- Filtering by species
- Filtering by creation date
- Displaying the owner relationship
- Read-only UUID and timestamps

The final evaluation should assess whether Django admin would materially reduce the need to build early TailTag support and moderation interfaces.

## 16. OpenAPI and API documentation

The POC will use drf-spectacular to generate an OpenAPI schema.

Proposed endpoints:

```text
/api/schema/
/api/docs/
```

The generated schema must accurately describe:

- Signup requests and responses
- Login and logout behavior
- Current-user responses
- Fursuit creation and update schemas
- Read-only fields
- Authentication requirements
- UUID route parameters
- Validation errors where practical

Schema generation and validation must run in CI.

The selected drf-spectacular version should be pinned through `uv.lock`, and schema output should be reviewed when dependencies are upgraded.

## 17. Settings and configuration

Proposed settings structure:

```text
config/settings/
├── base.py
├── local.py
└── production.py
```

### Base settings

Shared settings should include:

- Installed applications
- Middleware
- Authentication model
- REST Framework configuration
- OpenAPI configuration
- Logging defaults
- Time zone and localization
- Common security settings

### Local settings

Local settings may include:

- Debug mode
- Local allowed hosts
- Local PostgreSQL connection
- Developer-friendly logging
- Local CSRF origins

### Production settings

Production settings must include:

- Debug disabled
- Explicit allowed hosts
- Secure cookie settings
- Trusted CSRF origins
- Environment-provided secrets
- Production database configuration
- Static-file configuration for Django admin
- Production logging

Required configuration should be read from environment variables and validated during startup. Missing critical production configuration should fail fast.

## 18. Database and migrations

PostgreSQL is the canonical database for:

- Local development
- CI
- Railway deployment

SQLite should not be the authoritative test environment.

Migrations must:

- Be committed to the repository.
- Be reviewed as part of pull requests.
- Create the custom user model in the initial accounts migration.
- Avoid manual edits unless justified and documented.
- Pass a CI check confirming no uncommitted model changes exist.

The deployment process should run migrations as a controlled pre-deploy step, not automatically every time a web process starts.

## 19. Testing strategy

Use pytest and pytest-django.

The test suite should prioritize API and database behavior over extensive mocking.

### Authentication tests

Include:

- Successful signup
- Duplicate-email rejection
- Password hashing
- Successful login
- Invalid credentials
- Successful logout
- Current-user retrieval
- Unauthenticated current-user request
- Public signup cannot create a staff user
- CSRF behavior for signup, login, logout, and authenticated writes

### Fursuit tests

Include:

- Successful creation
- Required-field validation
- Field-length validation
- Listing only owned fursuits
- Retrieving an owned fursuit
- Updating an owned fursuit
- Deleting an owned fursuit
- Unauthenticated access rejection
- Cross-user retrieval rejection
- Cross-user update rejection
- Cross-user deletion rejection
- Owner field cannot be reassigned through request data

### Infrastructure tests and checks

Include:

- Model and migration checks
- No pending migrations
- OpenAPI schema generation
- OpenAPI schema validation
- Health endpoint behavior
- Django system checks
- Admin model registration smoke tests

## 20. Health endpoints

The POC will expose:

```http
GET /health/live
GET /health/ready
```

### Liveness

`/health/live` confirms that the process is running and able to serve a basic response.

It should not depend on PostgreSQL.

### Readiness

`/health/ready` confirms that the application is ready to serve traffic.

It should verify database connectivity and any other dependency required for the scoped POC.

Health responses must not disclose credentials, connection strings, internal hostnames, or stack traces.

## 21. Local development

The POC should support a documented local workflow using:

- `uv`
- Docker
- PostgreSQL
- Repository scripts or commands consistent with existing project conventions

A new contributor should be able to:

1. Install the documented prerequisites.
2. Copy the environment example.
3. Start PostgreSQL.
4. Synchronize dependencies.
5. Run migrations.
6. Start the API.
7. Run checks and tests.
8. Access API documentation and Django admin.

The setup must not rely on undocumented local machine state.

## 22. Deployment shape

The POC will use two Railway services:

```text
Django API
PostgreSQL
```

No Redis, worker, scheduler, or object-storage service will be added.

The production web process will use Gunicorn unless compatibility evaluation identifies a better supported alternative.

Conceptual start command:

```text
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

The deployment must:

- Bind to Railway’s provided port.
- Run with production settings.
- Use environment-provided secrets.
- Run migrations through a controlled deployment step.
- Serve Django admin static assets correctly.
- Expose health endpoints.
- Produce useful application logs.
- Restart without manual repair.

## 23. Evaluation process

The POC is complete only after the implementation is evaluated, not merely deployed.

Evaluation should include:

- Initial setup experience
- Day-to-day development ergonomics
- Model and migration workflow
- DRF API ergonomics
- Authentication and CSRF clarity
- Strict typing friction
- Test-writing ergonomics
- OpenAPI quality
- Django admin usefulness
- Docker and Railway deployment
- Code traceability
- Amount of project-specific infrastructure required

At least one contributor who did not build the initial scaffold should complete a small modification.

Suggested exercise:

> Add an optional `color` field to the fursuit model and update the migration, API schema, admin interface, tests, and documentation.

The exercise should record:

- Setup problems
- Files that needed modification
- Framework concepts the contributor needed to learn
- Type-checking friction
- Test and migration feedback
- Any unclear project conventions

## 24. Success criteria

The POC is successful if all of the following are true:

### Setup and contributor experience

- A contributor can run the service from documented instructions.
- Required setup does not depend on undocumented manual fixes.
- The code path from route to persistence is understandable.
- A small model change can be completed without extensive maintainer coaching.

### Typing

- Strict mypy passes.
- Core application code does not depend on broad `Any`.
- Type suppressions are rare, narrow, and justified.
- Django and DRF dynamic behavior does not make routine changes unreasonably difficult.

### API quality

- Authentication and ownership behavior are explicit.
- Request and response validation is reliable.
- The generated OpenAPI schema is usable by frontend contributors or client generators.
- API errors are understandable and consistent enough for the POC.

### Database and tests

- PostgreSQL development and test workflows are reliable.
- Migrations are straightforward to create and review.
- Ownership and security rules are covered by integration tests.
- Tests remain readable and do not require excessive mocking.

### Administration

- Django admin makes users and fursuits meaningfully searchable and manageable.
- The admin demonstrates practical value for early support or operational work.

### Deployment

- Docker builds consistently.
- Railway deployment is repeatable.
- Migrations execute predictably.
- Health checks work.
- The service restarts without manual intervention.

### Architecture

- The implementation remains proportionate to the feature scope.
- Django conventions reduce work rather than obscure behavior.
- The POC can be promoted without discarding its foundational models, migrations, tests, and deployment configuration.

## 25. Rejection or revision criteria

The recommendation should be **revise** or **reject** if one or more of the following occurs:

- Strict typing requires widespread ignores or untyped boundaries.
- Routine ORM usage produces unacceptable type-checking friction.
- Authentication or CSRF behavior remains ambiguous after documentation and tests.
- Ownership enforcement is difficult to express or audit.
- The OpenAPI schema requires extensive manual correction.
- A small model change requires disproportionate or opaque modifications.
- PostgreSQL testing or migrations are unreliable.
- Django admin provides little practical value.
- Deployment requires recurring undocumented manual steps.
- The POC requires substantial custom framework infrastructure to remain maintainable.
- Contributors consistently find framework behavior difficult to trace.
- Promoting the POC would require a substantial rewrite of its foundational code.

A single inconvenience should not automatically reject Django. The final recommendation should consider the combined effect on TailTag’s V0 velocity, V1 maintainability, and contributor experience.

## 26. Temporary decisions

The following decisions apply only to the POC and must be reconsidered before promotion:

- Session authentication
- Same-origin browser assumptions
- Cookie and CORS configuration
- Lack of email verification
- Lack of password recovery
- Hard deletion of fursuits
- Cascading user deletion
- Free-text species values
- Absence of images
- Absence of convention and catch models
- Lack of background workers
- Lack of notification infrastructure
- Lack of audit history
- Lack of rate limiting
- Minimal logging and observability
- DRF as the permanent Django API layer
- Gunicorn as the permanent production server
- Separate service-level uv project rather than a root workspace
- The POC directory name and deployment naming

## 27. Promotion path

If Django is selected:

1. Record the framework decision through the approved architecture-decision process.
2. Review every temporary decision and known shortcut.
3. Create follow-up issues for production requirements.
4. Rename `services/api-django-poc/` to `services/api/`.
5. Update CI, deployment, and documentation paths.
6. Retain the user model, fursuit model, migrations, tests, admin configuration, and deployment foundation where appropriate.
7. Continue development through normal scoped issues and pull requests.

If Django is rejected:

1. Document the specific reasons.
2. Separate Django-specific problems from implementation mistakes.
3. Preserve the evaluation results in repository documentation.
4. Remove or archive the POC code after the decision is recorded.
5. Reuse the same evaluation criteria when comparing another framework.

## 28. Approval gate

Approval of this document confirms:

- The POC scope is sufficiently narrow.
- Repository placement is acceptable.
- The proposed stack may proceed to compatibility verification.
- Authentication and CSRF behavior are defined.
- User and fursuit model boundaries are defined.
- Ownership and deletion behavior are defined.
- Testing, admin, OpenAPI, and deployment expectations are defined.
- Success and rejection criteria are measurable.
- Temporary decisions are explicit.

Once approved, issue #18 may begin scaffolding the service and locking compatible dependencies.
