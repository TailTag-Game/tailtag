import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/config/app_config.dart";

/// The validated [AppConfig]; must be overridden at the application root.
final appConfigProvider = Provider<AppConfig>(
  (ref) => throw StateError(
    "appConfigProvider was read without an override; start the app with "
    "runTailTagApp.",
  ),
);
