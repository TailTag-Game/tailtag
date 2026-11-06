/// The outcome of an account-access attempt that did not fail.
///
/// Failures are thrown as `AuthFailure`. A result never carries an email
/// address, a code, a token, or a Clerk identifier.
sealed class AuthAttemptResult {
  /// Creates a result.
  const new();
}

/// Clerk reports a complete attempt and an active session.
///
/// The auth state changes through the native state events, not through this
/// result.
final class AuthAttemptCompleted extends AuthAttemptResult {
  /// Creates the result.
  const new() : super();

  @override
  String toString() => "AuthAttemptCompleted";
}

/// The player dismissed a native sheet or browser session.
final class AuthAttemptCancelled extends AuthAttemptResult {
  /// Creates the result.
  const new() : super();

  @override
  String toString() => "AuthAttemptCancelled";
}

/// Clerk sent an email code and needs it before the attempt can finish.
final class AuthAttemptNeedsEmailCode extends AuthAttemptResult {
  /// Creates the result.
  const new() : super();

  @override
  String toString() => "AuthAttemptNeedsEmailCode";
}
