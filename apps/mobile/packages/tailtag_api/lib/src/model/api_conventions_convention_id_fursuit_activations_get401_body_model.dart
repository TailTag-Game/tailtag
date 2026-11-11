// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdFursuitActivationsGet401BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdFursuitActivationsGet401BodyModel({
    required this.detail,
  });

  factory ApiConventionsConventionIdFursuitActivationsGet401BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'detail'},
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsGet401BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsGet401BodyModel(
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'ApiConventionsConventionIdFursuitActivationsGet401BodyModel.detail',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsGet401BodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsConventionIdFursuitActivationsGet401BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsGet401BodyModel(
      detail: _$map[r'detail'].decodeJsonString(
        context: r'ApiConventionsConventionIdFursuitActivationsGet401BodyModel.detail',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsGet401BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'detail'},
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsGet401BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsGet401BodyModel(
      detail: _$values[r'detail'].decodeFormString(
        context: r'ApiConventionsConventionIdFursuitActivationsGet401BodyModel.detail',
      ),
    );
  }

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {r'detail': detail};

  $$ApiConventionsConventionIdFursuitActivationsGet401BodyModelCopyWith<
    ApiConventionsConventionIdFursuitActivationsGet401BodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdFursuitActivationsGet401BodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdFursuitActivationsGet401BodyModel &&
        other.detail == this.detail;
  }

  @_i3.override
  _i3.int get hashCode => detail.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'detail'] = _i1.PropertyValue.scalar(detail);
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
      r'Cannot uriEncode ApiConventionsConventionIdFursuitActivationsGet401BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdFursuitActivationsGet401BodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdFursuitActivationsGet401BodyModelCopyWith(
    ApiConventionsConventionIdFursuitActivationsGet401BodyModel value,
  ) =
      _ApiConventionsConventionIdFursuitActivationsGet401BodyModelCopyWith<
        $Res
      >;

  $Res call({_i3.String? detail});
  _i3.String get detail;
}

class _ApiConventionsConventionIdFursuitActivationsGet401BodyModelCopyWith<$Res>
    implements
        $$ApiConventionsConventionIdFursuitActivationsGet401BodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdFursuitActivationsGet401BodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdFursuitActivationsGet401BodyModel _value;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  $Res call({_i3.Object? detail = _sentinel}) {
    return (ApiConventionsConventionIdFursuitActivationsGet401BodyModel(
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
    ) as $Res);
  }
}
