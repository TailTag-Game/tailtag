import "package:tailtag_mobile/core/api/api_token_provider.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/auth/passkey.dart";

/// The player's authentication session.
///
/// This is TailTag's own boundary over the auth SDK: no SDK or channel type
/// appears here. The session is also the [ApiTokenProvider] of the API
/// transport, and [token] is null unless the state is [AuthSignedIn].
///
/// The access and passkey operations run one attempt at a time. If a caller
/// starts an attempt while another one is pending, the call throws
/// [AuthUnexpectedFailure] and the pending attempt continues. An email code
/// belongs to the attempt that the last start call or provider call created.
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

  /// Signs in or creates an account through Google.
  ///
  /// Clerk creates the account when none exists. [AuthAttemptCompleted]
  /// means that Clerk reports an active session. [AuthAttemptCancelled]
  /// means that the player dismissed the Google sheet or browser.
  /// [AuthAttemptNeedsEmailCode] means that Clerk sent an email code, which
  /// [verifyEmailCode] then checks. Throws [AuthProviderUnavailableFailure],
  /// [AuthConnectivityFailure], or [AuthUnexpectedFailure].
  Future<AuthAttemptResult> continueWithGoogle();

  /// Signs in or creates an account through Apple. Only iOS offers it.
  ///
  /// The results mean the same as for [continueWithGoogle]. The app asks
  /// Apple for the email address only, never the name. Throws
  /// [AuthProviderUnavailableFailure] when the device has no usable Apple
  /// Account, [AuthUnsupportedFailure] on Android, or
  /// [AuthConnectivityFailure] or [AuthUnexpectedFailure].
  Future<AuthAttemptResult> continueWithApple();

  /// Whether this device and the Clerk instance allow passkeys now.
  ///
  /// Android needs API 28 or later. Clerk must have passkey sign-in on. It
  /// never throws: any doubt is [PasskeyAvailability.unavailable].
  Future<PasskeyAvailability> passkeyAvailability();

  /// Signs in with a passkey that the system sheet offers.
  ///
  /// The sheet can also offer a passkey from another device.
  /// [AuthAttemptCompleted] means that Clerk reports an active session.
  /// [AuthAttemptCancelled] means that the player dismissed the sheet.
  /// Throws [AuthPasskeyUnavailableFailure], [AuthAccountNotFoundFailure],
  /// [AuthConnectivityFailure], or [AuthUnexpectedFailure].
  Future<AuthAttemptResult> signInWithPasskey();

  /// Adds a passkey to the signed-in player's account.
  ///
  /// [AuthAttemptCompleted] means that Clerk acknowledged the verified
  /// passkey. The auth state does not change. [AuthAttemptCancelled] means
  /// that the player dismissed the sheet. Throws
  /// [AuthPasskeyUnavailableFailure], [AuthReverificationRequiredFailure],
  /// [AuthSessionEndedFailure], [AuthConnectivityFailure], or
  /// [AuthUnexpectedFailure]. After a connectivity or unexpected failure,
  /// the outcome is not known: read the list before another change.
  Future<AuthAttemptResult> createPasskey();

  /// The signed-in player's verified passkeys, read fresh from Clerk.
  ///
  /// Throws [AuthSessionEndedFailure], [AuthConnectivityFailure], or
  /// [AuthUnexpectedFailure].
  Future<List<PasskeyInfo>> listPasskeys();

  /// Removes the passkey [passkeyId] from the signed-in player's account.
  ///
  /// It first reads fresh Clerk state and keeps another way to sign in:
  /// another verified passkey, or a verified email, Google, or Apple
  /// method that the instance allows. Otherwise it throws
  /// [AuthLastMethodRequiredFailure] and removes nothing. It can also throw
  /// [AuthReverificationRequiredFailure], [AuthSessionEndedFailure],
  /// [AuthConnectivityFailure], or [AuthUnexpectedFailure]. After a
  /// connectivity or unexpected failure, the outcome is not known: read the
  /// list before another change.
  Future<void> removePasskey(String passkeyId);

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
