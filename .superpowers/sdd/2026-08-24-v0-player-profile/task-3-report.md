# Task 3 — onboarding and mutable text-profile HTTP behavior

## Status

COMPLETE

## Changed production files

- `services/api/profiles/services.py`
- `services/api/profiles/serializers.py`
- `services/api/profiles/views.py`
- `services/api/profiles/urls.py`
- `services/api/config/urls.py`

## Acceptance coverage

- Adds authenticated `GET`, `PUT`, and `PATCH` handling for `/api/profile/`
  with the exact five-field player representation.
- GET lazily materializes only an incomplete, enabled conceptual profile.
- PUT normalizes both text fields, locks and atomically completes or replaces
  them, preserves the avatar and original completion timestamp, and guards
  disabled profiles.
- PATCH requires a completed enabled profile and nonempty partial input; it
  normalizes the complete resulting state without changing avatar or timestamp.
- Maps only the exact structured named handle conflict to the frozen `handle`
  uniqueness validation error. Other integrity failures propagate.
- Registers only `api/profile/`, leaving identity and `/api/me/` untouched.

## Commands and outcomes

```bash
cd services/api
uv run --locked --no-sync pytest -q \
  tests/test_player_profile_api.py \
  tests/test_player_profile_concurrency.py \
  tests/test_player_profile_integrity.py \
  tests/test_player_profile_eligibility.py \
  tests/test_current_user_api.py \
  tests/test_foundation.py
```

Focused RED before implementation: `45 failed, 18 passed`; failures were the
missing profile route and the intentionally deferred avatar route/schema.

After implementation and the approved acceptance-test correction: `59 passed,
5 failed`. The remaining failures are expected Task 4 work only:

- `/api/profile/avatar/` has not been registered, so avatar authentication,
  disabled-mutation, and avatar-preservation flows return `404`.
- Avatar route absence leaves `/api/profile/avatar/` out of the route inventory
  asserted by current-user and foundation tests.

```bash
cd services/api
uv run --locked --no-sync ruff format --check \
  profiles/services.py profiles/serializers.py profiles/views.py profiles/urls.py config/urls.py
uv run --locked --no-sync ruff check \
  profiles/services.py profiles/serializers.py profiles/views.py profiles/urls.py config/urls.py
uv run --locked --no-sync pyright profiles config/urls.py
```

Passed: files formatted, Ruff clean, and `0 errors, 0 warnings, 0 informations`.

```bash
make api-migrations-check
git diff --check
```

Passed: `No changes detected` and no whitespace errors.

## Concerns / handoff

The initial Task 3 report intentionally left avatar route/schema failures for
Task 4. This follow-up remains confined to serializer preprocessing and has no
additional concerns.

## Follow-up remediation — handle whitespace preprocessing

The approved follow-up acceptance tests found that DRF's default handle-field
trimming allowed surrounding ASCII and Unicode whitespace to bypass domain
normalization. Both text-profile handle serializers now set
`trim_whitespace=False`, preserving raw input for `normalize_handle` while
leaving display-name normalization unchanged.

```bash
cd services/api
uv run --locked --no-sync pytest -q tests/test_player_profile_api.py \
  -k 'handle_whitespace or completed_mutation_validation or exact_response'
uv run --locked --no-sync pytest -q \
  tests/test_player_profile_api.py tests/test_player_profile_openapi.py
uv run --locked --no-sync ruff format --check profiles/serializers.py
uv run --locked --no-sync ruff check profiles/serializers.py
uv run --locked --no-sync pyright profiles/serializers.py
git diff --check
```

Passed: `7 passed` focused whitespace/response cases and `53 passed` across
the profile API and OpenAPI suite; formatting, Ruff, Pyright (`0 errors`), and
whitespace checks are clean.
