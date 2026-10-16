// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post200_body_fursuit_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel({
    this.conventionId,
    this.fursuit,
  });

  factory ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel: contains complex types',
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel(
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel.convention_id',
      ),
      fursuit:
          _i4.ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.fromJson(
            _$map[r'fursuit'],
          ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel: contains complex types',
    );
  }

  final _i3.int? conventionId;

  final _i4.ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel?
  fursuit;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModelCopyWith<
    ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel &&
        other.conventionId == this.conventionId &&
        other.fursuit == this.fursuit;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([conventionId, fursuit]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    return <_i3.String, _i1.PropertyValue>{};
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModelCopyWith(
    ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel value,
  ) =
      _ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModelCopyWith<
        $Res
      >;

  $Res call({
    _i3.int? conventionId,
    _i4.ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel?
    fursuit,
  });
  _i3.int? get conventionId;
  _i4.ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel?
  get fursuit;
}

class _ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel
  _value;

  @_i3.override
  _i3.int? get conventionId => _value.conventionId;

  @_i3.override
  _i4.ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel?
  get fursuit => _value.fursuit;

  @_i3.override
  $Res call({
    _i3.Object? conventionId = _sentinel,
    _i3.Object? fursuit = _sentinel,
  }) {
    return (ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel(
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int?),
      fursuit: _i3.identical(fursuit, _sentinel)
          ? this.fursuit
          : (fursuit
                as _i4.ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel?),
    ) as $Res);
  }
}
