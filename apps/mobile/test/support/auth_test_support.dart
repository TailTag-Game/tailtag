import "dart:async";
import "dart:convert";

import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_session.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/auth/passkey.dart";

/// An [AuthSession] for tests that need neither Clerk nor a device.
///
/// Like the real session, [token] yields nothing unless the state is
/// [AuthSignedIn], and it runs one access attempt at a time. It records every
/// call so tests can assert on what the UI asked for.
///
/// Like the native side, resend and verify need an attempt that a start call
/// bound. Each access call fails with its configured failure, if any. Setting
/// [gate] holds every access call until the test completes it, so a test can
/// observe the pending state.
final class FakeAuthSession implements AuthSession {
  /// Starts in [initial] and hands out [tokenValue] while signed in.
  new({
    AuthState initial = const AuthSignedOut(),
    this.tokenValue,
    this.sessionEndsOnRecheck = true,
  }) : _state = initial;

  /// The token handed out while the state is [AuthSignedIn].
  String? tokenValue;

  /// Whether [recheckSession] finds no active session, as the real one does
  /// after a revocation.
  bool sessionEndsOnRecheck;

  /// The failure of the next start call, or null.
  AuthFailure? startFailure;

  /// The failure of the next resend call, or null.
  AuthFailure? resendFailure;

  /// The failure of the next verify call, or null.
  AuthFailure? verifyFailure;

  /// The result of a successful verify call.
  AuthAttemptResult verifyResult = const AuthAttemptCompleted();

  /// Whether a completed verify moves the state to [AuthSignedIn], as the
  /// native state events do.
  bool verifySignsIn = true;

  /// The failure of the next Google call, or null.
  AuthFailure? googleFailure;

  /// The result of a successful Google call. A completed result moves the
  /// state to [AuthSignedIn]. A needs-code result binds an attempt.
  AuthAttemptResult googleResult = const AuthAttemptCompleted();

  /// The failure of the next Apple call, or null.
  AuthFailure? appleFailure;

  /// The result of a successful Apple call, with the same rules as
  /// [googleResult].
  AuthAttemptResult appleResult = const AuthAttemptCompleted();

  /// What [passkeyAvailability] reports.
  PasskeyAvailability availability = PasskeyAvailability.available;

  /// The player's verified passkeys, as Clerk holds them.
  final List<PasskeyInfo> passkeys = [];

  /// The failure of the next passkey sign-in, or null.
  AuthFailure? passkeySignInFailure;

  /// The result of a successful passkey sign-in. A completed result moves
  /// the state to [AuthSignedIn].
  AuthAttemptResult passkeySignInResult = const AuthAttemptCompleted();

  /// The failure of the next passkey creation, or null.
  AuthFailure? createFailure;

  /// Whether a failed creation still adds the passkey, as a lost response
  /// after Clerk verified it does.
  bool createAppliesDespiteFailure = false;

  /// The result of a passkey creation that does not fail. A completed
  /// result adds a passkey to [passkeys].
  AuthAttemptResult createResult = const AuthAttemptCompleted();

  /// The failures of the next list reads, in order. Each read takes one.
  final List<AuthFailure> listFailures = [];

  /// The failure of the next removal, or null.
  AuthFailure? removeFailure;

  /// Whether a failed removal still removes the passkey, as a lost response
  /// does.
  bool removeAppliesDespiteFailure = false;

  /// Whether a removal that does not fail takes effect. False models a
  /// fresh read that still lists the passkey.
  bool removeTakesEffect = true;

  /// When set, passkey creation and removal wait for it.
  Completer<void>? passkeyWriteGate;

  int passkeySignInCalls = 0;
  int createCalls = 0;
  int listCalls = 0;
  final List<String> removeCalls = [];
  int _created = 0;

  /// The failure of the next sign-out, or null.
  AuthFailure? signOutFailure;

  /// The state after a failed sign-out, or null to keep the state.
  AuthState? stateAfterFailedSignOut;

  /// The state that [reloadSession] reaches.
  AuthState reloadOutcome = const AuthSignedOut();

  /// When set, every access call waits for it.
  Completer<void>? gate;

  final List<String> startEmailSignInCalls = [];
  final List<String> startEmailSignUpCalls = [];
  final List<String> verifyCodeCalls = [];
  int resendCalls = 0;
  int googleCalls = 0;
  int appleCalls = 0;

  /// Every access call that reached this session, including refused ones.
  int accessCalls = 0;
  int signOutCalls = 0;
  int recheckCalls = 0;
  int reloadCalls = 0;

  final StreamController<AuthState> _controller =
      StreamController<AuthState>.broadcast();
  AuthState _state;
  bool _attemptPending = false;

  /// Whether a start call bound an attempt, as the native side does.
  bool _bound = false;

  @override
  AuthState get state => _state;

  @override
  Stream<AuthState> get states => _controller.stream;

  /// Moves to [next] and tells listeners.
  void emit(AuthState next) {
    if (next.runtimeType != _state.runtimeType) {
      _bound = false;
    }
    _state = next;
    _controller.add(next);
  }

  @override
  Future<String?> token() async => _state is AuthSignedIn ? tokenValue : null;

  @override
  Future<void> startEmailSignIn(String emailAddress) => _attempt(() async {
    startEmailSignInCalls.add(emailAddress);
    _bound = false;
    _throwIfSet(startFailure);
    _bound = true;
  });

  @override
  Future<void> startEmailSignUp(String emailAddress) => _attempt(() async {
    startEmailSignUpCalls.add(emailAddress);
    _bound = false;
    _throwIfSet(startFailure);
    _bound = true;
  });

  @override
  Future<void> resendEmailCode() => _attempt(() async {
    resendCalls++;
    _throwIfSet(_bound ? resendFailure : const AuthSessionEndedFailure());
  });

  @override
  Future<AuthAttemptResult> verifyEmailCode(String code) => _attempt(() async {
    verifyCodeCalls.add(code);
    _throwIfSet(_bound ? verifyFailure : const AuthSessionEndedFailure());
    if (verifyResult is AuthAttemptCompleted && verifySignsIn) {
      emit(const AuthSignedIn());
    }
    return verifyResult;
  });

  @override
  Future<AuthAttemptResult> continueWithGoogle() => _attempt(() async {
    googleCalls++;
    return _provider(googleFailure, googleResult);
  });

  @override
  Future<AuthAttemptResult> continueWithApple() => _attempt(() async {
    appleCalls++;
    return _provider(appleFailure, appleResult);
  });

  @override
  Future<PasskeyAvailability> passkeyAvailability() async => availability;

  @override
  Future<AuthAttemptResult> signInWithPasskey() => _attempt(() async {
    passkeySignInCalls++;
    return _provider(passkeySignInFailure, passkeySignInResult);
  });

  @override
  Future<AuthAttemptResult> createPasskey() => _attempt(() async {
    createCalls++;
    await passkeyWriteGate?.future;
    final failure = createFailure;
    if (failure != null) {
      if (createAppliesDespiteFailure) {
        _addPasskey();
      }
      throw failure;
    }
    if (createResult is AuthAttemptCompleted) {
      _addPasskey();
    }
    return createResult;
  });

  @override
  Future<List<PasskeyInfo>> listPasskeys() => _attempt(() async {
    listCalls++;
    if (listFailures.isNotEmpty) {
      throw listFailures.removeAt(0);
    }
    return List.unmodifiable(passkeys);
  });

  @override
  Future<void> removePasskey(String passkeyId) => _attempt(() async {
    removeCalls.add(passkeyId);
    await passkeyWriteGate?.future;
    final failure = removeFailure;
    if (failure != null) {
      if (removeAppliesDespiteFailure) {
        passkeys.removeWhere((passkey) => passkey.id == passkeyId);
      }
      throw failure;
    }
    if (removeTakesEffect) {
      passkeys.removeWhere((passkey) => passkey.id == passkeyId);
    }
  });

  /// Adds a passkey with a predictable name to [passkeys].
  void addPasskey({String? name, DateTime? lastUsedAt}) =>
      _addPasskey(name: name, lastUsedAt: lastUsedAt);

  void _addPasskey({String? name, DateTime? lastUsedAt}) {
    _created++;
    passkeys.add(
      PasskeyInfo(
        id: "pk_placeholder_$_created",
        name: name ?? "Passkey $_created",
        createdAt: DateTime(2026, 11, _created),
        lastUsedAt: lastUsedAt,
      ),
    );
  }

  /// Ends any bound attempt, then fails with [failure] or returns [result],
  /// as the native provider flows do.
  AuthAttemptResult _provider(AuthFailure? failure, AuthAttemptResult result) {
    _bound = false;
    _throwIfSet(failure);
    switch (result) {
      case AuthAttemptCompleted():
        emit(const AuthSignedIn());
      case AuthAttemptNeedsEmailCode():
        _bound = true;
      case AuthAttemptCancelled():
        break;
    }
    return result;
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
    _bound = false;
    await gate?.future;
    final failure = signOutFailure;
    if (failure != null) {
      final after = stateAfterFailedSignOut;
      if (after != null) {
        emit(after);
      }
      throw failure;
    }
    emit(const AuthSignedOut());
  }

  @override
  Future<void> recheckSession() async {
    recheckCalls++;
    if (sessionEndsOnRecheck) {
      emit(const AuthSignedOut());
    }
  }

  @override
  Future<void> reloadSession() async {
    reloadCalls++;
    emit(const AuthRestoring());
    await gate?.future;
    emit(reloadOutcome);
  }

  Future<T> _attempt<T>(Future<T> Function() call) async {
    accessCalls++;
    if (_attemptPending) {
      throw const AuthUnexpectedFailure();
    }
    _attemptPending = true;
    try {
      await gate?.future;
      return await call();
    } finally {
      _attemptPending = false;
    }
  }

  static void _throwIfSet(AuthFailure? failure) {
    if (failure != null) {
      throw failure;
    }
  }
}

/// An unsigned, obviously fake JWT carrying [claims].
///
/// Segments are unpadded base64url, like a real JWT. The header is
/// `{"alg":"none"}` and the signature is empty.
String fakeJwt(Map<String, Object?> claims) {
  String segment(Object? json) =>
      base64Url.encode(utf8.encode(jsonEncode(json))).replaceAll("=", "");
  return "${segment({"alg": "none"})}.${segment(claims)}.";
}

/// A fake JWT with a base64url [payload] that is not built from claims, for
/// malformed-token cases.
String fakeJwtWithRawPayload(String payload) {
  final header = base64Url
      .encode(utf8.encode('{"alg":"none"}'))
      .replaceAll("=", "");
  return "$header.$payload.";
}
