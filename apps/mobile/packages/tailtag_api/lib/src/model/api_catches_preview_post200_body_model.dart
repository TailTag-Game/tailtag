// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_preview_post200_body_fursuit_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesPreviewPost200BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesPreviewPost200BodyModel({
    required this.fursuit,
    required this.conventionId,
  });

  factory ApiCatchesPreviewPost200BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ApiCatchesPreviewPost200BodyModel: contains complex types',
    );
  }

  factory ApiCatchesPreviewPost200BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiCatchesPreviewPost200BodyModel');
    return ApiCatchesPreviewPost200BodyModel(
      fursuit: _i4.ApiCatchesPreviewPost200BodyFursuitModel.fromJson(
        _$map[r'fursuit'],
      ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'ApiCatchesPreviewPost200BodyModel.convention_id',
      ),
    );
  }

  factory ApiCatchesPreviewPost200BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ApiCatchesPreviewPost200BodyModel: contains complex types',
    );
  }

  final _i4.ApiCatchesPreviewPost200BodyFursuitModel fursuit;

  final _i3.int conventionId;

  @_i3.override
  _i3.Object? toJson() => {
    r'fursuit': fursuit.toJson(),
    r'convention_id': conventionId,
  };

  $$ApiCatchesPreviewPost200BodyModelCopyWith<ApiCatchesPreviewPost200BodyModel>
  get copyWith => _ApiCatchesPreviewPost200BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesPreviewPost200BodyModel &&
        other.fursuit == this.fursuit &&
        other.conventionId == this.conventionId;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([fursuit, conventionId]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for ApiCatchesPreviewPost200BodyModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiCatchesPreviewPost200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiCatchesPreviewPost200BodyModelCopyWith<$Res> {
  factory $$ApiCatchesPreviewPost200BodyModelCopyWith(
    ApiCatchesPreviewPost200BodyModel value,
  ) = _ApiCatchesPreviewPost200BodyModelCopyWith<$Res>;

  $Res call({
    _i4.ApiCatchesPreviewPost200BodyFursuitModel? fursuit,
    _i3.int? conventionId,
  });
  _i4.ApiCatchesPreviewPost200BodyFursuitModel get fursuit;
  _i3.int get conventionId;
}

class _ApiCatchesPreviewPost200BodyModelCopyWith<$Res>
    implements $$ApiCatchesPreviewPost200BodyModelCopyWith<$Res> {
  _ApiCatchesPreviewPost200BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesPreviewPost200BodyModel _value;

  @_i3.override
  _i4.ApiCatchesPreviewPost200BodyFursuitModel get fursuit => _value.fursuit;

  @_i3.override
  _i3.int get conventionId => _value.conventionId;

  @_i3.override
  $Res call({
    _i3.Object? fursuit = _sentinel,
    _i3.Object? conventionId = _sentinel,
  }) {
    return (ApiCatchesPreviewPost200BodyModel(
      fursuit: _i3.identical(fursuit, _sentinel)
          ? this.fursuit
          : (fursuit as _i4.ApiCatchesPreviewPost200BodyFursuitModel),
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int),
    ) as $Res);
  }
}
