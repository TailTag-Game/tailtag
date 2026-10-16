// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_get400_body_code_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesGet400BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesGet400BodyModel({required this.code, required this.detail});

  factory ApiCatchesGet400BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesGet400BodyModel',
    );
    return ApiCatchesGet400BodyModel(
      code: _i4.ApiCatchesGet400BodyCodeModel.fromSimple(
        _$values[r'code'],
        explode: explode,
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'ApiCatchesGet400BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesGet400BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiCatchesGet400BodyModel');
    return ApiCatchesGet400BodyModel(
      code: _i4.ApiCatchesGet400BodyCodeModel.fromJson(_$map[r'code']),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'ApiCatchesGet400BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesGet400BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesGet400BodyModel',
    );
    return ApiCatchesGet400BodyModel(
      code: _i4.ApiCatchesGet400BodyCodeModel.fromForm(
        _$values[r'code'],
        explode: explode,
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'ApiCatchesGet400BodyModel.detail',
      ),
    );
  }

  final _i4.ApiCatchesGet400BodyCodeModel code;

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {r'code': code.toJson(), r'detail': detail};

  $$ApiCatchesGet400BodyModelCopyWith<ApiCatchesGet400BodyModel> get copyWith =>
      _ApiCatchesGet400BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesGet400BodyModel &&
        other.code == this.code &&
        other.detail == this.detail;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([code, detail]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'code'] = _i1.PropertyValue.scalar(code.toJson());
    _$result[r'detail'] = _i1.PropertyValue.scalar(detail);
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
      r'Cannot uriEncode ApiCatchesGet400BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiCatchesGet400BodyModelCopyWith<$Res> {
  factory $$ApiCatchesGet400BodyModelCopyWith(ApiCatchesGet400BodyModel value) =
      _ApiCatchesGet400BodyModelCopyWith<$Res>;

  $Res call({_i4.ApiCatchesGet400BodyCodeModel? code, _i3.String? detail});
  _i4.ApiCatchesGet400BodyCodeModel get code;
  _i3.String get detail;
}

class _ApiCatchesGet400BodyModelCopyWith<$Res>
    implements $$ApiCatchesGet400BodyModelCopyWith<$Res> {
  _ApiCatchesGet400BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesGet400BodyModel _value;

  @_i3.override
  _i4.ApiCatchesGet400BodyCodeModel get code => _value.code;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  $Res call({_i3.Object? code = _sentinel, _i3.Object? detail = _sentinel}) {
    return (ApiCatchesGet400BodyModel(
      code: _i3.identical(code, _sentinel)
          ? this.code
          : (code as _i4.ApiCatchesGet400BodyCodeModel),
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
    ) as $Res);
  }
}
