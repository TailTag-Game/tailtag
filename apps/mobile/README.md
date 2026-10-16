# TailTag mobile

This directory is the TailTag V0 Flutter host for Android and iOS. FVM selects
Flutter 3.47.2; Dart is bundled with that Flutter SDK.

The Dart project is `tailtag_mobile`. Installed apps use the name `TailTag` and
the identifier `app.tailtag`.

The current UI is only a neutral scaffold proving startup, routing, and
Riverpod composition.

Run these from the repository root on Windows, macOS, or Linux (iOS targets
need macOS with Xcode):

- `task mobile-setup` installs locked dependencies (needs FVM and the pinned
  SDK; run `fvm install` here once).
- `task mobile-check` checks the generated API client against the OpenAPI
  snapshot, then runs format, analysis, and tests; it does not build.
- `task mobile-api-generate` regenerates the API client after a contract change.
- `task mobile-doctor` diagnoses the environment.
- `task mobile-run DEVICE=<id>` launches the app on one connected Android or iOS
  target, using `config/development.json` copied from
  `config/development.example.json`.

Setup, configuration, local connectivity, CI, and the API contract and client
conventions are in
[Mobile contributor environment](../../docs/development/mobile.md). The Clerk
auth boundary is described in its
[Authentication](../../docs/development/mobile.md#authentication) section.
