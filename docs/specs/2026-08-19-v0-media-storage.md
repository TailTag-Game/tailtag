# V0 media storage and image-upload handling

**Issue:** [#112 — Establish V0 media storage and image-upload handling](https://github.com/TailTag-Game/tailtag/issues/112)

**Parent:** [#111 — Establish V0 participation and catchability domains](https://github.com/TailTag-Game/tailtag/issues/111)

**Status:** Approved for implementation

## Goal

Establish one server-controlled media boundary that later player-profile and
participating-character APIs can use to validate, normalize, store, replace,
remove, and read V0 images without depending directly on Cloudflare R2 or
persisting access credentials.

This issue creates infrastructure and reusable behavior only. Issue #113 owns
the player-profile model and authenticated avatar API. Issue #115 owns the
participating-character model and authenticated photo API.

## Selected architecture

Production-intent storage uses a dedicated private Cloudflare R2 development
bucket through its S3-compatible API. A TailTag-owned Django `Storage` backend
wraps the boto3 S3 client because the current released `django-storages` package
does not advertise compatibility with the repository's Django 6 and Python
3.13 versions. The backend accepts generic S3 endpoint, bucket, region, and
credential settings; no profile or fursuit code may import boto3 or R2-specific
configuration.

Local development uses Django filesystem storage under the ignored API media
directory. Automated tests override the default storage with Django's
`InMemoryStorage` or a focused fake and make no network requests. Production
settings fail closed unless complete S3-compatible media configuration is
present. CI and repository checks use non-secret synthetic configuration and
must never contact R2.

The database-facing value is always the opaque object key. The media boundary
may generate an ephemeral read URL on demand, but callers must not persist or
log that URL.

## Media boundary

The `media` Django application owns four responsibilities:

1. Validate and normalize accepted image bytes.
2. Generate and validate opaque server-owned object keys.
3. Store, delete, and generate read URLs through Django's storage abstraction.
4. Coordinate replacement and optional-removal ordering around a caller-owned
   database commit operation.

It owns no database model, migration, product endpoint, public serializer, or
user-facing profile/fursuit behavior.

## Image acceptance and normalization

An upload is accepted only when all of the following are true:

- The actual decoded format is JPEG, PNG, or static WebP.
- The submitted byte stream is no larger than 10 MiB (`10 * 1024 * 1024`).
- Decoded width multiplied by height is no larger than 25,000,000 pixels.
- Pillow can fully decode the image without truncated-data, malformed-data, or
  decompression-bomb warnings or errors.
- A WebP image contains exactly one non-animated frame.

The original filename, extension, and request `Content-Type` are never format
authorities. SVG, GIF, animated WebP, HEIC/HEIF, AVIF, and every unrecognized
format are rejected.

Accepted images are orientation-normalized and re-encoded in their decoded
accepted format. The re-encoded object contains pixels required for display but
does not carry source EXIF, XMP, comments, textual chunks, ICC data, or other
source metadata. The source byte stream is never stored. Cropping, presentation
resizing, thumbnails, filters, alternate renditions, and other product image
transformations remain excluded.

The normalizer returns canonical bytes together with the authoritative media
type and extension:

| Decoded format | Media type | Extension |
| --- | --- | --- |
| JPEG | `image/jpeg` | `.jpg` |
| PNG | `image/png` | `.png` |
| WebP | `image/webp` | `.webp` |

Validation errors expose stable classifications suitable for later conversion
to an HTTP 400 response without returning Pillow exception text, source
metadata, filenames, credentials, or object-storage internals.

## Object keys and access

Every object key has a fixed server-owned image namespace, a random UUID value,
and the canonical extension. It contains no username, TailTag user ID, Clerk ID,
original filename, client path, or other user-controlled or personal data.
Storage operations reject keys outside this format.

The production storage backend creates an S3 Signature Version 4 presigned
`GET` URL with a 600-second expiry. Presigned URLs are bearer credentials. They
must be returned only to an authorized caller by later product APIs and must
never be persisted, included in application logs, or exposed through error
messages. There are no presigned `PUT` URLs, direct-to-R2 uploads, public bucket
URLs, or upload-finalization protocol in this issue.

## Lifecycle ordering

The media boundary accepts caller-supplied commit operations so later domain
services can own their database transactions while reusing the required object
ordering.

Replacement follows this sequence:

```text
validate and normalize
  -> upload the new object
  -> synchronously commit the new database reference
  -> best-effort delete the old object
```

If the database commit operation raises after the new upload, the media boundary
attempts to delete the new object and then re-raises the original exception. A
failed compensating delete must not replace or hide that original exception.

If deletion of the old object fails after the database commit, the committed
new reference remains authoritative. The boundary records a sanitized warning
and tolerates the orphan; it must not restore the stale database reference.

Optional avatar removal follows this sequence:

```text
synchronously commit removal of the database reference
  -> best-effort delete the prior object
```

A failed post-commit deletion likewise leaves the valid absent reference in
place and may create an orphan. General account deletion, fursuit deletion,
scheduled garbage collection, bucket inventory reconciliation, and a generic
asset lifecycle platform remain outside this issue.

## Configuration and operations

Production settings require generic S3-compatible values for:

- endpoint URL;
- bucket name;
- region;
- access-key ID; and
- secret access key.

The endpoint must be HTTPS. The presigned read lifetime is fixed at 600 seconds
in the application contract rather than accepted from untrusted runtime input.
Startup failures name only the missing or invalid setting and never echo its
value.

Railway Development will use a dedicated private R2 development bucket. Its
credentials must have only the bucket/object permissions needed by the API and
must exist only at Railway's established secret boundary. Bucket creation,
credential creation or rotation, and Railway variable changes are explicit,
authorized maintainer operations; application startup, ordinary tests, and CI
must never perform them. Documentation must describe the sanitized variable
names and validation procedure without recording rendered values.

## Live R2 Development verification

The repository exposes one opt-in `make api-media-storage-smoke` command for a
real S3-compatible boundary check. It is a maintainer/developer operation, not
an application feature, deployment hook, health check, or ordinary CI gate.
`make api-check` and ordinary automated tests must remain fully networkless
with respect to object storage.

The command runs the checked-out repository revision through Railway's
Development `api` variable context and forces
`DJANGO_SETTINGS_MODULE=config.settings.production`. Before Django or storage
initialization, it requires all of the following exact, case-sensitive values:

- `RAILWAY_ENVIRONMENT_NAME=development`;
- `RAILWAY_SERVICE_NAME=api`; and
- `TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM=run-r2-development-media-storage-smoke`.

Missing or different identity values fail closed. In particular, an
environment identified as `production` is always rejected. After Django
initialization, the command also requires the configured default storage to be
the production `S3MediaStorage`; local filesystem and in-memory backends are
rejected.

The command creates an opaque image key and only synthetic, in-memory,
canonically normalized image bytes. It then performs this sequence against the
configured private bucket:

```text
upload canonical bytes
  -> require object existence
  -> create a 600-second presigned GET
  -> fetch without redirecting or logging the bearer URL
  -> require exact canonical-byte equality
```

Once the opaque key exists in memory, cleanup runs from a `finally` path after
every success or failure. Cleanup attempts deletion and then independently
checks that the object is absent. A deletion error, absence-check error, or
surviving object fails the command; cleanup is never downgraded to a warning.

Command output is limited to fixed stage-level `PASS` or `FAIL` messages and
the safe target identity `development/api`. It must never render exception
details, object keys, endpoint or bucket values, credentials, request
signatures, presigned URLs, or response bodies. Deterministic tests exercise
the orchestration through fakes and prohibit outbound network access.

The canonical live invocation from the checked-out branch is:

```bash
TAILTAG_MEDIA_STORAGE_SMOKE_CONFIRM=run-r2-development-media-storage-smoke \
railway run --service api --environment development -- make api-media-storage-smoke
```

Completion requires an authorized maintainer to provision the dedicated
private R2 Development bucket, create a bucket-scoped Object Read & Write
credential, stage the five `MEDIA_STORAGE_*` values only on Railway
Development's `api` service, run the command successfully, and record only the
command name, safe target identity, branch/revision, fixed stage outcomes,
cleanup/absence result, and overall `PASS`.

## Acceptance Contract

### Storage and configuration

- Local Django stores media on the ignored local filesystem.
- Ordinary automated tests use deterministic non-network storage.
- Production uses the S3-compatible Django storage backend and fails closed on
  missing or invalid required configuration.
- `make api-check` and all focused tests succeed without Cloudflare access or
  real R2 credentials.
- R2 and boto3 types do not leak into future profile or fursuit interfaces.

### Upload safety and privacy

- Valid JPEG, PNG, and static WebP inputs are fully decoded, orientation-applied,
  metadata-stripped, and canonically re-encoded before storage.
- Inputs exceeding 10 MiB or 25,000,000 decoded pixels are rejected.
- Decompression-bomb warnings and errors are rejected.
- Unsupported, mislabeled, malformed, truncated, and animated inputs are
  rejected based on decoded content rather than names or claimed content types.
- Stored bytes contain no source EXIF, XMP, comments, textual chunks, ICC data,
  or original byte tail.

### Keys and reads

- Keys are opaque, random, server-controlled, canonical-extension values under
  the fixed image namespace.
- Storage operations reject unrecognized or unsafe keys.
- Read access produces a presigned `GET` URL with a 600-second expiry in the R2
  backend.
- No function persists or logs a presigned URL, and no direct-upload URL exists.

### Lifecycle

- Replacement ordering is new upload, database-reference commit, then old-object
  deletion.
- A failed commit triggers best-effort compensation for the new object and
  preserves the original exception.
- A failed old-object deletion never reverses a committed reference.
- Optional removal commits the absent reference before best-effort object
  deletion.
- Orphan risk is documented without adding scheduled collection or generalized
  lifecycle infrastructure.

### Scope protection

- No player-profile or fursuit model, migration, endpoint, serializer, or
  ownership rule is added.
- No cropping, presentation resizing, thumbnail, derivative, filter, CDN, video,
  or arbitrary-file feature is added.
- No Cloudflare or Railway resource is created or changed by repository tests or
  application startup.

### Live Development verification

- `make api-media-storage-smoke` is opt-in and is not a prerequisite of
  `make api-check`, any ordinary CI job, application startup, or deployment.
- The command requires exact Railway `development`/`api` identity, the fixed
  explicit confirmation value, production settings, and `S3MediaStorage`.
- It uses only synthetic canonical bytes and an opaque server-generated key.
- It verifies upload, existence, a 600-second presigned GET with exact byte
  equality, deletion, and confirmed absence.
- Cleanup and the absence check run after every reachable storage-flow outcome;
  cleanup failure or surviving state fails the command.
- Output and recorded evidence contain only fixed sanitized stages and safe
  Development identity/revision information.
- A real successful R2 Development result is recorded before Issue #112 closes.

## Verification

Focused tests cover settings fail-closed behavior, deterministic storage,
normalization and metadata removal, format and resource rejection, opaque-key
validation, presigned reads, lifecycle ordering, live-smoke guards and ordered
cleanup, and secret sanitization. Completion requires the repository's
authoritative `make api-check`, its repository-owned Semgrep gate,
`git diff --check`, and the sanitized successful live R2 Development result.
