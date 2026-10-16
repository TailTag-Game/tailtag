import "dart:async";

import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_riverpod/misc.dart" show Override;
import "package:tailtag_mobile/core/api/api_providers.dart";
import "package:tailtag_mobile/core/auth/auth_session.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/auth/clerk_auth_session.dart";
import "package:tailtag_mobile/core/config/app_config_provider.dart";

/// The player's session. In production it is a [ClerkAuthSession] built from
/// the validated configuration, started once, and disposed with the provider.
final authSessionProvider = Provider<AuthSession>((ref) {
  final session = ClerkAuthSession.native(
    publishableKey: ref.watch(appConfigProvider).clerkPublishableKey,
  );
  ref.onDispose(session.dispose);
  unawaited(session.start());
  return session;
});

/// The session state: the current value first, then each change.
final authStateProvider = StreamProvider<AuthState>((ref) {
  final session = ref.watch(authSessionProvider);
  final controller = StreamController<AuthState>();
  // Listen before reading `state` so that no change falls in between.
  final subscription = session.states.listen(controller.add);
  controller.add(session.state);
  ref.onDispose(() {
    unawaited(subscription.cancel());
    unawaited(controller.close());
  });
  return controller.stream;
});

/// Makes the [authSessionProvider] session the token provider of the API
/// transport. The application root adds it to its overrides.
final Override authTokenOverride = apiTokenProviderProvider.overrideWith(
  (ref) => ref.watch(authSessionProvider),
);
