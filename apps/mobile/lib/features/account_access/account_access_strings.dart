import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";

/// The English text of the account-access screens.
abstract final class AccountAccessStrings {
  /// The account screen title.
  static const welcomeTitle = "Welcome to TailTag";

  /// The account screen text.
  static const welcomeBody = "Create an account or sign in to play.";

  /// The account-creation choice and the title of its email screen.
  static const createAccount = "Create account";

  /// The sign-in choice and the title of its email screen.
  static const signIn = "Sign in";

  /// The divider between the email choices and the provider choices.
  static const or = "or";

  /// The Google action. Google's branding guidelines approve this text.
  static const continueWithGoogle = "Continue with Google";

  /// The Apple action. The native Apple button draws this text itself, and
  /// it is the semantic label of that button.
  static const continueWithApple = "Continue with Apple";

  /// The passkey action.
  static const signInWithPasskey = "Sign in with a passkey";

  /// The note when passkeys do not work on this device.
  static const passkeysUnavailable =
      "Passkeys are not available on this device.";

  /// The email field label.
  static const emailLabel = "Email";

  /// The email field helper text.
  static const emailHelper = "We send a sign-in code to this address.";

  /// The email field error.
  static const emailInvalid =
      "Enter an email address, for example name@example.com.";

  /// The action that sends the first code.
  static const sendCode = "Send code";

  /// The code screen title.
  static const codeTitle = "Enter your code";

  /// The code screen text for [emailAddress].
  static String codeBody(String emailAddress) =>
      "We sent a 6-digit code to $emailAddress.";

  /// The code screen text after a provider attempt. The app knows no email
  /// address there.
  static const codeBodyProvider = "We sent a 6-digit code to your email.";

  /// The action that leaves code entry after a provider attempt.
  static const back = "Back";

  /// The code field label.
  static const codeLabel = "Code";

  /// The action that verifies the code.
  static const verify = "Verify";

  /// The action that sends another code.
  static const resend = "Send a new code";

  /// The action that returns to email entry.
  static const changeEmail = "Change email";

  /// The note after a new code is sent.
  static const codeResent = "We sent a new code. Check your email.";

  /// The switch from account creation to sign-in.
  static const signInInstead = "Sign in instead";

  /// The switch from sign-in to account creation.
  static const createInstead = "Create an account instead";

  /// The account-screen banner text for [failure] after the provider
  /// [action] failed. Only an unavailable provider has its own text.
  static String providerFailureMessage(
    AccessAction action,
    AuthFailure failure,
  ) => switch ((action, failure)) {
    (AccessAction.apple, AuthProviderUnavailableFailure()) =>
      "Sign in with Apple is not available on this device. Sign in to your "
          "Apple Account in Settings, or use email.",
    (AccessAction.passkey, AuthAccountNotFoundFailure()) =>
      "No TailTag account uses that passkey. Sign in another way.",
    _ => failureMessage(failure),
  };

  /// The banner text for [failure].
  static String failureMessage(AuthFailure failure) => switch (failure) {
    AuthConnectivityFailure() => UiStrings.noConnection,
    AuthInvalidCodeFailure() =>
      "That code is wrong or has expired. Check it, or send a new code.",
    AuthRateLimitedFailure() =>
      "Too many attempts. Wait a few minutes, then try again.",
    AuthAccountExistsFailure() => "An account already uses this email.",
    AuthAccountNotFoundFailure() => "No account uses this email.",
    AuthProviderUnavailableFailure() =>
      "Google sign-in is not available on this device. Add a Google account "
          "in Settings, or use email.",
    AuthSessionEndedFailure() =>
      "This code request has ended. Change the email to start again.",
    AuthUnsupportedFailure() =>
      "Account access is not available on this device.",
    AuthPasskeyUnavailableFailure() =>
      "This device cannot use a passkey right now. Sign in another way.",
    AuthReverificationRequiredFailure() ||
    AuthLastMethodRequiredFailure() ||
    AuthUnexpectedFailure() => UiStrings.unknownError,
  };
}
