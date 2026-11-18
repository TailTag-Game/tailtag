import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";
import "package:tailtag_mobile/core/catches/catch_providers.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// What the pending counts show. It lives in memory only.
@immutable
final class PendingSummaryState {
  /// Creates a state.
  const new({this.summary, this.serviceOff = false, this.ineligible = false});

  /// The counts of the last good read, or null before one.
  final PendingSummary? summary;

  /// Whether the server has no catch review, so every review entry hides
  /// (#512 AC27).
  final bool serviceOff;

  /// Whether the server refused the read with 403 (#512 AC26).
  final bool ineligible;

  /// Whether the review entries can show.
  bool get available => !serviceOff && !ineligible;
}

/// Owns the pending counts on the owner's suits in every open review
/// window (#512 AC2).
///
/// The convention home, the suit list, and the suit detail screen read it
/// when they open. It also reads on foreground return and after each list
/// read or action on the review screen. A failed read keeps the last
/// counts and shows no message, because the review screen owns errors.
final class PendingSummaryController extends Notifier<PendingSummaryState> {
  int _lastRead = 0;

  @override
  PendingSummaryState build() {
    ref
      ..watch(playerScopeProvider)
      ..listen(foregroundSignalProvider, (_, _) => unawaited(read()));
    _lastRead++;
    return const PendingSummaryState();
  }

  /// Reads the counts.
  Future<void> read() async {
    if (!ref.mounted) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final id = ++_lastRead;
    bool live() => ref.mounted && scope.isActive && id == _lastRead;
    try {
      final summary = await ref
          .read(catchRepositoryProvider)
          .pendingSummary(cancellation: scope.cancellation);
      if (live()) {
        state = PendingSummaryState(summary: summary);
      }
    } on ApiFailure catch (failure) {
      if (!live()) {
        return;
      }
      switch (failure) {
        case ApiNotFoundFailure(code: null):
          state = const PendingSummaryState(serviceOff: true);
        case ApiPermissionFailure():
          state = const PendingSummaryState(ineligible: true);
        case ApiFailure():
          // The last counts stay.
          break;
      }
    }
  }
}

/// The pending counts. They end when no screen shows them or the player
/// scope changes.
final NotifierProvider<PendingSummaryController, PendingSummaryState>
pendingSummaryProvider =
    NotifierProvider.autoDispose<PendingSummaryController, PendingSummaryState>(
      PendingSummaryController.new,
    );

/// Reads the pending counts again when a screen shows them.
void refreshPendingSummary(Ref ref) {
  if (ref.read(pendingSummaryProvider.exists)) {
    unawaited(ref.read(pendingSummaryProvider.notifier).read());
  }
}
