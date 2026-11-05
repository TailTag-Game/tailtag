import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";

void main() {
  // One case per ApiFailure subtype. A new subtype fails to compile in
  // genericErrorFor until it gets a case, and then needs a row here.
  const cases = <(ApiFailure, GenericError?)>[
    (ApiConnectivityFailure(), GenericError.noConnection),
    (ApiTimeoutFailure(), GenericError.timeout),
    (ApiServerFailure(statusCode: 503), GenericError.unknown),
    (ApiUnexpectedFailure(statusCode: 418), GenericError.unknown),
    // The app cancelled the request, so nothing shows.
    (ApiCancelledFailure(), null),
    // The auth flow sends the player to sign-in.
    (ApiUnauthenticatedFailure(statusCode: 401), null),
    // Features write the text for these.
    (ApiPermissionFailure(statusCode: 403, code: "not_owner"), null),
    (ApiNotFoundFailure(statusCode: 404), null),
    (ApiConflictFailure(statusCode: 409, code: "already_caught"), null),
    (ApiValidationFailure(statusCode: 400), null),
  ];

  for (final (failure, expected) in cases) {
    test("${failure.runtimeType} maps to $expected", () {
      expect(genericErrorFor(failure), expected);
    });
  }

  test("each generic error has the components.md text and action", () {
    expect(
      {for (final error in GenericError.values) error: error.message},
      {
        GenericError.noConnection:
            "No internet connection. Check your connection, then try again.",
        GenericError.timeout:
            "The server is taking too long to answer. Try again.",
        GenericError.unknown: "Something went wrong. Try again.",
      },
    );
    for (final error in GenericError.values) {
      expect(error.actionLabel, "Try again");
    }
  });
}
