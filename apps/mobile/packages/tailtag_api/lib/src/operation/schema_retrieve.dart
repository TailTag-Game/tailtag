// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i8;
import 'dart:core' as _i3;

import 'package:http/http.dart' as _i5;
import 'package:tailtag_api/src/model/api_schema_parameters_model.dart' as _i7;
import 'package:tailtag_api/src/model/api_schema_parameters_model2.dart' as _i6;
import 'package:tailtag_api/src/operation/http_operation.dart' as _i1;
import 'package:tailtag_api/src/response/api_schema_get200_response.dart'
    as _i2;
import 'package:tonik_util/tonik_util.dart' as _i4;

final class SchemaRetrieve
    extends _i1.HttpOperation<_i2.ApiSchemaGet200Response> {
  SchemaRetrieve(super.baseUrl, super.clientAccessor);

  _i3.Future<_i4.TonikResult<_i2.ApiSchemaGet200Response, _i5.Response>> call({
    _i6.ApiSchemaParametersModel2? format,
    _i7.ApiSchemaParametersModel? lang,
    _i4.TonikCancellation? cancellation,
  }) {
    return this.execute(
      cancellation: cancellation,
      prepare: () => _i1.HttpOperationRequest(
        method: 'GET',
        path: _path(),
        query: _queryParameters(format: format, lang: lang),
        data: _data(),
        options: _options(),
      ),
      decode: _parseResponse,
    );
  }

  _i3.List<_i3.String> _path() {
    return [r'api', r'schema', r''];
  }

  _i3.Object? _data() {
    return null;
  }

  _i3.String? _queryParameters({
    _i6.ApiSchemaParametersModel2? format,
    _i7.ApiSchemaParametersModel? lang,
  }) {
    final _$entries = <_i4.ParameterEntry>[];
    if (format != null) {
      _$entries.addAll(
        format.toForm(
          r'format',
          explode: true,
          allowEmpty: false,
          textEncoding: _i8.utf8,
        ),
      );
    }
    if (lang != null) {
      _$entries.addAll(
        lang.toForm(
          r'lang',
          explode: true,
          allowEmpty: false,
          textEncoding: _i8.utf8,
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
    _$headers['Accept'] = r'application/vnd.oai.openapi,application/yaml,application/vnd.oai.openapi+json,application/json';
    return _$headers;
  }

  _i2.ApiSchemaGet200Response _parseResponse(_i5.Response response) {
    final _$mediaType = _i4.extractMediaType(response.headers['content-type']);
    switch ((response.statusCode, _$mediaType)) {
      case (200, r'application/vnd.oai.openapi'):
        final _$body = _i4.TonikFileBytes(
          _i4.decodeResponseBytes(response.bodyBytes),
        );
        return _i2.ApiSchemaGet200ResponseVndOaiOpenapi(body: _$body);
      case (200, r'application/yaml'):
        final _$body = _i4.TonikFileBytes(
          _i4.decodeResponseBytes(response.bodyBytes),
        );
        return _i2.ApiSchemaGet200ResponseYaml(body: _$body);
      case (200, r'application/vnd.oai.openapi+json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _$json.decodeJsonMap((v) => v);
        return _i2.ApiSchemaGet200ResponseVndOaiOpenapiJson(body: _$body);
      case (200, r'application/json'):
        final _$json = _i4.decodeResponseJson<_i3.Object?>(response.bodyBytes);
        final _$body = _$json.decodeJsonMap((v) => v);
        return _i2.ApiSchemaGet200ResponseJson(body: _$body);
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
