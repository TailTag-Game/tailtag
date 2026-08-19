# V0 Media Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-portable Django media boundary that safely normalizes V0 images and stores them in private Cloudflare R2 for Railway Development while keeping local development and tests network-free.

**Architecture:** A new infrastructure-only `media` Django app owns image normalization, opaque keys, lifecycle sequencing, and a small boto3-backed Django `Storage` implementation. Settings select filesystem storage locally, in-memory storage in ordinary tests, and the S3-compatible backend in production; future profile and fursuit code consumes only the media service and persists only returned object keys.

**Tech Stack:** Python 3.13, Django 6.0, Pillow 12.x, boto3 1.x, pytest, strict Pyright, Ruff, PostgreSQL 17

## Global Constraints

- Production storage is a private Cloudflare R2 bucket accessed through the S3-compatible API.
- Persist only opaque server-controlled object keys; never persist or log presigned URLs.
- Presigned reads are `GET` only and expire after exactly 600 seconds.
- Uploads pass through a future authenticated Django product API; #112 adds no generic endpoint or presigned `PUT` path.
- Accept decoded JPEG, PNG, and static WebP only.
- Reject uploads larger than 10 MiB or images larger than 25,000,000 decoded pixels.
- Fully decode, orient, metadata-strip, and canonically re-encode every accepted image; never store source bytes.
- Local storage is filesystem-backed; ordinary tests use `InMemoryStorage`; no check contacts R2.
- No profile/fursuit model, migration, endpoint, serializer, product transformation, garbage collector, or external resource mutation is in scope.
- Production configuration is generic S3-compatible configuration so future providers do not affect domain code.

---

## File map

- `services/api/media/apps.py`: Django application registration only.
- `services/api/media/images.py`: upload limits, decoded-format validation, orientation, metadata-free canonical encoding, and stable rejection codes.
- `services/api/media/keys.py`: opaque key generation and strict key validation.
- `services/api/media/storage.py`: portable boto3-backed Django `Storage` adapter and presigned `GET` generation.
- `services/api/media/service.py`: storage-agnostic save/read/replace/remove orchestration.
- `services/api/config/settings/media.py`: immutable, sanitized S3-compatible environment configuration parser.
- `services/api/config/settings/base.py`: register the app and local filesystem default storage.
- `services/api/config/settings/production.py`: fail-closed S3-compatible storage selection.
- `services/api/tests/conftest.py`: autouse deterministic in-memory default storage.
- `services/api/tests/test_media_images.py`: black-box image acceptance and canonicalization tests.
- `services/api/tests/test_media_service.py`: keys, storage abstraction, and lifecycle-ordering tests.
- `services/api/tests/test_media_storage.py`: S3 adapter request and presign tests against a fake client.
- `services/api/tests/test_media_settings.py`: local/test/production storage and secret-sanitization tests.
- `services/api/pyproject.toml` and `services/api/uv.lock`: bounded Pillow, boto3, and S3 typing dependencies.
- `services/api/.env.example`, `.gitignore`, `services/api/README.md`, and `docs/development/backend-delivery-operations.md`: local path, Railway secret names, rollout order, validation, and orphan behavior.
- `Makefile` and `.github/workflows/api.yml`: non-secret synthetic production media configuration for credential-free deterministic checks.

### Task 1: Freeze independent acceptance tests

**Files:**
- Create: `services/api/tests/conftest.py`
- Create: `services/api/tests/test_media_images.py`
- Create: `services/api/tests/test_media_service.py`
- Create: `services/api/tests/test_media_storage.py`
- Create: `services/api/tests/test_media_settings.py`

**Interfaces:**
- Consumes: the approved spec at `docs/specs/2026-08-19-v0-media-storage.md` only.
- Produces: executable behavioral contracts for the exact interfaces declared in Tasks 2–4.

- [ ] **Step 1: Add test-only in-memory storage selection**

Create an autouse fixture which replaces only `STORAGES["default"]` and preserves the explicit `staticfiles` alias:

```python
@pytest.fixture(autouse=True)
def deterministic_default_storage(settings: SettingsWrapper) -> None:
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    }
```

- [ ] **Step 2: Define image acceptance tests against the wished-for API**

Tests import these exact declarations:

```python
from media.images import (
    MAX_IMAGE_BYTES,
    MAX_IMAGE_PIXELS,
    ImageRejectionCode,
    ImageValidationError,
    NormalizedImage,
    normalize_image,
)
```

Use generated Pillow fixtures, not committed binary assets. Assert:

```python
normalized = normalize_image(upload)
assert normalized == NormalizedImage(
    content=normalized.content,
    content_type="image/jpeg",
    extension="jpg",
    width=2,
    height=3,
)
```

Cover valid JPEG/PNG/static WebP, misleading filename and claimed MIME type,
orientation transpose, source-byte replacement, EXIF/XMP/comment/PNG-text/ICC
removal, exact byte and pixel boundaries, oversized bytes, oversized decoded
dimensions, Pillow decompression warnings/errors, SVG/GIF/animated WebP,
malformed/truncated input, and unsupported signatures. Each rejection asserts a
stable `ImageRejectionCode`, never a Pillow/provider diagnostic.

- [ ] **Step 3: Define key and lifecycle tests against the wished-for API**

Tests import:

```python
from media.keys import create_image_key, validate_image_key
from media.service import (
    read_image_url,
    remove_optional_image,
    replace_image,
    store_image,
)
```

Assert keys match `images/<32 lowercase hex>.<jpg|png|webp>`, two generated keys
differ, unsafe/unrecognized keys are rejected before storage access, saved
content is canonical, and `read_image_url()` returns but neither logs nor stores
the storage backend's URL.

Use an ordered fake `Storage` and commit callbacks to assert these sequences:

```python
assert events == ["save:new", "commit:new", "delete:old"]
assert events == ["save:new", "commit:new", "delete:new"]  # failed commit compensation
assert events == ["commit:remove", "delete:old"]
```

Also assert cleanup failure preserves the original commit exception, old-object
delete failure does not call commit again or revert it, and removal commit
failure never deletes the referenced object.

- [ ] **Step 4: Define S3 adapter tests against a fake boto3 client**

Instantiate `S3MediaStorage` with endpoint, bucket, region, access key, and
secret plus a patched client factory. Assert `put_object`, `get_object`,
`head_object`, and `delete_object` use only the configured bucket and validated
key. Assert URL generation calls:

```python
client.generate_presigned_url(
    "get_object",
    Params={"Bucket": "development-media", "Key": key},
    ExpiresIn=600,
)
```

No test assertion or failure output may contain the secret value or returned
presigned URL query string.

- [ ] **Step 5: Define settings tests**

Test the exact production variables:

```text
MEDIA_STORAGE_ENDPOINT_URL
MEDIA_STORAGE_BUCKET_NAME
MEDIA_STORAGE_REGION
MEDIA_STORAGE_ACCESS_KEY_ID
MEDIA_STORAGE_SECRET_ACCESS_KEY
```

Assert each is required in production, the endpoint is an HTTPS root URL
without credentials/query/fragment, failures name only the variable, local
settings select `FileSystemStorage`, production selects
`media.storage.S3MediaStorage`, and the production options fix the read expiry
at 600 seconds. Assert ordinary pytest storage resolves to `InMemoryStorage`.

- [ ] **Step 6: Run the tests and record the expected red state**

Run:

```bash
uv --directory services/api run pytest -q \
  tests/test_media_images.py \
  tests/test_media_service.py \
  tests/test_media_storage.py \
  tests/test_media_settings.py
```

Expected: collection fails because the new `media` interfaces do not exist.
The independent test author must report which plausible incorrect
implementations each test group rejects before production implementation begins.

### Task 2: Add dependencies and fail-closed storage configuration

**Files:**
- Create: `services/api/media/__init__.py`
- Create: `services/api/media/apps.py`
- Create: `services/api/config/settings/media.py`
- Modify: `services/api/config/settings/base.py`
- Modify: `services/api/config/settings/production.py`
- Modify: `services/api/pyproject.toml`
- Modify: `services/api/uv.lock`
- Modify: `services/api/tests/test_dependency_security.py`
- Modify: `Makefile`
- Modify: `.github/workflows/api.yml`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: exact environment names and storage aliases from Task 1.
- Produces: `S3MediaConfiguration`, `load_s3_media_configuration()`, registered `media` app, deterministic settings aliases, Pillow/boto3 runtime dependencies.

- [ ] **Step 1: Add bounded current dependencies and regenerate the lock**

Add runtime requirements `Pillow>=12.3,<13` and `boto3>=1.43,<2`, plus
`boto3-stubs[s3]>=1.43,<2` to the development group. Run:

```bash
uv --directory services/api lock
uv --directory services/api sync --all-groups --locked
```

Extend the dependency security contract to assert the declared bounds and
resolved minimum versions.

- [ ] **Step 2: Implement sanitized immutable media configuration**

Create the immutable `S3MediaConfiguration` dataclass with the five string
fields below, and implement
`load_s3_media_configuration(environment: Mapping[str, str]) -> S3MediaConfiguration`:

```python
@dataclass(frozen=True, slots=True)
class S3MediaConfiguration:
    endpoint_url: str
    bucket_name: str
    region: str
    access_key_id: str
    secret_access_key: str
```

Require every exact variable from Task 1. Validate the endpoint structurally
without ever interpolating supplied values into exceptions or `repr()` output;
override the dataclass representation so credential fields cannot be emitted.

- [ ] **Step 3: Register storage aliases**

Register `media.apps.MediaConfig`. In base/local behavior, set:

```python
MEDIA_ROOT = BASE_DIR / ".media"
MEDIA_URL = "/media/"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": MEDIA_ROOT, "base_url": MEDIA_URL},
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
```

Ignore `/services/api/.media/`. Production replaces only the default alias with
`media.storage.S3MediaStorage`, passing generic configuration plus
`url_expiry_seconds=600` and retaining the staticfiles alias.

- [ ] **Step 4: Keep deterministic checks fail-closed and network-free**

Add obviously synthetic, non-secret values for the five media variables to the
GitHub workflow's test environment and the Gunicorn configuration check. Do not
add real credentials, an R2 hostname tied to an account, or any storage call.

- [ ] **Step 5: Run focused settings/dependency tests**

Run:

```bash
uv --directory services/api run pytest -q \
  tests/test_media_settings.py tests/test_dependency_security.py \
  tests/test_production_settings.py tests/test_local_settings.py
```

Expected: settings/dependency tests pass; storage/image/service tests remain red
because their production modules are not implemented.

### Task 3: Implement safe image normalization

**Files:**
- Create: `services/api/media/images.py`
- Test: `services/api/tests/test_media_images.py`

**Interfaces:**
- Consumes: Pillow and Django file objects.
- Produces: `normalize_image(upload: File[bytes]) -> NormalizedImage` and stable rejection codes.

- [ ] **Step 1: Define the immutable result and safe failure types**

Implement:

```python
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000


class ImageRejectionCode(StrEnum):
    FILE_TOO_LARGE = "file_too_large"
    INVALID_IMAGE = "invalid_image"
    UNSUPPORTED_FORMAT = "unsupported_format"
    ANIMATED_IMAGE = "animated_image"
    TOO_MANY_PIXELS = "too_many_pixels"


class ImageValidationError(ValueError):
    code: ImageRejectionCode


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    content: bytes
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    extension: Literal["jpg", "png", "webp"]
    width: int
    height: int
```

- [ ] **Step 2: Enforce actual-byte and decoded-content limits**

Read at most `MAX_IMAGE_BYTES + 1` bytes. Open from `BytesIO` under a warning
context which turns `Image.DecompressionBombWarning` into an exception. Check
decoded format, frame count, dimensions, and `width * height` before full load;
then fully load under the same warning policy. Map Pillow errors to stable
TailTag rejection codes without retaining provider text.

- [ ] **Step 3: Normalize orientation and metadata-free pixels**

Apply `ImageOps.exif_transpose()`, convert display pixels to canonical `RGB` or
`RGBA`, copy them into a new metadata-free image, and save without passing
source `info`, EXIF, XMP, comment, text, or ICC values. Re-encode JPEG as `.jpg`,
PNG as `.png`, and static WebP as `.webp` with explicit fixed encoder settings.

- [ ] **Step 4: Run the image suite through red-green-refactor**

Run after each behavior:

```bash
uv --directory services/api run pytest -q tests/test_media_images.py
```

Expected final result: every image acceptance and rejection test passes with no
decompression warning escaping pytest.

### Task 4: Implement portable storage, keys, and lifecycle orchestration

**Files:**
- Create: `services/api/media/keys.py`
- Create: `services/api/media/storage.py`
- Create: `services/api/media/service.py`
- Modify: `services/api/pyproject.toml`
- Test: `services/api/tests/test_media_service.py`
- Test: `services/api/tests/test_media_storage.py`

**Interfaces:**
- Consumes: `NormalizedImage`, configured Django `Storage`, caller commit callbacks.
- Produces: opaque key helpers, S3-compatible storage backend, storage-agnostic product-facing media functions.

- [ ] **Step 1: Implement strict opaque keys**

Use a full-match regular expression for `images/[0-9a-f]{32}\.(jpg|png|webp)`.
`create_image_key(extension)` validates the canonical extension and uses
`uuid4().hex`; `validate_image_key(key)` raises a fixed `ValueError` for every
nonconforming key without echoing it.

- [ ] **Step 2: Implement the boto3-backed Django storage adapter**

`S3MediaStorage` accepts only generic S3-compatible options. It validates keys
before `put_object`, `get_object`, `head_object`, `delete_object`, or presigning.
It uses Signature Version 4 and implements Django `_save`, `_open`, `exists`,
`size`, `delete`, and `url`. `url()` generates only a `get_object` presign with
the configured fixed expiry. Keep boto3 typing imports under `TYPE_CHECKING` so
the production image does not require development stubs.

- [ ] **Step 3: Implement storage-agnostic media operations**

Expose these exact interfaces:

- `store_image(upload: File[bytes], *, storage: Storage | None = None) -> str`
- `read_image_url(key: str, *, storage: Storage | None = None) -> str`
- `replace_image(upload: File[bytes], *, old_key: str | None, commit_reference: Callable[[str], None], storage: Storage | None = None) -> str`
- `remove_optional_image(*, old_key: str | None, commit_removal: Callable[[], None], storage: Storage | None = None) -> None`

Wrap canonical bytes in a Django `ContentFile`, attach the canonical content
type for the storage adapter, and retain the name actually returned by
`Storage.save()`. Validate every returned or supplied key.

- [ ] **Step 4: Implement lifecycle compensation without URL logging**

On replacement commit failure, attempt deletion of the new key and re-raise the
original exception with its traceback. On post-commit old-key deletion failure,
log one fixed sanitized orphan warning containing no exception text, URL,
credential, original filename, or personal data; do not call the commit again.
Apply the same best-effort deletion rule after optional-removal commit.

- [ ] **Step 5: Run storage and lifecycle suites through red-green-refactor**

Run:

```bash
uv --directory services/api run pytest -q \
  tests/test_media_service.py tests/test_media_storage.py
```

Expected final result: all key, presign, storage, ordering, compensation, and
orphan tests pass without network access.

### Task 5: Document contributor and Railway operations

**Files:**
- Modify: `services/api/.env.example`
- Modify: `services/api/README.md`
- Modify: `docs/development/backend-delivery-operations.md`

**Interfaces:**
- Consumes: exact settings and runtime behavior from Tasks 2–4.
- Produces: non-secret setup, rollout, recovery, and limitation documentation.

- [ ] **Step 1: Document local and test behavior**

Document `.media/` filesystem storage, canonical accepted formats and limits,
metadata stripping, and the fact that tests use in-memory storage with no R2
dependency. Do not put R2 credentials in `.env.example`; list production-only
variable names as comments with redacted placeholders only when useful.

- [ ] **Step 2: Document Railway Development rollout order**

Require maintainers to create one private development bucket and minimum-scope
bucket/object credentials, stage the five Railway secret variables before
merging the fail-closed code, deploy through the normal protected-main path,
and validate a write/read/delete exercise without recording a credential or
presigned URL. State explicitly that repository implementation does not mutate
Cloudflare or Railway resources.

- [ ] **Step 3: Document lifecycle and recovery boundaries**

Record replacement/removal ordering, compensating deletion, tolerated orphans,
the absence of generalized garbage collection, and the rule that application
rollback does not restore or delete R2 objects.

- [ ] **Step 4: Run documentation checks**

Run:

```bash
./scripts/doctor.sh
git diff --check
```

Expected: documentation diff is clean. If Docker remains unavailable, record
the doctor failure verbatim and continue only with checks that do not claim
Docker/PostgreSQL coverage.

### Task 6: Deterministic integration and review gates

**Files:**
- Modify only when a failing check exposes an in-scope defect.

**Interfaces:**
- Consumes: all implementation and tests.
- Produces: fresh completion evidence and independent review findings.

- [ ] **Step 1: Run cheap deterministic checks**

Run:

```bash
uv --directory services/api run ruff format --check .
uv --directory services/api run ruff check .
uv --directory services/api run pyright
uv --directory services/api run pytest -q \
  tests/test_media_images.py \
  tests/test_media_service.py \
  tests/test_media_storage.py \
  tests/test_media_settings.py
git diff --check
```

- [ ] **Step 2: Run the authoritative repository gate**

Run `make api-check`. It must perform no network storage request. If Docker or
PostgreSQL is unavailable, report the environmental blocker and do not claim the
authoritative gate passed.

- [ ] **Step 3: Record Semgrep limitation**

Confirm that the repository still has no Semgrep configuration or owned command.
Do not add a CI toolchain under #112 and do not report Semgrep as passed.

- [ ] **Step 4: Run independent reviews**

Provide fresh reviewers the approved spec and final diff, not the implementer's
rationale. Require separate specification-compliance and code-quality/security
reviews. Remediate every critical or important finding and rerun affected tests.

- [ ] **Step 5: Run final verification**

Rerun `make api-check`, `git diff --check`, inspect `git status --short`, and
map every Acceptance Contract item to code/test evidence before reporting the
result. Cloudflare/Railway live validation remains pending until explicitly
authorized and provisioned.
