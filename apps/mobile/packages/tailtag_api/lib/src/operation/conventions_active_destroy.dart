// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_conventions_active_delete401_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_conventions_active_delete403_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response_wrapper/conventions_active_destroy_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class ConventionsActiveDestroy
    extends _i1.HttpOperation<_i2.ConventionsActiveDestroyResponse> {
  ConventionsActiveDestroy(super.baseUrl, super.clientAccessor);

  _i3.Future<
    _i4.TonikResult<_i2.ConventionsActiveDestroyResponse, _i5.Response>
  >
  call({_i4.TonikCancellation? cancellation}) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i1.HttpOperationRequest(
        method: 'DELETE',
        path: _path(),
        query: null,
        data: _data(),
        options: _options(),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path() {
    return [r'api', r'conventions', r'active', r''];
  }

  _i3.Object? _data() {
    return null;
  }

  _i3.Map<_i3.String, _i3.String> _options() {
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    return _$headers;
  }

  _i2.ConventionsActiveDestroyResponse _parseResponse(_i5.Response response) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (204, _):
        return _i2.ConventionsActiveDestroyResponse204();
      case (401, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i6.ApiConventionsActiveDelete401BodyModel.fromJson(
          _$json,
        );
        return _i2.ConventionsActiveDestroyResponse401(body: _$body);
      case (403, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i7.ApiConventionsActiveDelete403BodyModel.fromJson(
          _$json,
        );
        return _i2.ConventionsActiveDestroyResponse403(body: _$body);
      default:
        final _$content = response.headers['content-type'] ?? 'not specified';
        final _$matched = _$mediaType ?? 'none';
        final _$status = response.statusCode;
        throw _i4.ResponseDecodingException(
          'Unexpected content type: ${_$content} (matched as: ${_$matched}) for status code: ${_$status}',
        );
    }
  }
}
