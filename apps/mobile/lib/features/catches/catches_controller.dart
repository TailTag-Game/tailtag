import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_riverpod/misc.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";
import "package:tailtag_mobile/core/catches/catch_providers.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/conventions/convention_providers.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// What the collection shows. It lives in memory only.
@immutable
final class CatchesState {
  /// Creates a state.
  const new({
    required this.filter,
    this.catches,
    this.conventions = const [],
    this.hasNext = false,
    this.reading = false,
    this.loadingMore = false,
    this.readFailure,
  });

  /// The convention filter, or null for every convention.
  final int? filter;

  /// The loaded catches, newest first, or null before the first read.
  final List<CaughtFursuit>? catches;

  /// The player's conventions, for the filter chips.
  final List<Convention> conventions;

  /// Whether a later page exists.
  final bool hasNext;

  /// Whether a first-page read runs.
  final bool reading;

  /// Whether a later page loads.
  final bool loadingMore;

  /// The failure of the last read, or null.
  final ApiFailure? readFailure;
}

/// Owns the private collection while the Catches section is alive. It shows
/// only completed catches, never a pending request.
final class CatchesController extends Notifier<CatchesState> {
  /// Creates the controller for the selected convention [conventionId],
  /// which is the default filter.
  new(this.conventionId);

  /// The selected convention of the home.
  final int conventionId;

  int _lastRead = 0;
  int _page = 1;

  @override
  CatchesState build() {
    ref
      ..watch(playerScopeProvider)
      ..listen(foregroundSignalProvider, (_, _) => unawaited(read()));
    _lastRead++;
    _page = 1;
    return CatchesState(filter: conventionId, reading: true);
  }

  /// Shows [filter] and reads its first page.
  Future<void> select(int? filter) async {
    if (filter == state.filter) {
      return;
    }
    _lastRead++;
    state = CatchesState(filter: filter, conventions: state.conventions);
    await read();
  }

  /// Reads the conventions and the first page of the filter again.
  Future<void> read() async {
    if (!ref.mounted) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final id = ++_lastRead;
    bool live() => ref.mounted && scope.isActive && id == _lastRead;
    final filter = state.filter;
    state = CatchesState(
      filter: filter,
      catches: state.catches,
      conventions: state.conventions,
      hasNext: state.hasNext,
      reading: true,
    );
    try {
      final enrollments = await ref
          .read(conventionRepositoryProvider)
          .listEnrollments(cancellation: scope.cancellation);
      if (!live()) {
        return;
      }
      final page = await ref
          .read(catchRepositoryProvider)
          .listCatches(conventionId: filter, cancellation: scope.cancellation);
      if (!live()) {
        return;
      }
      _page = 1;
      state = CatchesState(
        filter: filter,
        catches: page.items,
        conventions: [
          for (final enrollment in enrollments) enrollment.convention,
        ],
        hasNext: page.hasNext,
      );
    } on ApiCancelledFailure {
      return;
    } on ApiFailure catch (failure) {
      if (live()) {
        state = CatchesState(
          filter: filter,
          catches: state.catches,
          conventions: state.conventions,
          hasNext: state.hasNext,
          readFailure: failure,
        );
      }
    }
  }

  /// Loads the next page, at the end of the list.
  Future<void> loadMore() async {
    if (!state.hasNext || state.loadingMore || state.reading) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    final id = _lastRead;
    bool live() => ref.mounted && scope.isActive && id == _lastRead;
    final current = state;
    state = CatchesState(
      filter: current.filter,
      catches: current.catches,
      conventions: current.conventions,
      hasNext: current.hasNext,
      loadingMore: true,
    );
    try {
      final page = await ref
          .read(catchRepositoryProvider)
          .listCatches(
            conventionId: current.filter,
            page: _page + 1,
            cancellation: scope.cancellation,
          );
      if (!live()) {
        return;
      }
      _page++;
      state = CatchesState(
        filter: current.filter,
        catches: [...?current.catches, ...page.items],
        conventions: current.conventions,
        hasNext: page.hasNext,
      );
    } on ApiCancelledFailure {
      return;
    } on ApiFailure catch (failure) {
      if (live()) {
        state = CatchesState(
          filter: current.filter,
          catches: current.catches,
          conventions: current.conventions,
          hasNext: current.hasNext,
          readFailure: failure,
        );
      }
    }
  }
}

/// The collection of the selected convention's home. It ends when the
/// Catches section closes or the player scope changes.
final NotifierProviderFamily<CatchesController, CatchesState, int>
catchesControllerProvider = NotifierProvider.autoDispose
    .family<CatchesController, CatchesState, int>(CatchesController.new);
