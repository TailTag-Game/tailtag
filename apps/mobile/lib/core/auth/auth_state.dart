import "package:tailtag_mobile/core/auth/auth_failure.dart";

/// Where the player's session stands.
///
/// A state never carries a token, an email address, or a Clerk identifier.
sealed class AuthState {
  /// Creates a state.
  const new();
}

/// The native SDK is still loading, so the session is not known yet.
final class AuthRestoring extends AuthState {
  /// Creates the state.
  const new() : super();

  @override
  String toString() => "AuthRestoring";
}

/// The SDK has loaded and there is no active session.
final class AuthSignedOut extends AuthState {
  /// Creates the state.
  const new() : super();

  @override
  String toString() => "AuthSignedOut";
}

/// The SDK has loaded and a session is active.
final class AuthSignedIn extends AuthState {
  /// Creates the state.
  const new() : super();

  @override
  String toString() => "AuthSignedIn";
}

/// Authentication could not start or broke.
final class AuthFailed extends AuthState {
  /// Creates the state for [failure].
  const new(this.failure) : super();

  /// Why authentication failed.
  final AuthFailure failure;

  @override
  String toString() => "AuthFailed(${failure.name})";
}
