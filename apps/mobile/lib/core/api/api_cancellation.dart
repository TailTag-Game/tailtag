import "dart:async";

/// A handle that aborts the in-flight API calls it was passed to.
///
/// A provider creates one, passes it to repository calls, and registers
/// `ref.onDispose(cancellation.cancel)`. Cancelled calls throw
/// `ApiCancelledFailure`.
final class ApiCancellation {
  final Completer<void> _completer = Completer<void>();

  /// Whether [cancel] has been called.
  bool get isCancelled => _completer.isCompleted;

  /// Completes once [cancel] has been called.
  Future<void> get whenCancelled => _completer.future;

  /// Aborts every call using this handle. Safe to call more than once.
  void cancel() {
    if (!_completer.isCompleted) {
      _completer.complete();
    }
  }
}
