// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_request_state.dart' as _i6;
import 'package:tailtag_api/src/model/fursuit_summary.dart' as _i4;
import 'package:tailtag_api/src/model/owner_request_player_model.dart' as _i5;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class OwnerRequest extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const OwnerRequest({
    required this.id,
    required this.fursuit,
    required this.conventionId,
    required this.player,
    required this.state,
    required this.requestedAt,
    required this.undoAvailableUntil,
    required this.priorDeclineCount,
    required this.playerBlocked,
    required this.approvalPaused,
    required this.reviewDeadlineAt,
  });

  factory OwnerRequest.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for OwnerRequest: contains complex types',
    );
  }

  factory OwnerRequest.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'OwnerRequest');
    return OwnerRequest(
      id: _$map[r'id'].decodeJsonInt(context: r'OwnerRequest.id'),
      fursuit: _i4.FursuitSummary.fromJson(_$map[r'fursuit']),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'OwnerRequest.convention_id',
      ),
      player: _i5.OwnerRequestPlayerModel.fromJson(_$map[r'player']),
      state: _i6.CatchRequestState.fromJson(_$map[r'state']),
      requestedAt: _$map[r'requested_at'].decodeJsonDateTime(
        context: r'OwnerRequest.requested_at',
      ),
      undoAvailableUntil: _$map[r'undo_available_until']
          .decodeJsonNullableDateTime(
            context: r'OwnerRequest.undo_available_until',
          ),
      priorDeclineCount: _$map[r'prior_decline_count'].decodeJsonInt(
        context: r'OwnerRequest.prior_decline_count',
      ),
      playerBlocked: _$map[r'player_blocked'].decodeJsonBool(
        context: r'OwnerRequest.player_blocked',
      ),
      approvalPaused: _$map[r'approval_paused'].decodeJsonBool(
        context: r'OwnerRequest.approval_paused',
      ),
      reviewDeadlineAt: _$map[r'review_deadline_at'].decodeJsonDateTime(
        context: r'OwnerRequest.review_deadline_at',
      ),
    );
  }

  factory OwnerRequest.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for OwnerRequest: contains complex types',
    );
  }

  final _i3.int id;

  final _i4.FursuitSummary fursuit;

  final _i3.int conventionId;

  final _i5.OwnerRequestPlayerModel player;

  final _i6.CatchRequestState state;

  final _i3.DateTime requestedAt;

  final _i3.DateTime? undoAvailableUntil;

  final _i3.int priorDeclineCount;

  final _i3.bool playerBlocked;

  final _i3.bool approvalPaused;

  final _i3.DateTime reviewDeadlineAt;

  @_i3.override
  _i3.Object? toJson() => {
    r'id': this.id,
    r'fursuit': this.fursuit.toJson(),
    r'convention_id': this.conventionId,
    r'player': this.player.toJson(),
    r'state': this.state.toJson(),
    r'requested_at': this.requestedAt.toTimeZonedIso8601String(),
    r'undo_available_until': this.undoAvailableUntil
        ?.toTimeZonedIso8601String(),
    r'prior_decline_count': this.priorDeclineCount,
    r'player_blocked': this.playerBlocked,
    r'approval_paused': this.approvalPaused,
    r'review_deadline_at': this.reviewDeadlineAt.toTimeZonedIso8601String(),
  };

  OwnerRequest Function({
    _i3.int? id,
    _i4.FursuitSummary? fursuit,
    _i3.int? conventionId,
    _i5.OwnerRequestPlayerModel? player,
    _i6.CatchRequestState? state,
    _i3.DateTime? requestedAt,
    _i3.DateTime? undoAvailableUntil,
    _i3.int? priorDeclineCount,
    _i3.bool? playerBlocked,
    _i3.bool? approvalPaused,
    _i3.DateTime? reviewDeadlineAt,
  })
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({
      _i3.int? id,
      _i4.FursuitSummary? fursuit,
      _i3.int? conventionId,
      _i5.OwnerRequestPlayerModel? player,
      _i6.CatchRequestState? state,
      _i3.DateTime? requestedAt,
      _i3.Object? undoAvailableUntil = _sentinel,
      _i3.int? priorDeclineCount,
      _i3.bool? playerBlocked,
      _i3.bool? approvalPaused,
      _i3.DateTime? reviewDeadlineAt,
    }) => OwnerRequest(
      id: id ?? this.id,
      fursuit: fursuit ?? this.fursuit,
      conventionId: conventionId ?? this.conventionId,
      player: player ?? this.player,
      state: state ?? this.state,
      requestedAt: requestedAt ?? this.requestedAt,
      undoAvailableUntil: _i3.identical(undoAvailableUntil, _sentinel)
          ? this.undoAvailableUntil
          : (undoAvailableUntil as _i3.DateTime?),
      priorDeclineCount: priorDeclineCount ?? this.priorDeclineCount,
      playerBlocked: playerBlocked ?? this.playerBlocked,
      approvalPaused: approvalPaused ?? this.approvalPaused,
      reviewDeadlineAt: reviewDeadlineAt ?? this.reviewDeadlineAt,
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is OwnerRequest &&
        other.id == this.id &&
        other.fursuit == this.fursuit &&
        other.conventionId == this.conventionId &&
        other.player == this.player &&
        other.state == this.state &&
        other.requestedAt == this.requestedAt &&
        other.undoAvailableUntil == this.undoAvailableUntil &&
        other.priorDeclineCount == this.priorDeclineCount &&
        other.playerBlocked == this.playerBlocked &&
        other.approvalPaused == this.approvalPaused &&
        other.reviewDeadlineAt == this.reviewDeadlineAt;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      this.id,
      this.fursuit,
      this.conventionId,
      this.player,
      this.state,
      this.requestedAt,
      this.undoAvailableUntil,
      this.priorDeclineCount,
      this.playerBlocked,
      this.approvalPaused,
      this.reviewDeadlineAt,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for OwnerRequest: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i7.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode OwnerRequest: complex types cannot be URI-encoded',
    );
  }
}
