import "package:tailtag_mobile/core/catches/catch_models.dart";

/// The text of owner catch review (#512).
abstract final class ReviewStrings {
  /// The review screen title and the suit list row title.
  static const title = "Review catches";

  /// The convention home row (AC3).
  static String toReview(int count) => count == 1
      ? "1 catch request to review"
      : "$count catch requests to review";

  /// The subtitle of the suit list row and the suit detail row.
  static String waiting(int count) =>
      count == 0 ? "Nothing to review" : "$count waiting for review";

  /// The suit detail row title.
  static const suitRequests = "Catch requests";

  /// The part of a group with pending requests.
  static const toReviewPart = "To review";

  /// The part of a group with the other requests.
  static const decidedPart = "Decided";

  /// The deadline line of a group.
  static String reviewUntil(String when) =>
      "You can review until the end of $when";

  /// The deadline line when only the instant is known.
  static String reviewUntilInstant(String when) => "You can review until $when";

  /// The empty state.
  static const empty = "No catch requests to review.";

  /// The empty state body.
  static const emptyBody =
      "When players send catches for your suits, they show here.";

  /// The state labels (AC11).
  static String stateLabel(CatchRequestState state) => switch (state) {
    CatchRequestState.pending => "Waiting for review",
    CatchRequestState.approved => "Approved",
    CatchRequestState.declined => "Declined",
    CatchRequestState.withdrawn => "Withdrawn",
    CatchRequestState.unavailable => "No longer available",
  };

  /// The handle as the row shows it.
  static String handle(String handle) => "@$handle";

  /// The earlier declines of the same player, suit, and convention (AC12).
  static String priorDeclines(int count) => count == 1
      ? "Declined $count time before here"
      : "Declined $count times before here";

  /// The badge of a blocked player.
  static const blocked = "Blocked";

  /// The note on a paused request, and its banner (AC16, AC24).
  static const paused = "You can't approve this right now.";

  /// The row buttons.
  static const approve = "Approve";

  /// The decline button, and the plain decline row of the sheet.
  static const decline = "Decline";

  /// The decline and block row of the sheet.
  static const declineAndBlock = "Decline and block";

  /// The subtitle of the decline and block row (AC15).
  static String blockHelp(String suit, String convention) =>
      "They can't send another catch for $suit at $convention.";

  /// The restore button.
  static const restore = "Restore";

  /// The remove block button.
  static const removeBlock = "Remove block";

  /// The undo action of the decline snackbar.
  static const undo = "Undo";

  /// The screen reader labels of the row buttons (AC32).
  static String approveFor(String name) => "Approve catch from $name";

  /// See [approveFor].
  static String declineFor(String name) => "Decline catch from $name";

  /// See [approveFor].
  static String restoreFor(String name) => "Restore catch from $name";

  /// See [approveFor].
  static String removeBlockFor(String name) => "Remove block for $name";

  /// The snackbars (AC18, AC19).
  static const approved = "Catch approved.";

  /// See [approved].
  static const declined = "Catch declined.";

  /// See [approved].
  static const blockedDone = "Player blocked.";

  /// See [approved].
  static const restored = "Request restored.";

  /// See [approved].
  static const unblocked = "Block removed.";

  /// The banners (AC20, AC24, AC25, AC27).
  static const tooLateToUndo =
      "It's too late to undo. You can restore it instead.";

  /// See [tooLateToUndo].
  static const changed = "This request changed. This is its current state.";

  /// See [tooLateToUndo].
  static const alreadyCaught = "This player already caught this suit here.";

  /// See [tooLateToUndo].
  static const cannotRestore = "This request can't be restored anymore.";

  /// See [tooLateToUndo].
  static const gone = "This request is no longer available.";

  /// See [tooLateToUndo].
  static const unknown = "We couldn't confirm that. This is the current state.";

  /// See [tooLateToUndo].
  static const serviceOff = "Catch review isn't available right now.";

  /// The "Catch approval" section of the suit detail screen (AC7).
  static const approvalSection = "Catch approval";

  /// The switch title.
  static const automatic = "Approve catches automatically";

  /// The switch subtitle while the mode is manual.
  static const manualHelp = "You review each catch.";

  /// The switch subtitle while the mode is automatic.
  static const automaticHelp =
      "New catches are approved at once. Requests already waiting stay for "
      "you to review.";
}
