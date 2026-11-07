import "dart:async";

import "package:tailtag_clerk/tailtag_clerk.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
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
  bool _attemptPending = false;

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
  Future<void> startEmailSignIn(String emailAddress) =>
      _attempt(() => _bridge.startEmailSignIn(emailAddress));

  @override
  Future<void> startEmailSignUp(String emailAddress) =>
      _attempt(() => _bridge.startEmailSignUp(emailAddress));

  @override
  Future<void> resendEmailCode() => _attempt(_bridge.resendEmailCode);

  /// The state is not set here: [AuthSignedIn] comes only from the native
  /// state events, which report the SDK session status.
  @override
  Future<AuthAttemptResult> verifyEmailCode(String code) =>
      _attempt(() async => _resultFor(await _bridge.verifyEmailCode(code)));

  /// The contract allows only three failures here. The native side maps
  /// Clerk errors with the shared email table, so any other category, such
  /// as a rate limit, becomes [AuthUnexpectedFailure].
  @override
  Future<AuthAttemptResult> continueWithGoogle() =>
      _provider(_bridge.continueWithGoogle);

  /// Like [continueWithGoogle], and [AuthUnsupportedFailure] also stays,
  /// because Android has no Apple flow. Its plugin has no Apple method.
  @override
  Future<AuthAttemptResult> continueWithApple() =>
      _provider(_bridge.continueWithApple, allowUnsupported: true);

  /// Runs one provider [call]. The state is not set here: [AuthSignedIn]
  /// comes only from the native state events, which report the SDK session
  /// status. Only the allowed failure categories stay. Every other one
  /// becomes [AuthUnexpectedFailure].
  Future<AuthAttemptResult> _provider(
    Future<String?> Function() call, {
    bool allowUnsupported = false,
  }) async {
    try {
      return await _attempt(() async => _resultFor(await call()));
    } on AuthFailure catch (failure) {
      throw switch (failure) {
        AuthProviderUnavailableFailure() ||
        AuthConnectivityFailure() => failure,
        AuthUnsupportedFailure() when allowUnsupported => failure,
        _ => const AuthUnexpectedFailure(),
      };
    }
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

  @override
  Future<void> reloadSession() async {
    if (_disposed) {
      return;
    }
    if (_subscription == null) {
      // The SDK never started, so start it again.
      _set(const AuthRestoring());
      await start();
      return;
    }
    _set(const AuthRestoring());
    try {
      await _bridge.reload();
    } on Object catch (error) {
      _set(AuthFailed(_failureFor(error)));
    }
  }

  /// Runs one account-access [call] and turns a bridge error into an
  /// [AuthFailure]. A second call while one is pending throws
  /// [AuthUnexpectedFailure] and leaves the pending call alone.
  Future<T> _attempt<T>(Future<T> Function() call) async {
    if (_attemptPending) {
      throw const AuthUnexpectedFailure();
    }
    _attemptPending = true;
    try {
      return await call();
    } on AuthFailure {
      rethrow;
    } on Object catch (error) {
      throw _failureFor(error);
    } finally {
      _attemptPending = false;
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

  /// Turns a native result name into an [AuthAttemptResult]. An unknown name
  /// is a failure, never a success.
  static AuthAttemptResult _resultFor(String? result) => switch (result) {
    "completed" => const AuthAttemptCompleted(),
    "needsEmailCode" => const AuthAttemptNeedsEmailCode(),
    "cancelled" => const AuthAttemptCancelled(),
    _ => throw const AuthUnexpectedFailure(),
  };

  static AuthFailure _failureFor(Object error) {
    if (error is! ClerkBridgeException) {
      return const AuthUnexpectedFailure();
    }
    return switch (error.category) {
      ClerkBridgeErrorCategory.connectivity => const AuthConnectivityFailure(),
      ClerkBridgeErrorCategory.invalidCode => const AuthInvalidCodeFailure(),
      ClerkBridgeErrorCategory.sessionEnded => const AuthSessionEndedFailure(),
      ClerkBridgeErrorCategory.unsupported => const AuthUnsupportedFailure(),
      ClerkBridgeErrorCategory.rateLimited => const AuthRateLimitedFailure(),
      ClerkBridgeErrorCategory.accountExists =>
        const AuthAccountExistsFailure(),
      ClerkBridgeErrorCategory.accountNotFound =>
        const AuthAccountNotFoundFailure(),
      ClerkBridgeErrorCategory.providerUnavailable =>
        const AuthProviderUnavailableFailure(),
      ClerkBridgeErrorCategory.unexpected => const AuthUnexpectedFailure(),
    };
  }
}
