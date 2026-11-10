// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesPreviewPost404BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesPreviewPost404BodyModel({
    required this.code,
    required this.detail,
  });

  factory ApiCatchesPreviewPost404BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesPreviewPost404BodyModel',
    );
    return ApiCatchesPreviewPost404BodyModel(
      code: _$values[r'code'].decodeSimpleString(
        context: r'ApiCatchesPreviewPost404BodyModel.code',
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'ApiCatchesPreviewPost404BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesPreviewPost404BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiCatchesPreviewPost404BodyModel');
    return ApiCatchesPreviewPost404BodyModel(
      code: _$map[r'code'].decodeJsonString(
        context: r'ApiCatchesPreviewPost404BodyModel.code',
      ),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'ApiCatchesPreviewPost404BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesPreviewPost404BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesPreviewPost404BodyModel',
    );
    return ApiCatchesPreviewPost404BodyModel(
      code: _$values[r'code'].decodeFormString(
        context: r'ApiCatchesPreviewPost404BodyModel.code',
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'ApiCatchesPreviewPost404BodyModel.detail',
      ),
    );
  }

  final _i3.String code;

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {r'code': code, r'detail': detail};

  $$ApiCatchesPreviewPost404BodyModelCopyWith<ApiCatchesPreviewPost404BodyModel>
  get copyWith => _ApiCatchesPreviewPost404BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesPreviewPost404BodyModel &&
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
    _$result[r'code'] = _i1.PropertyValue.scalar(code);
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
      r'Cannot uriEncode ApiCatchesPreviewPost404BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiCatchesPreviewPost404BodyModelCopyWith<$Res> {
  factory $$ApiCatchesPreviewPost404BodyModelCopyWith(
    ApiCatchesPreviewPost404BodyModel value,
  ) = _ApiCatchesPreviewPost404BodyModelCopyWith<$Res>;

  $Res call({_i3.String? code, _i3.String? detail});
  _i3.String get code;
  _i3.String get detail;
}

class _ApiCatchesPreviewPost404BodyModelCopyWith<$Res>
    implements $$ApiCatchesPreviewPost404BodyModelCopyWith<$Res> {
  _ApiCatchesPreviewPost404BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesPreviewPost404BodyModel _value;

  @_i3.override
  _i3.String get code => _value.code;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  $Res call({_i3.Object? code = _sentinel, _i3.Object? detail = _sentinel}) {
    return (ApiCatchesPreviewPost404BodyModel(
      code: _i3.identical(code, _sentinel) ? this.code : (code as _i3.String),
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
    ) as $Res);
  }
}
