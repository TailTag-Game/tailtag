## Task 4 report — portable storage, keys, and lifecycle orchestration

Implemented the frozen media storage contract in the assigned production modules.

- `media.keys` creates UUID-based opaque image keys and rejects every malformed
  key with one sanitized error.
- `media.storage.S3MediaStorage` keeps S3-compatible client details inside the
  adapter, validates all object keys before access, uses SigV4, and creates only
  600-second `get_object` presigned reads.
- `media.service` normalizes uploads, writes canonical bytes with their media
  type, retains and validates the storage-returned key, and enforces the
  replacement/removal commit and best-effort cleanup ordering without logging
  keys, URLs, or cleanup exception details.

Verification completed:

```text
uv --directory services/api run pytest -q tests/test_media_service.py tests/test_media_storage.py
23 passed

uv --directory services/api run pytest -q tests/test_media_images.py tests/test_media_service.py tests/test_media_storage.py tests/test_media_settings.py
61 passed

uv --directory services/api run ruff format --check media/keys.py media/storage.py media/service.py
uv --directory services/api run ruff check media/keys.py media/storage.py media/service.py
uv --directory services/api run pyright media/keys.py media/storage.py media/service.py
git diff --check
```

No migrations, API endpoints, external storage calls, or settings changes were
made. Semgrep is unavailable as documented by the approved Acceptance Contract.

### Regression round 1

Hardened the assigned storage/key/service boundary against newly frozen failure
contracts: non-string keys are sanitized `ValueError`s, read URLs have an
unoverrideable 600-second expiry, `exists()` returns `False` only for S3
not-found `ClientError` codes, and cleanup after a failed commit preserves the
original exception even if cleanup raises `BaseException`.

Verification completed:

```text
uv --directory services/api run pytest -q tests/test_media_service.py tests/test_media_storage.py
39 passed

uv --directory services/api run pytest -q tests/test_media_images.py tests/test_media_service.py tests/test_media_storage.py tests/test_media_settings.py
77 passed

uv --directory services/api run ruff format --check media/keys.py media/storage.py media/service.py
uv --directory services/api run ruff check media/keys.py media/storage.py media/service.py
uv --directory services/api run pyright media/keys.py media/storage.py media/service.py
git diff --check
```
