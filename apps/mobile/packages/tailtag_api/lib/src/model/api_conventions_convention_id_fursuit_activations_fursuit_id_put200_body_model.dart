// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel({
    this.fursuitId,
    this.conventionId,
    this.isActive,
    this.isEligible,
    this.activatedAt,
    this.deactivatedAt,
  });

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {
        r'fursuit_id',
        r'convention_id',
        r'is_active',
        r'is_eligible',
        r'activated_at',
        r'deactivated_at',
      },
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel(
      fursuitId: _$values[r'fursuit_id'].decodeSimpleInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.fursuit_id',
      ),
      conventionId: _$values[r'convention_id'].decodeSimpleInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.convention_id',
      ),
      isActive: _$values[r'is_active'].decodeSimpleBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.is_active',
      ),
      isEligible: _$values[r'is_eligible'].decodeSimpleBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.is_eligible',
      ),
      activatedAt: _$values[r'activated_at'].decodeSimpleDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.activated_at',
      ),
      deactivatedAt: _$values[r'deactivated_at'].decodeSimpleNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.deactivated_at',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel(
      fursuitId: _$map[r'fursuit_id'].decodeJsonInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.fursuit_id',
      ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.convention_id',
      ),
      isActive: _$map[r'is_active'].decodeJsonBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.is_active',
      ),
      isEligible: _$map[r'is_eligible'].decodeJsonBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.is_eligible',
      ),
      activatedAt: _$map[r'activated_at'].decodeJsonDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.activated_at',
      ),
      deactivatedAt: _$map[r'deactivated_at'].decodeJsonNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.deactivated_at',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {
        r'fursuit_id',
        r'convention_id',
        r'is_active',
        r'is_eligible',
        r'activated_at',
        r'deactivated_at',
      },
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel(
      fursuitId: _$values[r'fursuit_id'].decodeFormInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.fursuit_id',
      ),
      conventionId: _$values[r'convention_id'].decodeFormInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.convention_id',
      ),
      isActive: _$values[r'is_active'].decodeFormBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.is_active',
      ),
      isEligible: _$values[r'is_eligible'].decodeFormBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.is_eligible',
      ),
      activatedAt: _$values[r'activated_at'].decodeFormDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.activated_at',
      ),
      deactivatedAt: _$values[r'deactivated_at'].decodeFormNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel.deactivated_at',
      ),
    );
  }

  final _i3.int? fursuitId;

  final _i3.int? conventionId;

  final _i3.bool? isActive;

  final _i3.bool? isEligible;

  final _i3.DateTime? activatedAt;

  final _i3.DateTime? deactivatedAt;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModelCopyWith<
    ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel &&
        other.fursuitId == this.fursuitId &&
        other.conventionId == this.conventionId &&
        other.isActive == this.isActive &&
        other.isEligible == this.isEligible &&
        other.activatedAt == this.activatedAt &&
        other.deactivatedAt == this.deactivatedAt;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      fursuitId,
      conventionId,
      isActive,
      isEligible,
      activatedAt,
      deactivatedAt,
    ]);
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
    required _i4.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModelCopyWith(
    ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel value,
  ) =
      _ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModelCopyWith<
        $Res
      >;

  $Res call({
    _i3.int? fursuitId,
    _i3.int? conventionId,
    _i3.bool? isActive,
    _i3.bool? isEligible,
    _i3.DateTime? activatedAt,
    _i3.DateTime? deactivatedAt,
  });
  _i3.int? get fursuitId;
  _i3.int? get conventionId;
  _i3.bool? get isActive;
  _i3.bool? get isEligible;
  _i3.DateTime? get activatedAt;
  _i3.DateTime? get deactivatedAt;
}

class _ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel
  _value;

  @_i3.override
  _i3.int? get fursuitId => _value.fursuitId;

  @_i3.override
  _i3.int? get conventionId => _value.conventionId;

  @_i3.override
  _i3.bool? get isActive => _value.isActive;

  @_i3.override
  _i3.bool? get isEligible => _value.isEligible;

  @_i3.override
  _i3.DateTime? get activatedAt => _value.activatedAt;

  @_i3.override
  _i3.DateTime? get deactivatedAt => _value.deactivatedAt;

  @_i3.override
  $Res call({
    _i3.Object? fursuitId = _sentinel,
    _i3.Object? conventionId = _sentinel,
    _i3.Object? isActive = _sentinel,
    _i3.Object? isEligible = _sentinel,
    _i3.Object? activatedAt = _sentinel,
    _i3.Object? deactivatedAt = _sentinel,
  }) {
    return (ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel(
      fursuitId: _i3.identical(fursuitId, _sentinel)
          ? this.fursuitId
          : (fursuitId as _i3.int?),
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int?),
      isActive: _i3.identical(isActive, _sentinel)
          ? this.isActive
          : (isActive as _i3.bool?),
      isEligible: _i3.identical(isEligible, _sentinel)
          ? this.isEligible
          : (isEligible as _i3.bool?),
      activatedAt: _i3.identical(activatedAt, _sentinel)
          ? this.activatedAt
          : (activatedAt as _i3.DateTime?),
      deactivatedAt: _i3.identical(deactivatedAt, _sentinel)
          ? this.deactivatedAt
          : (deactivatedAt as _i3.DateTime?),
    ) as $Res);
  }
}
