import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";

/// The English text of the passkey screen.
abstract final class PasskeyStrings {
  /// The screen title.
  static const title = "Passkeys";

  /// The close action.
  static const close = "Close";

  /// The screen text.
  static const intro =
      "A passkey lets you sign in to TailTag with your fingerprint, face, or "
      "screen lock. Adding one is optional.";

  /// The note when passkeys do not work here. The account screen uses it
  /// too.
  static const unavailable = "Passkeys are not available on this device.";

  /// The add action.
  static const add = "Add a passkey";

  /// The empty list text.
  static const empty = "You have no passkeys yet.";

  /// The list heading.
  static const listHeading = "Your passkeys";

  /// The read failure text.
  static const readFailed = "TailTag could not load your passkeys.";

  /// The row detail for a passkey added on [added] and last used on
  /// [lastUsed], or never used.
  static String rowDetail(String added, String? lastUsed) {
    final use = lastUsed == null ? "Not used yet." : "Last used $lastUsed.";
    return "Added $added. $use";
  }

  /// The remove action label for the passkey [name].
  static String removeLabel(String name) => "Remove $name";

  /// The confirmation dialog title for the passkey [name].
  static String removeTitle(String name) => "Remove $name?";

  /// The confirmation dialog text.
  static const removeBody =
      "You can no longer sign in to TailTag with this passkey. This affects "
      "TailTag sign-in only.";

  /// The dialog action that removes the passkey.
  static const removeConfirm = "Remove";

  /// The dialog action that keeps the passkey.
  static const cancel = "Cancel";

  /// The snackbar after a confirmed addition.
  static const added = "Passkey added";

  /// The snackbar after a confirmed removal. The device password manager
  /// keeps its own copy.
  static const removed =
      "Passkey removed, but your password manager can still show it";

  /// The notice after a change with an unknown outcome.
  static const unconfirmed =
      "We cannot confirm the change. This is your current list.";

  /// The reverification text.
  static const reverification =
      "TailTag needs a fresh sign-in before it changes your passkeys. Sign "
      "out, sign in again, then come back here.";

  /// The action that starts the fresh sign-in.
  static const signOutAndIn = "Sign out and sign in again";

  /// The banner text for a change that failed with [failure].
  static String changeFailure(AuthFailure failure) => switch (failure) {
    AuthLastMethodRequiredFailure() =>
      "You need another way to sign in before you remove this passkey.",
    AuthPasskeyUnavailableFailure() =>
      "This device cannot create a passkey right now.",
    AuthSessionEndedFailure() => "Your session has ended. Sign in again.",
    AuthReverificationRequiredFailure() => reverification,
    AuthConnectivityFailure() => UiStrings.noConnection,
    _ => UiStrings.unknownError,
  };
}
