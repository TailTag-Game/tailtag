// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:collection/collection.dart' as _i4;
import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel({
    required this.payload,
  });

  factory ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'payload'},
      listKeys: {r'payload'},
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel(
      payload: _$values[r'payload'].decodeSimpleStringList(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel.payload',
      ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel(
      payload: _$map[r'payload'].decodeJsonList<_i3.String>(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel.payload',
      ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'payload'},
      listKeys: {r'payload'},
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel(
      payload: _$values[r'payload'].decodeFormStringList(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel.payload',
      ),
    );
  }

  final _i3.List<_i3.String> payload;

  @_i3.override
  _i3.Object? toJson() => {r'payload': payload};

  $$ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModelCopyWith<
    ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    const _$deepEquals = _i4.DeepCollectionEquality();
    return other
            is ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel &&
        _$deepEquals.equals(other.payload, this.payload);
  }

  @_i3.override
  _i3.int get hashCode {
    const deepEquals = _i4.DeepCollectionEquality();
    return deepEquals.hash(payload);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'payload'] = _i1.PropertyValue.array(payload);
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
      r'Cannot uriEncode ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModelCopyWith(
    ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel value,
  ) =
      _ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModelCopyWith<
        $Res
      >;

  $Res call({_i3.List<_i3.String>? payload});
  _i3.List<_i3.String> get payload;
}

class _ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel
  _value;

  @_i3.override
  _i3.List<_i3.String> get payload => _value.payload;

  @_i3.override
  $Res call({_i3.Object? payload = _sentinel}) {
    return (ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel(
      payload: _i3.identical(payload, _sentinel)
          ? this.payload
          : (payload as _i3.List<_i3.String>),
    ) as $Res);
  }
}
