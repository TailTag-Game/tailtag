// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_requests_post201_body_request_fursuit_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_catches_requests_post201_body_request_state_model.dart'
    as _i5;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class $RawApiCatchesRequestsPost201BodyRequestModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const $RawApiCatchesRequestsPost201BodyRequestModel({
    required this.id,
    required this.fursuit,
    required this.conventionId,
    required this.state,
    required this.requestedAt,
    required this.reviewDeadlineAt,
  });

  factory $RawApiCatchesRequestsPost201BodyRequestModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for $RawApiCatchesRequestsPost201BodyRequestModel: contains complex types',
    );
  }

  factory $RawApiCatchesRequestsPost201BodyRequestModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'$RawApiCatchesRequestsPost201BodyRequestModel',
    );
    return $RawApiCatchesRequestsPost201BodyRequestModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'$RawApiCatchesRequestsPost201BodyRequestModel.id',
      ),
      fursuit: _i4.ApiCatchesRequestsPost201BodyRequestFursuitModel.fromJson(
        _$map[r'fursuit'],
      ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'$RawApiCatchesRequestsPost201BodyRequestModel.convention_id',
      ),
      state: _i5.ApiCatchesRequestsPost201BodyRequestStateModel.fromJson(
        _$map[r'state'],
      ),
      requestedAt: _$map[r'requested_at'].decodeJsonDateTime(
        context: r'$RawApiCatchesRequestsPost201BodyRequestModel.requested_at',
      ),
      reviewDeadlineAt: _$map[r'review_deadline_at'].decodeJsonDateTime(
        context:
            r'$RawApiCatchesRequestsPost201BodyRequestModel.review_deadline_at',
      ),
    );
  }

  factory $RawApiCatchesRequestsPost201BodyRequestModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for $RawApiCatchesRequestsPost201BodyRequestModel: contains complex types',
    );
  }

  final _i3.int id;

  final _i4.ApiCatchesRequestsPost201BodyRequestFursuitModel fursuit;

  final _i3.int conventionId;

  final _i5.ApiCatchesRequestsPost201BodyRequestStateModel state;

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

  $$$RawApiCatchesRequestsPost201BodyRequestModelCopyWith<
    $RawApiCatchesRequestsPost201BodyRequestModel
  >
  get copyWith => _$RawApiCatchesRequestsPost201BodyRequestModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is $RawApiCatchesRequestsPost201BodyRequestModel &&
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
    r'parameterProperties not supported for ApiCatchesRequestsPost201BodyRequestModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode $RawApiCatchesRequestsPost201BodyRequestModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$$RawApiCatchesRequestsPost201BodyRequestModelCopyWith<$Res> {
  factory $$$RawApiCatchesRequestsPost201BodyRequestModelCopyWith(
    $RawApiCatchesRequestsPost201BodyRequestModel value,
  ) = _$RawApiCatchesRequestsPost201BodyRequestModelCopyWith<$Res>;

  $Res call({
    _i3.int? id,
    _i4.ApiCatchesRequestsPost201BodyRequestFursuitModel? fursuit,
    _i3.int? conventionId,
    _i5.ApiCatchesRequestsPost201BodyRequestStateModel? state,
    _i3.DateTime? requestedAt,
    _i3.DateTime? reviewDeadlineAt,
  });
  _i3.int get id;
  _i4.ApiCatchesRequestsPost201BodyRequestFursuitModel get fursuit;
  _i3.int get conventionId;
  _i5.ApiCatchesRequestsPost201BodyRequestStateModel get state;
  _i3.DateTime get requestedAt;
  _i3.DateTime get reviewDeadlineAt;
}

class _$RawApiCatchesRequestsPost201BodyRequestModelCopyWith<$Res>
    implements $$$RawApiCatchesRequestsPost201BodyRequestModelCopyWith<$Res> {
  _$RawApiCatchesRequestsPost201BodyRequestModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final $RawApiCatchesRequestsPost201BodyRequestModel _value;

  @_i3.override
  _i3.int get id => _value.id;

  @_i3.override
  _i4.ApiCatchesRequestsPost201BodyRequestFursuitModel get fursuit =>
      _value.fursuit;

  @_i3.override
  _i3.int get conventionId => _value.conventionId;

  @_i3.override
  _i5.ApiCatchesRequestsPost201BodyRequestStateModel get state => _value.state;

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
    return ($RawApiCatchesRequestsPost201BodyRequestModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int),
      fursuit: _i3.identical(fursuit, _sentinel)
          ? this.fursuit
          : (fursuit as _i4.ApiCatchesRequestsPost201BodyRequestFursuitModel),
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int),
      state: _i3.identical(state, _sentinel)
          ? this.state
          : (state as _i5.ApiCatchesRequestsPost201BodyRequestStateModel),
      requestedAt: _i3.identical(requestedAt, _sentinel)
          ? this.requestedAt
          : (requestedAt as _i3.DateTime),
      reviewDeadlineAt: _i3.identical(reviewDeadlineAt, _sentinel)
          ? this.reviewDeadlineAt
          : (reviewDeadlineAt as _i3.DateTime),
    ) as $Res);
  }
}

typedef ApiCatchesRequestsPost201BodyRequestModel =
    $RawApiCatchesRequestsPost201BodyRequestModel?;
