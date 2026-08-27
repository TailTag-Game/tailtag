# Use Flutter for mobile V0

**Status:** accepted

## Context and constraints

TailTag needs a mobile client that can serve Android and iOS without creating two independent V0 client implementations. The backend is the source of business and domain rules; its current unversioned product namespace is `/api/`, with the authoritative schema at `/api/schema/`, documentation at `/api/docs/`, and `/api/me/` as the authenticated identity proof.

The future application belongs at `apps/mobile/`. Its canonical domain is `tailtag.app`; Android application ID and namespace, and the iOS bundle identifier, are all `app.tailtag`. Retired legacy applications and `finnthepanther` identifiers have no migration, compatibility, signing, or store-continuity requirements.

## Decision

Use Flutter for the V0 Android and iOS application. Issue #131 will create and commit repository-owned `apps/mobile/.fvmrc` configuration pinning exact stable Flutter `3.47.1`; use the Dart SDK bundled with Flutter rather than independently pinning Dart. The corresponding upstream Flutter tag is `6655482ec06e547f90abf8ae7590466f4415978d` and it bundles Dart `3.13.1`. Flutter upgrades require an explicit reviewed pull request and must never track a moving channel.

Support Android API 24 and newer and iOS 15.1 and newer. Phones are primary; tablets must remain compatible but receive no V0-specific optimization. Physical devices are optional for baseline validation.

Organize the application by feature with Views, ViewModels, Repositories, and Services. Features may depend only on shared, explicitly owned boundaries, not on sibling features. Do not add a domain/use-case layer until demonstrated complexity justifies it. Use `go_router` for routing, Riverpod for state and dependency ownership without a second DI framework or foundation code generation, and `package:http` through an injected, composable `Client`.

Generate a low-level OpenAPI client and DTO layer from the backend schema, but hide it behind TailTag-owned repositories and services: feature code must never import generated wire models. Pin the generator and its configuration, and prove deterministic regeneration followed by a clean-diff drift check.

Use a typed, TailTag-owned `AppConfig` populated from compile-time Dart defines. Selecting a local or Railway Development API is configuration, not flavors or schemes. Values embedded in an app are not secrets.

Use `clerk_flutter` only behind a TailTag-owned injectable auth/session interface. Clerk owns session persistence and token refresh; TailTag adds no separate persistent bearer-token store, and feature code receives no Clerk types. The mobile API sends exactly one Clerk session token as `Authorization: Bearer`. This SDK is an initial beta direction to reassess in #135, not a dependency pin in this decision.

## Alternatives considered

Separate native Android and iOS clients, a different cross-platform client framework, a moving Flutter channel, direct feature access to generated API or Clerk types, and a custom persistent bearer-token store.

## Consequences and risks

Flutter gives TailTag one client architecture and shared feature behavior, but requires disciplined feature boundaries and repository-owned SDK/tooling configuration. Generated wire contracts and Clerk SDK details are deliberately contained so that their changes do not spread through product features.

Compile-time values must be treated as public application contents. Server-side authorization remains authoritative; a client token is transport authentication, not a substitute for server-controlled domain rules.

## Validation and future migration

Issue #131 owns the scaffold, identifiers, minimum implementations, committed `apps/mobile/.fvmrc` exact Flutter `3.47.1` pin, and Android/iOS build and launch proof. Issue #132 owns root commands, `AppConfig` implementation, configuration inputs, and diagnostics. Issue #133 owns CI. Issue #134 owns generator and client implementation plus regeneration proof. Issue #135 owns live Clerk proof. Issue #136 owns independent clean-environment validation. Frontend architecture requires approval from `@TailTag-Game/core-maintainers`, with relevant mobile/frontend contributors reviewing changes.

This is a documentation-only decision: it creates no application secret, Flutter scaffold, dependency, platform project, screen, command or diagnostic implementation, product behavior, or `apps/mobile/` directory. If Flutter or the contained integrations cease to meet the approved requirements, replace this ADR through a reviewed successor that preserves API/auth contracts and provides a migration and rollback plan.

## References

- [Flutter SDK archive](https://docs.flutter.dev/install/archive) and [supported platforms](https://docs.flutter.dev/reference/supported-platforms)
- [FVM project configuration](https://fvm.app/documentation/getting-started/configuration)
- [Dart compilation environment declarations](https://api.dart.dev/stable/dart-core/String/String.fromEnvironment.html)
- [`package:http`](https://pub.dev/packages/http), [Riverpod testing and overrides](https://riverpod.dev/docs/how_to/testing), and [`go_router`](https://pub.dev/packages/go_router)
- [Clerk Flutter SDK](https://clerk.com/docs/references/flutter/overview)
