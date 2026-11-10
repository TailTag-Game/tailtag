// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_catches_requests_post200_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_catches_requests_post201_body_model.dart'
    as _i9;
import 'package:tailtag_api/src/model/api_catches_requests_post400_body_model.dart'
    as _i10;
import 'package:tailtag_api/src/model/api_catches_requests_post401_body_model.dart'
    as _i11;
import 'package:tailtag_api/src/model/api_catches_requests_post403_body_model.dart'
    as _i12;
import 'package:tailtag_api/src/model/api_catches_requests_post404_body_model.dart'
    as _i13;
import 'package:tailtag_api/src/model/api_catches_requests_post409_body_model.dart'
    as _i14;
import 'package:tailtag_api/src/model/api_catches_requests_post500_body_model.dart'
    as _i15;
import 'package:tailtag_api/src/model/api_catches_requests_post_body_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response_wrapper/catch_requests_create_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class CatchRequestsCreate
    extends _i1.HttpOperation<_i2.CatchRequestsCreateResponse> {
  CatchRequestsCreate(super.baseUrl, super.clientAccessor);

  _i3.Future<_i4.TonikResult<_i2.CatchRequestsCreateResponse, _i5.Response>>
  call({
    _i6.ApiCatchesRequestsPostBodyBodyModel? body,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i1.HttpOperationRequest(
        method: 'POST',
        path: _path(),
        query: null,
        data: _data(body: body),
        options: _options(body: body),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path() {
    return [r'api', r'catches', r'requests', r''];
  }

  _i3.Object? _data({_i6.ApiCatchesRequestsPostBodyBodyModel? body}) {
    if (body == null) return null;
    return _i7.utf8.encode(_i7.jsonEncode(body.toJson()));
  }

  _i3.Map<_i3.String, _i3.String> _options({
    _i6.ApiCatchesRequestsPostBodyBodyModel? body,
  }) {
    final _$contentType = body == null ? null : r'application/json';
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    if (_$contentType != null) {
      _$headers[r'Content-Type'] = _$contentType;
    }
    return _$headers;
  }

  _i2.CatchRequestsCreateResponse _parseResponse(_i5.Response response) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i8.ApiCatchesRequestsPost200BodyModel.fromJson(_$json);
        return _i2.CatchRequestsCreateResponse200(body: _$body);
      case (201, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i9.ApiCatchesRequestsPost201BodyModel.fromJson(_$json);
        return _i2.CatchRequestsCreateResponse201(body: _$body);
      case (400, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i10.ApiCatchesRequestsPost400BodyModel.fromJson(_$json);
        return _i2.CatchRequestsCreateResponse400(body: _$body);
      case (401, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i11.ApiCatchesRequestsPost401BodyModel.fromJson(_$json);
        return _i2.CatchRequestsCreateResponse401(body: _$body);
      case (403, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i12.ApiCatchesRequestsPost403BodyModel.fromJson(_$json);
        return _i2.CatchRequestsCreateResponse403(body: _$body);
      case (404, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i13.ApiCatchesRequestsPost404BodyModel.fromJson(_$json);
        return _i2.CatchRequestsCreateResponse404(body: _$body);
      case (409, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i14.ApiCatchesRequestsPost409BodyModel.fromJson(_$json);
        return _i2.CatchRequestsCreateResponse409(body: _$body);
      case (500, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i15.ApiCatchesRequestsPost500BodyModel.fromJson(_$json);
        return _i2.CatchRequestsCreateResponse500(body: _$body);
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
