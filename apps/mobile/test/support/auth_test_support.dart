import "dart:async";
import "dart:convert";

import "package:tailtag_mobile/core/auth/auth_session.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";

/// An [AuthSession] for tests that need neither Clerk nor a device.
///
/// Like the real session, [token] yields nothing unless the state is
/// [AuthSignedIn]. It records every call so tests can assert on what the UI
/// asked for.
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

  final List<String> startEmailCodeCalls = [];
  final List<String> verifyCodeCalls = [];
  int signOutCalls = 0;
  int recheckCalls = 0;

  final StreamController<AuthState> _controller =
      StreamController<AuthState>.broadcast();
  AuthState _state;

  @override
  AuthState get state => _state;

  @override
  Stream<AuthState> get states => _controller.stream;

  /// Moves to [next] and tells listeners.
  void emit(AuthState next) {
    _state = next;
    _controller.add(next);
  }

  @override
  Future<String?> token() async => _state is AuthSignedIn ? tokenValue : null;

  @override
  Future<void> startEmailCode(String emailAddress) async {
    startEmailCodeCalls.add(emailAddress);
  }

  @override
  Future<void> verifyEmailCode(String code) async {
    verifyCodeCalls.add(code);
    emit(const AuthSignedIn());
  }

  @override
  Future<void> signOut() async {
    signOutCalls++;
    emit(const AuthSignedOut());
  }

  @override
  Future<void> recheckSession() async {
    recheckCalls++;
    if (sessionEndsOnRecheck) {
      emit(const AuthSignedOut());
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
