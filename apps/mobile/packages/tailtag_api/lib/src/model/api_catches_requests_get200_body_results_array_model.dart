// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_requests_get200_body_results_array_fursuit_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_catches_requests_get200_body_results_array_state_model.dart'
    as _i5;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesRequestsGet200BodyResultsArrayModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesRequestsGet200BodyResultsArrayModel({
    required this.id,
    required this.fursuit,
    required this.conventionId,
    required this.state,
    required this.requestedAt,
    required this.reviewDeadlineAt,
  });

  factory ApiCatchesRequestsGet200BodyResultsArrayModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ApiCatchesRequestsGet200BodyResultsArrayModel: contains complex types',
    );
  }

  factory ApiCatchesRequestsGet200BodyResultsArrayModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiCatchesRequestsGet200BodyResultsArrayModel',
    );
    return ApiCatchesRequestsGet200BodyResultsArrayModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'ApiCatchesRequestsGet200BodyResultsArrayModel.id',
      ),
      fursuit:
          _i4.ApiCatchesRequestsGet200BodyResultsArrayFursuitModel.fromJson(
            _$map[r'fursuit'],
          ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'ApiCatchesRequestsGet200BodyResultsArrayModel.convention_id',
      ),
      state: _i5.ApiCatchesRequestsGet200BodyResultsArrayStateModel.fromJson(
        _$map[r'state'],
      ),
      requestedAt: _$map[r'requested_at'].decodeJsonDateTime(
        context: r'ApiCatchesRequestsGet200BodyResultsArrayModel.requested_at',
      ),
      reviewDeadlineAt: _$map[r'review_deadline_at'].decodeJsonDateTime(
        context:
            r'ApiCatchesRequestsGet200BodyResultsArrayModel.review_deadline_at',
      ),
    );
  }

  factory ApiCatchesRequestsGet200BodyResultsArrayModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ApiCatchesRequestsGet200BodyResultsArrayModel: contains complex types',
    );
  }

  final _i3.int id;

  final _i4.ApiCatchesRequestsGet200BodyResultsArrayFursuitModel fursuit;

  final _i3.int conventionId;

  final _i5.ApiCatchesRequestsGet200BodyResultsArrayStateModel state;

  final _i3.DateTime requestedAt;

  final _i3.DateTime reviewDeadlineAt;

  @_i3.override
  _i3.Object? toJson() => {
    r'id': id,
    r'fursuit': fursuit.toJson(),
    r'convention_id': conventionId,
    r'state': state.toJson(),
    r'requested_at': requestedAt.toTimeZonedIso8601String(),
    r'review_deadline_at': reviewDeadlineAt.toTimeZonedIso8601String(),
  };

  $$ApiCatchesRequestsGet200BodyResultsArrayModelCopyWith<
    ApiCatchesRequestsGet200BodyResultsArrayModel
  >
  get copyWith => _ApiCatchesRequestsGet200BodyResultsArrayModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesRequestsGet200BodyResultsArrayModel &&
        other.id == this.id &&
        other.fursuit == this.fursuit &&
        other.conventionId == this.conventionId &&
        other.state == this.state &&
        other.requestedAt == this.requestedAt &&
        other.reviewDeadlineAt == this.reviewDeadlineAt;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      id,
      fursuit,
      conventionId,
      state,
      requestedAt,
      reviewDeadlineAt,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for ApiCatchesRequestsGet200BodyResultsArrayModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiCatchesRequestsGet200BodyResultsArrayModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiCatchesRequestsGet200BodyResultsArrayModelCopyWith<$Res> {
  factory $$ApiCatchesRequestsGet200BodyResultsArrayModelCopyWith(
    ApiCatchesRequestsGet200BodyResultsArrayModel value,
  ) = _ApiCatchesRequestsGet200BodyResultsArrayModelCopyWith<$Res>;

  $Res call({
    _i3.int? id,
    _i4.ApiCatchesRequestsGet200BodyResultsArrayFursuitModel? fursuit,
    _i3.int? conventionId,
    _i5.ApiCatchesRequestsGet200BodyResultsArrayStateModel? state,
    _i3.DateTime? requestedAt,
    _i3.DateTime? reviewDeadlineAt,
  });
  _i3.int get id;
  _i4.ApiCatchesRequestsGet200BodyResultsArrayFursuitModel get fursuit;
  _i3.int get conventionId;
  _i5.ApiCatchesRequestsGet200BodyResultsArrayStateModel get state;
  _i3.DateTime get requestedAt;
  _i3.DateTime get reviewDeadlineAt;
}

class _ApiCatchesRequestsGet200BodyResultsArrayModelCopyWith<$Res>
    implements $$ApiCatchesRequestsGet200BodyResultsArrayModelCopyWith<$Res> {
  _ApiCatchesRequestsGet200BodyResultsArrayModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesRequestsGet200BodyResultsArrayModel _value;

  @_i3.override
  _i3.int get id => _value.id;

  @_i3.override
  _i4.ApiCatchesRequestsGet200BodyResultsArrayFursuitModel get fursuit =>
      _value.fursuit;

  @_i3.override
  _i3.int get conventionId => _value.conventionId;

  @_i3.override
  _i5.ApiCatchesRequestsGet200BodyResultsArrayStateModel get state =>
      _value.state;

  @_i3.override
  _i3.DateTime get requestedAt => _value.requestedAt;

  @_i3.override
  _i3.DateTime get reviewDeadlineAt => _value.reviewDeadlineAt;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? fursuit = _sentinel,
    _i3.Object? conventionId = _sentinel,
    _i3.Object? state = _sentinel,
    _i3.Object? requestedAt = _sentinel,
    _i3.Object? reviewDeadlineAt = _sentinel,
  }) {
    return (ApiCatchesRequestsGet200BodyResultsArrayModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int),
      fursuit: _i3.identical(fursuit, _sentinel)
          ? this.fursuit
          : (fursuit
                as _i4.ApiCatchesRequestsGet200BodyResultsArrayFursuitModel),
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int),
      state: _i3.identical(state, _sentinel)
          ? this.state
          : (state as _i5.ApiCatchesRequestsGet200BodyResultsArrayStateModel),
      requestedAt: _i3.identical(requestedAt, _sentinel)
          ? this.requestedAt
          : (requestedAt as _i3.DateTime),
      reviewDeadlineAt: _i3.identical(reviewDeadlineAt, _sentinel)
          ? this.reviewDeadlineAt
          : (reviewDeadlineAt as _i3.DateTime),
    ) as $Res);
  }
}
