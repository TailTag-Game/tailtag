# Railway Development Django admin operations

## Status

Approved design for [Issue #170](https://github.com/TailTag-Game/tailtag/issues/170).

## Objective

Make the existing Django administration surface operational in Railway
Development. The deployed application must serve Django admin static assets
with production settings, and a maintainer must be able to create or reconcile
one dedicated Development operator without persisting or disclosing its local
credential.

This work restores an existing operator path. It does not add a product role,
operator HTTP API, alternate authentication system, or custom admin frontend.

## Context

The production image currently starts Gunicorn without collecting static files,
and neither Gunicorn nor Django serves `STATIC_ROOT` in production. As a result,
the admin HTML is reachable while its CSS and JavaScript return `404`.

Django's deployment guidance separates static delivery into collecting assets
and serving the collected directory. WhiteNoise provides the smallest
production-style fit for the existing single-container Railway service: its
middleware runs directly after Django's security middleware and serves files
collected into `STATIC_ROOT`. See the
[Django static deployment guide](https://docs.djangoproject.com/en/6.0/howto/static-files/deployment/)
and [WhiteNoise Django guide](https://whitenoise.readthedocs.io/en/stable/django.html).

Railway provides an interactive shell inside a deployed service through
[`railway ssh`](https://docs.railway.com/cli/ssh). Railway also supplies the
`RAILWAY_ENVIRONMENT_NAME` and `RAILWAY_SERVICE_NAME` runtime variables used by
the operator-command guard.

## Design

### Static assets

- Add WhiteNoise as a locked runtime dependency.
- Place `whitenoise.middleware.WhiteNoiseMiddleware` immediately after
  `django.middleware.security.SecurityMiddleware`.
- Use `whitenoise.storage.CompressedManifestStaticFilesStorage` for production
  static files.
- Add a minimal build-only Django settings module with inert,
  network-independent configuration and the same staticfiles backend as
  production.
- Run `collectstatic --noinput` with the build settings after application source
  is copied into the production image.
- Keep Gunicorn as the runtime command. Do not run `collectstatic`, migrations,
  or operator provisioning during application startup.

The production `default` storage alias remains `media.storage.S3MediaStorage`.
No media URL route, public bucket, or shared static/media storage is introduced.

### Development operator command

Add a narrowly scoped Django management command named
`bootstrap_development_operator`. A maintainer invokes it interactively inside
the deployed Development `api` container:

```text
railway ssh --service api --environment development
python manage.py bootstrap_development_operator --settings=config.settings.production
```

Before accessing the database, the command must require all of the following:

- `RAILWAY_ENVIRONMENT_NAME` is exactly `development`;
- `RAILWAY_SERVICE_NAME` is exactly `api`;
- standard input and output are interactive terminals; and
- the maintainer types the documented fixed confirmation phrase.

The command prompts privately for the dedicated operator identifier and the
password twice. Sensitive inputs are never accepted through command arguments
or environment variables and are never included in output or exception text.
Django's configured password validators run before any write.

The database operation is atomic:

- If the identifier does not exist, create one account through
  `UserManager.create_superuser`.
- If the matching account is already both staff and superuser, lock it and
  replace its local password. This is the supported rerun/recovery path.
- If the matching account is an ordinary or partially privileged application
  user, refuse without changing it. The command never elevates a player account.

Success output states only whether the operator was created or reconciled. It
does not include the identifier, password, password hash, database key, or other
account detail.

### Failure behavior

The command exits nonzero without mutation when the target environment or
service is wrong, the process is not interactive, confirmation fails, an input
is empty, passwords differ, password validation fails, the matching account is
not already a full operator, or the database operation fails. Transactional
failure must not leave partial privilege or password changes.

## Acceptance Contract

1. The production image deterministically contains collected Django admin
   static assets.
2. With production settings and `DEBUG=False`, the application serves a
   collected admin CSS or JavaScript asset successfully with an appropriate
   content type.
3. Railway Development `/admin/login/` and every referenced built-in admin CSS
   and JavaScript asset return `200` after deployment.
4. Static delivery does not change the private production media backend or add
   a public media route.
5. The operator command can create one dedicated operator only in an
   interactive Railway Development `api` service process.
6. A rerun reconciles an existing full operator by rotating its password without
   creating another account.
7. The command refuses to elevate an ordinary or partially privileged account.
8. Every rejected or failed command path leaves account state unchanged and
   emits no sensitive input.
9. The operator can sign in to the existing Django admin and use the already
   approved Convention, fursuit-enablement, activation/session, and credential
   inspection controls.
10. An ordinary player remains unable to access Django admin or gain operator
    authority.
11. Migrations, static collection, and operator provisioning remain absent from
    Gunicorn and application startup.
12. The full deterministic backend validation gate passes.

## Test Surface Contract

Tests may use these existing or package-internal seams:

- Django settings inspection in an isolated subprocess;
- Django's staticfiles collection machinery with a temporary `STATIC_ROOT`;
- WhiteNoise middleware around the Django WSGI application or an equivalent
  production-settings HTTP client check;
- source-level production Docker-stage assertions in the existing runtime
  contract tests;
- `call_command` for the management command;
- patched terminal streams and private-input functions for deterministic command
  tests; and
- the real PostgreSQL-backed `accounts.User` manager and model invariants.

Tests may mock terminal input and Railway-provided environment metadata. They
must not mock the user manager, password hashing and validation, transaction
behavior, static storage backend, or HTTP static response being asserted. No
production API or generalized test-only seam may be added.

The live Railway check exercises the deployed image, actual Gunicorn/WhiteNoise
path, Django admin login, and existing operator controls. Committed evidence is
sanitized and contains no identifier, credential, session value, presigned URL,
or private media object data.

## Scope Guard

### Outcome

Railway Development serves a functional existing Django admin and supports a
safe, interactive, rerunnable dedicated-operator bootstrap procedure.

### Non-goals

- operator or admin HTTP APIs;
- automatic provisioning during build, pre-deploy, startup, or health checks;
- credentials in source, Railway variables, arguments, logs, or evidence;
- production operator provisioning;
- player-account elevation;
- custom admin UI or authentication;
- public media delivery or storage redesign; and
- unrelated Wave 2 or Wave 3 behavior.

### Expected change surface

- API dependency manifest and lockfile;
- production/build Django settings;
- production Docker image instructions;
- one `accounts` management command;
- focused settings, runtime, static-delivery, and command tests; and
- maintained backend operations documentation.

### Proof

- focused regression and command tests;
- the complete repository backend validation command, including Semgrep;
- independent specification and code review;
- a production-image or equivalent black-box static-delivery check; and
- sanitized Railway Development verification after reviewed deployment.

## Rollout and recovery

The static change rolls out with the normal reviewed `main` deployment. A failed
`collectstatic` step fails the image build before deployment. Runtime rollback is
the normal deployment rollback because this change has no schema migration.

Operator creation is an explicit one-time action after deployment. A rerun only
rotates the password of the same existing full operator. Unsafe preexisting
account state requires manual investigation; the command does not repair or
elevate it.
