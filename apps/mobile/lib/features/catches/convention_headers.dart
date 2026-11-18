import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/conventions/convention_providers.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// Reads the conventions that the group headers of a request list need,
/// by ID (#511 AC22, #512 AC10).
///
/// The enrollments give most of them. A request can belong to a convention
/// that the player is no longer enrolled in, so each missing one is read
/// on its own. A failed single read leaves that convention out, and its
/// header falls back to "Another convention". A failed enrollments read
/// throws its [ApiFailure]. The result is null when [live] turns false.
Future<Map<int, Convention>?> readHeaderConventions(
  Ref ref,
  PlayerScope scope,
  Iterable<int> conventionIds, {
  required bool Function() live,
}) async {
  final repository = ref.read(conventionRepositoryProvider);
  final enrollments = await repository.listEnrollments(
    cancellation: scope.cancellation,
  );
  if (!live()) {
    return null;
  }
  final conventions = <int, Convention>{
    for (final enrollment in enrollments)
      enrollment.convention.id: enrollment.convention,
  };
  final missing = {
    for (final id in conventionIds)
      if (!conventions.containsKey(id)) id,
  };
  for (final id in missing) {
    try {
      conventions[id] = await repository.readConvention(
        id,
        cancellation: scope.cancellation,
      );
    } on ApiFailure {
      // The header falls back to "Another convention".
    }
    if (!live()) {
      return null;
    }
  }
  return conventions;
}
