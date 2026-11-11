import "package:flutter/widgets.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/app/app.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/config/app_config.dart";
import "package:tailtag_mobile/core/config/app_config_provider.dart";

/// Validates compile-time configuration, then starts the app.
void main() => runTailTagApp(AppConfig.fromEnvironment());

/// Starts the app with validated configuration available to Riverpod.
void runTailTagApp(AppConfig config) {
  runApp(
    ProviderScope(
      overrides: [
        appConfigProvider.overrideWithValue(config),
        authTokenOverride,
      ],
      child: const TailTagApp(),
    ),
  );
}
