import "dart:async";
import "dart:convert";

import "package:http/http.dart" as http;
import "package:tailtag_mobile/core/api/api_diagnostic.dart";
import "package:tailtag_mobile/core/api/api_token_provider.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/api/tailtag_http_client.dart";

/// The API origin used by transport tests.
final Uri testApiBaseUrl = Uri.parse("https://dev.tailtag.app");

/// A token provider for tests that need neither Clerk nor Railway.
final class FakeApiTokenProvider implements ApiTokenProvider {
  new(this.value);

  final String? value;

  @override
  Future<String?> token() => Future<String?>.value(value);
}

/// A token provider whose refresh never completes, as an offline Clerk
/// refresh can.
final class HangingApiTokenProvider implements ApiTokenProvider {
  @override
  Future<String?> token() => Completer<String?>().future;
}

/// What a [FakeHttpClient] saw at the wire, captured after the body was
/// finalized so that generated multipart headers are present.
final class RecordedRequest {
  new({
    required this.method,
    required this.url,
    required this.headers,
    required this.followRedirects,
    required this.bodyBytes,
  });

  final String method;
  final Uri url;

  /// Lower-cased header names.
  final Map<String, String> headers;
  final bool followRedirects;
  final List<int> bodyBytes;

  String? get authorization => headers["authorization"];

  /// Body decoded leniently, for asserting on multipart field names.
  String get bodyText => latin1.decode(bodyBytes);
}

enum _Mode { respond, hang, deaf, fail }

/// The only substitute at the transport boundary: the network.
///
/// It exists to observe headers, `followRedirects`, and whether the abort
/// trigger of an abortable request fired, and to hang the way a stalled
/// socket does.
final class FakeHttpClient extends http.BaseClient {
  new _(this._mode, this._status, this._body, this._headers, this._error);

  factory respond(
    int status, {
    String body = "",
    String contentType = "application/json",
    Map<String, String> headers = const {},
  }) => ._(_Mode.respond, status, body, {
    "content-type": contentType,
    ...headers,
  }, null);

  /// Never responds. With [listenForAbort] false it also never subscribes to
  /// the abort trigger, like `IOClient` while DNS, TCP and TLS are pending.
  factory hang({bool listenForAbort = true}) =>
      ._(listenForAbort ? _Mode.hang : _Mode.deaf, 0, "", const {}, null);

  factory fail(Object error) => ._(_Mode.fail, 0, "", const {}, error);

  final _Mode _mode;
  final int _status;
  final String _body;
  final Map<String, String> _headers;
  final Object? _error;

  final List<RecordedRequest> requests = [];
  final Completer<void> _sent = Completer<void>();
  bool _aborted = false;

  /// Completes once the first request has reached this client.
  Future<void> get requestSent => _sent.future;

  /// Whether the abort trigger of a hanging request fired.
  bool get aborted => _aborted;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final bodyBytes = await request.finalize().toBytes();
    requests.add(
      RecordedRequest(
        method: request.method,
        url: request.url,
        headers: {
          for (final entry in request.headers.entries)
            entry.key.toLowerCase(): entry.value,
        },
        followRedirects: request.followRedirects,
        bodyBytes: bodyBytes,
      ),
    );
    if (!_sent.isCompleted) {
      _sent.complete();
    }

    switch (_mode) {
      case _Mode.respond:
        return http.StreamedResponse(
          Stream.value(utf8.encode(_body)),
          _status,
          headers: _headers,
          request: request,
        );
      case _Mode.fail:
        Error.throwWithStackTrace(_error!, StackTrace.current);
      case _Mode.deaf:
        await Completer<void>().future;
        throw StateError("unreachable");
      case _Mode.hang:
        final stalled = Completer<http.StreamedResponse>();
        if (request case http.Abortable(:final abortTrigger?)) {
          unawaited(
            abortTrigger.then((_) {
              _aborted = true;
              stalled.completeError(http.RequestAbortedException(request.url));
            }),
          );
        }
        final response = await stalled.future;
        return response;
    }
  }
}

/// Builds a real [ApiTransport] over a real [TailTagHttpClient] whose inner
/// client is [inner].
ApiTransport createTestTransport(
  http.Client inner, {
  String? token = "test-token",
  Duration jsonTimeout = apiJsonTimeout,
  Duration multipartTimeout = apiMultipartTimeout,
  ApiDiagnosticSink? diagnostics,
  ApiTokenProvider? tokenProvider,
}) {
  return ApiTransport(
    client: TailTagHttpClient(
      inner: inner,
      apiBaseUrl: testApiBaseUrl,
      tokenProvider: tokenProvider ?? FakeApiTokenProvider(token),
    ),
    apiBaseUrl: testApiBaseUrl,
    jsonTimeout: jsonTimeout,
    multipartTimeout: multipartTimeout,
    diagnostics: diagnostics,
  );
}
