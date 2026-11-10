// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_preview_post500_body_code_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesPreviewPost500BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesPreviewPost500BodyModel({
    required this.code,
    required this.detail,
  });

  factory ApiCatchesPreviewPost500BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesPreviewPost500BodyModel',
    );
    return ApiCatchesPreviewPost500BodyModel(
      code: _i4.ApiCatchesPreviewPost500BodyCodeModel.fromSimple(
        _$values[r'code'],
        explode: explode,
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'ApiCatchesPreviewPost500BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesPreviewPost500BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiCatchesPreviewPost500BodyModel');
    return ApiCatchesPreviewPost500BodyModel(
      code: _i4.ApiCatchesPreviewPost500BodyCodeModel.fromJson(_$map[r'code']),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'ApiCatchesPreviewPost500BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesPreviewPost500BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesPreviewPost500BodyModel',
    );
    return ApiCatchesPreviewPost500BodyModel(
      code: _i4.ApiCatchesPreviewPost500BodyCodeModel.fromForm(
        _$values[r'code'],
        explode: explode,
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'ApiCatchesPreviewPost500BodyModel.detail',
      ),
    );
  }

  final _i4.ApiCatchesPreviewPost500BodyCodeModel code;

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {r'code': code.toJson(), r'detail': detail};

  $$ApiCatchesPreviewPost500BodyModelCopyWith<ApiCatchesPreviewPost500BodyModel>
  get copyWith => _ApiCatchesPreviewPost500BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesPreviewPost500BodyModel &&
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
      r'Cannot uriEncode ApiCatchesPreviewPost500BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiCatchesPreviewPost500BodyModelCopyWith<$Res> {
  factory $$ApiCatchesPreviewPost500BodyModelCopyWith(
    ApiCatchesPreviewPost500BodyModel value,
  ) = _ApiCatchesPreviewPost500BodyModelCopyWith<$Res>;

  $Res call({
    _i4.ApiCatchesPreviewPost500BodyCodeModel? code,
    _i3.String? detail,
  });
  _i4.ApiCatchesPreviewPost500BodyCodeModel get code;
  _i3.String get detail;
}

class _ApiCatchesPreviewPost500BodyModelCopyWith<$Res>
    implements $$ApiCatchesPreviewPost500BodyModelCopyWith<$Res> {
  _ApiCatchesPreviewPost500BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesPreviewPost500BodyModel _value;

  @_i3.override
  _i4.ApiCatchesPreviewPost500BodyCodeModel get code => _value.code;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  $Res call({_i3.Object? code = _sentinel, _i3.Object? detail = _sentinel}) {
    return (ApiCatchesPreviewPost500BodyModel(
      code: _i3.identical(code, _sentinel)
          ? this.code
          : (code as _i4.ApiCatchesPreviewPost500BodyCodeModel),
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
    ) as $Res);
  }
}
