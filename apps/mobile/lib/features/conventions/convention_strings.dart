import "package:flutter/material.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/features/conventions/convention_picker_controller.dart";

/// The English text of the picker and the home.
abstract final class ConventionStrings {
  /// The app name, in the home title.
  static const appName = "TailTag";

  /// The picker title.
  static const pickerTitle = "Choose a convention";

  /// The picker loading label.
  static const loading = "Loading conventions";

  /// The empty state title.
  static const emptyTitle = "No conventions are open";

  /// The empty state body.
  static const emptyBody = "Check back soon, or refresh.";

  /// The action for a convention that the player has not joined.
  static const joinAndEnter = "Join and enter";

  /// The action for a convention that the player already joined.
  static const enterConvention = "Enter convention";

  /// The badge of a joined convention.
  static const joined = "Joined";

  /// The badge of the selected convention.
  static const selected = "Selected";

  /// The action that opens the picker from the home.
  static const changeConvention = "Change convention";

  /// The action that reads again.
  static const refresh = "Refresh";

  /// The action that leaves the picker.
  static const close = "Close";

  /// The action that opens the passkey screen.
  static const managePasskeys = "Manage passkeys";

  /// The sign-out action.
  static const signOut = "Sign out";

  /// The debug proof action.
  static const authProof = "Auth proof (debug)";

  /// The banner on the home of a convention that is not open.
  static const inactive =
      "This convention is not open right now. Choose another convention.";

  /// The banner after the server refuses an entry.
  static const entryFailed =
      "TailTag could not enter that convention. Choose another convention.";

  /// The banner after a write with no definite answer.
  static const unknownOutcome =
      "TailTag could not confirm your convention entry. Try again to check.";

  /// The banner when a recovery read shows the enrollment only.
  static const notEntered =
      "You joined this convention, but TailTag did not enter it. Choose "
      "Enter convention.";

  /// The banner when a recovery read shows no enrollment.
  static const notJoined =
      "TailTag did not enter that convention. You can try again.";

  /// The banner when the API refuses the token of an active session.
  static const apiAccess =
      "TailTag could not confirm your account. Try again, or sign out.";

  /// The text of [banner].
  static String bannerText(PickerBanner banner) => switch (banner) {
    PickerBanner.entryFailed => entryFailed,
    PickerBanner.unknownError => GenericError.unknown.message,
    PickerBanner.unknownOutcome => unknownOutcome,
    PickerBanner.notEntered => notEntered,
    PickerBanner.notJoined => notJoined,
    PickerBanner.apiAccess => apiAccess,
  };

  /// The tone of [banner].
  static StatusTone bannerTone(PickerBanner banner) => switch (banner) {
    PickerBanner.entryFailed ||
    PickerBanner.unknownError ||
    PickerBanner.apiAccess => StatusTone.error,
    PickerBanner.unknownOutcome ||
    PickerBanner.notEntered ||
    PickerBanner.notJoined => StatusTone.warning,
  };

  /// The badge text of [status].
  static String statusLabel(ConventionStatus status) => switch (status) {
    ConventionStatus.active => "Active",
    ConventionStatus.paused => "Paused",
    ConventionStatus.completed => "Completed",
    ConventionStatus.cancelled => "Cancelled",
    ConventionStatus.draft => "Not open",
  };

  /// The badge tone of [status].
  static StatusTone statusTone(ConventionStatus status) => switch (status) {
    ConventionStatus.active => StatusTone.success,
    ConventionStatus.paused => StatusTone.warning,
    ConventionStatus.completed ||
    ConventionStatus.cancelled ||
    ConventionStatus.draft => StatusTone.neutral,
  };

  /// The calendar dates of [convention]. One date shows when the start and
  /// the end match.
  static String dates(BuildContext context, Convention convention) {
    final format = MaterialLocalizations.of(context).formatShortDate;
    final start = format(convention.startDate);
    return convention.startDate == convention.endDate
        ? start
        : "$start to ${format(convention.endDate)}";
  }
}
