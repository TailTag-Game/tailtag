# TailTag mobile

This directory is the TailTag V0 Flutter host for Android and iOS. FVM selects
Flutter 3.47.1; Dart is bundled with that Flutter SDK.

The Dart project is `tailtag_mobile`. Installed apps use the name `TailTag` and
the identifier `app.tailtag`.

The current UI is only a neutral scaffold proving startup, routing, and
Riverpod composition.

Root commands, configuration, and diagnostics; CI; API/OpenAPI integration;
and Clerk integration remain assigned to issues #132–#135. Do not infer setup
or run commands from this scaffold: issue #132 defines the contributor
interface.
