# Hybrid replica trust runbook

This runbook records how TailTag trusts each connection of the hybrid replica, and how the owner rotates or revokes each credential. It also gives the live checks of [#357](https://github.com/TailTag-Game/tailtag/issues/357). The hybrid replica is an isolated copy of Staging on Cloud Run, Neon and Cloudflare R2. The parent is [#352](https://github.com/TailTag-Game/tailtag/issues/352).

[ADR 0010](../adrs/0010-keep-railway-for-v0-hosting-after-gcp-evaluation.md) stays in force. Provisioning is in [the provisioning runbook](hybrid-replica-provisioning.md). Releases are in [the release runbook](hybrid-replica-release.md). Placeholders such as `<PROJECT_ID>` have the meanings in the provisioning runbook.

## Boundaries

- Every check here touches only replica resources. No check reads or writes Railway, Development or Staging.
- Every live step needs owner authorization. This includes each drill, each secret version and each temporary probe.
- No check prints a credential, a private identifier, a database URL, a token, an object key or a signed URL.
- Faults never change an environment value in the service template. The release copies that template, so a fault there reaches the next release.
- No release runs during a drill. Traffic stays pinned to the serving revision by name.

## Trust matrix

A connection is one path where one party trusts another. Each connection has one row in each table. The owner is the only operator of every credential.

### Identity and transport

| Connection | Identity | Issuer, signature and key | Audience and authorized party | TLS and server validation |
| --- | --- | --- | --- | --- |
| Cloud Run ingress | Anyone. The service is public, like Staging. | None at ingress. The API checks each request. | None | Google-managed certificate on the `run.app` host |
| Clerk session tokens | The two synthetic Clerk users | RS256 signature checked offline with the pinned key in `clerk-jwt-key`. The key is the issuer boundary. The API has no `iss` check. | `aud` is not configured, so a token that carries `aud` fails. `azp` must be in the allowlist, which holds only `https://accounts.replica.tailtag.app`. A token with no `azp` passes only when `exp - iat` is 60 seconds or less. | No call to Clerk at verification time |
| Neon `runtime` | `tt-runtime` through `runtime-database-url` | Password | None | `sslmode=verify-full` with the Debian CA bundle (`SSL_CERT_FILE`) |
| Neon `migrator` | `tt-migrator` through `migrator-database-url` | Password | None | Same as `runtime` |
| Neon `maintainer` | `tt-maintainer` through `maintainer-database-url` | Password | None | Same as `runtime` |
| Neon admin `tailtag_admin` | The owner only | Password | None | `verify-full` in the role script (certifi CA bundle) |
| R2 runtime | `tt-runtime` through the two media secrets | S3 Signature Version 4 with the runtime keys | Bucket-scoped token | HTTPS to the R2 endpoint with default certificate checks |
| R2 Terraform | `tf-infra` run by the owner | Cloudflare API token, held only in the owner's token terminal | R2 admin on the replica Cloudflare account only | HTTPS to the Cloudflare API |
| Secret Manager | Each service account, by named secret | Google IAM | None | Google APIs over TLS |
| Artifact Registry | `tt-deployer` pushes. Cloud Run pulls. | Google IAM | None | Google APIs over TLS |
| GitHub WIF | `tt-deployer` | GitHub OIDC token. WIF (Workload Identity Federation) is the keyless sign-in from GitHub Actions. | The pool accepts only this repository, the `replica` environment and the workflow ref | Google STS over TLS |
| Terraform state | The owner and `tf-infra` | Google IAM | None | Google APIs over TLS |
| Neon Terraform token | The owner, through `tf-infra` runs | Neon API key, held only in the owner's token terminal | The replica Neon organization | HTTPS to the Neon API |
| Porkbun DNS | The owner | Porkbun account login | None | HTTPS to Porkbun |
| Sentry | Not wired. #358 owns it. | NOT_EXERCISED | NOT_EXERCISED | NOT_EXERCISED |

### Ownership and secrets

| Connection | Resource owner | Least permission | Secret location | Rotation |
| --- | --- | --- | --- | --- |
| Cloud Run ingress | The owner | Service invoker check off, by design | None | None |
| Clerk session tokens | The owner (replica Clerk application) | Two synthetic users only | `clerk-jwt-key` (a public key) | None. See [Clerk key](#clerk-key). |
| Neon `runtime` | The owner (replica Neon project) | Rows only. See [Database grant sets](#database-grant-sets). | `runtime-database-url` | [Database role passwords](#database-role-passwords) |
| Neon `migrator` | The owner | Owns the tables. Cannot make roles or databases. | `migrator-database-url` | [Database role passwords](#database-role-passwords) |
| Neon `maintainer` | The owner | Owns the database. Reset only. | `maintainer-database-url` | [Database role passwords](#database-role-passwords) |
| Neon admin | The owner | Neon admin. Break-glass use only. | Foundation Terraform state, and the Neon console | [Neon admin password](#neon-admin-password) |
| R2 runtime | The owner (replica Cloudflare account) | Object Read & Write on the replica bucket | `media-access-key-id`, `media-secret-access-key` | [R2 runtime token](#r2-runtime-token) |
| R2 Terraform | The owner | R2 admin on the replica account | The owner's token terminal only | [Provider tokens](#provider-tokens) |
| Secret Manager | The owner (replica project) | One accessor binding per secret and identity | None | None |
| Artifact Registry | The owner | Deployer writes. Tags are immutable. | None | None |
| GitHub WIF | The owner | Deployer runs the migrate job and acts as `tt-runtime` and `tt-migrator` only | No key | [Deployer](#deployer) |
| Terraform state | The owner | Read by the owner and `tf-infra` only | It holds the Neon admin password | [Neon admin password](#neon-admin-password) |
| Neon Terraform token | The owner | Neon organization API key | The owner's token terminal only | [Provider tokens](#provider-tokens) |
| Porkbun DNS | The owner | Clerk records under `replica.tailtag.app` | Porkbun account | [Porkbun](#porkbun) |
| Sentry | #358 | NOT_EXERCISED | `sentry-dsn` has no version | NOT_EXERCISED |

## Database grant sets

`task replica-neon-roles -- --project <PROJECT_ID> --limits` checks every cell below. It reads the three role URLs from Secret Manager into memory. It tries each operation in a savepoint that always rolls back, inside a transaction that also rolls back. The target table is `django_migrations`. Each attempt has a 2-second lock timeout and a 5-second statement timeout.

| Check | `runtime` | `migrator` | `maintainer` |
| --- | --- | --- | --- |
| `CREATE TABLE` in `public` | denied | allowed | allowed |
| `ALTER TABLE ... ADD COLUMN` | denied | allowed | denied |
| `DROP TABLE` | denied | allowed | allowed |
| `TRUNCATE` | denied | allowed | denied |
| `CREATE ROLE` | denied | denied | denied |
| SELECT grant option on the table | no | yes | no |
| `rolsuper`, `rolcreaterole`, `rolcreatedb`, `rolbypassrls` | false | false | false |
| Member of `pg_signal_backend` | no | no | yes |

`maintainer` owns the database, so it also owns the `public` schema. A schema owner can make tables and drop any table in the schema. This is by design, because reset needs the ownership. Two controls bound it: only the owner can run the reset job, and only `tt-maintainer` can read `maintainer-database-url`.

GRANT by a role that does not own the table gives only a warning in PostgreSQL. So the check reads the grant option instead of running GRANT. The `pg_signal_backend` membership row stands for `pg_terminate_backend`.

The Neon admin role `tailtag_admin` is the owner's break-glass role. Its grant set is the Neon admin set: it belongs to `neon_superuser`, so it can make roles and databases. It is never a superuser. When `NEON_ADMIN_DATABASE_URL` is set, the check prints the admin attributes with no verdict. The proof compares them with this set. A printed `rolsuper: true` is a FAIL.

## Rotation and compromise response

The owner is the operator for every step. A compromise means that a value left its secret location. For each credential, revoke first, then replace, then start fresh instances.

If time allows, collect the surfaces and run the [leak scan](#leak-scan) before you revoke. The scan reads only the newest secret version, so after a revocation it cannot find the leaked old value.

Every runtime secret uses the `latest` version. Cloud Run reads an environment secret once, when an instance starts. So a new value reaches only instances that start after the change. Jobs read it at each execution.

### Database role passwords

1. Run `task replica-neon-roles -- --project <PROJECT_ID> --rotate`. The old passwords stop working at once, and the script writes each new URL to its secret.
2. Start fresh service instances. Run a release of the serving SHA from the release runbook. The release makes a new revision, so new instances start.
3. Make sure that `/health/ready` returns 200.

Until step 2 ends, the service cannot reach the database. On a compromise, do step 1 at once. A new password does not end open sessions. So, as the Neon admin, end every session of the compromised role with `pg_terminate_backend`.

### Neon admin password

1. In the Neon console, reset the `tailtag_admin` password.
2. In the token terminal, run a foundation plan. If it shows a change, stop and ask the owner before an apply.

The role script reads the admin URL from `NEON_ADMIN_DATABASE_URL`, so copy the new URL from the console when it is next needed.

### R2 runtime token

1. In the replica Cloudflare account, roll the R2 token. The old secret stops working at once. The access key ID stays the same.
2. Add the new secret access key as a new version of `media-secret-access-key`, as in step 3 of the provisioning runbook.
3. Start fresh service instances, as above.
4. Run `task replica-media-smoke` and make sure that it passes.

On a compromise, delete the token instead of rolling it. Then make a new bucket-scoped token and add both keys.

### Provider tokens

The Cloudflare and Neon Terraform tokens live only in the owner's token terminal. On a compromise, delete the token in the provider console and make a new one. A routine rotation is the same.

### Deployer

`tt-deployer` has no key. On a compromise of the GitHub workflow or the `replica` environment, remove the deployer subject binding with a Terraform change. Then read the Cloud Run audit log for actions by the deployer.

### Clerk key

`clerk-jwt-key` is the public key of the replica Clerk application. Clerk documents no rotation of the instance signing key. The API checks tokens offline, so a running instance keeps trusting the old key until it stops. If someone gets the Clerk private key, do these steps in order:

1. Make a new Clerk application, its DNS records and new synthetic users.
2. Add the new public key as a new `clerk-jwt-key` version.
3. Run a release of the serving SHA. The release makes a new revision, so new instances start with the new key. The old revision keeps no traffic.
4. Make sure that a token signed by the old application gets 401.
5. Delete the old Clerk application.

### Porkbun

Porkbun holds only the Clerk DNS records. On a compromise of the account, secure the account, then compare the `replica.tailtag.app` records with the Clerk dashboard.

## Live checks

Each check needs owner authorization. Record each result as PASS, FAIL or NOT_EXERCISED in the #357 proof.

### Clerk and object access

A temporary reviewed probe runs these checks. It follows the [field-beta probe contract](../specs/2026-10-01-field-beta-observability-validation.md#probe-contract). The owner reviews it in full before the run. It runs outside the repository, and the owner deletes it after the run. The owner pastes short-lived session tokens at hidden prompts. To copy a token, sign in to `https://accounts.replica.tailtag.app` as that user, open the browser console and run `copy(await Clerk.session.getToken())`. A token lives about 60 seconds, so copy it right before its prompt. Use a private window for the second user.

The service scales to zero, so a probe first warms `/health/ready` with retries for up to 3 minutes. A first request after a pause took more than 20 seconds.

- A valid token gets 200 from `/api/me/`.
- The API denies each of these: no `Authorization` header, a malformed header, an expired token and a token with a changed signature. Send the expired token more than 5 seconds after its `exp`, because the Clerk library allows 5 seconds of clock difference.
- With the catcher token, `GET`, `PATCH` and the photo `PUT` on the owner's fursuit return 404.
- The catcher's fursuit list holds only the catcher's records.

### Media round trip and isolation

1. In the replica Cloudflare account, make a second bucket for the run. Use a name that differs from the replica bucket. Copy the name exactly from the dashboard, and record that the bucket exists. R2 can answer 403 for a bucket that does not exist, so a wrong name gives a false PASS.
2. In a terminal, set `TAILTAG_REPLICA_MEDIA_ENDPOINT_URL` and `TAILTAG_REPLICA_MEDIA_BUCKET` to the replica values. Set `TAILTAG_REPLICA_MEDIA_SMOKE_CONFIRM=run-r2-replica-media-storage-smoke`.
3. Run `task replica-media-smoke -- --project <PROJECT_ID> --isolation-bucket <SECOND_BUCKET>`.
4. Delete the second bucket.

The command refuses any endpoint and bucket that do not match the hashed replica pin. It reads the R2 runtime keys into memory only. It runs the media smoke sequence, then four isolation probes. Only 401 or 403 counts as denied for the S3 probes. A missing key in the second bucket counts as allowed, because the request reached the bucket. The unsigned read prints its HTTP status. R2 answers every unsigned S3 request with HTTP 400, code `InvalidArgument` and message `Authorization`, before it looks up the object. So the unsigned read counts 401, 403 and that exact 400 as denied. Any other status, such as another 400, a 404 or a 429, is a FAIL, because it does not prove a refusal.

In the dashboard, make sure that the runtime token has Object Read & Write on the replica bucket only. Also make sure that r2.dev public access is off. r2.dev is the Cloudflare public URL for a bucket.

### Database grant sets

Run `task replica-neon-roles -- --project <PROJECT_ID> --limits`. To add the admin report, set `NEON_ADMIN_DATABASE_URL` first, as in the provisioning runbook.

### TLS controlled failure

First, prove the host name case offline. On the owner workstation, connect with the libpq of the image, `verify-full`, a Neon host name in `us-east-1` and a dummy password. Neon uses wildcard regional DNS, so any `ep-<name>.us-east-1.aws.neon.tech` name resolves. Set `hostaddr` to the address of `us-east-2.aws.neon.tech`. Make sure that the error says that the server certificate for `*.us-east-2.aws.neon.tech` does not match the host name. The certificate check runs before the password is sent. A control run with a `us-east-1` address passes TLS and fails only at the password.

Then run two executions of the migrate job. The job refuses to run without the `TAILTAG_JOB_REQUEST` identity that the release sends, so each execution sends that request plus one TLS variable. The `^@^` prefix makes `@` the separator, because the request holds commas:

```sh
gcloud run jobs execute tailtag-replica-migrate --region=us-east4 --project=<PROJECT_ID> --wait '--update-env-vars=^@^TAILTAG_JOB_REQUEST={"identity":{"source_sha":"<FULL_SHA>","environment":"replica"}}@SSL_CERT_FILE=/etc/ssl/certs/DigiCert_Global_Root_G2.pem'
gcloud run jobs execute tailtag-replica-migrate --region=us-east4 --project=<PROJECT_ID> --wait '--update-env-vars=^@^TAILTAG_JOB_REQUEST={"identity":{"source_sha":"<FULL_SHA>","environment":"replica"}}@PGHOSTADDR=<US_EAST_2_ADDRESS>'
```

`<FULL_SHA>` is the source SHA that the jobs run. ISRG Root X1 is the root certificate that Neon uses, and the DigiCert file does not hold it. `PGHOSTADDR` is the libpq setting for the server address. Each execution must exit non-zero with the result `FAIL_MIGRATION`, and the service traffic must not move. The job runner prints only one fixed result line, so the logs do not name the libpq error. The offline check above shows the error class. Then run one execution with the request and no TLS variable, and make sure that it ends `PASS`.

### Provider faults

Service faults run on a no-traffic revision behind the `candidate` traffic tag. A revision is one fixed version of the service. A traffic tag gives a revision its own URL, and only the `candidate` tag host passes the replica host pin.

Make the drill revision with the release script's own helpers: `_Release.precheck`, then `_deploy` with the serving digest and a label such as `drill-<n>`. They remove `template.revision`, set the template label `tailtag-release`, keep the image, and add the `candidate` tag on the new revision with 0 percent. `_Release.restore` removes the tag again. Never use `gcloud run deploy` or `gcloud run services update`, because they write a revision name into the template. Terraform ignores template labels, so the next plan shows no change.

| Fault | Make it | Expected result | Restore |
| --- | --- | --- | --- |
| Database unavailable | With the Neon API, set the `disabled` field of the default branch's read-write endpoint to true | A catch attempt gets no 2xx response (the #357 drill saw 500) | Set `disabled` to false, then make sure that `/health/ready` returns 200 |
| Wrong Clerk key | Add a new `clerk-jwt-key` version that holds an unrelated public key, then make the drill revision | A valid token gets 401 | Add the good key again as a new version, then disable the wrong version. Make sure that a valid token gets 200 from the serving revision. |
| R2 credential revoked | Roll the R2 token, as in [R2 runtime token](#r2-runtime-token) | Media fails, and a catch still succeeds | Add the new key, then start fresh instances |

During a fault, a new instance of the serving revision can also read a bad `latest` version. The replica has no players, so the proof records the window instead.

A temporary reviewed probe makes the catch attempts. After the restore, make sure that catch history holds no catch from a failed attempt. A retry of a failed attempt returns 201 once, and a repeat returns 200 `already_caught`. Then run a replica reset to restore the baseline.

Before the Neon fault, test the restore on a temporary branch. Make a branch with its own compute and a role made with the Neon API. Connect with the URI from Neon's `connection_uri` API, then disable and enable the endpoint and time the recovery. Never build a Neon host by hand: hosts carry a cell label such as `c-2`, and a wrong host gets a misleading "password authentication failed". Then delete the branch. In the #357 check, a disabled endpoint refused queries within 2 seconds, and queries worked again 2 seconds after the re-enable. If the restore is slow or fails, stop and ask the owner for another database fault.

### Restore checklist

Before the next release, make sure that each of these is true:

- The `candidate` tag is gone.
- `clerk-jwt-key`, `media-access-key-id` and `media-secret-access-key` have the good value as their newest enabled version.
- The Neon endpoint accepts connections.
- The serving revision returns `/health/ready` 200, and the host identity names the serving revision.
- A foundation plan shows no change.

Cloud Run cannot delete the latest created revision. Delete a drill revision after the next release makes a newer one.

### Leak scan

A canary scan searches for the exact secret values and reports only counts. It reads the `latest` secret versions only. So run it before any rotation drill, or old values that leaked go unseen. Collect each surface into a local directory, then run:

```sh
task replica-canary-scan -- --project <PROJECT_ID> logs=<DIR> actions=<DIR> issues=<DIR> history=<FILE> outputs=<FILE> image=<FILE>
```

| Surface | How to collect it |
| --- | --- |
| Cloud Logging | `gcloud logging read --freshness=31d --format=json` for the replica project. Without `--freshness`, the command reads only the last day. |
| Actions | `gh run download` and the log archive of each replica release run |
| Issues and pull requests | `gh issue view` and `gh pr view` with comments, as JSON, for #352 to #361 and their pull requests |
| Git history | `git log -p --all --text`, so that binary files show their content |
| Terraform outputs | `terraform output -json` for both roots |
| Image | `docker save` of the serving digest, which holds every layer and `build-identity.json` |

The scan reads six secrets: `django-secret-key`, the three database URLs and the two media keys. For a database URL it searches for the password. It adds the Neon admin password when `NEON_ADMIN_DATABASE_URL` is set. It skips `clerk-jwt-key`, which is a public key, and `sentry-dsn`, which has no version until #358. Exit 0 means no match, 1 means a match, and 2 means the scan did not run. Exit 2 also means that the scan left a compressed blob closed, such as a zstd layer. In that case, open the blob first and scan it as its own surface. The replica image holds two known cases. One is the Debian apt log `var/log/apt/eipp.log.xz`, compressed with xz. The other is the python-dateutil `zoneinfo.tar.gz`, a tar inside a gzip one level past the depth limit.

The Neon admin password in Terraform state is a known exposure, so do not scan the state file. Only the owner and `tf-infra` can read it. Delete the collected surfaces after the scan.

### IAM readback

Run Policy Troubleshooter for `tt-runtime`, `tt-migrator`, `tt-maintainer`, `tt-deployer` and `tf-infra`. Policy Troubleshooter is a Google Cloud tool that tells whether IAM grants a permission. Check every named secret, the run and update permissions of each job, and `setIamPolicy` on the service, the jobs and the project. Use the command form in step 7 of the provisioning runbook. Run at most two checks at a time and retry after HTTP 429, because Policy Troubleshooter has a low request quota. Then read the IAM policies of the project, each secret and each job, and list every binding.

The overall answer reads `UNKNOWN_INFO` when the owner cannot read organization deny policies. In that case, record the allow policy state.

## What never to do

- Never change a service template environment value for a drill.
- Never start a release while a drill revision, a wrong secret version or a disabled endpoint is in place.
- Never use a Development or Staging token, key or bucket in a check.
- Never commit a temporary probe or a collected surface.
- Never scan or print the Terraform state.
