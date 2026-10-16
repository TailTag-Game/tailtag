// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get200_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get400_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get401_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get403_body_model.dart'
    as _i9;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get404_body_model.dart'
    as _i10;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get405_body_model.dart'
    as _i11;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_catch_credential_get_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class ConventionFursuitCatchCredentialGet
    extends _i1.HttpOperation<_i2.ConventionFursuitCatchCredentialGetResponse> {
  ConventionFursuitCatchCredentialGet(super.baseUrl, super.clientAccessor);

  _i3.Future<
    _i4.TonikResult<
      _i2.ConventionFursuitCatchCredentialGetResponse,
      _i5.Response
    >
  >
  call({
    required _i3.int conventionId,
    required _i3.int fursuitId,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i1.HttpOperationRequest(
        method: 'GET',
        path: _path(conventionId: conventionId, fursuitId: fursuitId),
        query: null,
        data: _data(),
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
      r'catch-credential',
      r'',
    ];
  }

  _i3.Object? _data() {
    return null;
  }

  _i3.Map<_i3.String, _i3.String> _options() {
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    return _$headers;
  }

  _i2.ConventionFursuitCatchCredentialGetResponse _parseResponse(
    _i5.Response response,
  ) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body =
            _i6.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel.fromJson(
              _$json,
            );
        return _i2.ConventionFursuitCatchCredentialGetResponse200(body: _$body);
      case (400, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body =
            _i7.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet400BodyModel.fromJson(
              _$json,
            );
        return _i2.ConventionFursuitCatchCredentialGetResponse400(body: _$body);
      case (401, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body =
            _i8.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet401BodyModel.fromJson(
              _$json,
            );
        return _i2.ConventionFursuitCatchCredentialGetResponse401(body: _$body);
      case (403, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body =
            _i9.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet403BodyModel.fromJson(
              _$json,
            );
        return _i2.ConventionFursuitCatchCredentialGetResponse403(body: _$body);
      case (404, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body =
            _i10.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet404BodyModel.fromJson(
              _$json,
            );
        return _i2.ConventionFursuitCatchCredentialGetResponse404(body: _$body);
      case (405, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body =
            _i11.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet405BodyModel.fromJson(
              _$json,
            );
        return _i2.ConventionFursuitCatchCredentialGetResponse405(body: _$body);
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
