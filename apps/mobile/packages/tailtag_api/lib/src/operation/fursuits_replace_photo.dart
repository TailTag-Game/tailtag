// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:async' as _i7;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_fursuits_id_photo_put200_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_fursuits_id_photo_put_body_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response_wrapper/fursuits_replace_photo_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class FursuitsReplacePhoto
    extends _i1.HttpOperation<_i2.FursuitsReplacePhotoResponse> {
  FursuitsReplacePhoto(super.baseUrl, super.clientAccessor);

  _i3.Future<_i4.TonikResult<_i2.FursuitsReplacePhotoResponse, _i5.Response>>
  call({
    _i6.ApiFursuitsIdPhotoPutBodyBodyModel? body,
    required _i3.int id,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.executeAsync(
      cancellation: cancellation,
      prepare: () async => _i1.HttpOperationRequest(
        method: 'PUT',
        path: _path(id: id),
        query: null,
        data: await _data(body: body),
        options: _options(),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path({required _i3.int id}) {
    return [
      r'api',
      r'fursuits',
      id.toSimple(explode: false, allowEmpty: false),
      r'photo',
      r'',
    ];
  }

  _i7.Future<_i3.Object?> _data({
    _i6.ApiFursuitsIdPhotoPutBodyBodyModel? body,
  }) async {
    if (body == null) return null;
    final _$multipartFiles = <_i5.MultipartFile>[];
    _$multipartFiles.add(
      _i5.MultipartFile.fromBytes(
        (r'photo').replaceAll(r'\', r'\\'),
        body.photo.toBytes(),
        filename: (body.photo.fileName ?? r'photo').replaceAll(r'\', r'\\'),
        contentType: _i5.MediaType.parse(r'application/octet-stream'),
      ),
    );
    if (_$multipartFiles.isEmpty) {
      throw _i4.EncodingException(
        r'Multipart request body must contain at least one part.',
      );
    }
    return _$multipartFiles;
  }

  _i3.Map<_i3.String, _i3.String> _options() {
    final _$headers = <_i3.String, _i3.String>{};
    _$headers['Accept'] = r'application/json';
    return _$headers;
  }

  _i2.FursuitsReplacePhotoResponse _parseResponse(_i5.Response response) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _i8.ApiFursuitsIdPhotoPut200BodyModel.fromJson(_$json);
        return _i2.FursuitsReplacePhotoResponse200(body: _$body);
      case (400, _):
        return _i2.FursuitsReplacePhotoResponse400();
      case (401, _):
        return _i2.FursuitsReplacePhotoResponse401();
      case (403, _):
        return _i2.FursuitsReplacePhotoResponse403();
      case (404, _):
        return _i2.FursuitsReplacePhotoResponse404();
      case (405, _):
        return _i2.FursuitsReplacePhotoResponse405();
      case (500, _):
        return _i2.FursuitsReplacePhotoResponse500();
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
