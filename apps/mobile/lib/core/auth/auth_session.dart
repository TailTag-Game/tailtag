import "package:tailtag_mobile/core/api/api_token_provider.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";

/// The player's authentication session.
///
/// This is TailTag's own boundary over the auth SDK: no SDK or channel type
/// appears here. The session is also the [ApiTokenProvider] of the API
/// transport, and [token] is null unless the state is [AuthSignedIn].
///
/// The email operations run one attempt at a time. If a caller starts an
/// attempt while another one is pending, the call throws
/// [AuthUnexpectedFailure] and the pending attempt continues. An email code
/// belongs to the attempt that the last start call created.
abstract interface class AuthSession implements ApiTokenProvider {
  /// The current state.
  AuthState get state;

  /// Later state changes. The current value is in [state].
  Stream<AuthState> get states;

  /// Starts an email sign-in for [emailAddress] and sends a code.
  ///
  /// Throws an [AuthFailure], for example [AuthAccountNotFoundFailure].
  Future<void> startEmailSignIn(String emailAddress);

  /// Starts an email account creation for [emailAddress] and sends a code.
  ///
  /// Throws an [AuthFailure], for example [AuthAccountExistsFailure].
  Future<void> startEmailSignUp(String emailAddress);

  /// Sends a new code for the current attempt.
  ///
  /// Throws [AuthSessionEndedFailure] when no attempt is current, or another
  /// [AuthFailure].
  Future<void> resendEmailCode();

  /// Verifies [code] for the current attempt.
  ///
  /// [AuthAttemptCompleted] means that Clerk reports an active session. The
  /// state then becomes [AuthSignedIn] through the native state events.
  /// Throws an [AuthFailure], for example [AuthInvalidCodeFailure].
  Future<AuthAttemptResult> verifyEmailCode(String code);

  /// Ends the session. On success, the state becomes [AuthSignedOut].
  ///
  /// Throws an [AuthFailure] when it fails.
  Future<void> signOut();

  /// Checks the session once after the API rejected a token.
  ///
  /// If no session is active, the state becomes [AuthSignedOut]. Otherwise,
  /// the state does not change.
  Future<void> recheckSession();

  /// Loads the native session state again after [AuthFailed].
  ///
  /// It never clears secure session storage and never throws. The state
  /// becomes [AuthRestoring] and then follows the native SDK. If the reload
  /// fails, the state becomes [AuthFailed] again. The state becomes
  /// [AuthSignedOut] only when the SDK reports it.
  Future<void> reloadSession();
}
