// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel({
    required this.isActive,
  });

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'is_active'},
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel(
      isActive: _$values[r'is_active'].decodeSimpleBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel.is_active',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel(
      isActive: _$map[r'is_active'].decodeJsonBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel.is_active',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'is_active'},
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel(
      isActive: _$values[r'is_active'].decodeFormBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel.is_active',
      ),
    );
  }

  final _i3.bool isActive;

  @_i3.override
  _i3.Object? toJson() => {r'is_active': isActive};

  $$ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModelCopyWith<
    ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel &&
        other.isActive == this.isActive;
  }

  @_i3.override
  _i3.int get hashCode => isActive.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'is_active'] = _i1.PropertyValue.scalar(isActive.toString());
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
      r'Cannot uriEncode ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModelCopyWith(
    ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel value,
  ) =
      _ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModelCopyWith<
        $Res
      >;

  $Res call({_i3.bool? isActive});
  _i3.bool get isActive;
}

class _ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel
  _value;

  @_i3.override
  _i3.bool get isActive => _value.isActive;

  @_i3.override
  $Res call({_i3.Object? isActive = _sentinel}) {
    return (ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel(
      isActive: _i3.identical(isActive, _sentinel)
          ? this.isActive
          : (isActive as _i3.bool),
    ) as $Res);
  }
}
