// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/request_catch_fursuit_model.dart' as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class RequestCatch extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const RequestCatch({
    required this.id,
    required this.caughtAt,
    required this.approvedAt,
    required this.conventionId,
    required this.fursuit,
  });

  factory RequestCatch.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for RequestCatch: contains complex types',
    );
  }

  factory RequestCatch.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'RequestCatch');
    return RequestCatch(
      id: _$map[r'id'].decodeJsonInt(context: r'RequestCatch.id'),
      caughtAt: _$map[r'caught_at'].decodeJsonDateTime(
        context: r'RequestCatch.caught_at',
      ),
      approvedAt: _$map[r'approved_at'].decodeJsonDateTime(
        context: r'RequestCatch.approved_at',
      ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'RequestCatch.convention_id',
      ),
      fursuit: _i4.RequestCatchFursuitModel.fromJson(_$map[r'fursuit']),
    );
  }

  factory RequestCatch.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for RequestCatch: contains complex types',
    );
  }

  final _i3.int id;

  final _i3.DateTime caughtAt;

  final _i3.DateTime approvedAt;

  final _i3.int conventionId;

  final _i4.RequestCatchFursuitModel fursuit;

  @_i3.override
  _i3.Object? toJson() => {
    r'id': this.id,
    r'caught_at': this.caughtAt.toTimeZonedIso8601String(),
    r'approved_at': this.approvedAt.toTimeZonedIso8601String(),
    r'convention_id': this.conventionId,
    r'fursuit': this.fursuit.toJson(),
  };

  RequestCatch Function({
    _i3.int? id,
    _i3.DateTime? caughtAt,
    _i3.DateTime? approvedAt,
    _i3.int? conventionId,
    _i4.RequestCatchFursuitModel? fursuit,
  })
  get copyWith {
    return ({
      _i3.int? id,
      _i3.DateTime? caughtAt,
      _i3.DateTime? approvedAt,
      _i3.int? conventionId,
      _i4.RequestCatchFursuitModel? fursuit,
    }) => RequestCatch(
      id: id ?? this.id,
      caughtAt: caughtAt ?? this.caughtAt,
      approvedAt: approvedAt ?? this.approvedAt,
      conventionId: conventionId ?? this.conventionId,
      fursuit: fursuit ?? this.fursuit,
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is RequestCatch &&
        other.id == this.id &&
        other.caughtAt == this.caughtAt &&
        other.approvedAt == this.approvedAt &&
        other.conventionId == this.conventionId &&
        other.fursuit == this.fursuit;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      this.id,
      this.caughtAt,
      this.approvedAt,
      this.conventionId,
      this.fursuit,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for RequestCatch: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode RequestCatch: complex types cannot be URI-encoded',
    );
  }
}
