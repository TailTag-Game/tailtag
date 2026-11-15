import "package:flutter/material.dart";

/// The English text of the suit screens. V0 is English only.
abstract final class FursuitStrings {
  /// The home button and the list title.
  static const mySuits = "My suits";

  /// The register button and the register screen title.
  static const registerSuit = "Register suit";

  /// The empty list title.
  static const emptyTitle = "No suits yet";

  /// The empty list body.
  static const emptyBody =
      "Register a suit to take part in conventions and get caught.";

  /// The name field label.
  static const nameLabel = "Suit name";

  /// The photo field label.
  static const photoLabel = "Photo";

  /// The photo field button when the form has no photo.
  static const addPhoto = "Add photo";

  /// The photo button when the suit or form has a photo.
  static const changePhoto = "Change photo";

  /// The name button on the suit screen.
  static const changeName = "Change name";

  /// The library choice of the photo sheet.
  static const choosePhoto = "Choose photo";

  /// The camera choice of the photo sheet.
  static const takePhoto = "Take photo";

  /// The save button.
  static const save = "Save";

  /// The cancel button of a sheet or dialog.
  static const cancel = "Cancel";

  /// The message when the device refused camera access.
  static const cameraDenied =
      "TailTag cannot use the camera. Allow camera access in Settings, "
      "or choose a photo instead.";

  /// The message when the device refused photo library access.
  static const libraryDenied =
      "TailTag cannot open your photos. Allow photo access in Settings, "
      "or take a photo instead.";

  /// The message when the picker failed for another reason.
  static const pickFailed = "The photo could not be opened. Try another one.";

  /// The banner after a create with no definite answer.
  static const createUnknownOutcome =
      "We could not confirm that your suit was saved. Check My suits before "
      "you try again.";

  /// The banner after another write with no definite answer.
  static const writeUnknownOutcome =
      "We could not confirm the change. Check the current state before you "
      "try again.";

  /// The banner when the API refused the token of an active session.
  static const apiAccess =
      "TailTag could not confirm your account. Try again, or sign out and "
      "sign in again.";

  /// The banner when the player profile cannot make changes.
  static const notEligible =
      "Your account cannot change suits right now. Contact TailTag staff if "
      "this looks wrong.";

  /// The detail screen text when the suit is not in the list.
  static const suitMissing = "This suit was not found.";

  /// The badge of a suit that does not participate.
  static const badgeNotParticipating = "Not participating";

  /// The badge of a suit that the server does not allow to participate.
  static const badgeCantParticipate = "Can't participate";

  /// The badge of a participating suit with no live session.
  static const badgeParticipating = "Participating";

  /// The badge of a suit with a live session.
  static const badgeCatchable = "Catchable";

  /// The section title on the suit screen.
  static String atConvention(String convention) => "At $convention";

  /// The participation switch title.
  static String participatingAt(String convention) =>
      "Participating at $convention";

  /// The participation switch subtitle while it can change.
  static const participationHelp =
      "Turn this on to take part at this convention.";

  /// The session switch title.
  static const outForCatching = "Out for catching";

  /// The session switch subtitle while it can change and is off.
  static const sessionHelp = "Turn this on while you are out in your suit.";

  /// The session switch subtitle while the suit is catchable.
  static String outUntil(String time) => "Out until $time";

  /// Disabled reason: staff disabled the suit.
  static const suitDisabled = "TailTag staff disabled this suit.";

  /// Disabled reason: the convention is not open for play.
  static const conventionClosed = "This convention is not open for play.";

  /// Disabled reason: the suit does not participate.
  static const participateFirst = "Turn on participation first.";

  /// Disabled reason: the server does not allow participation now.
  static const cannotParticipate = "This suit cannot participate right now.";

  /// The note after a session timed out.
  static String sessionTimedOut(String time) =>
      "Your last session timed out at $time.";

  /// The note after staff ended a session.
  static String sessionStaffEnded(String time) =>
      "TailTag staff ended your last session at $time.";

  /// The deactivation dialog title.
  static const deactivateTitle = "Stop participating?";

  /// The deactivation dialog body.
  static const deactivateBody =
      "This also ends the catch session, so players cannot catch this suit "
      "here until you turn it on again.";

  /// The deactivation confirm button.
  static const deactivateConfirm = "Stop";

  /// The snackbar after the owner stopped a session.
  static const sessionStopped = "Catch session ended";

  /// The snackbar after a name change.
  static const nameSaved = "Name saved";

  /// The snackbar after a photo change.
  static const photoSaved = "Photo saved";

  /// A time of [value] in device local time. A time on another day also
  /// shows the date.
  static String time(BuildContext context, DateTime value, DateTime now) {
    final local = MaterialLocalizations.of(context);
    final at = value.toLocal();
    final today = now.toLocal();
    final clock = local.formatTimeOfDay(TimeOfDay.fromDateTime(at));
    if (at.year == today.year &&
        at.month == today.month &&
        at.day == today.day) {
      return clock;
    }
    return "${local.formatShortMonthDay(at)}, $clock";
  }
}
