# V0 Flutter application scaffold

**Issue:** [#131 — Scaffold the TailTag V0 Flutter application](https://github.com/TailTag-Game/tailtag/issues/131)

**Parent:** [#128 — Establish the TailTag V0 Flutter application foundation](https://github.com/TailTag-Game/tailtag/issues/128)

**Status:** Approved for implementation

## Goal

Create the smallest reproducible Android and iOS Flutter host that implements
the architecture approved by issue #130. The scaffold proves that the pinned
toolchain, native identifiers, application shell, routing, state-composition
root, and supported platform projects work without introducing product
behavior or consuming work assigned to later Flutter-foundation issues.

## Frozen decisions

- The application lives at `apps/mobile/`.
- The Dart package and Flutter project name is `tailtag_mobile`.
- The installed and user-facing application name is `TailTag`.
- Android application ID and namespace are exactly `app.tailtag`.
- The iOS application bundle identifier is exactly `app.tailtag`.
- Android supports API 26 and newer. iOS supports 15.1 and newer.
- `apps/mobile/.fvmrc` pins exact stable Flutter `3.47.1`; Dart comes from that
  Flutter SDK and is not independently pinned.
- Generate and retain only Android and iOS platform projects.
- Direct Dart dependencies use ordinary compatible constraints, and the
  resolved application dependency graph is committed in `pubspec.lock`.
- Issue #131 uses `flutter_riverpod` and `go_router`. It does not add
  `package:http`, `clerk_flutter`, or another unused architecture dependency.
- The root shell is `ProviderScope` -> `MaterialApp.router`, with one `/` route
  rendering a neutral static `TailTag` placeholder.
- The placeholder uses default Material behavior. It is not a product screen
  and does not establish the future TailTag design system.
- The initial source boundaries are `lib/app/`, `lib/core/`, and
  `lib/features/`. Only `lib/app/` contains production Dart behavior in this
  issue. `core` and `features` receive concise boundary documentation rather
  than speculative modules, placeholder abstractions, or empty hierarchies.
- Build and launch evidence is sanitized in the pull request or issue. Machine
  logs and screenshots are not committed.

## Chosen scaffold approach

Use Flutter's generator with the pinned SDK and explicit Android/iOS-only
selection, then deliberately normalize the result to this contract. Do not
treat generator defaults as authoritative for identifiers, names, minimum
platform versions, files, or example behavior.

This approach is preferred over committing the generator wholesale because it
keeps only reproducible host files. It is preferred over hand-authoring native
projects because the pinned Flutter generator provides the most reliable
version-matched baseline.

## Application structure

The intended application-owned structure is:

```text
apps/mobile/
├── .fvmrc
├── README.md
├── analysis_options.yaml
├── android/
├── ios/
├── lib/
│   ├── main.dart
│   ├── app/
│   │   ├── app.dart
│   │   └── router.dart
│   ├── core/
│   │   └── README.md
│   └── features/
│       └── README.md
├── pubspec.lock
├── pubspec.yaml
└── test/
    └── app/
        └── app_test.dart
```

Generated files required by the Android and iOS hosts remain in their standard
locations. Generated web, desktop, IDE, local-tool, build-output, and example
counter files do not remain. The implementation may retain other
Flutter-required metadata files when the pinned toolchain needs them for
reproducibility.

`main.dart` owns only framework startup and the root `ProviderScope`.
`app.dart` owns the `MaterialApp.router` application host. `router.dart` owns
the single route and neutral placeholder. The placeholder must not introduce
authentication, onboarding, convention, fursuit, gameplay, collection, API,
or design-system concepts.

The `core` and `features` boundary documents state the approved dependency
direction: features may use explicitly owned shared/core infrastructure but
may not import sibling features. They do not predict future feature names or
create unused layers.

## Native configuration

Generate the `tailtag_mobile` Flutter project and then explicitly set the final
native identity. In particular, do not rely on `flutter create --org
app.tailtag`, because its derived identifier would include the project name.

All relevant Android application ID and namespace declarations must resolve to
`app.tailtag`, and the minimum SDK must be API 26. All relevant iOS build
configurations must resolve the application bundle identifier to `app.tailtag`
and the deployment target to iOS 15.1. Generated test-host identifiers may use
the platform's conventional derived suffix where required, but no installable
application configuration may retain a generator-derived `tailtag_mobile`
identifier.

The installed application label/display name is `TailTag` on both platforms.
No signing identity, provisioning profile, store metadata, legacy identifier,
or migration behavior is introduced.

## Dependency and repository policy

Resolve dependencies using the FVM-selected SDK and commit `pubspec.lock`.
Select current `flutter_riverpod` and `go_router` releases that support Flutter
3.47.1 and Dart 3.13.1, verified against authoritative package metadata and the
actual solver. Do not independently pin Dart or follow a moving Flutter
channel.

Align Flutter build outputs, local FVM state, IDE files, and platform-local
state with the repository's ignore conventions. Keep the dirty primary checkout
out of scaffold verification evidence. The later-approved root
`AGENTS.override.md` ignore and obsolete documentation removals are deliberate
repository housekeeping. No contributor path, secret, token, emulator
identifier, Xcode user data, or machine-specific state may be committed.

## Documentation

Update the existing mobile and structural documentation to say that the
scaffold now exists and accurately describe its location and boundaries.
Remove only statements made obsolete by issue #131. Do not document or imply
root `make mobile-*` commands, runtime `AppConfig`, API connectivity, Clerk
configuration, diagnostics, CI, or clean-environment onboarding owned by
issues #132 through #136.

## Acceptance Contract

Completion requires fresh evidence for all of the following:

1. `apps/mobile/` is a Flutter project named `tailtag_mobile`, while Android
   and iOS install/display the name `TailTag`.
2. `.fvmrc` selects exact Flutter 3.47.1 and the resolved Dart version is the
   SDK-bundled Dart 3.13.1.
3. Only Android and iOS platform projects exist.
4. Every installable Android configuration uses application ID and namespace
   `app.tailtag`, with minimum API 26.
5. Every installable iOS configuration uses bundle identifier `app.tailtag`,
   with minimum iOS 15.1.
6. Locked dependency resolution succeeds without manually editing generated
   state.
7. The app starts through `ProviderScope` and `MaterialApp.router`; `/` renders
   the static `TailTag` placeholder.
8. The widget test rejects a scaffold that fails to start or does not render
   the approved placeholder through the configured root route.
9. Static analysis and tests pass with the pinned SDK.
10. Android debug build and emulator launch succeed.
11. iOS debug simulator build and Simulator launch succeed on macOS.
12. Startup requires no backend, live configuration, Clerk state, secrets, or
    developer-machine path.
13. A temporary clean worktree created from the committed implementation
    branch reproduces locked resolution, analysis, tests, and both platform
    builds. Platform launches may use the same committed branch and appropriate
    host environments, with sanitized evidence recorded outside the repository.
14. Structural documentation accurately reflects the scaffold without
    claiming capability owned by later issues.

## Explicit exclusions

Issue #131 does not implement:

- product screens, navigation flows, or feature behavior;
- TailTag theme, assets, design tokens, or shared product widgets;
- runtime configuration, flavors, schemes, API environment selection, or
  Android local-host mapping;
- HTTP transport, OpenAPI generation, DTOs, repositories, or backend calls;
- Clerk initialization, authentication, token handling, or session storage;
- root mobile commands, contributor diagnostics, or CI workflows;
- web, desktop, signing, store distribution, notifications, analytics, crash
  reporting, or production configuration.

Those boundaries remain owned by issues #132 through #136 and #139.

## Replan triggers

Stop and return for approval if implementation evidence requires changing the
Flutter/Dart version, native identifiers, minimum platform versions, supported
platform set, dependency ownership, root shell, public architecture boundary,
or another child issue's scope. Ordinary generator-file normalization and
version-compatible package selection do not require a new product decision.
