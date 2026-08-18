# Final SDK claim-shape regression tests — RED evidence

## Scope

Test-only regression coverage for Issue #96's generic authentication failure
boundary. Production code is intentionally unchanged.

## Focused RED command and output

```text
cd services/api
DJANGO_SECRET_KEY=test-only-settings-key DATABASE_URL=postgresql://tailtag:password@127.0.0.1:5432/tailtag \\
  uv run pytest -q tests/test_clerk_authentication.py::test_post_signature_malformed_claims_fail_generically_without_disclosure

FFF                                                                      [100%]
FAILED tests/test_clerk_authentication.py::test_post_signature_malformed_claims_fail_generically_without_disclosure[non-numeric-expiry]
FAILED tests/test_clerk_authentication.py::test_post_signature_malformed_claims_fail_generically_without_disclosure[v2-nonmapping-organization]
FAILED tests/test_clerk_authentication.py::test_post_signature_malformed_claims_fail_generically_without_disclosure[v2-nonstring-features]
3 failed in 0.20s
```

The failures are the intended current-head RED state, after real offline RS256
signature verification:

```text
TypeError: int() argument must be a string, a bytes-like object or a real number, not 'list'
AttributeError: 'str' object has no attribute 'get'
AttributeError: 'list' object has no attribute 'split'
```

The three parametrized cases use a signed otherwise-valid session token with,
respectively, `exp=[]`; v2 `o="not-an-object"`; and v2 mapping-shaped `o`
with string `per`/`fpm` plus non-string `fea`. Each requires a stock
`AuthenticationFailed`, its generic public detail, and no token, subject,
session ID, malformed-claim marker, or raw exception-class disclosure.

## Existing acceptance coverage

```text
cd services/api
DJANGO_SECRET_KEY=test-only-settings-key DATABASE_URL=postgresql://tailtag:password@127.0.0.1:5432/tailtag \\
  uv run pytest -q tests/test_clerk_authentication.py -k 'not post_signature_malformed_claims'

...........................................                              [100%]
43 passed, 3 deselected in 0.36s
```

## Static validation

```text
cd services/api
uv run ruff format tests/test_clerk_authentication.py
1 file left unchanged

uv run ruff format --check tests/test_clerk_authentication.py
1 file already formatted

uv run ruff check tests/test_clerk_authentication.py
All checks passed!

uv run pyright tests/test_clerk_authentication.py
0 errors, 0 warnings, 0 informations

git diff --check
```

`git diff --check` produced no output and exited successfully.
