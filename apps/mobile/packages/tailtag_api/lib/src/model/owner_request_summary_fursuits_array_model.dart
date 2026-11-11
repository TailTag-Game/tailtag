// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class OwnerRequestSummaryFursuitsArrayModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const OwnerRequestSummaryFursuitsArrayModel({
    required this.fursuitId,
    required this.pendingCount,
  });

  factory OwnerRequestSummaryFursuitsArrayModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'fursuit_id', r'pending_count'},
      listKeys: {},
      context: r'OwnerRequestSummaryFursuitsArrayModel',
    );
    return OwnerRequestSummaryFursuitsArrayModel(
      fursuitId: _$values[r'fursuit_id'].decodeSimpleInt(
        context: r'OwnerRequestSummaryFursuitsArrayModel.fursuit_id',
      ),
      pendingCount: _$values[r'pending_count'].decodeSimpleInt(
        context: r'OwnerRequestSummaryFursuitsArrayModel.pending_count',
      ),
    );
  }

  factory OwnerRequestSummaryFursuitsArrayModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'OwnerRequestSummaryFursuitsArrayModel',
    );
    return OwnerRequestSummaryFursuitsArrayModel(
      fursuitId: _$map[r'fursuit_id'].decodeJsonInt(
        context: r'OwnerRequestSummaryFursuitsArrayModel.fursuit_id',
      ),
      pendingCount: _$map[r'pending_count'].decodeJsonInt(
        context: r'OwnerRequestSummaryFursuitsArrayModel.pending_count',
      ),
    );
  }

  factory OwnerRequestSummaryFursuitsArrayModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'fursuit_id', r'pending_count'},
      listKeys: {},
      context: r'OwnerRequestSummaryFursuitsArrayModel',
    );
    return OwnerRequestSummaryFursuitsArrayModel(
      fursuitId: _$values[r'fursuit_id'].decodeFormInt(
        context: r'OwnerRequestSummaryFursuitsArrayModel.fursuit_id',
      ),
      pendingCount: _$values[r'pending_count'].decodeFormInt(
        context: r'OwnerRequestSummaryFursuitsArrayModel.pending_count',
      ),
    );
  }

  final _i3.int fursuitId;

  final _i3.int pendingCount;

  @_i3.override
  _i3.Object? toJson() => {
    r'fursuit_id': fursuitId,
    r'pending_count': pendingCount,
  };

  $$OwnerRequestSummaryFursuitsArrayModelCopyWith<
    OwnerRequestSummaryFursuitsArrayModel
  >
  get copyWith => _OwnerRequestSummaryFursuitsArrayModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is OwnerRequestSummaryFursuitsArrayModel &&
        other.fursuitId == this.fursuitId &&
        other.pendingCount == this.pendingCount;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([fursuitId, pendingCount]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'fursuit_id'] = _i1.PropertyValue.scalar(fursuitId.toString());
    _$result[r'pending_count'] = _i1.PropertyValue.scalar(
      pendingCount.toString(),
    );
    return _$result;
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i4.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode OwnerRequestSummaryFursuitsArrayModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$OwnerRequestSummaryFursuitsArrayModelCopyWith<$Res> {
  factory $$OwnerRequestSummaryFursuitsArrayModelCopyWith(
    OwnerRequestSummaryFursuitsArrayModel value,
  ) = _OwnerRequestSummaryFursuitsArrayModelCopyWith<$Res>;

  $Res call({_i3.int? fursuitId, _i3.int? pendingCount});
  _i3.int get fursuitId;
  _i3.int get pendingCount;
}

class _OwnerRequestSummaryFursuitsArrayModelCopyWith<$Res>
    implements $$OwnerRequestSummaryFursuitsArrayModelCopyWith<$Res> {
  _OwnerRequestSummaryFursuitsArrayModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final OwnerRequestSummaryFursuitsArrayModel _value;

  @_i3.override
  _i3.int get fursuitId => _value.fursuitId;

  @_i3.override
  _i3.int get pendingCount => _value.pendingCount;

  @_i3.override
  $Res call({
    _i3.Object? fursuitId = _sentinel,
    _i3.Object? pendingCount = _sentinel,
  }) {
    return (OwnerRequestSummaryFursuitsArrayModel(
      fursuitId: _i3.identical(fursuitId, _sentinel)
          ? this.fursuitId
          : (fursuitId as _i3.int),
      pendingCount: _i3.identical(pendingCount, _sentinel)
          ? this.pendingCount
          : (pendingCount as _i3.int),
    ) as $Res);
  }
}
