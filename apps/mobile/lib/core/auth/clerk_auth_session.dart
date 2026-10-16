import "dart:async";

import "package:tailtag_clerk/tailtag_clerk.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_session.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";

/// The [AuthSession] backed by the native Clerk SDKs.
///
/// This is the only app file that imports `package:tailtag_clerk`. TailTag
/// adds no storage for sessions or tokens: each native SDK keeps the session
/// in its own secure storage.
final class ClerkAuthSession implements AuthSession {
  /// Creates a session over a native bridge. Call [start] before use.
  new({required this._bridge, required this._publishableKey});

  /// Creates a session over the real native bridge.
  factory native({required String publishableKey}) =>
      ClerkAuthSession(bridge: TailTagClerk(), publishableKey: publishableKey);

  final TailTagClerk _bridge;
  final String _publishableKey;
  final StreamController<AuthState> _controller =
      StreamController<AuthState>.broadcast();
  StreamSubscription<ClerkBridgeState>? _subscription;
  AuthState _state = const AuthRestoring();
  bool _disposed = false;

  @override
  AuthState get state => _state;

  @override
  Stream<AuthState> get states => _controller.stream;

  /// Starts the native SDK, then follows its state.
  ///
  /// It never throws. If the SDK cannot start, the state becomes
  /// [AuthFailed]. When the returned future completes, the session is
  /// already subscribed to the native state events.
  Future<void> start() async {
    try {
      await _bridge.configure(publishableKey: _publishableKey);
    } on Object catch (error) {
      _set(AuthFailed(_failureFor(error)));
      return;
    }
    if (_disposed) {
      return;
    }
    _subscription = _bridge.states.listen(
      (event) => _set(switch (event) {
        ClerkBridgeState.loading => const AuthRestoring(),
        ClerkBridgeState.signedOut => const AuthSignedOut(),
        ClerkBridgeState.signedIn => const AuthSignedIn(),
      }),
      onError: (Object error) => _set(AuthFailed(_failureFor(error))),
    );
  }

  /// Stops following the native state and closes [states].
  void dispose() {
    _disposed = true;
    unawaited(_subscription?.cancel());
    unawaited(_controller.close());
  }

  @override
  Future<String?> token() async {
    if (_state is! AuthSignedIn) {
      return null;
    }
    try {
      return await _bridge.getToken();
    } on Object {
      return null;
    }
  }

  @override
  Future<void> startEmailCode(String emailAddress) =>
      _guard(() => _bridge.startEmailCode(emailAddress));

  @override
  Future<void> verifyEmailCode(String code) async {
    await _guard(() => _bridge.verifyCode(code));
    _set(const AuthSignedIn());
  }

  @override
  Future<void> signOut() async {
    await _guard(_bridge.signOut);
    _set(const AuthSignedOut());
  }

  @override
  Future<void> recheckSession() async {
    try {
      final token = await _bridge.getToken(skipCache: true);
      if (token == null) {
        _set(const AuthSignedOut());
      }
    } on ClerkBridgeException catch (error) {
      if (error.category == ClerkBridgeErrorCategory.sessionEnded) {
        _set(const AuthSignedOut());
      }
    } on Object {
      // Any other error leaves the state as it is.
    }
  }

  /// Runs [call] and turns a bridge error into an [AuthFailure].
  Future<void> _guard(Future<void> Function() call) async {
    try {
      await call();
    } on Object catch (error) {
      throw _failureFor(error);
    }
  }

  /// Moves to [next] and tells listeners. A repeat of the same state, such as
  /// the native echo of a sign-in that just finished, is dropped.
  void _set(AuthState next) {
    if (_disposed) {
      return;
    }
    if (next is! AuthFailed && next.runtimeType == _state.runtimeType) {
      return;
    }
    _state = next;
    _controller.add(next);
  }

  static AuthFailure _failureFor(Object error) {
    if (error is! ClerkBridgeException) {
      return const AuthUnexpectedFailure();
    }
    return switch (error.category) {
      ClerkBridgeErrorCategory.connectivity => const AuthConnectivityFailure(),
      ClerkBridgeErrorCategory.invalidCode => const AuthInvalidCodeFailure(),
      ClerkBridgeErrorCategory.sessionEnded => const AuthSessionEndedFailure(),
      ClerkBridgeErrorCategory.unsupported => const AuthUnsupportedFailure(),
      ClerkBridgeErrorCategory.unexpected => const AuthUnexpectedFailure(),
    };
  }
}
