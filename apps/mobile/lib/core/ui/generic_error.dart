import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";

/// The errors that every flow can get, with their status banner text.
///
/// See "Generic error text" in docs/design/components.md. Show one in a
/// `StatusBanner` with the error tone.
enum GenericError {
  /// The device has no connection.
  noConnection(UiStrings.noConnection),

  /// The server takes too long to answer.
  timeout(UiStrings.timeout),

  /// Any other error, including a server `code` that the feature does not
  /// know and a field error with no `code`.
  unknown(UiStrings.unknownError);

  new(this.message);

  /// The banner text.
  final String message;

  /// The banner action label.
  String get actionLabel => UiStrings.tryAgain;
}

/// The generic error for [failure], or null when the app must not show a
/// generic banner.
///
/// It returns null for these failures:
///
/// - `ApiCancelledFailure`: the app cancelled the request, so nothing shows.
/// - `ApiUnauthenticatedFailure`: the auth flow sends the player to sign-in.
/// - `ApiPermissionFailure`, `ApiNotFoundFailure`, `ApiConflictFailure`, and
///   `ApiValidationFailure`: the feature shows its own text for a `code` that
///   it knows. For any other `code`, or no `code`, it shows
///   [GenericError.unknown].
GenericError? genericErrorFor(ApiFailure failure) {
  return switch (failure) {
    ApiConnectivityFailure() => GenericError.noConnection,
    ApiTimeoutFailure() => GenericError.timeout,
    ApiServerFailure() || ApiUnexpectedFailure() => GenericError.unknown,
    ApiCancelledFailure() ||
    ApiUnauthenticatedFailure() ||
    ApiPermissionFailure() ||
    ApiNotFoundFailure() ||
    ApiConflictFailure() ||
    ApiValidationFailure() => null,
  };
}
