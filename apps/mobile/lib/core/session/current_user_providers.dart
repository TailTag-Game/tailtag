import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_providers.dart";
import "package:tailtag_mobile/core/session/current_user_repository.dart";

/// The repository for the signed-in player's identity.
final currentUserRepositoryProvider = Provider<CurrentUserRepository>(
  (ref) => CurrentUserRepository(ref.watch(apiTransportProvider)),
);
