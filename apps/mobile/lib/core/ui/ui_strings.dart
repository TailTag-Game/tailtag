/// The English text that shared UI owns.
///
/// Features write all other text. "Back" and "Dismiss" come from
/// `MaterialLocalizations`. V0 is English only. A later localization pass
/// moves these strings into translation files.
abstract final class UiStrings {
  /// The screen reader value of a control that waits for the server.
  static const loading = "Loading";

  /// The subtitle of a switch row that waits for the server.
  static const updating = "Updating";

  /// The action of a generic error banner.
  static const tryAgain = "Try again";

  /// The banner text when the device has no connection.
  static const noConnection =
      "No internet connection. Check your connection, then try again.";

  /// The banner text when the server takes too long.
  static const timeout = "The server is taking too long to answer. Try again.";

  /// The banner text for any other error.
  static const unknownError = "Something went wrong. Try again.";
}
