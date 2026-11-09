import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_providers.dart";
import "package:tailtag_mobile/core/session/player_profile_repository.dart";

/// The repository for the signed-in player's profile.
final playerProfileRepositoryProvider = Provider<PlayerProfileRepository>(
  (ref) => PlayerProfileRepository(ref.watch(apiTransportProvider)),
);
