# Catch administration and operator correction

## Overview

Catch administration provides authorized TailTag operators with visibility into confirmed catch records and an operational mechanism to remove invalid, disputed, or erroneous catches.

Catch records represent immutable gameplay facts created through player interactions. In rare operational scenarios—such as duplicate or mistaken confirmations during on-site dispute resolution—operators require a safe, auditable method to inspect and correct catch records.

## Immutable catch records

Catches cannot be manually created or edited through the Django administration interface:

- **No manual creation:** Catches can only be minted through the authoritative confirmation pipeline (`confirm_catch` in `catches.services`). Operators cannot create synthetic catches or arbitrary awards via admin.
- **No modification:** Catch attributes (`id`, `catcher_user`, `fursuit`, `convention`, `activation`, `catch_session`, and `caught_at`) are read-only. Gameplay provenance cannot be altered after the fact.
- **Bulk actions disabled:** Standard Django admin bulk actions (including bulk delete) are explicitly removed (`actions = None`, `delete_queryset` raises `PermissionDenied`). Each correction must be reviewed and executed individually.

## Permission boundary and operator authorization

Access to the Catch administration interface is restricted to authorized deletion operators:

- **Staff and superuser authorization:** Access requires an authenticated staff user (`is_staff=True`) with explicit `catches.delete_catch` model permission or superuser status.
- **Inspection tied to deletion authority:** Catch inspection (`has_view_permission`) strictly requires `has_delete_permission`. Staff users with only `catches.view_catch` permission are denied access to prevent unauthorized inspection of gameplay catches.
- **Player access barred:** Non-staff player accounts and unauthenticated requests are denied access and redirected to login.

## Safe search and inspection workflows

Operators locate catch records using safe, non-sensitive search identifiers:

- **Supported search fields:**
  - Catch ID (exact match)
  - Catcher user ID (exact internal integer ID)
  - Catcher Clerk user ID (e.g., `user_...`)
  - Fursuit name (substring match)
  - Fursuit TailTag ID (exact UUID string, e.g. `3fa85f64-5717-4562-b3fc-2c963f66afa6`)
  - Convention name (substring match)

### Sensitive credential protection and query sanitization

Raw QR catch credentials and payload strings (e.g., `tailtag:catch:v1:...`) represent short-lived secrets and must never be queried, stored in access logs, or retained in operational notes.

To defend against inadvertent operator copy-paste of raw QR tokens or payload strings into the search bar, a multi-layer defense is enforced:

1. **Client-side submission prevention:** The admin changelist template (`admin/catches/catch/change_list.html`) intercepts search form submissions (`#changelist-search`). If the query contains a pattern matching a sensitive QR catch credential token (`CATCH_CREDENTIAL_TOKEN_PATTERN`), client-side JavaScript cancels the form submission (`event.preventDefault()`), clears the input field, and warns the operator that credential tokens cannot be searched. This prevents the credential from ever being transmitted across the wire as a GET request URL.
2. **Server-side detection and immediate redirect:** If a request bearing a credential token is received by Django (e.g. from an API client, scripted query, or if JavaScript is disabled), `CatchAdmin.changelist_view` detects the pattern and immediately returns an HTTP 302 redirect (`HttpResponseRedirect`) to a sanitized URL (`?q=__tailtag_admin_credential_query_redacted__`). This redirect forces the browser to discard the original credential-bearing URL, updating the address bar and browser history to the sanitized URL so that subsequent same-origin navigation does not leak the secret in `Referer` headers.
3. **Railway and Gunicorn logging boundary:** In production, Gunicorn is invoked without `--access-logfile` (`CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]`). Gunicorn does not emit HTTP request-line access logs to container stdout, preventing query parameters from entering Railway application logs. Django's application logging logs structured events without dumping raw GET query strings. Upstream ingress or reverse proxies capture raw network request lines at the edge before application middleware executes; the client-side form interception is the active defense against exposing credentials in ingress request lines.

## Operator correction and deletion

When a catch is confirmed to be invalid or disputed, authorized staff operators can remove it through the individual object delete view in Django admin.

### Atomic execution and data integrity

Catch removal is executed by `remove_catch_as_operator` in `catches.services`:

1. **Transaction isolation and row locking:** Execution occurs within an atomic transaction (`transaction.atomic()`). The target `Catch` row is locked with `select_for_update()`.
2. **Referential integrity:** The `Catch` model references foreign keys (`catcher_user`, `fursuit`, `convention`, `activation`, `catch_session`) with `on_delete=models.PROTECT`. Deleting the `Catch` removes only the catch event itself; upstream accounts, fursuits, activations, and convention records remain untouched and intact.
3. **Committed audit logging:** Following deletion, a structured audit log entry is registered with `transaction.on_commit()`:
   ```text
   Operator removed catch <catch_id> (catcher_user_id=<user_id>, fursuit_id=<fursuit_id>, convention_id=<convention_id>, activation_id=<activation_id>, catch_session_id=<session_id>).
   ```
   Because it is registered with `transaction.on_commit()`, the log is emitted only after the transaction commits successfully. The audit log contains only internal database identifiers and never includes secrets, tokens, or credential payloads.
