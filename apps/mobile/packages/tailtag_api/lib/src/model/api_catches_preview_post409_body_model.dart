// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesPreviewPost409BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesPreviewPost409BodyModel({
    required this.code,
    required this.detail,
  });

  factory ApiCatchesPreviewPost409BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesPreviewPost409BodyModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return ApiCatchesPreviewPost409BodyModel(
      code: _$values[r'code'].decodeSimpleString(
        context: r'ApiCatchesPreviewPost409BodyModel.code',
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'ApiCatchesPreviewPost409BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesPreviewPost409BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiCatchesPreviewPost409BodyModel');
    return ApiCatchesPreviewPost409BodyModel(
      code: _$map[r'code'].decodeJsonString(
        context: r'ApiCatchesPreviewPost409BodyModel.code',
      ),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'ApiCatchesPreviewPost409BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesPreviewPost409BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesPreviewPost409BodyModel',
    );
    return ApiCatchesPreviewPost409BodyModel(
      code: _$values[r'code'].decodeFormString(
        context: r'ApiCatchesPreviewPost409BodyModel.code',
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'ApiCatchesPreviewPost409BodyModel.detail',
      ),
    );
  }

  final _i3.String code;

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {r'code': this.code, r'detail': this.detail};

  ApiCatchesPreviewPost409BodyModel Function({
    _i3.String? code,
    _i3.String? detail,
  })
  get copyWith {
    return ({_i3.String? code, _i3.String? detail}) =>
        ApiCatchesPreviewPost409BodyModel(
          code: code ?? this.code,
          detail: detail ?? this.detail,
        );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesPreviewPost409BodyModel &&
        other.code == this.code &&
        other.detail == this.detail;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([this.code, this.detail]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'code'] = _i1.PropertyValue.scalar(this.code);
    _$result[r'detail'] = _i1.PropertyValue.scalar(this.detail);
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
      r'Cannot uriEncode ApiCatchesPreviewPost409BodyModel: complex types cannot be URI-encoded',
    );
  }
}
