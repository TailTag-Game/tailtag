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
    r'id': id,
    r'fursuit': fursuit.toJson(),
    r'convention_id': conventionId,
    r'player': player.toJson(),
    r'state': state.toJson(),
    r'requested_at': requestedAt.toTimeZonedIso8601String(),
    r'undo_available_until': undoAvailableUntil?.toTimeZonedIso8601String(),
    r'prior_decline_count': priorDeclineCount,
    r'player_blocked': playerBlocked,
    r'approval_paused': approvalPaused,
    r'review_deadline_at': reviewDeadlineAt.toTimeZonedIso8601String(),
  };

  $$OwnerRequestCopyWith<OwnerRequest> get copyWith =>
      _OwnerRequestCopyWith(this);

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
      id,
      fursuit,
      conventionId,
      player,
      state,
      requestedAt,
      undoAvailableUntil,
      priorDeclineCount,
      playerBlocked,
      approvalPaused,
      reviewDeadlineAt,
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

abstract class $$OwnerRequestCopyWith<$Res> {
  factory $$OwnerRequestCopyWith(OwnerRequest value) =
      _OwnerRequestCopyWith<$Res>;

  $Res call({
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
  });
  _i3.int get id;
  _i4.FursuitSummary get fursuit;
  _i3.int get conventionId;
  _i5.OwnerRequestPlayerModel get player;
  _i6.CatchRequestState get state;
  _i3.DateTime get requestedAt;
  _i3.DateTime? get undoAvailableUntil;
  _i3.int get priorDeclineCount;
  _i3.bool get playerBlocked;
  _i3.bool get approvalPaused;
  _i3.DateTime get reviewDeadlineAt;
}

class _OwnerRequestCopyWith<$Res> implements $$OwnerRequestCopyWith<$Res> {
  _OwnerRequestCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final OwnerRequest _value;

  @_i3.override
  _i3.int get id => _value.id;

  @_i3.override
  _i4.FursuitSummary get fursuit => _value.fursuit;

  @_i3.override
  _i3.int get conventionId => _value.conventionId;

  @_i3.override
  _i5.OwnerRequestPlayerModel get player => _value.player;

  @_i3.override
  _i6.CatchRequestState get state => _value.state;

  @_i3.override
  _i3.DateTime get requestedAt => _value.requestedAt;

  @_i3.override
  _i3.DateTime? get undoAvailableUntil => _value.undoAvailableUntil;

  @_i3.override
  _i3.int get priorDeclineCount => _value.priorDeclineCount;

  @_i3.override
  _i3.bool get playerBlocked => _value.playerBlocked;

  @_i3.override
  _i3.bool get approvalPaused => _value.approvalPaused;

  @_i3.override
  _i3.DateTime get reviewDeadlineAt => _value.reviewDeadlineAt;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? fursuit = _sentinel,
    _i3.Object? conventionId = _sentinel,
    _i3.Object? player = _sentinel,
    _i3.Object? state = _sentinel,
    _i3.Object? requestedAt = _sentinel,
    _i3.Object? undoAvailableUntil = _sentinel,
    _i3.Object? priorDeclineCount = _sentinel,
    _i3.Object? playerBlocked = _sentinel,
    _i3.Object? approvalPaused = _sentinel,
    _i3.Object? reviewDeadlineAt = _sentinel,
  }) {
    return (OwnerRequest(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int),
      fursuit: _i3.identical(fursuit, _sentinel)
          ? this.fursuit
          : (fursuit as _i4.FursuitSummary),
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int),
      player: _i3.identical(player, _sentinel)
          ? this.player
          : (player as _i5.OwnerRequestPlayerModel),
      state: _i3.identical(state, _sentinel)
          ? this.state
          : (state as _i6.CatchRequestState),
      requestedAt: _i3.identical(requestedAt, _sentinel)
          ? this.requestedAt
          : (requestedAt as _i3.DateTime),
      undoAvailableUntil: _i3.identical(undoAvailableUntil, _sentinel)
          ? this.undoAvailableUntil
          : (undoAvailableUntil as _i3.DateTime?),
      priorDeclineCount: _i3.identical(priorDeclineCount, _sentinel)
          ? this.priorDeclineCount
          : (priorDeclineCount as _i3.int),
      playerBlocked: _i3.identical(playerBlocked, _sentinel)
          ? this.playerBlocked
          : (playerBlocked as _i3.bool),
      approvalPaused: _i3.identical(approvalPaused, _sentinel)
          ? this.approvalPaused
          : (approvalPaused as _i3.bool),
      reviewDeadlineAt: _i3.identical(reviewDeadlineAt, _sentinel)
          ? this.reviewDeadlineAt
          : (reviewDeadlineAt as _i3.DateTime),
    ) as $Res);
  }
}
