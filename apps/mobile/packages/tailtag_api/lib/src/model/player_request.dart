// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_request_state.dart' as _i5;
import 'package:tailtag_api/src/model/fursuit_summary.dart' as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class PlayerRequest extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const PlayerRequest({
    required this.id,
    required this.fursuit,
    required this.conventionId,
    required this.state,
    required this.requestedAt,
    required this.reviewDeadlineAt,
  });

  factory PlayerRequest.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for PlayerRequest: contains complex types',
    );
  }

  factory PlayerRequest.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'PlayerRequest');
    return PlayerRequest(
      id: _$map[r'id'].decodeJsonInt(context: r'PlayerRequest.id'),
      fursuit: _i4.FursuitSummary.fromJson(_$map[r'fursuit']),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'PlayerRequest.convention_id',
      ),
      state: _i5.CatchRequestState.fromJson(_$map[r'state']),
      requestedAt: _$map[r'requested_at'].decodeJsonDateTime(
        context: r'PlayerRequest.requested_at',
      ),
      reviewDeadlineAt: _$map[r'review_deadline_at'].decodeJsonDateTime(
        context: r'PlayerRequest.review_deadline_at',
      ),
    );
  }

  factory PlayerRequest.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for PlayerRequest: contains complex types',
    );
  }

  final _i3.int id;

  final _i4.FursuitSummary fursuit;

  final _i3.int conventionId;

  final _i5.CatchRequestState state;

  final _i3.DateTime requestedAt;

  final _i3.DateTime reviewDeadlineAt;

  @_i3.override
  _i3.Object? toJson() => {
    r'id': this.id,
    r'fursuit': this.fursuit.toJson(),
    r'convention_id': this.conventionId,
    r'state': this.state.toJson(),
    r'requested_at': this.requestedAt.toTimeZonedIso8601String(),
    r'review_deadline_at': this.reviewDeadlineAt.toTimeZonedIso8601String(),
  };

  PlayerRequest Function({
    _i3.int? id,
    _i4.FursuitSummary? fursuit,
    _i3.int? conventionId,
    _i5.CatchRequestState? state,
    _i3.DateTime? requestedAt,
    _i3.DateTime? reviewDeadlineAt,
  })
  get copyWith {
    return ({
      _i3.int? id,
      _i4.FursuitSummary? fursuit,
      _i3.int? conventionId,
      _i5.CatchRequestState? state,
      _i3.DateTime? requestedAt,
      _i3.DateTime? reviewDeadlineAt,
    }) => PlayerRequest(
      id: id ?? this.id,
      fursuit: fursuit ?? this.fursuit,
      conventionId: conventionId ?? this.conventionId,
      state: state ?? this.state,
      requestedAt: requestedAt ?? this.requestedAt,
      reviewDeadlineAt: reviewDeadlineAt ?? this.reviewDeadlineAt,
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is PlayerRequest &&
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
      this.id,
      this.fursuit,
      this.conventionId,
      this.state,
      this.requestedAt,
      this.reviewDeadlineAt,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for PlayerRequest: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode PlayerRequest: complex types cannot be URI-encoded',
    );
  }
}
