// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i2;

@_i1.immutable
sealed class ApiSchemaGet200Response {
  const ApiSchemaGet200Response();
}

@_i1.immutable
class ApiSchemaGet200ResponseVndOaiOpenapi extends ApiSchemaGet200Response {
  const ApiSchemaGet200ResponseVndOaiOpenapi({required this.body});

  final _i2.TonikFile body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiSchemaGet200ResponseVndOaiOpenapi &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ApiSchemaGet200ResponseYaml extends ApiSchemaGet200Response {
  const ApiSchemaGet200ResponseYaml({required this.body});

  final _i2.TonikFile body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiSchemaGet200ResponseYaml && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ApiSchemaGet200ResponseVndOaiOpenapiJson extends ApiSchemaGet200Response {
  const ApiSchemaGet200ResponseVndOaiOpenapiJson({required this.body});

  final _i3.Map<_i3.String, _i3.Object?> body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiSchemaGet200ResponseVndOaiOpenapiJson &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ApiSchemaGet200ResponseJson extends ApiSchemaGet200Response {
  const ApiSchemaGet200ResponseJson({required this.body});

  final _i3.Map<_i3.String, _i3.Object?> body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiSchemaGet200ResponseJson && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
