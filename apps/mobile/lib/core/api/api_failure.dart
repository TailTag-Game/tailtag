/// The outcome categories of a failed API call, safe to log.
enum ApiFailureCategory {
  /// The network could not be reached or the connection broke.
  connectivity,

  /// The request outlived its deadline.
  timeout,

  /// The caller cancelled the request.
  cancelled,

  /// HTTP 401.
  unauthenticated,

  /// HTTP 403.
  permission,

  /// HTTP 404.
  notFound,

  /// HTTP 409.
  conflict,

  /// HTTP 400.
  validation,

  /// HTTP 5xx.
  server,

  /// Anything else.
  unexpected,
}

/// Why an API call did not produce a result.
///
/// The model is deliberately small: a category, the HTTP status when a
/// response arrived, and the server's machine-readable `code` when it sent
/// one. The server's free-text `detail`, bodies, and headers are never kept,
/// so no failure can leak them through logging.
sealed class ApiFailure implements Exception {
  /// Creates a failure with an optional HTTP [statusCode] and server [code].
  const new({this.statusCode, this.code});

  /// The HTTP status, or null when no response was received.
  final int? statusCode;

  /// The server's `code` string, when the error body carried one.
  final String? code;

  /// The loggable category of this failure.
  ApiFailureCategory get category;

  @override
  String toString() {
    final parts = [
      category.name,
      if (statusCode != null) "status: $statusCode",
      if (code != null) "code: $code",
    ];
    return "ApiFailure(${parts.join(", ")})";
  }
}

/// The network could not be reached or the connection broke.
final class ApiConnectivityFailure extends ApiFailure {
  /// Creates the failure.
  const new() : super();

  @override
  ApiFailureCategory get category => ApiFailureCategory.connectivity;
}

/// The request outlived its deadline and was aborted.
final class ApiTimeoutFailure extends ApiFailure {
  /// Creates the failure.
  const new() : super();

  @override
  ApiFailureCategory get category => ApiFailureCategory.timeout;
}

/// The caller cancelled the request, normally by disposing its provider.
final class ApiCancelledFailure extends ApiFailure {
  /// Creates the failure.
  const new() : super();

  @override
  ApiFailureCategory get category => ApiFailureCategory.cancelled;
}

/// HTTP 401.
final class ApiUnauthenticatedFailure extends ApiFailure {
  /// Creates the failure.
  const new({super.statusCode, super.code});

  @override
  ApiFailureCategory get category => ApiFailureCategory.unauthenticated;
}

/// HTTP 403.
final class ApiPermissionFailure extends ApiFailure {
  /// Creates the failure.
  const new({super.statusCode, super.code});

  @override
  ApiFailureCategory get category => ApiFailureCategory.permission;
}

/// HTTP 404.
final class ApiNotFoundFailure extends ApiFailure {
  /// Creates the failure.
  const new({super.statusCode, super.code});

  @override
  ApiFailureCategory get category => ApiFailureCategory.notFound;
}

/// HTTP 409.
final class ApiConflictFailure extends ApiFailure {
  /// Creates the failure.
  const new({super.statusCode, super.code});

  @override
  ApiFailureCategory get category => ApiFailureCategory.conflict;
}

/// HTTP 400, with the per-field messages the server returned.
final class ApiValidationFailure extends ApiFailure {
  /// Creates the failure.
  const new({super.statusCode, super.code, this.fieldErrors = const {}});

  /// Field name to messages. Only string-list values are kept, and the
  /// `code` and `detail` keys are never fields.
  final Map<String, List<String>> fieldErrors;

  @override
  ApiFailureCategory get category => ApiFailureCategory.validation;
}

/// HTTP 5xx.
final class ApiServerFailure extends ApiFailure {
  /// Creates the failure.
  const new({super.statusCode, super.code});

  @override
  ApiFailureCategory get category => ApiFailureCategory.server;
}

/// Anything else: other statuses (including redirects), a response that does
/// not decode, or a malformed body.
final class ApiUnexpectedFailure extends ApiFailure {
  /// Creates the failure.
  const new({super.statusCode, super.code});

  @override
  ApiFailureCategory get category => ApiFailureCategory.unexpected;
}
