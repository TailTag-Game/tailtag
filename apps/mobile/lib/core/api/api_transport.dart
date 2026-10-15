import "dart:async";
import "dart:convert";
import "dart:io";

import "package:http/http.dart" as http;
import "package:tailtag_api/tailtag_api.dart";
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_diagnostic.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tonik_util/tonik_util.dart";

/// Deadline for a JSON request.
const Duration apiJsonTimeout = Duration(seconds: 15);

/// Deadline for a multipart upload.
const Duration apiMultipartTimeout = Duration(seconds: 60);

/// Which trigger aborted a request; stored as the [TonikCancellation] reason.
/// The first trigger to fire wins, because `TonikCancellation.cancel` ignores
/// later calls, so the reason is always the one that actually aborted.
enum _AbortTrigger { caller, deadline }

/// The one place that builds the generated client and runs its operations.
///
/// Repositories pass a generated operation to [execute]. It owns the abort
/// handle and the deadline, maps every outcome to an [ApiFailure], and
/// reports one `ApiDiagnostic`. Feature code never sees this class.
final class ApiTransport {
  /// Creates a transport that sends through [client] to [apiBaseUrl].
  ///
  /// [client] is normally a `TailTagHttpClient`, which carries the token and
  /// redirect rules; the transport itself only owns abort and mapping.
  new({
    required http.Client client,
    required Uri apiBaseUrl,
    this._jsonTimeout = apiJsonTimeout,
    this._multipartTimeout = apiMultipartTimeout,
    this._diagnostics,
  }) {
    final server = CustomServer(
      baseUrl: apiBaseUrl.toString(),
      serverConfig: ServerConfig.client(_MethodRecordingClient(client)),
    );
    me = MeApi(server);
    profile = ProfileApi(server);
  }

  final Duration _jsonTimeout;
  final Duration _multipartTimeout;
  final ApiDiagnosticSink? _diagnostics;

  /// The generated `/api/me/` operations.
  late final MeApi me;

  /// The generated `/api/profile/` operations.
  late final ProfileApi profile;

  /// Runs [call] with an abort handle and returns the generated response
  /// wrapper of a 2xx response, or throws an [ApiFailure].
  ///
  /// Outcomes are mapped by HTTP status, not by the generated result type:
  /// the generated client reports undocumented statuses as decoding errors
  /// and documented non-2xx statuses as successes, but both are failures
  /// here.
  Future<R> execute<R extends Object>({
    required String operationId,
    required Future<TonikResult<R, http.Response>> Function(
      TonikCancellation token,
    )
    call,
    ApiCancellation? cancellation,
    bool multipart = false,
  }) async {
    final stopwatch = Stopwatch()..start();
    final record = _CallRecord();
    final token = TonikCancellation();

    // The call and the abort triggers race to settle this completer; the
    // first to complete it decides the outcome and the later ones are no-ops.
    // The race exists because aborting the token only helps once the stack
    // below is listening to it: a stalled token provider or a pending
    // DNS/TCP/TLS connect would otherwise outlive the deadline and `cancel`.
    final outcome = Completer<_Settled<R>>();

    void abort(_AbortTrigger trigger) {
      if (outcome.isCompleted) {
        return;
      }
      // Aborting the token still matters after the outcome is decided here:
      // it aborts the request as soon as the stack below starts listening.
      // dart-lang/http#1934: in http 1.6.0, aborting a request before its
      // response body has been read can leave the connection open (fixed in
      // the unreleased http 1.7). The deadline and cancel do not wait for the
      // connect phase, because nothing below listens to the abort until then.
      token.cancel(trigger);
      // `cancel` keeps the first reason, so this reads the trigger that won.
      outcome.complete(
        _Failed<R>(_failureForError(const Object(), token), null),
      );
    }

    final timer = Timer(
      multipart ? _multipartTimeout : _jsonTimeout,
      () => abort(_AbortTrigger.deadline),
    );
    if (cancellation != null) {
      if (cancellation.isCancelled) {
        abort(_AbortTrigger.caller);
      } else {
        unawaited(
          cancellation.whenCancelled.then((_) => abort(_AbortTrigger.caller)),
        );
      }
    }

    // `_settle` never throws, so the call's future cannot fail unhandled even
    // when it loses the race; a late result is simply dropped, and only this
    // method ever reports a diagnostic.
    unawaited(
      runZoned(
        () => _settle(call, token),
        zoneValues: {_recordKey: record},
      ).then((settled) {
        if (!outcome.isCompleted) {
          outcome.complete(settled);
        }
      }),
    );

    final _Settled<R> settled;
    try {
      settled = await outcome.future;
    } finally {
      timer.cancel();
    }

    _report(
      ApiDiagnostic(
        method: record.method ?? "UNKNOWN",
        operationId: operationId,
        statusCode: settled.statusCode,
        duration: stopwatch.elapsed,
        failure: switch (settled) {
          _Failed<R>(:final failure) => failure.category,
          _Succeeded<R>() => null,
        },
      ),
    );

    switch (settled) {
      case _Succeeded<R>(:final value):
        return value;
      case _Failed<R>(:final failure):
        throw failure;
    }
  }

  Future<_Settled<R>> _settle<R extends Object>(
    Future<TonikResult<R, http.Response>> Function(TonikCancellation token)
    call,
    TonikCancellation token,
  ) async {
    final TonikResult<R, http.Response> result;
    try {
      result = await call(token);
    } on Object catch (error) {
      return _Failed<R>(_failureForError(error, token), null);
    }

    switch (result) {
      case TonikSuccess<R, http.Response>(:final value, :final response):
        if (_isSuccess(response.statusCode)) {
          return _Succeeded<R>(value, response.statusCode);
        }
        return _Failed<R>(_failureForResponse(response), response.statusCode);
      case TonikError<R, http.Response>(:final error, :final response):
        if (response != null) {
          return _Failed<R>(_failureForResponse(response), response.statusCode);
        }
        return _Failed<R>(_failureForError(error, token), null);
    }
  }

  void _report(ApiDiagnostic diagnostic) {
    try {
      _diagnostics?.call(diagnostic);
    } on Object {
      // A broken diagnostic sink must never change the outcome of a call.
    }
  }
}

bool _isSuccess(int status) => status >= 200 && status < 300;

/// A failure with no usable response: the transport, or the request itself.
ApiFailure _failureForError(Object error, TonikCancellation token) {
  if (token.isCancelled) {
    return switch (token.reason) {
      _AbortTrigger.deadline => const ApiTimeoutFailure(),
      _ => const ApiCancelledFailure(),
    };
  }
  return switch (error) {
    http.RequestAbortedException() => const ApiCancelledFailure(),
    http.ClientException() ||
    SocketException() ||
    HandshakeException() => const ApiConnectivityFailure(),
    TimeoutException() => const ApiTimeoutFailure(),
    _ => const ApiUnexpectedFailure(),
  };
}

/// A failure with a response, mapped by status alone.
ApiFailure _failureForResponse(http.Response response) {
  final status = response.statusCode;
  if (status < 400) {
    // 3xx (never followed), or a 2xx whose body did not decode.
    return ApiUnexpectedFailure(statusCode: status);
  }
  final body = _ErrorBody.parse(response.bodyBytes);
  return switch (status) {
    400 => ApiValidationFailure(
      statusCode: status,
      code: body.code,
      fieldErrors: body.fieldErrors,
    ),
    401 => ApiUnauthenticatedFailure(statusCode: status, code: body.code),
    403 => ApiPermissionFailure(statusCode: status, code: body.code),
    404 => ApiNotFoundFailure(statusCode: status, code: body.code),
    409 => ApiConflictFailure(statusCode: status, code: body.code),
    >= 500 && < 600 => ApiServerFailure(statusCode: status, code: body.code),
    _ => ApiUnexpectedFailure(statusCode: status, code: body.code),
  };
}

/// The two parts of a DRF error body TailTag uses; `detail` is dropped.
final class _ErrorBody {
  const new({this.code, this.fieldErrors = const {}});

  factory parse(List<int> bytes) {
    final Object? decoded;
    try {
      decoded = jsonDecode(utf8.decode(bytes, allowMalformed: true));
    } on FormatException {
      return const _ErrorBody();
    }
    if (decoded is! Map<String, Object?>) {
      return const _ErrorBody();
    }
    final code = decoded["code"];
    final fieldErrors = <String, List<String>>{};
    for (final MapEntry(:key, :value) in decoded.entries) {
      if (key == "code" || key == "detail") {
        continue;
      }
      if (value is List<Object?> && value.every((item) => item is String)) {
        fieldErrors[key] = List<String>.from(value);
      }
    }
    return _ErrorBody(
      code: code is String ? code : null,
      fieldErrors: fieldErrors,
    );
  }

  final String? code;
  final Map<String, List<String>> fieldErrors;
}

sealed class _Settled<R extends Object> {
  const new(this.statusCode);

  final int? statusCode;
}

final class _Succeeded<R extends Object> extends _Settled<R> {
  const new(this.value, int super.statusCode);

  final R value;
}

final class _Failed<R extends Object> extends _Settled<R> {
  const new(this.failure, super.statusCode);

  final ApiFailure failure;
}

const Symbol _recordKey = #tailtagApiCallRecord;

/// Per-call scratch space for what only the wire knows: the HTTP method of a
/// request that never produced a response.
final class _CallRecord {
  String? method;
}

/// Reports each request's method to the `execute` call that made it, through
/// the zone the generated operation runs in.
final class _MethodRecordingClient extends http.BaseClient {
  new(this._inner);

  final http.Client _inner;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    if (Zone.current[_recordKey] case final _CallRecord record) {
      record.method = request.method;
    }
    return _inner.send(request);
  }

  @override
  void close() => _inner.close();
}
