// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:http/http.dart' as _i6;
import 'package:tailtag_api/src/model/api_schema_parameters_model.dart' as _i8;
import 'package:tailtag_api/src/model/api_schema_parameters_model2.dart' as _i7;
import 'package:tailtag_api/src/operation/schema_retrieve.dart' as _i2;
import 'package:tailtag_api/src/response/api_schema_get200_response.dart'
    as _i5;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i4;

class SchemaApi {
  SchemaApi(_i1.Server server)
    : _schemaRetrieve = _i2.SchemaRetrieve(server.baseUrl, () => server.client);

  final _i2.SchemaRetrieve _schemaRetrieve;

  /// OpenApi3 schema for this API. Format can be selected via content negotiation.
  ///
  /// - YAML: application/vnd.oai.openapi
  /// - JSON: application/vnd.oai.openapi+json
  ///
  /// Security:
  /// - HTTP Bearer
  _i3.Future<_i4.TonikResult<_i5.ApiSchemaGet200Response, _i6.Response>>
  schemaRetrieve({
    _i7.ApiSchemaParametersModel2? format,
    _i8.ApiSchemaParametersModel? lang,
    _i4.TonikCancellation? cancellation,
  }) async =>
      _schemaRetrieve(format: format, lang: lang, cancellation: cancellation);
}
