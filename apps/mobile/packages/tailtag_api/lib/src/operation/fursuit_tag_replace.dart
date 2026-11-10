// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post200_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post400_body_model.dart'
    as _i9;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post404_body_model.dart'
    as _i10;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post409_body_model.dart'
    as _i11;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post_body_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response_wrapper/fursuit_tag_replace_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class FursuitTagReplace
    extends _i1.HttpOperation<_i2.FursuitTagReplaceResponse> {
  FursuitTagReplace(super.baseUrl, super.clientAccessor);

  _i3.Future<_i4.TonikResult<_i2.FursuitTagReplaceResponse, _i5.Response>>
  call({
    _i6.ApiFursuitsIdTagReplacePostBodyBodyModel? body,
    required _i3.int id,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i1.HttpOperationRequest(
        method: 'POST',
        path: _path(id: id),
        query: null,
        data: _data(body: body),
        options: _options(body: body),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path({required _i3.int id}) {
    return [
      r'api',
      r'fursuits',
      id.toSimple(explode: false, allowEmpty: false),
      r'tag',
      r'replace',
      r'',
    ];
  }

  _i3.Object? _data({_i6.ApiFursuitsIdTagReplacePostBodyBodyModel? body}) {
    if (body == null) return null;
    return _i7.utf8.encode(_i7.jsonEncode(body.toJson()));
  }

  _i3.Map<_i3.String, _i3.String> _options({
    _i6.ApiFursuitsIdTagReplacePostBodyBodyModel? body,
  }) {
    final _$contentType = body == null ? null : r'application/json';
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    if (_$contentType != null) {
      _$headers[r'Content-Type'] = _$contentType;
    }
    return _$headers;
  }

  _i2.FursuitTagReplaceResponse _parseResponse(_i5.Response response) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i8.ApiFursuitsIdTagReplacePost200BodyModel.fromJson(
          _$json,
        );
        return _i2.FursuitTagReplaceResponse200(body: _$body);
      case (400, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i9.ApiFursuitsIdTagReplacePost400BodyModel.fromJson(
          _$json,
        );
        return _i2.FursuitTagReplaceResponse400(body: _$body);
      case (401, _):
        return _i2.FursuitTagReplaceResponse401();
      case (403, _):
        return _i2.FursuitTagReplaceResponse403();
      case (404, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i10.ApiFursuitsIdTagReplacePost404BodyModel.fromJson(
          _$json,
        );
        return _i2.FursuitTagReplaceResponse404(body: _$body);
      case (405, _):
        return _i2.FursuitTagReplaceResponse405();
      case (409, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i11.ApiFursuitsIdTagReplacePost409BodyModel.fromJson(
          _$json,
        );
        return _i2.FursuitTagReplaceResponse409(body: _$body);
      case (500, _):
        return _i2.FursuitTagReplaceResponse500();
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
