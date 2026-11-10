// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i1;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_rotate_post200_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_rotate_post400_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_rotate_post401_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_rotate_post403_body_model.dart'
    as _i9;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_rotate_post404_body_model.dart'
    as _i10;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_rotate_post405_body_model.dart'
    as _i11;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i2;
import 'package:tailtag_api/src/response_wrapper/convention_fursuit_catch_credential_rotate_response.dart'
    as _i3;
import 'package:tonik_util/tonik_util.dart' as _i4;

@_i1.Deprecated('This operation is deprecated.')
final class ConventionFursuitCatchCredentialRotate
    extends
        _i2.HttpOperation<_i3.ConventionFursuitCatchCredentialRotateResponse> {
  ConventionFursuitCatchCredentialRotate(super.baseUrl, super.clientAccessor);

  _i1.Future<
    _i4.TonikResult<
      _i3.ConventionFursuitCatchCredentialRotateResponse,
      _i5.Response
    >
  >
  call({
    required _i1.int conventionId,
    required _i1.int fursuitId,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i2.HttpOperationRequest(
        method: 'POST',
        path: _path(conventionId: conventionId, fursuitId: fursuitId),
        query: null,
        data: _data(),
        options: _options(),
      ),
      decode: _parseResponse,
    );
  }

  _i1.List<_i1.String> _path({
    required _i1.int conventionId,
    required _i1.int fursuitId,
  }) {
    return [
      r'api',
      r'conventions',
      conventionId.toSimple(explode: false, allowEmpty: false),
      r'fursuit-activations',
      fursuitId.toSimple(explode: false, allowEmpty: false),
      r'catch-credential',
      r'rotate',
      r'',
    ];
  }

  _i1.Object? _data() {
    return null;
  }

  _i1.Map<_i1.String, _i1.String> _options() {
    final _$headers = <_i1.String, _i1.String>{};
    _$headers['Accept'] = r'application/json';
    return _$headers;
  }

  _i3.ConventionFursuitCatchCredentialRotateResponse _parseResponse(
    _i5.Response response,
  ) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i6.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialRotatePost200BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialRotateResponse200(
          body: _$body,
        );
      case (400, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i7.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialRotatePost400BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialRotateResponse400(
          body: _$body,
        );
      case (401, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i8.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialRotatePost401BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialRotateResponse401(
          body: _$body,
        );
      case (403, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i9.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialRotatePost403BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialRotateResponse403(
          body: _$body,
        );
      case (404, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i10.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialRotatePost404BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialRotateResponse404(
          body: _$body,
        );
      case (405, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i1.Object?>(response.bodyBytes);
        final _$body =
            _i11.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialRotatePost405BodyModel.fromJson(
              _$json,
            );
        return _i3.ConventionFursuitCatchCredentialRotateResponse405(
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
