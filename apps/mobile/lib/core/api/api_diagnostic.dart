import "package:tailtag_mobile/core/api/api_failure.dart";

/// What the transport reports about one finished call.
///
/// The fields are an allow-list: no URL, query string, header, body, token,
/// or server `detail` can appear here.
final class ApiDiagnostic {
  /// Creates a diagnostic.
  const new({
    required this.method,
    required this.operationId,
    required this.statusCode,
    required this.duration,
    required this.failure,
  });

  /// The HTTP method, or `UNKNOWN` if the request never reached the wire.
  final String method;

  /// The OpenAPI operation id, such as `meRetrieve`.
  final String operationId;

  /// Null when no response was received.
  final int? statusCode;

  /// How long the call took.
  final Duration duration;

  /// Null when the call succeeded.
  final ApiFailureCategory? failure;

  @override
  String toString() =>
      "ApiDiagnostic($method $operationId, status: $statusCode, "
      "duration: ${duration.inMilliseconds}ms, failure: ${failure?.name})";
}

/// Receives one [ApiDiagnostic] per finished call.
typedef ApiDiagnosticSink = void Function(ApiDiagnostic diagnostic);
