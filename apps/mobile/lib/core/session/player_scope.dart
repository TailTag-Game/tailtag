import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_cancellation.dart";

/// One player session as the app sees it: one value of the session epoch.
///
/// A new scope starts when a session starts and when sign-out starts. The
/// previous scope closes at that moment: its [cancellation] aborts every API
/// call that used it, and [isActive] becomes false. Async work captures the
/// scope before it waits and checks [isActive] before it writes state, so a
/// late response can never reach a later session.
final class PlayerScope {
  /// Creates an active scope for [epoch].
  new(this.epoch);

  /// The session epoch. It goes up by one with each new scope.
  final int epoch;

  /// Aborts the API calls of this scope when the scope closes.
  final ApiCancellation cancellation = ApiCancellation();

  bool _active = true;

  /// Whether this is still the current scope.
  bool get isActive => _active;

  void _close() {
    _active = false;
    cancellation.cancel();
  }

  @override
  String toString() => "PlayerScope($epoch)";
}

/// Owns the current [PlayerScope].
///
/// Only the entry coordinator calls [advance]. Player-scoped providers watch
/// [playerScopeProvider], so a new scope disposes and rebuilds them. That
/// clears their data, their forms, and their pending work.
final class PlayerScopeController extends Notifier<PlayerScope> {
  @override
  PlayerScope build() => PlayerScope(0);

  /// Closes the current scope and starts the next one.
  void advance() {
    final previous = state.._close();
    state = PlayerScope(previous.epoch + 1);
  }
}

/// The current player scope.
final playerScopeProvider =
    NotifierProvider<PlayerScopeController, PlayerScope>(
      PlayerScopeController.new,
    );
