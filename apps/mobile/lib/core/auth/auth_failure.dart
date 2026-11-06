/// Why an authentication call did not succeed.
///
/// The model is deliberately small: a category and nothing else. Native
/// messages and details are never kept, so no failure can leak a token, an
/// email address, or a Clerk identifier through logging.
sealed class AuthFailure implements Exception {
  /// Creates a failure.
  const new();

  /// The loggable name of this failure's category.
  String get name;

  @override
  String toString() => "AuthFailure($name)";
}

/// The network could not be reached.
final class AuthConnectivityFailure extends AuthFailure {
  /// Creates the failure.
  const new() : super();

  @override
  String get name => "connectivity";
}

/// The verification code was wrong or has expired.
final class AuthInvalidCodeFailure extends AuthFailure {
  /// Creates the failure.
  const new() : super();

  @override
  String get name => "invalidCode";
}

/// There is no session, or the session was ended or revoked.
final class AuthSessionEndedFailure extends AuthFailure {
  /// Creates the failure.
  const new() : super();

  @override
  String get name => "sessionEnded";
}

/// Authentication is not available on this platform.
final class AuthUnsupportedFailure extends AuthFailure {
  /// Creates the failure.
  const new() : super();

  @override
  String get name => "unsupported";
}

/// Clerk refused a send or an attempt because of its rate limits.
final class AuthRateLimitedFailure extends AuthFailure {
  /// Creates the failure.
  const new() : super();

  @override
  String get name => "rateLimited";
}

/// Email account creation found an existing account.
final class AuthAccountExistsFailure extends AuthFailure {
  /// Creates the failure.
  const new() : super();

  @override
  String get name => "accountExists";
}

/// Email sign-in found no account.
final class AuthAccountNotFoundFailure extends AuthFailure {
  /// Creates the failure.
  const new() : super();

  @override
  String get name => "accountNotFound";
}

/// Anything else.
final class AuthUnexpectedFailure extends AuthFailure {
  /// Creates the failure.
  const new() : super();

  @override
  String get name => "unexpected";
}
