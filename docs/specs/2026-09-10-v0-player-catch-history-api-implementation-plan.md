# V0 Player Catch-History API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the one private, read-only `GET /api/catches/` contract approved
for Issue #177, backed directly by the authenticated player's durable Catch
rows.

**Architecture:** Extend the existing `catches` Django app with one strict query
serializer, one focused page-number paginator, one safe response projection, and
one authenticated read view. The view begins with an owner-scoped, eager-loaded
Catch queryset, optionally narrows it by an independently validated Convention,
and delegates counting/page links to the paginator. Explicit schema carriers
keep the generated OpenAPI contract closed without changing global DRF behavior.

**Tech Stack:** Python 3.13, Django 6.0, Django REST Framework 3.17.2,
drf-spectacular, PostgreSQL, pytest/pytest-django, Ruff, Pyright, and Semgrep.

**Canonical specification:**
[`docs/specs/2026-09-10-v0-player-catch-history-api.md`](./2026-09-10-v0-player-catch-history-api.md)

## Global Constraints

- `Catch` remains the only durable collection/history source of truth.
- The only new public resource is authenticated `GET /api/catches/`; do not add
  `/collection/` or another history route.
- The request accepts only optional `convention_id`, `page`, and `page_size`
  parameters, each at most once and using positive ASCII decimal digits.
- Pagination defaults to 20 and rejects a `page_size` greater than 100.
- Ordering is server-owned and exactly `-caught_at, -id`.
- `catch_count` is the total matching row count before pagination, never page
  length and never a caught/total denominator.
- The base queryset derives ownership only from
  `request.user`/`Catch.catcher_user`; no client-selected identity is accepted.
- Every entry exposes exactly Catch `id`, fursuit `id`, `name`, `photo_url`,
  Convention `id`, `name`, and `caught_at`.
- Photo reads reuse `media.service.read_image_url`; no nullable/omitted/public
  fallback is allowed and signing failure returns a sanitized whole-request 500.
- Do not change models, migrations, indexes, services, dependencies, settings,
  global exception/pagination behavior, or #174–#176 semantics.
- No production implementation begins until the independent acceptance tests
  are authored and the parent approves their traceability and adequacy.
- Immediately before every commit, `git var GIT_AUTHOR_IDENT` and
  `git var GIT_COMMITTER_IDENT` must both report exactly
  `Finn the Panther <finn@finnthepanther.com>` before the timestamp suffix. Any
  mismatch is a fatal stop under the TailTag identity boundary.

---

## ADW phase ledger

- **Scope:** STANDARD COMPACT
- **Assurance:** SECURITY, TEST ADEQUACY
- **Completed:** issue/source reconnaissance; approved public design; frozen
  Acceptance Contract; frozen Test Surface Contract; Scope Guard; this
  implementation plan
- **Next:** environment-ready baseline; independent test authorship;
  test-adequacy and scope approval
- **Pending:** production implementation; focused deterministic gate; full
  `make api-check`; plausible-mutant analysis; fresh compact review; parent
  authoritative verification
- **Skipped:** schema migration/rehearsal, performance benchmark infrastructure,
  browser QA, and Railway deployment validation because #177 changes only a
  backend read contract and #179 owns deployed Wave 3 validation

## Planned file map

| File | Responsibility |
| --- | --- |
| `services/api/tests/catch_history_test_support.py` | Issue-local fixture creation for many Catch rows without expanding shared test infrastructure |
| `services/api/tests/test_catch_history_api.py` | Runtime authentication, privacy, filtering, ordering, pagination, schema, media, failure, read-only, and query-count acceptance tests |
| `services/api/tests/test_catch_history_openapi.py` | Exact generated OpenAPI acceptance tests and alternate-route/selector absence |
| `services/api/catches/serializers.py` | Strict query parsing, closed schema constants/carriers, typed safe entry projection |
| `services/api/catches/pagination.py` | Bounded page-number pagination and renamed closed response envelope |
| `services/api/catches/views.py` | Authenticated owner-scoped query orchestration, Convention distinction, error mapping, and sanitized failure boundary |
| `services/api/catches/urls.py` | Register the empty app-relative path as `catch-history` while preserving `confirm/` |

No other file is expected to change. If implementation needs another production
or shared-test file, return to the parent for a scope decision before editing it.

### Task 1: Establish the environment-ready baseline

**Files:** None.

**Interfaces:**

- Consumes: the committed dependency lockfiles, local PostgreSQL configuration,
  and repository-owned validation commands.
- Produces: fresh evidence that test authors and implementers start from a
  working baseline rather than inheriting an unrelated failure.

- [ ] **Step 1: Confirm the focused branch and clean tree**

  Run:

  ```bash
  git status --short --branch
  ```

  Expected: branch `feat/player-catch-history-api` and no uncommitted paths.

- [ ] **Step 2: Confirm locked tools and dependencies are callable**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync python --version
  uv --directory services/api run --locked --no-sync pytest --version
  uv --directory services/api run --locked --no-sync ruff --version
  uv --directory services/api run --locked --no-sync pyright --version
  ```

  Expected: all four commands exit 0 without changing `uv.lock`.

- [ ] **Step 3: Run the authoritative pre-change backend baseline**

  Run:

  ```bash
  make api-check
  ```

  Expected: format, lint, strict typing, Semgrep, PostgreSQL-backed tests,
  Django checks, migration drift, OpenAPI validation, and Gunicorn configuration
  all pass. Any pre-existing failure stops test dispatch until classified.

### Task 2: Author independent runtime acceptance tests

**Ownership:** The independent `test_author` owns only the three test files
listed in Tasks 2 and 3. It must not edit production code or weaken #174–#176
tests.

**Files:**

- Create: `services/api/tests/catch_history_test_support.py`
- Create: `services/api/tests/test_catch_history_api.py`

**Interfaces:**

- Consumes: frozen AC-01 through AC-12, AC-14, and AC-15; public Django ORM;
  `tests.authentication_support.force_authenticated_client`; existing
  `tests.catch_test_support.create_catch`; and
  `catches.serializers.media_service.read_image_url` as the sole allowed media
  mock boundary.
- Produces: deterministic RED tests for the exact runtime contract; an
  issue-local `create_history_catch` fixture helper used only by the new
  history tests.

- [ ] **Step 1: Add an issue-local fixture factory**

  Create `catch_history_test_support.py` with this public signature:

  ```python
  @dataclass(frozen=True)
  class HistoryCatch:
      catch: Any
      fursuit: Fursuit
      convention: Convention


  def create_history_catch(
      *,
      catcher_user: User,
      ordinal: int,
      convention: Convention | None = None,
      caught_at: datetime.datetime | None = None,
  ) -> HistoryCatch:
      """Create one valid, uniquely targeted Catch for history API tests."""
  ```

  The function must create a unique target owner, non-null-photo fursuit,
  activation, and catch session. When `convention` is supplied, the activation
  and session use it; otherwise it creates a Convention. It creates the Catch
  through the existing `create_catch` helper and uses `QuerySet.update()` plus
  `refresh_from_db()` when `caught_at` is supplied because `auto_now_add` owns
  normal creation timestamps. Photo keys use deterministic valid values derived
  from `ordinal`; no real media object or signed URL is created.

- [ ] **Step 2: Add authentication, route, and privacy tests**

  Add tests named
  `test_catch_history_requires_repository_bearer_authentication`,
  `test_catch_history_returns_only_the_authenticated_players_rows`,
  `test_catch_history_rejects_client_selected_identity`, and
  `test_catch_history_is_read_only`. Parameterize the identity-selector test
  with:

  ```python
  ("user_id", "catcher_id", "player_id", "owner_id", "clerk_user_id")
  ```

  Parameterize the read-only test with:

  ```python
  ("post", "put", "patch", "delete")
  ```

  The authentication test uses a real synthetic Bearer header with
  `fake_clerk_session_verification`, not only `force_authenticate`. The isolation
  test interleaves at least two catches for the authenticated user with a catch
  belonging to another user and asserts both `results` IDs and `catch_count`.
  Every forbidden selector must return exactly:

  ```python
  {
      "code": "invalid_query",
      "detail": "The catch-history query is invalid.",
  }
  ```

  The method tests assert HTTP 405 and an unchanged Catch row count.

- [ ] **Step 3: Add all-time, Convention, and query-closure tests**

  Add tests named `test_catch_history_reports_all_time_matching_count`,
  `test_catch_history_filters_the_owner_scoped_query_by_convention`,
  `test_catch_history_distinguishes_missing_from_existing_empty_convention`, and
  `test_catch_history_rejects_every_noncanonical_query`. Parameterize the query
  test with exactly:

  ```python
  (
      "unknown=1",
      "convention_id=",
      "convention_id=abc",
      "convention_id=0",
      "convention_id=-1",
      "convention_id=%2B1",
      "convention_id=%201",
      "convention_id=1.0",
      "convention_id=1e2",
      "page=",
      "page=last",
      "page=0",
      "page=-1",
      "page_size=",
      "page_size=0",
      "page_size=101",
      "page=1&page=2",
      "page_size=20&page_size=10",
      "convention_id=1&convention_id=2",
  )
  ```

  The Convention test creates catches for the same player in two existing
  Conventions and another player's catch in the requested Convention; only the
  authenticated player's requested-Convention rows count. Missing Convention
  returns exact `convention_not_found`; existing-empty returns exact 200 empty
  envelope. Every invalid query returns the same exact `invalid_query` body and
  does not echo the query.

- [ ] **Step 4: Add deterministic ordering and pagination tests**

  Add tests named
  `test_catch_history_orders_newest_first_with_descending_id_tie_breaker`,
  `test_catch_history_uses_default_twenty_item_pages_and_total_count`,
  `test_catch_history_accepts_explicit_page_size_through_one_hundred`,
  `test_catch_history_links_retain_convention_scope_and_page_size`,
  `test_catch_history_returns_closed_invalid_page_for_out_of_range_page`, and
  `test_catch_history_accepts_the_first_page_of_an_empty_scope`.

  Arrange equal timestamps with approved `QuerySet.update()`. Assert the entire
  ordered ID sequence, disjoint stable page contents, `catch_count` on every
  page, exact `next`/`previous` nullability, and that scoped links contain only
  `convention_id`, `page`, and `page_size`. The 100-item test creates 101 catches,
  requests `page_size=100`, and proves the first page has 100 results while the
  total remains 101. The out-of-range response is exactly:

  ```python
  {
      "code": "invalid_page",
      "detail": "The requested page does not exist.",
  }
  ```

- [ ] **Step 5: Add exact projection and media-boundary tests**

  Add tests named `test_catch_history_projects_only_the_approved_closed_fields`,
  `test_catch_history_generates_one_fresh_photo_url_per_result`, and
  `test_catch_history_sanitizes_photo_url_generation_failure`.

  Patch only the approved media function with a deterministic return such as
  `/api/media/images/fake-read`; assert the API makes it absolute through the
  request boundary. Assert exact key sets for envelope, entry, fursuit, and
  Convention; RFC 3339 UTC `caught_at`; and absence of every forbidden field or
  term from the serialized body. The success test asserts one media call per
  result and the exact expected photo keys. The failure test raises an exception
  containing synthetic secret-like material and asserts only the frozen 500
  body, no partial `results`, and one fixed sanitized log record containing none
  of the exception text, photo key, URL/signature material, IDs, or query values.

- [ ] **Step 6: Add occupancy-independent database query coverage**

  Add a test named
  `test_catch_history_database_queries_do_not_grow_with_page_occupancy`.

  Use `CaptureQueriesContext(connection)` around only each forced-authenticated
  `GET`, with the deterministic media fake active. Make both requests
  Convention-filtered so they execute equivalent existence/count/page paths.
  Compare a Convention containing one row with another containing 20 rows and
  assert equal query counts, successful serialization, and result lengths 1 and
  20. Also inspect captured SQL to require a Catch page query joining both the
  fursuit and Convention tables; this makes removal of either `select_related`
  fail instead of allowing a false-positive constant query count.

- [ ] **Step 7: Run the runtime tests and preserve the expected RED state**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_catch_history_api.py
  ```

  Expected: collection succeeds, then tests fail because `GET /api/catches/`
  is not registered/implemented. Failures caused by broken fixtures, imports,
  database setup, or assertions are test defects and must be corrected before
  approval.

- [ ] **Step 8: Commit only the runtime acceptance-test unit**

  After the required Git identity verification, run:

  ```bash
  git add services/api/tests/catch_history_test_support.py \
    services/api/tests/test_catch_history_api.py
  git commit -m "test(api): define player catch history behavior"
  ```

### Task 3: Author independent OpenAPI acceptance tests

**Files:**

- Create: `services/api/tests/test_catch_history_openapi.py`

**Interfaces:**

- Consumes: frozen AC-01, AC-02, AC-06 through AC-11, AC-13 through AC-15 and
  the generated `/api/schema/` document.
- Produces: deterministic RED tests that reject permissive parameters, schemas,
  unsafe fields, alternate history resources, or changes to confirmation.

- [ ] **Step 1: Add exact path, operation, and security assertions**

  Add a test named
  `test_catch_history_openapi_has_one_closed_bearer_get_contract`.

  Load and dereference the generated schema using the established helper pattern
  from `test_catch_confirmation_openapi.py`. Assert `/api/catches/` exists with
  exactly `get`; `/api/catches/confirm/` remains exactly `post`; no schema path
  contains `collection`; the history operation has the sole repository Bearer
  security requirement and no `requestBody`.

- [ ] **Step 2: Add exact query-parameter assertions**

  Add a test named
  `test_catch_history_openapi_documents_only_the_frozen_query_parameters`.

  Assert exact parameter names and query location:

  ```python
  {
      "convention_id": {"type": "integer", "minimum": 1},
      "page": {"type": "integer", "minimum": 1, "default": 1},
      "page_size": {
          "type": "integer",
          "minimum": 1,
          "maximum": 100,
          "default": 20,
      },
  }
  ```

  Require every parameter to be optional, single-valued, and described as
  accepting canonical positive ASCII decimal input. Assert no ordering or
  player/catcher/owner/provider selector exists.

- [ ] **Step 3: Add exact success-schema assertions**

  Add a test named
  `test_catch_history_openapi_has_the_exact_closed_success_projection`.

  Assert HTTP 200 has only `application/json`; every object has
  `additionalProperties: false`; all fields are required; and the exact nested
  shape is:

  ```text
  catch_count: integer, minimum 0
  next: string(uri), nullable
  previous: string(uri), nullable
  results[]:
    id: integer, readOnly
    fursuit:
      id: integer, readOnly
      name: string, readOnly
      photo_url: string(uri), readOnly
    convention:
      id: integer, readOnly
      name: string, readOnly
    caught_at: string(date-time), readOnly
  ```

  Serialize the operation and transitive schemas and reject forbidden identity,
  credential, lifecycle, progression, rarity, leaderboard, denominator,
  collection-entry, and mutable/write material.

- [ ] **Step 4: Add exact response/error assertions**

  Add a test named
  `test_catch_history_openapi_documents_every_closed_response`.

  Assert response statuses are exactly `200`, `400`, `401`, `404`, and `500`.
  Assert 400 permits only `invalid_query`, 404 permits exactly
  `convention_not_found | invalid_page`, 500 permits only `server_error`, and
  each domain/error object is closed with exactly `code` and `detail`.
  Authentication retains the closed `detail`-only schema. Descriptions must
  distinguish missing Convention from existing-empty scope, define
  `catch_count`, state `-caught_at, -id`, and document whole-request failure for
  photo URL signing.

- [ ] **Step 5: Run the OpenAPI tests and preserve the expected RED state**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_catch_history_openapi.py
  ```

  Expected: collection succeeds, then assertions fail because the history GET
  operation and schemas are absent. Fix only test defects before approval.

- [ ] **Step 6: Commit only the OpenAPI acceptance-test unit**

  After the required Git identity verification, run:

  ```bash
  git add services/api/tests/test_catch_history_openapi.py
  git commit -m "test(api): freeze player catch history schema"
  ```

### Task 4: Parent test-adequacy and scope gate

**Files:** No production files.

**Interfaces:**

- Consumes: Tasks 2–3 RED tests, frozen AC-01 through AC-15, and the
  traceability table in the canonical specification.
- Produces: explicit parent approval or a bounded test-only revision request.

- [ ] **Step 1: Verify traceability**

  Produce a table mapping every new test function to at least one AC item or the
  SECURITY/TEST ADEQUACY modifiers. Reject unmapped tests and identify any AC
  item without negative as well as positive evidence.

- [ ] **Step 2: Perform plausible-mutant review before implementation**

  Confirm the tests reject at least these incorrect implementations:

  ```text
  unscoped Catch.objects.all()
  filtering from a client-supplied catcher ID
  checking Convention only inside the owner-scoped Catch query
  catch_count = len(current_page)
  ordering only by -caught_at
  silently accepting/clamping malformed or over-maximum parameters
  returning DRF's default count envelope
  omitting select_related("fursuit", "convention")
  exposing Convention status or Catch provenance
  returning a null/partial photo result after signing failure
  leaking exception text, object key, or signed URL in logs
  adding GET behavior to /api/catches/confirm/ or a /collection/ route
  ```

- [ ] **Step 3: Approve the tests without changing production code**

  Record approval only when tests fail for the expected missing-behavior reasons,
  every test maps to approved scope, and no test invents a production seam. The
  approved tests become immutable implementation inputs; implementers may not
  weaken them to obtain GREEN.

### Task 5: Implement strict query parsing and safe response projection

**Ownership:** A fresh `implementer` owns only the production files listed in
Tasks 5–7. It receives the frozen specification, this plan, and the approved
tests; it must not edit acceptance tests.

**Files:**

- Modify: `services/api/catches/serializers.py`

**Interfaces:**

- Consumes: raw DRF `Request.query_params`, a fully eager-loaded `Catch`, and the
  existing `media.service.read_image_url` boundary.
- Produces:
  `CatchHistoryQuery(convention_id: int | None, page: int, page_size: int)`,
  `parse_catch_history_query(request) -> CatchHistoryQuery`,
  `catch_history_entry_data(catch, *, request) -> CatchHistoryEntryData`, exact
  schema constants, and drf-spectacular carrier serializers.

- [ ] **Step 1: Run the focused RED tests**

  Run Tasks 2–3 test commands and confirm only the approved missing history
  behavior fails.

- [ ] **Step 2: Add strict typed query parsing**

  Implement a frozen dataclass and parser equivalent to:

  ```python
  @dataclass(frozen=True)
  class CatchHistoryQuery:
      convention_id: int | None
      page: int
      page_size: int


  class CatchHistoryQueryError(ValueError):
      """The public catch-history query is not canonical."""


  def parse_catch_history_query(request: Request) -> CatchHistoryQuery:
      allowed = {"convention_id", "page", "page_size"}
      values = dict(request.query_params.lists())
      if set(values) - allowed or any(len(items) != 1 for items in values.values()):
          raise CatchHistoryQueryError

      def positive(name: str, *, default: int | None = None, maximum: int | None = None) -> int | None:
          items = values.get(name)
          if items is None:
              return default
          raw = items[0]
          if not raw.isascii() or not raw.isdigit():
              raise CatchHistoryQueryError
          parsed = int(raw)
          if parsed < 1 or (maximum is not None and parsed > maximum):
              raise CatchHistoryQueryError
          return parsed

      return CatchHistoryQuery(
          convention_id=positive("convention_id"),
          page=cast(int, positive("page", default=1)),
          page_size=cast(int, positive("page_size", default=20, maximum=100)),
      )
  ```

  Keep error details out of the exception so accidental logging cannot echo raw
  input. Add strict typing without `Any` in the production parser.

- [ ] **Step 3: Add the exact projection and schema carriers**

  Add typed nested response dictionaries and
  `catch_history_entry_data(catch: Catch, *, request: Request)`. It must read
  only eager-loaded `catch.fursuit` and `catch.convention`, format `caught_at` in
  UTC, call `media_service.read_image_url(catch.fursuit.photo_key)` once, wrap a
  relative development URL with `request.build_absolute_uri`, and return the
  exact approved keys.

  Add direct schema constants for the success envelope and 400/401/404/500
  responses. Add serializer-extension carriers following the existing
  `CatchConfirmationResponseSchemaSerializer` pattern. Every object must be
  closed and every approved field required; `next` and `previous` are required
  nullable URI strings.

- [ ] **Step 4: Run static checks for the serializer unit**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync ruff format --check catches/serializers.py
  uv --directory services/api run --locked --no-sync ruff check catches/serializers.py
  uv --directory services/api run --locked --no-sync pyright catches/serializers.py
  ```

  Expected: all pass. Runtime tests remain RED because the view and route do not
  exist yet.

- [ ] **Step 5: Commit the serializer and projection unit**

  After the required Git identity verification, run:

  ```bash
  git add services/api/catches/serializers.py
  git commit -m "feat(api): define catch history contracts"
  ```

### Task 6: Implement bounded pagination

**Files:**

- Create: `services/api/catches/pagination.py`

**Interfaces:**

- Consumes: an already validated request and ordered Catch queryset.
- Produces:
  `CatchHistoryPagination(PageNumberPagination)`,
  `paginate_queryset(queryset, request, view=None)`, and
  `get_paginated_response(data) -> Response` with exact
  `catch_count/next/previous/results` keys.

- [ ] **Step 1: Add the focused paginator**

  Implement:

  ```python
  class CatchHistoryPagination(PageNumberPagination):
      page_size = 20
      page_query_param = "page"
      page_size_query_param = "page_size"
      max_page_size = 100
      last_page_strings: tuple[str, ...] = ()

      def get_paginated_response(self, data: list[CatchHistoryEntryData]) -> Response:
          return Response(
              {
                  "catch_count": self.page.paginator.count,
                  "next": self.get_next_link(),
                  "previous": self.get_previous_link(),
                  "results": data,
              }
          )
  ```

  Before calling DRF pagination, the view must validate the query. Set the
  paginator instance's `page_size` from the validated `CatchHistoryQuery` so the
  framework does not reinterpret or clamp raw input. Do not add global
  `REST_FRAMEWORK` pagination settings.

- [ ] **Step 2: Run focused static checks**

  Run Ruff format/lint and Pyright against `catches/pagination.py`. Expected:
  all pass.

- [ ] **Step 3: Commit the paginator unit**

  After the required Git identity verification, run:

  ```bash
  git add services/api/catches/pagination.py
  git commit -m "feat(api): add bounded catch history pagination"
  ```

### Task 7: Implement the authenticated history view, URL, and OpenAPI operation

**Files:**

- Modify: `services/api/catches/views.py`
- Modify: `services/api/catches/urls.py`

**Interfaces:**

- Consumes: `parse_catch_history_query`, `CatchHistoryPagination`,
  `catch_history_entry_data`, `Catch`, `Convention`, and the existing
  repository authentication classes.
- Produces: `CatchHistoryView` at app-relative `""`, URL name
  `catch-history`, operation ID `catch_history_list`, and exact documented
  200/400/401/404/500 responses.

- [ ] **Step 1: Add the owner-scoped read flow**

  Implement a GET flow equivalent to:

  ```python
  query = parse_catch_history_query(request)
  catches = (
      Catch.objects.filter(catcher_user=_user(request))
      .select_related("fursuit", "convention")
      .order_by("-caught_at", "-id")
  )
  if query.convention_id is not None:
      if not Convention.objects.filter(pk=query.convention_id).exists():
          return _domain_error(
              "convention_not_found",
              "The convention was not found.",
              status.HTTP_404_NOT_FOUND,
          )
      catches = catches.filter(convention_id=query.convention_id)

  paginator = CatchHistoryPagination()
  paginator.page_size = query.page_size
  page = paginator.paginate_queryset(catches, request, view=self)
  data = [catch_history_entry_data(catch, request=request) for catch in page]
  return paginator.get_paginated_response(data)
  ```

  Catch `CatchHistoryQueryError` as the frozen 400 response. Translate only
  paginator `NotFound` to the frozen `invalid_page` 404. Catch every unexpected
  database/projection/pagination failure as the frozen sanitized 500. Keep a
  separate fixed `"Unexpected catch history failure."` log helper rather than
  changing #176's catch-confirmation logging behavior.

- [ ] **Step 2: Register only the approved route**

  In `catches/urls.py`, add:

  ```python
  path("", CatchHistoryView.as_view(), name="catch-history")
  ```

  Preserve `path("confirm/", CatchConfirmationView.as_view(),
  name="catch-confirm")` unchanged.

- [ ] **Step 3: Document the exact operation**

  Apply `@extend_schema` to `get` with explicit `OpenApiParameter` definitions
  for `convention_id`, `page`, and `page_size`, `request=None`, tag `catches`,
  operation ID `catch_history_list`, and exact response schema carriers. Use one
  closed 404 schema whose code enum is exactly
  `convention_not_found | invalid_page`; descriptions must preserve the frozen
  missing-versus-empty distinction and signing-failure behavior.

- [ ] **Step 4: Run the focused API and OpenAPI tests**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_catch_history_api.py \
    tests/test_catch_history_openapi.py \
    tests/test_catch_confirmation_api.py \
    tests/test_catch_confirmation_openapi.py
  ```

  Expected: all pass. Do not edit the approved history tests or existing
  confirmation tests to obtain GREEN.

- [ ] **Step 5: Commit the route and view unit**

  After the required Git identity verification, run:

  ```bash
  git add services/api/catches/views.py services/api/catches/urls.py
  git commit -m "feat(api): expose private player catch history"
  ```

### Task 8: Deterministic verification and assurance review

**Files:** All files changed by Tasks 2–7; no new scope.

**Interfaces:**

- Consumes: complete cohesive Issue #177 diff.
- Produces: deterministic evidence and a review-ready change with every AC item
  accounted for.

- [ ] **Step 1: Run the narrow deterministic gate**

  Run:

  ```bash
  uv --directory services/api run --locked --no-sync ruff format --check \
    catches tests/catch_history_test_support.py \
    tests/test_catch_history_api.py tests/test_catch_history_openapi.py
  uv --directory services/api run --locked --no-sync ruff check \
    catches tests/catch_history_test_support.py \
    tests/test_catch_history_api.py tests/test_catch_history_openapi.py
  uv --directory services/api run --locked --no-sync pyright
  uv --directory services/api run --locked --no-sync pytest -q \
    tests/test_catch_history_api.py tests/test_catch_history_openapi.py \
    tests/test_catch_confirmation_api.py tests/test_catch_confirmation_openapi.py
  ```

  Expected: all pass.

- [ ] **Step 2: Run the authoritative repository gate**

  Run:

  ```bash
  make api-check
  ```

  Expected: all repository checks pass, including Semgrep, PostgreSQL-backed
  tests, migration drift, OpenAPI validation, and production configuration.

- [ ] **Step 3: Prove scope discipline from the diff**

  Run:

  ```bash
  git diff --check main...HEAD
  git diff --name-status main...HEAD
  git diff --stat main...HEAD
  ```

  Expected: only the frozen spec, this plan, the three planned production files,
  optional focused paginator, and three planned test files appear. No model,
  migration, service, dependency, setting, generated artifact, secret, debug, or
  scratch change is present.

- [ ] **Step 4: Perform post-implementation plausible-mutant analysis**

  Re-evaluate every mutant listed in Task 4 against the final tests. Classify
  each as killed, equivalent/irrelevant, or a meaningful missing protection.
  Resolve meaningful gaps within approved scope before review; replan any gap
  that would expand the contract or production surface.

- [ ] **Step 5: Dispatch one fresh STANDARD COMPACT reviewer**

  Give the reviewer the frozen specification, this plan, final diff, test
  traceability, deterministic command output, and mutant analysis. Require one
  combined review of specification compliance, correctness, test adequacy,
  SECURITY, code quality, query behavior, and scope discipline using
  BLOCKER/HIGH/MEDIUM/LOW/NIT severity. Resolve every contract violation and
  BLOCKER/HIGH finding before completion; the parent decides whether MEDIUM
  findings belong in scope.

- [ ] **Step 6: Run parent authoritative verification after review fixes**

  Re-run focused tests, `make api-check`, `git diff --check`, and final diff
  inspection after the last code change. Account for AC-01 through AC-15, list
  files changed and tests added, confirm no migration/API-write/data rollback is
  needed, and state that deployment validation remains owned by #179.

## Execution handoff

The required execution path is subagent-driven ADW: establish the baseline,
dispatch a fresh independent `test_author`, approve test adequacy, dispatch a
separate `implementer`, run deterministic gates, dispatch one fresh compact
reviewer, and finish with parent verification. Production implementation must
not begin in the test-author context.
