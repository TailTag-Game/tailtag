// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:collection/collection.dart' as _i5;
import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/owner_request_summary_fursuits_array_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class OwnerRequestSummary extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const OwnerRequestSummary({
    required this.pendingCount,
    required this.fursuits,
  });

  factory OwnerRequestSummary.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for OwnerRequestSummary: contains complex types',
    );
  }

  factory OwnerRequestSummary.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'OwnerRequestSummary');
    return OwnerRequestSummary(
      pendingCount: _$map[r'pending_count'].decodeJsonInt(
        context: r'OwnerRequestSummary.pending_count',
      ),
      fursuits: _$map[r'fursuits']
          .decodeJsonList<_i3.Object?>(context: r'OwnerRequestSummary.fursuits')
          .map(_i4.OwnerRequestSummaryFursuitsArrayModel.fromJson)
          .toList(),
    );
  }

  factory OwnerRequestSummary.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for OwnerRequestSummary: contains complex types',
    );
  }

  final _i3.int pendingCount;

  final _i3.List<_i4.OwnerRequestSummaryFursuitsArrayModel> fursuits;

  @_i3.override
  _i3.Object? toJson() => {
    r'pending_count': pendingCount,
    r'fursuits': fursuits.map((e) => e.toJson()).toList(),
  };

  $$OwnerRequestSummaryCopyWith<OwnerRequestSummary> get copyWith =>
      _OwnerRequestSummaryCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    const _$deepEquals = _i5.DeepCollectionEquality();
    return other is OwnerRequestSummary &&
        other.pendingCount == this.pendingCount &&
        _$deepEquals.equals(other.fursuits, this.fursuits);
  }

  @_i3.override
  _i3.int get hashCode {
    const deepEquals = _i5.DeepCollectionEquality();
    return _i3.Object.hashAll([pendingCount, deepEquals.hash(fursuits)]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for OwnerRequestSummary: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode OwnerRequestSummary: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$OwnerRequestSummaryCopyWith<$Res> {
  factory $$OwnerRequestSummaryCopyWith(OwnerRequestSummary value) =
      _OwnerRequestSummaryCopyWith<$Res>;

  $Res call({
    _i3.int? pendingCount,
    _i3.List<_i4.OwnerRequestSummaryFursuitsArrayModel>? fursuits,
  });
  _i3.int get pendingCount;
  _i3.List<_i4.OwnerRequestSummaryFursuitsArrayModel> get fursuits;
}

class _OwnerRequestSummaryCopyWith<$Res>
    implements $$OwnerRequestSummaryCopyWith<$Res> {
  _OwnerRequestSummaryCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final OwnerRequestSummary _value;

  @_i3.override
  _i3.int get pendingCount => _value.pendingCount;

  @_i3.override
  _i3.List<_i4.OwnerRequestSummaryFursuitsArrayModel> get fursuits =>
      _value.fursuits;

  @_i3.override
  $Res call({
    _i3.Object? pendingCount = _sentinel,
    _i3.Object? fursuits = _sentinel,
  }) {
    return (OwnerRequestSummary(
      pendingCount: _i3.identical(pendingCount, _sentinel)
          ? this.pendingCount
          : (pendingCount as _i3.int),
      fursuits: _i3.identical(fursuits, _sentinel)
          ? this.fursuits
          : (fursuits as _i3.List<_i4.OwnerRequestSummaryFursuitsArrayModel>),
    ) as $Res);
  }
}
