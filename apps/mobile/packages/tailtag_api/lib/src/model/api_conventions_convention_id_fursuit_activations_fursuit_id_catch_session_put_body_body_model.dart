// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel({
    required this.isActive,
  });

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'is_active'},
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel(
      isActive: _$values[r'is_active'].decodeSimpleBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel.is_active',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel(
      isActive: _$map[r'is_active'].decodeJsonBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel.is_active',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'is_active'},
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel(
      isActive: _$values[r'is_active'].decodeFormBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel.is_active',
      ),
    );
  }

  final _i3.bool isActive;

  @_i3.override
  _i3.Object? toJson() => {r'is_active': this.isActive};

  ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel
  Function({_i3.bool? isActive})
  get copyWith {
    return ({_i3.bool? isActive}) =>
        ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel(
          isActive: isActive ?? this.isActive,
        );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel &&
        other.isActive == this.isActive;
  }

  @_i3.override
  _i3.int get hashCode => this.isActive.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'is_active'] = _i1.PropertyValue.scalar(this.isActive.toString());
    return _$result;
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i4.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel: complex types cannot be URI-encoded',
    );
  }
}
