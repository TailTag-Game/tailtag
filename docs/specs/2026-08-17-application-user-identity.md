# TailTag application-user identity

**Issue:** [#95 — Define the TailTag application-user model and identity contract](https://github.com/TailTag-Game/tailtag/issues/95)  
**Status:** Approved for implementation

## Goal

Establish one TailTag-owned application identity that Django, Django REST
Framework, and future domain models can use without treating a Clerk identifier
as TailTag's domain identity.

## Identity contract

- `accounts.User` is Django's configured user model through
  `AUTH_USER_MODEL`.
- Its repository-standard `BigAutoField` primary key is the canonical TailTag
  application-user identity.
- `clerk_user_id` is a required, unique external identity link. It identifies
  the corresponding Clerk user but is not a TailTag domain identifier and must
  not be used as a downstream foreign key.
- Future model fields reference `settings.AUTH_USER_MODEL`. Runtime code obtains
  the model with `django.contrib.auth.get_user_model()`.
- After issues #96 and #97 add authentication and resolution, an authenticated
  DRF request exposes the resolved `accounts.User` instance as `request.user`.

## Model and administration

`accounts.User` extends `AbstractBaseUser` and `PermissionsMixin`. It explicitly
adds only `clerk_user_id` and `is_staff`; its primary key is supplied by the
repository's `BigAutoField` default. Framework-provided password, last-login,
group, and permission fields support Django integration and administration;
they do not define TailTag product roles or account lifecycle behavior.

Normal application-user creation rejects Django privilege flags and local
passwords. The model rejects a usable password for a non-superuser and clears
the local password when a superuser is demoted. Django staff and superuser
support remains available for administration; admin passwords are validated
against the administrative user's Clerk ID as well as the other configured
password rules. Admin lists and searches stable identity fields without
exposing password material.

No profile, gameplay, deletion, webhook, Clerk verification, request
authentication, or just-in-time provisioning behavior is included.

## Integrity and verification

The database enforces that `clerk_user_id` is nonempty and unique, and that a
usable local password belongs only to a user with both Django staff and
superuser flags. Tests cover TailTag-owned primary keys, the required unique
Clerk link, ordinary-user privilege and password boundaries, configured-user
resolution, the downstream foreign-key convention, safe admin configuration,
and the deliberately narrow field surface. The initial migration must apply to
a fresh PostgreSQL database, and migration-drift detection must remain clean.

## Existing development databases

Databases that already applied Django's admin migrations with the former
`auth.User` setting cannot adopt this user-model swap through the #95 migration
alone. Django's applied admin migration has a dynamic dependency on the
configured user model, so changing that setting retroactively changes the
migration graph.

Issue `#95` does not reset or rewrite any existing database or migration
history. A fresh database is the supported migration baseline for this initial
identity contract. Existing development databases require a separately
authorized and coordinated reset or transition before a revision containing
this change is deployed. No production environment exists, and this
specification does not authorize any environment operation.
