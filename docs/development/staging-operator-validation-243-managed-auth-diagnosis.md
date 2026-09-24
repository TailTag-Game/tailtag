# #243 managed operator authentication diagnosis

Status: frozen repository-only diagnostic contract. The 2026-09-24 matrix
`FAIL_AUTHENTICATION` remains historical evidence; cases 1–9 were not exercised.
The dedicated limited operator remains active and the exclusive Staging window
remains held. This contract authorizes no credential change by itself.

## Scope and acceptance

Use one reviewed, exact-instance, interactive **read-only** diagnostic to test
only the managed operator's local credential. The result is evidence about a
local password match, not proof that the Django admin HTTP login protocol
succeeded. The subsequent matrix must establish that real HTTP behavior.

1. Before SSH, require the approved GitHub and Railway identities, canonical
   credential-free Staging preflight, approved deployment receipt, one exact
   running instance, repeated public preflight, and a separate read-only
   operator inspector `PASS` for both roles. In the remote process, repeat the
   exact build/runtime target and full role/fixture checks before prompting.
2. Require a real stdin/stdout terminal and hidden, non-echoing input for one
   managed identifier/password pair. Input is never accepted in argv, env,
   files, logs or chat. Refuse a missing/non-hidden terminal. No alternate
   account or automatic retry.
3. In a short PostgreSQL `READ ONLY` transaction, require exactly the current
   managed-group member and the frozen exact #205 role shape before prompting.
   Close that transaction while waiting for hidden input. Then use a fresh
   `READ ONLY` transaction to recheck the role, look up the entered identifier
   without printing it, and require it to identify that exact member. Require
   a usable password. Call Django's `check_password` without a setter so hash
   upgrade cannot write. The query and check must cause no database, audit,
   session, provider or application mutation. Reject Django debug/query
   logging and installed SQL execution wrappers before any secret input, so
   the entered identifier cannot reach a custom query logger.
4. Emit only fixed remote classifications:

   - `CREDENTIAL_ACCEPTED`: the entered identifier selects the sole exact
     managed operator and the local password matches its stored hash;
   - `CREDENTIAL_REJECTED`: exact identity, usable hash, password mismatch;
   - `IDENTITY_MISMATCH` or `IDENTITY_AMBIGUOUS`: identifier does not select
     that sole actor, or selection/group membership is ambiguous;
   - `PASSWORD_UNUSABLE`: selected exact actor has no usable local hash;
   - `AUTH_PROTOCOL_FAILURE`: real hidden input unavailable or the password
     checker cannot produce a reliable boolean;
   - `EXECUTION_FAILURE`: database/query/startup failure;
   - `TARGET_OR_ROLE_FAILURE`: target or inspected role prerequisite fails.

   The local launcher separately reports a sanitized target/guard failure or
   transport uncertainty. For transport, distinguish a nonzero exit,
   unallowlisted stderr, timeout and execution exception using fixed category
   codes without retaining raw output. The launcher returns the existing
   public result shape `{result, phase, identity, target_verified, window_utc}`;
   its `target_verified` remains false because it cannot parse inherited
   remote stdout. A zero transport exit is only
   `TRANSPORT_EXITED_ZERO_UNVERIFIED`. It must not turn a displayed remote
   classification or an SSH exit code alone into authenticated success.
   Unknown errors remain fail closed and never print exception content.
   The positive live gate requires the combined sanitized Terminal evidence:
   remote `CREDENTIAL_ACCEPTED` with the exact verified public identity and
   valid window, the unique completion marker, and local
   `TRANSPORT_EXITED_ZERO_UNVERIFIED` with zero exit and allowlisted stderr.
   Any missing or conflicting part is uncertain and stops this attempt.
5. Preserve the result and observed source/deployment in a new chronological
   entry. Do not rewrite the prior matrix failure. A `CREDENTIAL_ACCEPTED`
   permits a new fully guarded matrix attempt from case 1 under the standing
   authorization. A submitted `CREDENTIAL_REJECTED` establishes a mismatch
   only; it does not distinguish a stale password from an input mistake.
   Credential reconciliation is considered only after the operator confirms
   the intended exact managed identity and credential situation, with both
   roles still independently `PASS`, and only through the existing guarded
   bootstrap's exact-account password path. Recheck roles and credentials
   afterward. `PASSWORD_UNUSABLE` at the mandatory inspector gate is a hard
   stop because managed `PASS` is absent. Any role, target, identity, query
   or protocol ambiguity stops before mutation.

The mandatory inspector gate already requires a usable managed password. If
that is the sole drift in an otherwise exact managed role, the inspector emits
`FAIL_MANAGED_OPERATOR_PASSWORD_UNUSABLE`; the launcher reports the fixed
`PASSWORD_UNUSABLE` category and stops before SSH or a secret prompt. This is
not an inspector `PASS` and does not authorize credential rotation. The
launcher has not completed its second public preflight on that branch, so its
identity field remains unset; cite the separate verified inspector evidence
for the observed tuple. The remote check also returns `PASSWORD_UNUSABLE`
without prompting if the hash becomes unusable after an inspector `PASS`.

## Test surface and proof

STANDARD COMPACT; SECURITY, DATA INTEGRITY, TEST ADEQUACY and RELIABILITY.
Extend the established exact-instance inspector/SSH pattern with one focused
diagnostic entry point and a dedicated local test file. Public seams are the
launcher `run()` result, reviewed remote bootstrap running with controlled
local Django/ORM fixtures, and a real local PTY for non-echo. Provider calls
may be faked; the actual User model and PostgreSQL read-only transaction must
be exercised against disposable local data. Do not add product APIs or model
changes. Tests must reject plausible wrong-role, extra-member, wrong password,
unusable hash, no TTY, query failure, raw-output and write-path mutants.
Local tests do not establish live Staging credential state. Independent review
must approve target pinning, permission exactness, no writes, privacy and the
limited meaning of `CREDENTIAL_ACCEPTED` before one live diagnostic call.
