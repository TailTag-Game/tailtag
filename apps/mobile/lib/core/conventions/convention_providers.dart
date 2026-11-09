import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_providers.dart";
import "package:tailtag_mobile/core/conventions/convention_repository.dart";

/// The repository for conventions and the player's participation.
final conventionRepositoryProvider = Provider<ConventionRepository>(
  (ref) => ConventionRepository(ref.watch(apiTransportProvider)),
);
