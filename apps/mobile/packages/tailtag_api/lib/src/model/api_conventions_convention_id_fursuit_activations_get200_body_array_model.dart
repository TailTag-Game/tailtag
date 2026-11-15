// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_get200_body_array_catch_session_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel({
    required this.catchSession,
    this.fursuitId,
    this.conventionId,
    this.isActive,
    this.isEligible,
    this.activatedAt,
    this.deactivatedAt,
  });

  factory ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel: contains complex types',
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context:
          r'ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel',
    );
    return ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel(
      fursuitId: _$map[r'fursuit_id'].decodeJsonInt(
        context: r'ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.fursuit_id',
      ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.convention_id',
      ),
      isActive: _$map[r'is_active'].decodeJsonBool(
        context: r'ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.is_active',
      ),
      isEligible: _$map[r'is_eligible'].decodeJsonBool(
        context: r'ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.is_eligible',
      ),
      activatedAt: _$map[r'activated_at'].decodeJsonDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.activated_at',
      ),
      deactivatedAt: _$map[r'deactivated_at'].decodeJsonNullableDateTime(
        context: r'ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.deactivated_at',
      ),
      catchSession: _$map[r'catch_session'] == null
          ? null
          : _i4.ApiConventionsConventionIdFursuitActivationsGet200BodyArrayCatchSessionModel.fromJson(
              _$map[r'catch_session'],
            ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel: contains complex types',
    );
  }

  final _i3.int? fursuitId;

  final _i3.int? conventionId;

  final _i3.bool? isActive;

  final _i3.bool? isEligible;

  final _i3.DateTime? activatedAt;

  final _i3.DateTime? deactivatedAt;

  /// The newest catch session of this activation, or null when it has none. is_active is true only for a live session of an operational activation. An unfinalized session past expires_at reads as ended_at = expires_at and end_reason expired. The read writes nothing.
  final _i4.ApiConventionsConventionIdFursuitActivationsGet200BodyArrayCatchSessionModel?
  catchSession;

  @_i3.override
  _i3.Object? toJson() => {r'catch_session': this.catchSession?.toJson()};

  ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel Function({
    _i3.int? fursuitId,
    _i3.int? conventionId,
    _i3.bool? isActive,
    _i3.bool? isEligible,
    _i3.DateTime? activatedAt,
    _i3.DateTime? deactivatedAt,
    _i4.ApiConventionsConventionIdFursuitActivationsGet200BodyArrayCatchSessionModel?
    catchSession,
  })
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({
      _i3.Object? fursuitId = _sentinel,
      _i3.Object? conventionId = _sentinel,
      _i3.Object? isActive = _sentinel,
      _i3.Object? isEligible = _sentinel,
      _i3.Object? activatedAt = _sentinel,
      _i3.Object? deactivatedAt = _sentinel,
      _i3.Object? catchSession = _sentinel,
    }) => ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel(
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
      catchSession: _i3.identical(catchSession, _sentinel)
          ? this.catchSession
          : (catchSession
                as _i4.ApiConventionsConventionIdFursuitActivationsGet200BodyArrayCatchSessionModel?),
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel &&
        other.fursuitId == this.fursuitId &&
        other.conventionId == this.conventionId &&
        other.isActive == this.isActive &&
        other.isEligible == this.isEligible &&
        other.activatedAt == this.activatedAt &&
        other.deactivatedAt == this.deactivatedAt &&
        other.catchSession == this.catchSession;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      this.fursuitId,
      this.conventionId,
      this.isActive,
      this.isEligible,
      this.activatedAt,
      this.deactivatedAt,
      this.catchSession,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel: complex types cannot be URI-encoded',
    );
  }
}
