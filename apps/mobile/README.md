# TailTag mobile

This directory is the TailTag V0 Flutter host for Android and iOS. FVM selects
Flutter 3.47.2; Dart is bundled with that Flutter SDK.

The Dart project is `tailtag_mobile`. Installed apps use the name `TailTag` and
the identifier `app.tailtag`.

The current UI is only a neutral scaffold proving startup, routing, and
Riverpod composition.

Run these from the repository root on macOS or Linux (Windows uses the raw
`fvm` commands in the guide):

- `make mobile-setup` installs locked dependencies (needs FVM and the pinned
  SDK; run `fvm install` here once).
- `make mobile-check` runs format, analysis, and tests; it does not build.
- `make mobile-doctor` diagnoses the environment.
- `make mobile-run DEVICE=<id>` launches the app on one connected Android or iOS
  target, using `config/development.json` copied from
  `config/development.example.json`.

Setup, configuration, local connectivity, and the Windows command table are in
[Mobile contributor environment](../../docs/development/mobile.md). CI;
API/OpenAPI integration; and Clerk integration remain assigned to issues
#133–#135.
