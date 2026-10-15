// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:async' as _i7;
import 'dart:convert' as _i8;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_profile_patch200_body_model.dart'
    as _i9;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/request_body/api_profile_patch_body_request_body.dart'
    as _i6;
import 'package:tailtag_api/src/response_wrapper/profile_partial_update_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class ProfilePartialUpdate
    extends _i1.HttpOperation<_i2.ProfilePartialUpdateResponse> {
  ProfilePartialUpdate(super.baseUrl, super.clientAccessor);

  _i3.Future<_i4.TonikResult<_i2.ProfilePartialUpdateResponse, _i5.Response>>
  call({
    _i6.ApiProfilePatchBodyRequestBody? body,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.executeAsync(
      cancellation: cancellation,
      prepare: () async => _i1.HttpOperationRequest(
        method: 'PATCH',
        path: _path(),
        query: null,
        data: await _data(body: body),
        options: _options(body: body),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path() {
    return [r'api', r'profile', r''];
  }

  _i7.Future<_i3.Object?> _data({
    _i6.ApiProfilePatchBodyRequestBody? body,
  }) async {
    return switch (body) {
      final _i6.ApiProfilePatchBodyRequestBodyJson value => _i8.utf8.encode(
        _i8.jsonEncode(value.value.toJson()),
      ),
      final _i6.ApiProfilePatchBodyRequestBodyXWwwFormUrlencoded value =>
        _i8.utf8.encode(
          value.value
              .toForm(
                '',
                explode: true,
                allowEmpty: true,
                useQueryComponent: true,
                textEncoding: _i8.utf8,
              )
              .map((e) => e.name.isEmpty ? e.value : '${e.name}=${e.value}')
              .join('&'),
        ),
      final _i6.ApiProfilePatchBodyRequestBodyFormData value => await () async {
        final _$multipartFiles = <_i5.MultipartFile>[];
        if (value.value.handle != null) {
          _$multipartFiles.add(
            _i5.MultipartFile.fromBytes(
              (r'handle').replaceAll(r'\', r'\\'),
              _i8.utf8.encode(value.value.handle!),
              contentType: _i5.MediaType.parse(r'text/plain'),
            ),
          );
        }
        if (value.value.displayName != null) {
          _$multipartFiles.add(
            _i5.MultipartFile.fromBytes(
              (r'display_name').replaceAll(r'\', r'\\'),
              _i8.utf8.encode(value.value.displayName!),
              contentType: _i5.MediaType.parse(r'text/plain'),
            ),
          );
        }
        if (_$multipartFiles.isEmpty) {
          throw _i4.EncodingException(
            r'Multipart request body must contain at least one part.',
          );
        }
        return _$multipartFiles;
      }(),
      null => null,
    };
  }

  _i3.Map<_i3.String, _i3.String> _options({
    _i6.ApiProfilePatchBodyRequestBody? body,
  }) {
    final _$contentType = switch (body) {
      _i6.ApiProfilePatchBodyRequestBodyJson _ => r'application/json',

      _i6.ApiProfilePatchBodyRequestBodyXWwwFormUrlencoded _ =>
        r'application/x-www-form-urlencoded',

      _i6.ApiProfilePatchBodyRequestBodyFormData _ => null,

      null => null,
    };
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    if (_$contentType != null) {
      _$headers[r'Content-Type'] = _$contentType;
    }
    return _$headers;
  }

  _i2.ProfilePartialUpdateResponse _parseResponse(_i5.Response response) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i9.ApiProfilePatch200BodyModel.fromJson(_$json);
        return _i2.ProfilePartialUpdateResponse200(body: _$body);
      case (400, _):
        return _i2.ProfilePartialUpdateResponse400();
      case (401, _):
        return _i2.ProfilePartialUpdateResponse401();
      case (403, _):
        return _i2.ProfilePartialUpdateResponse403();
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
