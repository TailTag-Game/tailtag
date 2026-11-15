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
    _i3.bool isHeader = false,
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
    r'fursuit': this.fursuit.toJson(),
    r'convention': this.convention.toJson(),
  };

  CatchHistoryResponseSchemaResultsArrayModel Function({
    _i3.int? id,
    _i4.CatchHistoryResponseSchemaResultsArrayFursuitModel? fursuit,
    _i5.CatchHistoryResponseSchemaResultsArrayConventionModel? convention,
    _i3.DateTime? caughtAt,
  })
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({
      _i3.Object? id = _sentinel,
      _i4.CatchHistoryResponseSchemaResultsArrayFursuitModel? fursuit,
      _i5.CatchHistoryResponseSchemaResultsArrayConventionModel? convention,
      _i3.Object? caughtAt = _sentinel,
    }) => CatchHistoryResponseSchemaResultsArrayModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      fursuit: fursuit ?? this.fursuit,
      convention: convention ?? this.convention,
      caughtAt: _i3.identical(caughtAt, _sentinel)
          ? this.caughtAt
          : (caughtAt as _i3.DateTime?),
    );
  }

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
    return _i3.Object.hashAll([
      this.id,
      this.fursuit,
      this.convention,
      this.caughtAt,
    ]);
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
