import "package:flutter_riverpod/flutter_riverpod.dart";

/// Counts each return of the app from a hidden state.
///
/// The app root fires it. The coordinator and the feature controllers listen
/// to it, and each one decides whether its stage reloads.
final class ForegroundSignal extends Notifier<int> {
  @override
  int build() => 0;

  /// Reports one return to the foreground.
  void fire() => state++;
}

/// The foreground signal.
final foregroundSignalProvider = NotifierProvider<ForegroundSignal, int>(
  ForegroundSignal.new,
);
