# Replacement Development hosted Clerk authentication

Status: focused amendment to the replacement Development candidate contract.

The replacement Development Clerk Account Portal completed an ordinary user
sign-in. A browser-memory claim check showed that its session token's `azp`
matches that exact hosted portal origin and does not match
`http://localhost:3000`. No token or user identifier was retained. The merged
Development readiness guard currently accepts only the localhost origin, so
it cannot authorize this ordinary hosted-portal session.

## Acceptance contract

- Development readiness requires the **ordered exact pair** of authorized
  parties: the existing `http://localhost:3000` backend-tooling origin, then
  the separately pinned replacement Development Clerk hosted portal origin.
  A missing, reordered, extra, or different origin fails readiness.
- The hosted portal pin uses a code-owned, framed SHA-256 commitment to the
  exact HTTPS origin. The provider hostname is not accepted by suffix or
  wildcard. No caller-supplied expected digest is trusted.
- Replacement Railway runtime, database, API hostname, and Staging
  candidate/canonical guards retain their existing contracts.
- A fresh ordinary Development session token must authenticate at its own
  `/api/me/`; Development and Staging tokens must each fail at the other API.

## Test surface and scope

Use the existing Development readiness and target-binding test surfaces.
Synthetic origins may replace the digest constant within disposable unit
tests. Do not add an application authentication API or alter Clerk token
verification semantics. The production change is limited to exact origin
pinning and the Development readiness assertion.

Stage the new Railway Development `CLERK_AUTHORIZED_PARTIES` value with
`--skip-deploys` before merging the reviewed source change. The next controlled
Development deployment must carry both the new code and setting. Verify the
new deployment's identity/readiness and ordinary authenticated API smoke
before describing Development as usable.
