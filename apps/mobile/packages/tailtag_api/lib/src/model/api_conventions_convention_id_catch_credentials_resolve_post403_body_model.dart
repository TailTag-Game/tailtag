// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel({
    required this.detail,
  });

  factory ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'detail'},
      listKeys: {},
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel(
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel.detail',
      ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel(
      detail: _$map[r'detail'].decodeJsonString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel.detail',
      ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'detail'},
      listKeys: {},
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel(
      detail: _$values[r'detail'].decodeFormString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel.detail',
      ),
    );
  }

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {r'detail': detail};

  $$ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModelCopyWith<
    ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel &&
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
      r'Cannot uriEncode ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModelCopyWith(
    ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel value,
  ) =
      _ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModelCopyWith<
        $Res
      >;

  $Res call({_i3.String? detail});
  _i3.String get detail;
}

class _ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel
  _value;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  $Res call({_i3.Object? detail = _sentinel}) {
    return (ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel(
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
    ) as $Res);
  }
}
