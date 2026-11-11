// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_session_put200_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_session_put_body_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_catch_session_set_state_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class ConventionFursuitCatchSessionSetState
    extends
        _i1.HttpOperation<_i2.ConventionFursuitCatchSessionSetStateResponse> {
  ConventionFursuitCatchSessionSetState(super.baseUrl, super.clientAccessor);

  _i3.Future<
    _i4.TonikResult<
      _i2.ConventionFursuitCatchSessionSetStateResponse,
      _i5.Response
    >
  >
  call({
    required _i6.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel
    body,
    required _i3.int conventionId,
    required _i3.int fursuitId,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i1.HttpOperationRequest(
        method: 'PUT',
        path: _path(conventionId: conventionId, fursuitId: fursuitId),
        query: null,
        data: _data(body: body),
        options: _options(),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path({
    required _i3.int conventionId,
    required _i3.int fursuitId,
  }) {
    return [
      r'api',
      r'conventions',
      conventionId.toSimple(explode: false, allowEmpty: false),
      r'fursuit-activations',
      fursuitId.toSimple(explode: false, allowEmpty: false),
      r'catch-session',
      r'',
    ];
  }

  _i3.Object? _data({
    required _i6.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel
    body,
  }) {
    return _i7.utf8.encode(_i7.jsonEncode(body.toJson()));
  }

  _i3.Map<_i3.String, _i3.String> _options() {
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    _$headers[r'Content-Type'] = r'application/json';
    return _$headers;
  }

  _i2.ConventionFursuitCatchSessionSetStateResponse _parseResponse(
    _i5.Response response,
  ) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body =
            _i8.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.fromJson(
              _$json,
            );
        return _i2.ConventionFursuitCatchSessionSetStateResponse200(
          body: _$body,
        );
      case (400, _):
        return _i2.ConventionFursuitCatchSessionSetStateResponse400();
      case (401, _):
        return _i2.ConventionFursuitCatchSessionSetStateResponse401();
      case (403, _):
        return _i2.ConventionFursuitCatchSessionSetStateResponse403();
      case (404, _):
        return _i2.ConventionFursuitCatchSessionSetStateResponse404();
      case (405, _):
        return _i2.ConventionFursuitCatchSessionSetStateResponse405();
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
