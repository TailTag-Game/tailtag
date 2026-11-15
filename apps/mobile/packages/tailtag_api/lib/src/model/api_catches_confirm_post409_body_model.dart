// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_confirm_post409_body_code_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesConfirmPost409BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesConfirmPost409BodyModel({
    required this.code,
    required this.detail,
  });

  factory ApiCatchesConfirmPost409BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesConfirmPost409BodyModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return ApiCatchesConfirmPost409BodyModel(
      code: _i4.ApiCatchesConfirmPost409BodyCodeModel.fromSimple(
        _$values[r'code'],
        explode: explode,
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'ApiCatchesConfirmPost409BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesConfirmPost409BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiCatchesConfirmPost409BodyModel');
    return ApiCatchesConfirmPost409BodyModel(
      code: _i4.ApiCatchesConfirmPost409BodyCodeModel.fromJson(_$map[r'code']),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'ApiCatchesConfirmPost409BodyModel.detail',
      ),
    );
  }

  factory ApiCatchesConfirmPost409BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'ApiCatchesConfirmPost409BodyModel',
    );
    return ApiCatchesConfirmPost409BodyModel(
      code: _i4.ApiCatchesConfirmPost409BodyCodeModel.fromForm(
        _$values[r'code'],
        explode: explode,
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'ApiCatchesConfirmPost409BodyModel.detail',
      ),
    );
  }

  final _i4.ApiCatchesConfirmPost409BodyCodeModel code;

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {r'code': this.code.toJson(), r'detail': this.detail};

  ApiCatchesConfirmPost409BodyModel Function({
    _i4.ApiCatchesConfirmPost409BodyCodeModel? code,
    _i3.String? detail,
  })
  get copyWith {
    return ({
      _i4.ApiCatchesConfirmPost409BodyCodeModel? code,
      _i3.String? detail,
    }) => ApiCatchesConfirmPost409BodyModel(
      code: code ?? this.code,
      detail: detail ?? this.detail,
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesConfirmPost409BodyModel &&
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
    _$result[r'code'] = _i1.PropertyValue.scalar(this.code.toJson());
    _$result[r'detail'] = _i1.PropertyValue.scalar(this.detail);
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
      r'Cannot uriEncode ApiCatchesConfirmPost409BodyModel: complex types cannot be URI-encoded',
    );
  }
}
