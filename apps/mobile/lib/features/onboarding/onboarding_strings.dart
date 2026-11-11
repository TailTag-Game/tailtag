import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/features/onboarding/onboarding_controller.dart";

/// The English text of the onboarding form.
abstract final class OnboardingStrings {
  /// The screen title.
  static const title = "Set up your profile";

  /// The handle field label.
  static const handleLabel = "Handle";

  /// The handle helper text.
  static const handleHelper = "Use 2 to 32 letters, numbers, or underscores.";

  /// The display name field label.
  static const displayNameLabel = "Display name";

  /// The empty handle error.
  static const handleEmpty = "Enter a handle";

  /// The empty display name error.
  static const displayNameEmpty = "Enter a display name";

  /// The submit action.
  static const submit = "Continue";

  /// The action that opens the passkey screen.
  static const managePasskeys = "Manage passkeys";

  /// The sign-out action.
  static const signOut = "Sign out";

  /// The banner after a save with no definite answer.
  static const unknownOutcome =
      "TailTag could not confirm that your profile saved. Try again to check.";

  /// The banner when the API refuses the token of an active session.
  static const apiAccess =
      "TailTag could not confirm your account. Try again, or sign out.";

  /// The text of [banner].
  static String bannerText(OnboardingBanner banner) => switch (banner) {
    OnboardingBanner.unknownError => GenericError.unknown.message,
    OnboardingBanner.unknownOutcome => unknownOutcome,
    OnboardingBanner.apiAccess => apiAccess,
  };
}
