// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:async' as _i7;
import 'dart:convert' as _i8;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_conventions_enrollments_post400_body_model.dart'
    as _i10;
import 'package:tailtag_api/src/model/api_conventions_enrollments_post401_body_model.dart'
    as _i11;
import 'package:tailtag_api/src/model/api_conventions_enrollments_post403_body_model.dart'
    as _i12;
import 'package:tailtag_api/src/model/api_conventions_enrollments_post404_body_model.dart'
    as _i13;
import 'package:tailtag_api/src/model/convention_enrollment.dart' as _i9;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/request_body/api_conventions_enrollments_post_body_request_body.dart'
    as _i6;
import 'package:tailtag_api/src/response_wrapper/conventions_enrollments_create_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class ConventionsEnrollmentsCreate
    extends _i1.HttpOperation<_i2.ConventionsEnrollmentsCreateResponse> {
  ConventionsEnrollmentsCreate(super.baseUrl, super.clientAccessor);

  _i3.Future<
    _i4.TonikResult<_i2.ConventionsEnrollmentsCreateResponse, _i5.Response>
  >
  call({
    required _i6.ApiConventionsEnrollmentsPostBodyRequestBody body,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.executeAsync(
      cancellation: cancellation,
      prepare: () async => _i1.HttpOperationRequest(
        method: 'POST',
        path: _path(),
        query: null,
        data: await _data(body: body),
        options: _options(body: body),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path() {
    return [r'api', r'conventions', r'enrollments', r''];
  }

  _i7.Future<_i3.Object?> _data({
    required _i6.ApiConventionsEnrollmentsPostBodyRequestBody body,
  }) async {
    return switch (body) {
      final _i6.ApiConventionsEnrollmentsPostBodyRequestBodyJson value =>
        _i8.utf8.encode(_i8.jsonEncode(value.value.toJson())),
      final _i6.ApiConventionsEnrollmentsPostBodyRequestBodyXWwwFormUrlencoded
      value =>
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
      final _i6.ApiConventionsEnrollmentsPostBodyRequestBodyFormData value =>
        await () async {
          final _$multipartFiles = <_i5.MultipartFile>[];
          _$multipartFiles.add(
            _i5.MultipartFile.fromBytes(
              (r'convention_id').replaceAll(r'\', r'\\'),
              _i8.utf8.encode(value.value.conventionId.toString()),
              contentType: _i5.MediaType.parse(r'text/plain'),
            ),
          );
          if (value.value.setActive != null) {
            _$multipartFiles.add(
              _i5.MultipartFile.fromBytes(
                (r'set_active').replaceAll(r'\', r'\\'),
                _i8.utf8.encode(value.value.setActive!.toString()),
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
    };
  }

  _i3.Map<_i3.String, _i3.String> _options({
    required _i6.ApiConventionsEnrollmentsPostBodyRequestBody body,
  }) {
    final _$contentType = switch (body) {
      _i6.ApiConventionsEnrollmentsPostBodyRequestBodyJson _ =>
        r'application/json',

      _i6.ApiConventionsEnrollmentsPostBodyRequestBodyXWwwFormUrlencoded _ =>
        r'application/x-www-form-urlencoded',

      _i6.ApiConventionsEnrollmentsPostBodyRequestBodyFormData _ => null,
    };
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    if (_$contentType != null) {
      _$headers[r'Content-Type'] = _$contentType;
    }
    return _$headers;
  }

  _i2.ConventionsEnrollmentsCreateResponse _parseResponse(
    _i5.Response response,
  ) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i9.ConventionEnrollment.fromJson(_$json);
        return _i2.ConventionsEnrollmentsCreateResponse200(body: _$body);
      case (201, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i9.ConventionEnrollment.fromJson(_$json);
        return _i2.ConventionsEnrollmentsCreateResponse201(body: _$body);
      case (400, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i10.ApiConventionsEnrollmentsPost400BodyModel.fromJson(
          _$json,
        );
        return _i2.ConventionsEnrollmentsCreateResponse400(body: _$body);
      case (401, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i11.ApiConventionsEnrollmentsPost401BodyModel.fromJson(
          _$json,
        );
        return _i2.ConventionsEnrollmentsCreateResponse401(body: _$body);
      case (403, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i12.ApiConventionsEnrollmentsPost403BodyModel.fromJson(
          _$json,
        );
        return _i2.ConventionsEnrollmentsCreateResponse403(body: _$body);
      case (404, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i13.ApiConventionsEnrollmentsPost404BodyModel.fromJson(
          _$json,
        );
        return _i2.ConventionsEnrollmentsCreateResponse404(body: _$body);
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
