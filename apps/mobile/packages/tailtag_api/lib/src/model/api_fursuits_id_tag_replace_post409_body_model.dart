// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post409_body_code_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post409_body_current_model.dart'
    as _i5;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiFursuitsIdTagReplacePost409BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsIdTagReplacePost409BodyModel({
    required this.code,
    required this.detail,
    this.current,
  });

  factory ApiFursuitsIdTagReplacePost409BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ApiFursuitsIdTagReplacePost409BodyModel: contains complex types',
    );
  }

  factory ApiFursuitsIdTagReplacePost409BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiFursuitsIdTagReplacePost409BodyModel',
    );
    return ApiFursuitsIdTagReplacePost409BodyModel(
      code: _i4.ApiFursuitsIdTagReplacePost409BodyCodeModel.fromJson(
        _$map[r'code'],
      ),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'ApiFursuitsIdTagReplacePost409BodyModel.detail',
      ),
      current: _$map[r'current'] == null
          ? null
          : _i5.ApiFursuitsIdTagReplacePost409BodyCurrentModel.fromJson(
              _$map[r'current'],
            ),
    );
  }

  factory ApiFursuitsIdTagReplacePost409BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ApiFursuitsIdTagReplacePost409BodyModel: contains complex types',
    );
  }

  final _i4.ApiFursuitsIdTagReplacePost409BodyCodeModel code;

  final _i3.String detail;

  /// Present only for tag_version_conflict. It never carries a payload. State none means the suit never had a tag.
  final _i5.ApiFursuitsIdTagReplacePost409BodyCurrentModel? current;

  @_i3.override
  _i3.Object? toJson() => {
    r'code': code.toJson(),
    r'detail': detail,
    if (current != null) r'current': current?.toJson(),
  };

  $$ApiFursuitsIdTagReplacePost409BodyModelCopyWith<
    ApiFursuitsIdTagReplacePost409BodyModel
  >
  get copyWith => _ApiFursuitsIdTagReplacePost409BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsIdTagReplacePost409BodyModel &&
        other.code == this.code &&
        other.detail == this.detail &&
        other.current == this.current;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([code, detail, current]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for ApiFursuitsIdTagReplacePost409BodyModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiFursuitsIdTagReplacePost409BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiFursuitsIdTagReplacePost409BodyModelCopyWith<$Res> {
  factory $$ApiFursuitsIdTagReplacePost409BodyModelCopyWith(
    ApiFursuitsIdTagReplacePost409BodyModel value,
  ) = _ApiFursuitsIdTagReplacePost409BodyModelCopyWith<$Res>;

  $Res call({
    _i4.ApiFursuitsIdTagReplacePost409BodyCodeModel? code,
    _i3.String? detail,
    _i5.ApiFursuitsIdTagReplacePost409BodyCurrentModel? current,
  });
  _i4.ApiFursuitsIdTagReplacePost409BodyCodeModel get code;
  _i3.String get detail;
  _i5.ApiFursuitsIdTagReplacePost409BodyCurrentModel? get current;
}

class _ApiFursuitsIdTagReplacePost409BodyModelCopyWith<$Res>
    implements $$ApiFursuitsIdTagReplacePost409BodyModelCopyWith<$Res> {
  _ApiFursuitsIdTagReplacePost409BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiFursuitsIdTagReplacePost409BodyModel _value;

  @_i3.override
  _i4.ApiFursuitsIdTagReplacePost409BodyCodeModel get code => _value.code;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  _i5.ApiFursuitsIdTagReplacePost409BodyCurrentModel? get current =>
      _value.current;

  @_i3.override
  $Res call({
    _i3.Object? code = _sentinel,
    _i3.Object? detail = _sentinel,
    _i3.Object? current = _sentinel,
  }) {
    return (ApiFursuitsIdTagReplacePost409BodyModel(
      code: _i3.identical(code, _sentinel)
          ? this.code
          : (code as _i4.ApiFursuitsIdTagReplacePost409BodyCodeModel),
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
      current: _i3.identical(current, _sentinel)
          ? this.current
          : (current as _i5.ApiFursuitsIdTagReplacePost409BodyCurrentModel?),
    ) as $Res);
  }
}
