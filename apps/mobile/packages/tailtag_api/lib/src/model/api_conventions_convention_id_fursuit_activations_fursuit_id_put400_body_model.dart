// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:collection/collection.dart' as _i4;
import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel({
    required this.isActive,
  });

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'is_active'},
      listKeys: {r'is_active'},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel(
      isActive: _$values[r'is_active'].decodeSimpleStringList(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel.is_active',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel(
      isActive: _$map[r'is_active'].decodeJsonList<_i3.String>(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel.is_active',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'is_active'},
      listKeys: {r'is_active'},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel(
      isActive: _$values[r'is_active'].decodeFormStringList(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel.is_active',
      ),
    );
  }

  final _i3.List<_i3.String> isActive;

  @_i3.override
  _i3.Object? toJson() => {r'is_active': isActive};

  $$ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModelCopyWith<
    ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    const _$deepEquals = _i4.DeepCollectionEquality();
    return other
            is ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel &&
        _$deepEquals.equals(other.isActive, this.isActive);
  }

  @_i3.override
  _i3.int get hashCode {
    const deepEquals = _i4.DeepCollectionEquality();
    return deepEquals.hash(isActive);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'is_active'] = _i1.PropertyValue.array(isActive);
    return _$result;
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModelCopyWith(
    ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel value,
  ) =
      _ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModelCopyWith<
        $Res
      >;

  $Res call({_i3.List<_i3.String>? isActive});
  _i3.List<_i3.String> get isActive;
}

class _ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel
  _value;

  @_i3.override
  _i3.List<_i3.String> get isActive => _value.isActive;

  @_i3.override
  $Res call({_i3.Object? isActive = _sentinel}) {
    return (ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel(
      isActive: _i3.identical(isActive, _sentinel)
          ? this.isActive
          : (isActive as _i3.List<_i3.String>),
    ) as $Res);
  }
}
