import "package:tailtag_mobile/core/api/api_token_provider.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";

/// The player's authentication session.
///
/// This is TailTag's own boundary over the auth SDK: no SDK or channel type
/// appears here. The session is also the [ApiTokenProvider] of the API
/// transport, and [token] is null unless the state is [AuthSignedIn].
abstract interface class AuthSession implements ApiTokenProvider {
  /// The current state.
  AuthState get state;

  /// Later state changes. The current value is in [state].
  Stream<AuthState> get states;

  /// Sends a verification code to [emailAddress].
  ///
  /// Throws an [AuthFailure] when it fails.
  Future<void> startEmailCode(String emailAddress);

  /// Completes the sign-in with [code]. On success, the state becomes
  /// [AuthSignedIn].
  ///
  /// Throws an [AuthFailure] when it fails.
  Future<void> verifyEmailCode(String code);

  /// Ends the session. On success, the state becomes [AuthSignedOut].
  ///
  /// Throws an [AuthFailure] when it fails.
  Future<void> signOut();

  /// Checks the session once after the API rejected a token.
  ///
  /// If no session is active, the state becomes [AuthSignedOut]. Otherwise,
  /// the state does not change.
  Future<void> recheckSession();
}
