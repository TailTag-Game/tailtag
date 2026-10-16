// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:collection/collection.dart' as _i4;
import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesConfirmPost400BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesConfirmPost400BodyModel({required this.payload});

  factory ApiCatchesConfirmPost400BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'payload'},
      listKeys: {r'payload'},
      context: r'ApiCatchesConfirmPost400BodyModel',
    );
    return ApiCatchesConfirmPost400BodyModel(
      payload: _$values[r'payload'].decodeSimpleStringList(
        context: r'ApiCatchesConfirmPost400BodyModel.payload',
      ),
    );
  }

  factory ApiCatchesConfirmPost400BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiCatchesConfirmPost400BodyModel');
    return ApiCatchesConfirmPost400BodyModel(
      payload: _$map[r'payload'].decodeJsonList<_i3.String>(
        context: r'ApiCatchesConfirmPost400BodyModel.payload',
      ),
    );
  }

  factory ApiCatchesConfirmPost400BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'payload'},
      listKeys: {r'payload'},
      context: r'ApiCatchesConfirmPost400BodyModel',
    );
    return ApiCatchesConfirmPost400BodyModel(
      payload: _$values[r'payload'].decodeFormStringList(
        context: r'ApiCatchesConfirmPost400BodyModel.payload',
      ),
    );
  }

  final _i3.List<_i3.String> payload;

  @_i3.override
  _i3.Object? toJson() => {r'payload': payload};

  $$ApiCatchesConfirmPost400BodyModelCopyWith<ApiCatchesConfirmPost400BodyModel>
  get copyWith => _ApiCatchesConfirmPost400BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    const _$deepEquals = _i4.DeepCollectionEquality();
    return other is ApiCatchesConfirmPost400BodyModel &&
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
      r'Cannot uriEncode ApiCatchesConfirmPost400BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiCatchesConfirmPost400BodyModelCopyWith<$Res> {
  factory $$ApiCatchesConfirmPost400BodyModelCopyWith(
    ApiCatchesConfirmPost400BodyModel value,
  ) = _ApiCatchesConfirmPost400BodyModelCopyWith<$Res>;

  $Res call({_i3.List<_i3.String>? payload});
  _i3.List<_i3.String> get payload;
}

class _ApiCatchesConfirmPost400BodyModelCopyWith<$Res>
    implements $$ApiCatchesConfirmPost400BodyModelCopyWith<$Res> {
  _ApiCatchesConfirmPost400BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesConfirmPost400BodyModel _value;

  @_i3.override
  _i3.List<_i3.String> get payload => _value.payload;

  @_i3.override
  $Res call({_i3.Object? payload = _sentinel}) {
    return (ApiCatchesConfirmPost400BodyModel(
      payload: _i3.identical(payload, _sentinel)
          ? this.payload
          : (payload as _i3.List<_i3.String>),
    ) as $Res);
  }
}
