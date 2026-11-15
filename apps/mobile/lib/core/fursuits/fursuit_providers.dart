import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_providers.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_repository.dart";
import "package:tailtag_mobile/core/fursuits/photo_source.dart";

/// The repository for the player's suits.
final fursuitRepositoryProvider = Provider<FursuitRepository>(
  (ref) => FursuitRepository(ref.watch(apiTransportProvider)),
);

/// The device photo picker. Tests override it with a fake.
final photoSourceProvider = Provider<PhotoSource>(
  (ref) => const ImagePickerPhotoSource(),
);
