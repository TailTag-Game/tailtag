// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:async' as _i3;
import 'dart:core' as _i1;

import 'package:http/http.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

abstract base class HttpOperation<T> {
  HttpOperation(this.baseUrl, this.clientAccessor);

  final _i1.String baseUrl;

  final _i2.Client Function() clientAccessor;

  _i3.Future<_i4.TonikResult<T, _i2.Response>> execute({
    _i4.TonikCancellation? cancellation,
    required HttpOperationRequest Function() prepare,
    required T Function(_i2.Response) decode,
  }) async {
    late final HttpOperationRequest request;
    late final _HttpPreparedRequest prepared;
    try {
      request = prepare();
      final baseUri = _i1.Uri.parse(baseUrl);
      final pathResult = request.path;
      final newPath = baseUri.path.endsWith('/')
          ? '${baseUri.path.substring(0, baseUri.path.length - 1)}/${pathResult.join('/')}'
          : '${baseUri.path}/${pathResult.join('/')}';
      final uri = baseUri.replace(path: newPath, query: request.query);
      prepared = _HttpPreparedRequest(uri, request.data, request.options);
    } on _i1.Object catch (exception, stackTrace) {
      return _i4.TonikError<T, _i2.Response>(
        exception,
        stackTrace: stackTrace,
        type: _i4.TonikErrorType.encoding,
        response: null,
      );
    }

    final dispatched = await _dispatch<T>(
      method: request.method,
      prepared: prepared,
      cancellation: cancellation,
    );
    final error = dispatched.error;
    if (error != null) return error;
    final response = dispatched.response!;

    final T value;
    try {
      value = decode(response);
    } on _i1.Object catch (exception, stackTrace) {
      return _i4.TonikError<T, _i2.Response>(
        exception,
        stackTrace: stackTrace,
        type: _i4.TonikErrorType.decoding,
        response: response,
      );
    }
    return _i4.TonikSuccess<T, _i2.Response>(value, response);
  }

  _i3.Future<_i4.TonikResult<T, _i2.Response>> executeAsync({
    _i4.TonikCancellation? cancellation,
    required _i3.Future<HttpOperationRequest> Function() prepare,
    required T Function(_i2.Response) decode,
  }) async {
    late final HttpOperationRequest request;
    late final _HttpPreparedRequest prepared;
    try {
      request = await prepare();
      final baseUri = _i1.Uri.parse(baseUrl);
      final pathResult = request.path;
      final newPath = baseUri.path.endsWith('/')
          ? '${baseUri.path.substring(0, baseUri.path.length - 1)}/${pathResult.join('/')}'
          : '${baseUri.path}/${pathResult.join('/')}';
      final uri = baseUri.replace(path: newPath, query: request.query);
      prepared = _HttpPreparedRequest(uri, request.data, request.options);
    } on _i1.Object catch (exception, stackTrace) {
      return _i4.TonikError<T, _i2.Response>(
        exception,
        stackTrace: stackTrace,
        type: _i4.TonikErrorType.encoding,
        response: null,
      );
    }

    final dispatched = await _dispatch<T>(
      method: request.method,
      prepared: prepared,
      cancellation: cancellation,
    );
    final error = dispatched.error;
    if (error != null) return error;
    final response = dispatched.response!;

    final T value;
    try {
      value = decode(response);
    } on _i1.Object catch (exception, stackTrace) {
      return _i4.TonikError<T, _i2.Response>(
        exception,
        stackTrace: stackTrace,
        type: _i4.TonikErrorType.decoding,
        response: response,
      );
    }
    return _i4.TonikSuccess<T, _i2.Response>(value, response);
  }

  _i3.Future<_i4.TonikResult<void, _i2.Response>> executeVoid({
    _i4.TonikCancellation? cancellation,
    required HttpOperationRequest Function() prepare,
    required void Function(_i2.Response) decode,
  }) async {
    late final HttpOperationRequest request;
    late final _HttpPreparedRequest prepared;
    try {
      request = prepare();
      final baseUri = _i1.Uri.parse(baseUrl);
      final pathResult = request.path;
      final newPath = baseUri.path.endsWith('/')
          ? '${baseUri.path.substring(0, baseUri.path.length - 1)}/${pathResult.join('/')}'
          : '${baseUri.path}/${pathResult.join('/')}';
      final uri = baseUri.replace(path: newPath, query: request.query);
      prepared = _HttpPreparedRequest(uri, request.data, request.options);
    } on _i1.Object catch (exception, stackTrace) {
      return _i4.TonikError<void, _i2.Response>(
        exception,
        stackTrace: stackTrace,
        type: _i4.TonikErrorType.encoding,
        response: null,
      );
    }

    final dispatched = await _dispatch<void>(
      method: request.method,
      prepared: prepared,
      cancellation: cancellation,
    );
    final error = dispatched.error;
    if (error != null) return error;
    final response = dispatched.response!;

    try {
      decode(response);
    } on _i1.Object catch (exception, stackTrace) {
      return _i4.TonikError<void, _i2.Response>(
        exception,
        stackTrace: stackTrace,
        type: _i4.TonikErrorType.decoding,
        response: response,
      );
    }
    return _i4.TonikSuccess<void, _i2.Response>(null, response);
  }

  _i3.Future<_i4.TonikResult<void, _i2.Response>> executeVoidAsync({
    _i4.TonikCancellation? cancellation,
    required _i3.Future<HttpOperationRequest> Function() prepare,
    required void Function(_i2.Response) decode,
  }) async {
    late final HttpOperationRequest request;
    late final _HttpPreparedRequest prepared;
    try {
      request = await prepare();
      final baseUri = _i1.Uri.parse(baseUrl);
      final pathResult = request.path;
      final newPath = baseUri.path.endsWith('/')
          ? '${baseUri.path.substring(0, baseUri.path.length - 1)}/${pathResult.join('/')}'
          : '${baseUri.path}/${pathResult.join('/')}';
      final uri = baseUri.replace(path: newPath, query: request.query);
      prepared = _HttpPreparedRequest(uri, request.data, request.options);
    } on _i1.Object catch (exception, stackTrace) {
      return _i4.TonikError<void, _i2.Response>(
        exception,
        stackTrace: stackTrace,
        type: _i4.TonikErrorType.encoding,
        response: null,
      );
    }

    final dispatched = await _dispatch<void>(
      method: request.method,
      prepared: prepared,
      cancellation: cancellation,
    );
    final error = dispatched.error;
    if (error != null) return error;
    final response = dispatched.response!;

    try {
      decode(response);
    } on _i1.Object catch (exception, stackTrace) {
      return _i4.TonikError<void, _i2.Response>(
        exception,
        stackTrace: stackTrace,
        type: _i4.TonikErrorType.decoding,
        response: response,
      );
    }
    return _i4.TonikSuccess<void, _i2.Response>(null, response);
  }

  _i3.Future<_HttpDispatchResult<V>> _dispatch<V>({
    required _i1.String method,
    required _HttpPreparedRequest prepared,
    required _i4.TonikCancellation? cancellation,
  }) async {
    if (cancellation != null && cancellation.isCancelled) {
      final exception = _i2.RequestAbortedException(prepared.uri);
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: _i1.StackTrace.current,
          type: _i4.TonikErrorType.cancelled,
          response: null,
        ),
        null,
      );
    }

    final _i2.Client resolvedClient;
    try {
      resolvedClient = clientAccessor();
    } on _i1.Object catch (exception, stackTrace) {
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: stackTrace,
          type: _i4.TonikErrorType.other,
          response: null,
        ),
        null,
      );
    }

    late final _i2.BaseRequest request;
    try {
      final data = prepared.data;
      if (data is _i4.TonikMultipartBody) {
        final bodyRequest = _i2.AbortableRequest(
          method,
          prepared.uri,
          abortTrigger: cancellation?.whenCancelled,
        );
        bodyRequest.bodyBytes = data.bodyBytes;
        request = bodyRequest;
      } else if (data is _i1.List<_i2.MultipartFile>) {
        final multipartRequest = _i2.AbortableMultipartRequest(
          method,
          prepared.uri,
          abortTrigger: cancellation?.whenCancelled,
        );
        multipartRequest.fields.addAll(const <_i1.String, _i1.String>{});
        multipartRequest.files.addAll(data);
        request = multipartRequest;
      } else {
        final ordinaryRequest = _i2.AbortableRequest(
          method,
          prepared.uri,
          abortTrigger: cancellation?.whenCancelled,
        );
        if (data case final _i1.List<_i1.int> bodyBytes) {
          ordinaryRequest.bodyBytes = bodyBytes;
        } else if (data != null) {
          throw _i1.StateError('Unexpected HTTP request body type.');
        }
        request = ordinaryRequest;
      }
      request.headers.addAll(prepared.options);
      if (data is _i4.TonikMultipartBody) {
        request.headers['content-type'] = data.contentType;
      }
    } on _i1.Object catch (exception, stackTrace) {
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: stackTrace,
          type: _i4.TonikErrorType.encoding,
          response: null,
        ),
        null,
      );
    }

    final _i2.StreamedResponse streamedResponse;
    try {
      streamedResponse = await resolvedClient.send(request);
    } on _i2.RequestAbortedException catch (exception, stackTrace) {
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: stackTrace,
          type: _requestAbortErrorType(cancellation),
          response: null,
        ),
        null,
      );
    } on _i2.ClientException catch (exception, stackTrace) {
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: stackTrace,
          type: _i4.TonikErrorType.network,
          response: null,
        ),
        null,
      );
    } on _i3.TimeoutException catch (exception, stackTrace) {
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: stackTrace,
          type: _i4.TonikErrorType.network,
          response: null,
        ),
        null,
      );
    } on _i1.Object catch (exception, stackTrace) {
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: stackTrace,
          type: _i4.TonikErrorType.other,
          response: null,
        ),
        null,
      );
    }

    final _i2.Response response;
    try {
      response = await _i2.Response.fromStream(streamedResponse);
    } on _i2.RequestAbortedException catch (exception, stackTrace) {
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: stackTrace,
          type: _requestAbortErrorType(cancellation),
          response: null,
        ),
        null,
      );
    } on _i1.Object catch (exception, stackTrace) {
      return _HttpDispatchResult<V>(
        _i4.TonikError<V, _i2.Response>(
          exception,
          stackTrace: stackTrace,
          type: _i4.TonikErrorType.network,
          response: null,
        ),
        null,
      );
    }
    return _HttpDispatchResult<V>(null, response);
  }

  _i4.TonikErrorType _requestAbortErrorType(
    _i4.TonikCancellation? cancellation,
  ) => cancellation?.isCancelled ?? false
      ? _i4.TonikErrorType.cancelled
      : _i4.TonikErrorType.network;
}

final class HttpOperationRequest {
  HttpOperationRequest({
    required this.method,
    required this.path,
    required this.query,
    required this.data,
    required this.options,
  });

  final _i1.String method;

  final _i1.List<_i1.String> path;

  final _i1.String? query;

  final _i1.Object? data;

  final _i1.Map<_i1.String, _i1.String> options;
}

class _HttpPreparedRequest {
  _HttpPreparedRequest(this.uri, this.data, this.options);

  final _i1.Uri uri;

  final _i1.Object? data;

  final _i1.Map<_i1.String, _i1.String> options;
}

class _HttpDispatchResult<T> {
  _HttpDispatchResult(this.error, this.response);

  final _i4.TonikError<T, _i2.Response>? error;

  final _i2.Response? response;
}
