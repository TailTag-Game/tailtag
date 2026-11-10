// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i1;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post200_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post400_body_model.dart'
    as _i9;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post401_body_model.dart'
    as _i10;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post403_body_model.dart'
    as _i11;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post404_body_model.dart'
    as _i12;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post405_body_model.dart'
    as _i13;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post_body_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i2;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_catch_credential_resolve_response.dart'
    as _i3;
import 'package:tonik_util/tonik_util.dart' as _i4;

@_i1.Deprecated('This operation is deprecated.')
final class ConventionFursuitCatchCredentialResolve
    extends
        _i2.HttpOperation<_i3.ConventionFursuitCatchCredentialResolveResponse> {
  ConventionFursuitCatchCredentialResolve(super.baseUrl, super.clientAccessor);

  _i1.Future<
    _i4.TonikResult<
      _i3.ConventionFursuitCatchCredentialResolveResponse,
      _i5.Response
    >
  >
  call({
    _i6.ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel?
    body,
    required _i1.int conventionId,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i2.HttpOperationRequest(
        method: 'POST',
        path: _path(conventionId: conventionId),
        query: null,
        data: _data(body: body),
        options: _options(body: body),
      ),
      decode: _parseResponse,
    );
  }

  _i1.List<_i1.String> _path({required _i1.int conventionId}) {
    return [
      r'api',
      r'conventions',
      conventionId.toSimple(explode: false, allowEmpty: false),
      r'catch-credentials',
      r'resolve',
      r'',
    ];
  }

  _i1.Object? _data({
    _i6.ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel?
    body,
  }) {
    if (body == null) return null;
    return _i7.utf8.encode(_i7.jsonEncode(body.toJson()));
  }

  _i1.Map<_i1.String, _i1.String> _options({
    _i6.ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel?
    body,
  }) {
    final _$contentType = body == null ? null : r'application/json';
    final _$headers = <_i1.String, _i1.String>{};
    _$headers['Accept'] = r'application/json';
    if (_$contentType != null) {
      _$headers[r'Content-Type'] = _$contentType;
    }
    return _$headers;
  }

  _i3.ConventionFursuitCatchCredentialResolveResponse _parseResponse(
    _i5.Response response,
  ) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i8.ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialResolveResponse200(
          body: _$body,
        );
      case (400, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i9.ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialResolveResponse400(
          body: _$body,
        );
      case (401, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i10.ApiConventionsConventionIdCatchCredentialsResolvePost401BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialResolveResponse401(
          body: _$body,
        );
      case (403, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i11.ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialResolveResponse403(
          body: _$body,
        );
      case (404, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i12.ApiConventionsConventionIdCatchCredentialsResolvePost404BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialResolveResponse404(
          body: _$body,
        );
      case (405, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i13.ApiConventionsConventionIdCatchCredentialsResolvePost405BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialResolveResponse405(
          body: _$body,
        );
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
