// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_catches_get400_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_catches_get401_body_model.dart'
    as _i9;
import 'package:tailtag_api/src/model/api_catches_get404_body_model.dart'
    as _i10;
import 'package:tailtag_api/src/model/api_catches_get500_body_model.dart'
    as _i11;
import 'package:tailtag_api/src/model/catch_history_response_schema.dart'
    as _i7;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response_wrapper/catch_history_list_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class CatchHistoryList
    extends _i1.HttpOperation<_i2.CatchHistoryListResponse> {
  CatchHistoryList(super.baseUrl, super.clientAccessor);

  static const _i3.int pageDefault = 1;

  static const _i3.int pageSizeDefault = 20;

  _i3.Future<_i4.TonikResult<_i2.CatchHistoryListResponse, _i5.Response>> call({
    _i3.int? conventionId,
    _i3.int page = pageDefault,
    _i3.int pageSize = pageSizeDefault,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i1.HttpOperationRequest(
        method: 'GET',
        path: _path(),
        query: _queryParameters(
          conventionId: conventionId,
          page: page,
          pageSize: pageSize,
        ),
        data: _data(),
        options: _options(),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path() {
    return [r'api', r'catches', r''];
  }

  _i3.Object? _data() {
    return null;
  }

  _i3.String? _queryParameters({
    _i3.int? conventionId,
    _i3.int? page,
    _i3.int? pageSize,
  }) {
    final _$entries = <_i4.ParameterEntry>[];
    if (conventionId != null) {
      _$entries.addAll(
        conventionId.toForm(
          r'convention_id',
          explode: true,
          allowEmpty: false,
          textEncoding: _i6.utf8,
        ),
      );
    }
    if (page != null) {
      _$entries.addAll(
        page.toForm(
          r'page',
          explode: true,
          allowEmpty: false,
          textEncoding: _i6.utf8,
        ),
      );
    }
    if (pageSize != null) {
      _$entries.addAll(
        pageSize.toForm(
          r'page_size',
          explode: true,
          allowEmpty: false,
          textEncoding: _i6.utf8,
        ),
      );
    }
    if (_$entries.isEmpty) {
      return null;
    }
    return _$entries
        .map((e) => e.name.isEmpty ? e.value : '${e.name}=${e.value}')
        .join('&');
  }

  _i3.Map<_i3.String, _i3.String> _options() {
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    return _$headers;
  }

  _i2.CatchHistoryListResponse _parseResponse(_i5.Response response) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i7.CatchHistoryResponseSchema.fromJson(_$json);
        return _i2.CatchHistoryListResponse200(body: _$body);
      case (400, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i8.ApiCatchesGet400BodyModel.fromJson(_$json);
        return _i2.CatchHistoryListResponse400(body: _$body);
      case (401, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i9.ApiCatchesGet401BodyModel.fromJson(_$json);
        return _i2.CatchHistoryListResponse401(body: _$body);
      case (404, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i10.ApiCatchesGet404BodyModel.fromJson(_$json);
        return _i2.CatchHistoryListResponse404(body: _$body);
      case (500, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i11.ApiCatchesGet500BodyModel.fromJson(_$json);
        return _i2.CatchHistoryListResponse500(body: _$body);
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
