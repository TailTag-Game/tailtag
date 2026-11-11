// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/catch_request_action_error.dart' as _i11;
import 'package:tailtag_api/src/model/catch_request_decline.dart' as _i6;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i9;
import 'package:tailtag_api/src/model/detail_error.dart' as _i10;
import 'package:tailtag_api/src/model/owner_request.dart' as _i8;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response_wrapper/catch_incoming_requests_decline_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class CatchIncomingRequestsDecline
    extends _i1.HttpOperation<_i2.CatchIncomingRequestsDeclineResponse> {
  CatchIncomingRequestsDecline(super.baseUrl, super.clientAccessor);

  _i3.Future<
    _i4.TonikResult<_i2.CatchIncomingRequestsDeclineResponse, _i5.Response>
  >
  call({
    required _i6.CatchRequestDecline body,
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
        options: _options(),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path({required _i3.int id}) {
    return [
      r'api',
      r'catches',
      r'incoming-requests',
      id.toSimple(explode: false, allowEmpty: false),
      r'decline',
      r'',
    ];
  }

  _i3.Object? _data({required _i6.CatchRequestDecline body}) {
    return _i7.utf8.encode(_i7.jsonEncode(body.toJson()));
  }

  _i3.Map<_i3.String, _i3.String> _options() {
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    _$headers[r'Content-Type'] = r'application/json';
    return _$headers;
  }

  _i2.CatchIncomingRequestsDeclineResponse _parseResponse(
    _i5.Response response,
  ) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i8.OwnerRequest.fromJson(_$json);
        return _i2.CatchIncomingRequestsDeclineResponse200(body: _$body);
      case (400, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i9.CatchRequestError.fromJson(_$json);
        return _i2.CatchIncomingRequestsDeclineResponse400(body: _$body);
      case (401, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i10.DetailError.fromJson(_$json);
        return _i2.CatchIncomingRequestsDeclineResponse401(body: _$body);
      case (403, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i10.DetailError.fromJson(_$json);
        return _i2.CatchIncomingRequestsDeclineResponse403(body: _$body);
      case (404, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i11.CatchRequestActionError.fromJson(_$json);
        return _i2.CatchIncomingRequestsDeclineResponse404(body: _$body);
      case (409, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i11.CatchRequestActionError.fromJson(_$json);
        return _i2.CatchIncomingRequestsDeclineResponse409(body: _$body);
      case (500, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i9.CatchRequestError.fromJson(_$json);
        return _i2.CatchIncomingRequestsDeclineResponse500(body: _$body);
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
