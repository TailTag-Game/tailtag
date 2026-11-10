// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_requests_post201_body_catch_fursuit_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class $RawApiCatchesRequestsPost201BodyCatchModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const $RawApiCatchesRequestsPost201BodyCatchModel({
    required this.id,
    required this.caughtAt,
    required this.approvedAt,
    required this.conventionId,
    required this.fursuit,
  });

  factory $RawApiCatchesRequestsPost201BodyCatchModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for $RawApiCatchesRequestsPost201BodyCatchModel: contains complex types',
    );
  }

  factory $RawApiCatchesRequestsPost201BodyCatchModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'$RawApiCatchesRequestsPost201BodyCatchModel',
    );
    return $RawApiCatchesRequestsPost201BodyCatchModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'$RawApiCatchesRequestsPost201BodyCatchModel.id',
      ),
      caughtAt: _$map[r'caught_at'].decodeJsonDateTime(
        context: r'$RawApiCatchesRequestsPost201BodyCatchModel.caught_at',
      ),
      approvedAt: _$map[r'approved_at'].decodeJsonDateTime(
        context: r'$RawApiCatchesRequestsPost201BodyCatchModel.approved_at',
      ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'$RawApiCatchesRequestsPost201BodyCatchModel.convention_id',
      ),
      fursuit: _i4.ApiCatchesRequestsPost201BodyCatchFursuitModel.fromJson(
        _$map[r'fursuit'],
      ),
    );
  }

  factory $RawApiCatchesRequestsPost201BodyCatchModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for $RawApiCatchesRequestsPost201BodyCatchModel: contains complex types',
    );
  }

  final _i3.int id;

  final _i3.DateTime caughtAt;

  final _i3.DateTime approvedAt;

  final _i3.int conventionId;

  final _i4.ApiCatchesRequestsPost201BodyCatchFursuitModel fursuit;

  @_i3.override
  _i3.Object? toJson() => {
    r'id': id,
    r'caught_at': caughtAt.toTimeZonedIso8601String(),
    r'approved_at': approvedAt.toTimeZonedIso8601String(),
    r'convention_id': conventionId,
    r'fursuit': fursuit.toJson(),
  };

  $$$RawApiCatchesRequestsPost201BodyCatchModelCopyWith<
    $RawApiCatchesRequestsPost201BodyCatchModel
  >
  get copyWith => _$RawApiCatchesRequestsPost201BodyCatchModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is $RawApiCatchesRequestsPost201BodyCatchModel &&
        other.id == this.id &&
        other.caughtAt == this.caughtAt &&
        other.approvedAt == this.approvedAt &&
        other.conventionId == this.conventionId &&
        other.fursuit == this.fursuit;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      id,
      caughtAt,
      approvedAt,
      conventionId,
      fursuit,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for ApiCatchesRequestsPost201BodyCatchModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode $RawApiCatchesRequestsPost201BodyCatchModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$$RawApiCatchesRequestsPost201BodyCatchModelCopyWith<$Res> {
  factory $$$RawApiCatchesRequestsPost201BodyCatchModelCopyWith(
    $RawApiCatchesRequestsPost201BodyCatchModel value,
  ) = _$RawApiCatchesRequestsPost201BodyCatchModelCopyWith<$Res>;

  $Res call({
    _i3.int? id,
    _i3.DateTime? caughtAt,
    _i3.DateTime? approvedAt,
    _i3.int? conventionId,
    _i4.ApiCatchesRequestsPost201BodyCatchFursuitModel? fursuit,
  });
  _i3.int get id;
  _i3.DateTime get caughtAt;
  _i3.DateTime get approvedAt;
  _i3.int get conventionId;
  _i4.ApiCatchesRequestsPost201BodyCatchFursuitModel get fursuit;
}

class _$RawApiCatchesRequestsPost201BodyCatchModelCopyWith<$Res>
    implements $$$RawApiCatchesRequestsPost201BodyCatchModelCopyWith<$Res> {
  _$RawApiCatchesRequestsPost201BodyCatchModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final $RawApiCatchesRequestsPost201BodyCatchModel _value;

  @_i3.override
  _i3.int get id => _value.id;

  @_i3.override
  _i3.DateTime get caughtAt => _value.caughtAt;

  @_i3.override
  _i3.DateTime get approvedAt => _value.approvedAt;

  @_i3.override
  _i3.int get conventionId => _value.conventionId;

  @_i3.override
  _i4.ApiCatchesRequestsPost201BodyCatchFursuitModel get fursuit =>
      _value.fursuit;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? caughtAt = _sentinel,
    _i3.Object? approvedAt = _sentinel,
    _i3.Object? conventionId = _sentinel,
    _i3.Object? fursuit = _sentinel,
  }) {
    return ($RawApiCatchesRequestsPost201BodyCatchModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int),
      caughtAt: _i3.identical(caughtAt, _sentinel)
          ? this.caughtAt
          : (caughtAt as _i3.DateTime),
      approvedAt: _i3.identical(approvedAt, _sentinel)
          ? this.approvedAt
          : (approvedAt as _i3.DateTime),
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int),
      fursuit: _i3.identical(fursuit, _sentinel)
          ? this.fursuit
          : (fursuit as _i4.ApiCatchesRequestsPost201BodyCatchFursuitModel),
    ) as $Res);
  }
}

typedef ApiCatchesRequestsPost201BodyCatchModel =
    $RawApiCatchesRequestsPost201BodyCatchModel?;
