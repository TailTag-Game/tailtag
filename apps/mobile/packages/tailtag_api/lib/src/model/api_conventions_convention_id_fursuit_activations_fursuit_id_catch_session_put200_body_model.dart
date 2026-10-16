// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_session_put200_body_end_reason_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel({
    this.fursuitId,
    this.conventionId,
    this.isActive,
    this.startedAt,
    this.expiresAt,
    this.endedAt,
    this.endReason,
  });

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.fromSimple(
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
        r'started_at',
        r'expires_at',
        r'ended_at',
        r'end_reason',
      },
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel(
      fursuitId: _$values[r'fursuit_id'].decodeSimpleInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.fursuit_id',
      ),
      conventionId: _$values[r'convention_id'].decodeSimpleInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.convention_id',
      ),
      isActive: _$values[r'is_active'].decodeSimpleBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.is_active',
      ),
      startedAt: _$values[r'started_at'].decodeSimpleNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.started_at',
      ),
      expiresAt: _$values[r'expires_at'].decodeSimpleNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.expires_at',
      ),
      endedAt: _$values[r'ended_at'].decodeSimpleNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.ended_at',
      ),
      endReason: _$values[r'end_reason'] == null
          ? null
          : _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyEndReasonModel.fromSimple(
              _$values[r'end_reason'],
              explode: explode,
            ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel(
      fursuitId: _$map[r'fursuit_id'].decodeJsonInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.fursuit_id',
      ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.convention_id',
      ),
      isActive: _$map[r'is_active'].decodeJsonBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.is_active',
      ),
      startedAt: _$map[r'started_at'].decodeJsonNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.started_at',
      ),
      expiresAt: _$map[r'expires_at'].decodeJsonNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.expires_at',
      ),
      endedAt: _$map[r'ended_at'].decodeJsonNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.ended_at',
      ),
      endReason: _$map[r'end_reason'] == null
          ? null
          : _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyEndReasonModel.fromJson(
              _$map[r'end_reason'],
            ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.fromForm(
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
        r'started_at',
        r'expires_at',
        r'ended_at',
        r'end_reason',
      },
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel(
      fursuitId: _$values[r'fursuit_id'].decodeFormInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.fursuit_id',
      ),
      conventionId: _$values[r'convention_id'].decodeFormInt(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.convention_id',
      ),
      isActive: _$values[r'is_active'].decodeFormBool(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.is_active',
      ),
      startedAt: _$values[r'started_at'].decodeFormNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.started_at',
      ),
      expiresAt: _$values[r'expires_at'].decodeFormNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.expires_at',
      ),
      endedAt: _$values[r'ended_at'].decodeFormNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel.ended_at',
      ),
      endReason: _$values[r'end_reason'] == null
          ? null
          : _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyEndReasonModel.fromForm(
              _$values[r'end_reason'],
              explode: explode,
            ),
    );
  }

  final _i3.int? fursuitId;

  final _i3.int? conventionId;

  final _i3.bool? isActive;

  final _i3.DateTime? startedAt;

  final _i3.DateTime? expiresAt;

  final _i3.DateTime? endedAt;

  final _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyEndReasonModel?
  endReason;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModelCopyWith<
    ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel &&
        other.fursuitId == this.fursuitId &&
        other.conventionId == this.conventionId &&
        other.isActive == this.isActive &&
        other.startedAt == this.startedAt &&
        other.expiresAt == this.expiresAt &&
        other.endedAt == this.endedAt &&
        other.endReason == this.endReason;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      fursuitId,
      conventionId,
      isActive,
      startedAt,
      expiresAt,
      endedAt,
      endReason,
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
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModelCopyWith(
    ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel
    value,
  ) =
      _ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModelCopyWith<
        $Res
      >;

  $Res call({
    _i3.int? fursuitId,
    _i3.int? conventionId,
    _i3.bool? isActive,
    _i3.DateTime? startedAt,
    _i3.DateTime? expiresAt,
    _i3.DateTime? endedAt,
    _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyEndReasonModel?
    endReason,
  });
  _i3.int? get fursuitId;
  _i3.int? get conventionId;
  _i3.bool? get isActive;
  _i3.DateTime? get startedAt;
  _i3.DateTime? get expiresAt;
  _i3.DateTime? get endedAt;
  _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyEndReasonModel?
  get endReason;
}

class _ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel
  _value;

  @_i3.override
  _i3.int? get fursuitId => _value.fursuitId;

  @_i3.override
  _i3.int? get conventionId => _value.conventionId;

  @_i3.override
  _i3.bool? get isActive => _value.isActive;

  @_i3.override
  _i3.DateTime? get startedAt => _value.startedAt;

  @_i3.override
  _i3.DateTime? get expiresAt => _value.expiresAt;

  @_i3.override
  _i3.DateTime? get endedAt => _value.endedAt;

  @_i3.override
  _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyEndReasonModel?
  get endReason => _value.endReason;

  @_i3.override
  $Res call({
    _i3.Object? fursuitId = _sentinel,
    _i3.Object? conventionId = _sentinel,
    _i3.Object? isActive = _sentinel,
    _i3.Object? startedAt = _sentinel,
    _i3.Object? expiresAt = _sentinel,
    _i3.Object? endedAt = _sentinel,
    _i3.Object? endReason = _sentinel,
  }) {
    return (ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel(
      fursuitId: _i3.identical(fursuitId, _sentinel)
          ? this.fursuitId
          : (fursuitId as _i3.int?),
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int?),
      isActive: _i3.identical(isActive, _sentinel)
          ? this.isActive
          : (isActive as _i3.bool?),
      startedAt: _i3.identical(startedAt, _sentinel)
          ? this.startedAt
          : (startedAt as _i3.DateTime?),
      expiresAt: _i3.identical(expiresAt, _sentinel)
          ? this.expiresAt
          : (expiresAt as _i3.DateTime?),
      endedAt: _i3.identical(endedAt, _sentinel)
          ? this.endedAt
          : (endedAt as _i3.DateTime?),
      endReason: _i3.identical(endReason, _sentinel)
          ? this.endReason
          : (endReason
                as _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyEndReasonModel?),
    ) as $Res);
  }
}
