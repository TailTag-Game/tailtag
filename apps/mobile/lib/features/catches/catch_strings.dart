import "package:flutter/material.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";

/// The English text of the scanner, the request list, and the collection.
/// V0 is English only. The #511 refinement (G7) approved this text.
abstract final class CatchStrings {
  /// The bar destinations.
  static const navHome = "Home";

  /// The bar destination and the collection title.
  static const navCatches = "Catches";

  /// The bar destination and the request list title.
  static const navRequests = "Requests";

  /// The bar destination of the suit list.
  static const navSuits = "Suits";

  /// The home button and the scanner title.
  static const scanTag = "Scan a TailTag";

  /// Why the home scan button is off.
  static String scanClosed(String convention) =>
      "Catching isn't open at $convention right now.";

  // Camera.

  /// The scanner text before the first system prompt.
  static const cameraIntro =
      "TailTag uses your camera to scan TailTags. "
      "It saves no photos from the scanner.";

  /// The button that asks for the camera.
  static const turnOnCamera = "Turn on camera";

  /// The scanner text while the camera runs.
  static const pointCamera = "Point your camera at a TailTag.";

  /// The scanner text after a refusal.
  static const cameraDenied =
      "TailTag needs camera access to scan tags. Turn it on in Settings.";

  /// The button that opens the system settings.
  static const openSettings = "Open settings";

  /// The scanner text when the camera or the code reader fails.
  static const scannerNotReady =
      "The scanner is getting ready. Try again in a moment.";

  /// The screen reader label of the camera view.
  static const viewfinderLabel =
      "Camera viewfinder. Point the camera at a TailTag.";

  /// The screen reader announcement of a valid read.
  static const tagFound = "TailTag found";

  /// The torch button labels.
  static const torchOn = "Turn on flashlight";

  /// The torch button label while the flashlight is on.
  static const torchOff = "Turn off flashlight";

  /// The scanner notice for a QR code that is not a TailTag.
  static const notATag = "This QR code isn't a TailTag.";

  // Preview and results.

  /// The confirm button of the preview.
  static String catchSuit(String name) => "Catch $name";

  /// The second button of the preview and of a refusal.
  static const scanAgain = "Scan again";

  /// The result after a new pending request.
  static String sent(String name, String date) =>
      "Catch sent. $name's owner will review it by the end of $date.";

  /// The result after an automatic catch.
  static String caught(String name) =>
      "You caught $name! It's in your collection.";

  /// The result when a request already waits.
  static String alreadyPending(String name) =>
      "You already sent a catch for $name. It's waiting for review.";

  /// The result when the suit is already in the collection.
  static String alreadyCaught(String name) =>
      "You already caught $name at this convention.";

  /// The neutral refusal. It also covers a block.
  static const unavailable = "This TailTag can't be caught right now.";

  /// The result of a scan of the player's own suit.
  static const ownSuit = "This is your own suit.";

  /// The result when the player cannot catch at the convention.
  static const ineligible = "You can't catch at this convention right now.";

  /// The result when the review window is closed or has no time zone.
  static String closed(String convention) =>
      "Catching is closed at $convention.";

  /// The result of a cooldown or the per-player limit.
  static String wait(int seconds) {
    final minutes = seconds ~/ 60;
    final rest = (seconds % 60).toString().padLeft(2, "0");
    return "Please wait before trying again. "
        "You can try again in $minutes:$rest.";
  }

  /// The result of a submission with no definite answer.
  static const unknown =
      "We couldn't confirm your catch. Check your connection, then check "
      "again. You can also check Requests and Catches.";

  /// The button that sends the same submission again.
  static const checkAgain = "Check again";

  /// The result when the server has no catch flow.
  static const serviceOff = "Catching isn't available right now.";

  /// The result when the server selection differs from the home.
  static const conventionChanged =
      "Your convention changed. We've updated your home.";

  /// The button that closes the scanner after a convention change.
  static const backToHome = "Back to home";

  /// The button that opens the request list.
  static const seeRequests = "See my requests";

  /// The button that opens the collection.
  static const seeCatches = "See my catches";

  // Request list.

  /// The empty request list.
  static const requestsEmpty = "No catch requests yet.";

  /// The empty request list body.
  static const requestsEmptyBody = "Scan a TailTag to send one.";

  /// The header of a convention that the app could not read.
  static const otherConvention = "Another convention";

  /// The deadline line of a request group.
  static String reviewUntil(String when) =>
      "Owners can review until the end of $when";

  /// The deadline line when only the instant is known.
  static String reviewUntilInstant(String when) =>
      "Owners can review until $when";

  /// The request state labels.
  static String stateLabel(CatchRequestState state) => switch (state) {
    CatchRequestState.pending => "Waiting for review",
    CatchRequestState.approved => "Caught",
    CatchRequestState.declined => "Not accepted",
    CatchRequestState.withdrawn => "Withdrawn",
    CatchRequestState.unavailable => "No longer available",
  };

  /// The withdraw button and the dialog's confirm button.
  static const withdraw = "Withdraw";

  /// The withdraw dialog title.
  static const withdrawTitle = "Withdraw this catch?";

  /// The withdraw dialog body.
  static const withdrawBody = "The owner won't see it anymore.";

  /// The dialog's cancel button.
  static const cancel = "Cancel";

  /// The snackbar after a withdrawal.
  static const withdrawn = "Catch withdrawn.";

  /// The banner when another action changed the request first.
  static const requestChanged =
      "This request changed. This is its current state.";

  /// The banner when the request is gone.
  static const requestGone = "This request is no longer available.";

  /// The banner after a withdrawal with no definite answer.
  static const withdrawUnknown =
      "We couldn't confirm the withdrawal. This is the current state.";

  /// The request list without the catch flow on the server.
  static const requestsOff = "Catch requests aren't available right now.";

  // Collection.

  /// The filter chip for every convention.
  static const allConventions = "All";

  /// The empty collection.
  static const catchesEmpty = "No catches yet.";

  /// The empty collection body.
  static const catchesEmptyBody = "Scan a TailTag to catch a suit.";

  // Dates.

  /// The last review day in the convention's own calendar: the day before
  /// the local deadline date, such as "Tue, Jan 19". With no local date,
  /// [deadlineAt] in device time.
  static String reviewEnd(
    BuildContext context, {
    required Convention? convention,
    required DateTime deadlineAt,
  }) {
    final localizations = MaterialLocalizations.of(context);
    final local = convention?.reviewDeadlineLocalDate;
    if (local != null) {
      final lastDay = DateTime(local.year, local.month, local.day - 1);
      return localizations.formatMediumDate(lastDay);
    }
    return instant(context, deadlineAt);
  }

  /// [time] in device time, as a date and a time.
  static String instant(BuildContext context, DateTime time) {
    final localizations = MaterialLocalizations.of(context);
    final local = time.toLocal();
    final clock = localizations.formatTimeOfDay(
      TimeOfDay.fromDateTime(local),
      alwaysUse24HourFormat: MediaQuery.alwaysUse24HourFormatOf(context),
    );
    return "${localizations.formatMediumDate(local)}, $clock";
  }
}
