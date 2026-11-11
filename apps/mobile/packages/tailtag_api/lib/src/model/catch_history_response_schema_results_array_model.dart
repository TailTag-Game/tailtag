// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_history_response_schema_results_array_convention_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/catch_history_response_schema_results_array_fursuit_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchHistoryResponseSchemaResultsArrayModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchHistoryResponseSchemaResultsArrayModel({
    required this.fursuit,
    required this.convention,
    this.id,
    this.caughtAt,
  });

  factory CatchHistoryResponseSchemaResultsArrayModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for CatchHistoryResponseSchemaResultsArrayModel: contains complex types',
    );
  }

  factory CatchHistoryResponseSchemaResultsArrayModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'CatchHistoryResponseSchemaResultsArrayModel',
    );
    return CatchHistoryResponseSchemaResultsArrayModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'CatchHistoryResponseSchemaResultsArrayModel.id',
      ),
      fursuit: _i4.CatchHistoryResponseSchemaResultsArrayFursuitModel.fromJson(
        _$map[r'fursuit'],
      ),
      convention:
          _i5.CatchHistoryResponseSchemaResultsArrayConventionModel.fromJson(
            _$map[r'convention'],
          ),
      caughtAt: _$map[r'caught_at'].decodeJsonDateTime(
        context: r'CatchHistoryResponseSchemaResultsArrayModel.caught_at',
      ),
    );
  }

  factory CatchHistoryResponseSchemaResultsArrayModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for CatchHistoryResponseSchemaResultsArrayModel: contains complex types',
    );
  }

  final _i3.int? id;

  final _i4.CatchHistoryResponseSchemaResultsArrayFursuitModel fursuit;

  final _i5.CatchHistoryResponseSchemaResultsArrayConventionModel convention;

  final _i3.DateTime? caughtAt;

  @_i3.override
  _i3.Object? toJson() => {
    r'fursuit': fursuit.toJson(),
    r'convention': convention.toJson(),
  };

  $$CatchHistoryResponseSchemaResultsArrayModelCopyWith<
    CatchHistoryResponseSchemaResultsArrayModel
  >
  get copyWith => _CatchHistoryResponseSchemaResultsArrayModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchHistoryResponseSchemaResultsArrayModel &&
        other.id == this.id &&
        other.fursuit == this.fursuit &&
        other.convention == this.convention &&
        other.caughtAt == this.caughtAt;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([id, fursuit, convention, caughtAt]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for CatchHistoryResponseSchemaResultsArrayModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode CatchHistoryResponseSchemaResultsArrayModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchHistoryResponseSchemaResultsArrayModelCopyWith<$Res> {
  factory $$CatchHistoryResponseSchemaResultsArrayModelCopyWith(
    CatchHistoryResponseSchemaResultsArrayModel value,
  ) = _CatchHistoryResponseSchemaResultsArrayModelCopyWith<$Res>;

  $Res call({
    _i3.int? id,
    _i4.CatchHistoryResponseSchemaResultsArrayFursuitModel? fursuit,
    _i5.CatchHistoryResponseSchemaResultsArrayConventionModel? convention,
    _i3.DateTime? caughtAt,
  });
  _i3.int? get id;
  _i4.CatchHistoryResponseSchemaResultsArrayFursuitModel get fursuit;
  _i5.CatchHistoryResponseSchemaResultsArrayConventionModel get convention;
  _i3.DateTime? get caughtAt;
}

class _CatchHistoryResponseSchemaResultsArrayModelCopyWith<$Res>
    implements $$CatchHistoryResponseSchemaResultsArrayModelCopyWith<$Res> {
  _CatchHistoryResponseSchemaResultsArrayModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchHistoryResponseSchemaResultsArrayModel _value;

  @_i3.override
  _i3.int? get id => _value.id;

  @_i3.override
  _i4.CatchHistoryResponseSchemaResultsArrayFursuitModel get fursuit =>
      _value.fursuit;

  @_i3.override
  _i5.CatchHistoryResponseSchemaResultsArrayConventionModel get convention =>
      _value.convention;

  @_i3.override
  _i3.DateTime? get caughtAt => _value.caughtAt;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? fursuit = _sentinel,
    _i3.Object? convention = _sentinel,
    _i3.Object? caughtAt = _sentinel,
  }) {
    return (CatchHistoryResponseSchemaResultsArrayModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      fursuit: _i3.identical(fursuit, _sentinel)
          ? this.fursuit
          : (fursuit as _i4.CatchHistoryResponseSchemaResultsArrayFursuitModel),
      convention: _i3.identical(convention, _sentinel)
          ? this.convention
          : (convention
                as _i5.CatchHistoryResponseSchemaResultsArrayConventionModel),
      caughtAt: _i3.identical(caughtAt, _sentinel)
          ? this.caughtAt
          : (caughtAt as _i3.DateTime?),
    ) as $Res);
  }
}
