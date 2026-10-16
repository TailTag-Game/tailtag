// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:collection/collection.dart' as _i5;
import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_history_response_schema_results_array_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchHistoryResponseSchema extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchHistoryResponseSchema({
    required this.catchCount,
    required this.next,
    required this.previous,
    required this.results,
  });

  factory CatchHistoryResponseSchema.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for CatchHistoryResponseSchema: contains complex types',
    );
  }

  factory CatchHistoryResponseSchema.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchHistoryResponseSchema');
    return CatchHistoryResponseSchema(
      catchCount: _$map[r'catch_count'].decodeJsonInt(
        context: r'CatchHistoryResponseSchema.catch_count',
      ),
      next: _$map[r'next'].decodeJsonNullableUri(
        context: r'CatchHistoryResponseSchema.next',
      ),
      previous: _$map[r'previous'].decodeJsonNullableUri(
        context: r'CatchHistoryResponseSchema.previous',
      ),
      results: _$map[r'results']
          .decodeJsonList<_i3.Object?>(
            context: r'CatchHistoryResponseSchema.results',
          )
          .map(_i4.CatchHistoryResponseSchemaResultsArrayModel.fromJson)
          .toList(),
    );
  }

  factory CatchHistoryResponseSchema.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for CatchHistoryResponseSchema: contains complex types',
    );
  }

  final _i3.int catchCount;

  final _i3.Uri? next;

  final _i3.Uri? previous;

  final _i3.List<_i4.CatchHistoryResponseSchemaResultsArrayModel> results;

  @_i3.override
  _i3.Object? toJson() => {
    r'catch_count': catchCount,
    r'next': next?.toString(),
    r'previous': previous?.toString(),
    r'results': results.map((e) => e.toJson()).toList(),
  };

  $$CatchHistoryResponseSchemaCopyWith<CatchHistoryResponseSchema>
  get copyWith => _CatchHistoryResponseSchemaCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    const _$deepEquals = _i5.DeepCollectionEquality();
    return other is CatchHistoryResponseSchema &&
        other.catchCount == this.catchCount &&
        other.next == this.next &&
        other.previous == this.previous &&
        _$deepEquals.equals(other.results, this.results);
  }

  @_i3.override
  _i3.int get hashCode {
    const deepEquals = _i5.DeepCollectionEquality();
    return _i3.Object.hashAll([
      catchCount,
      next,
      previous,
      deepEquals.hash(results),
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for CatchHistoryResponseSchema: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode CatchHistoryResponseSchema: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchHistoryResponseSchemaCopyWith<$Res> {
  factory $$CatchHistoryResponseSchemaCopyWith(
    CatchHistoryResponseSchema value,
  ) = _CatchHistoryResponseSchemaCopyWith<$Res>;

  $Res call({
    _i3.int? catchCount,
    _i3.Uri? next,
    _i3.Uri? previous,
    _i3.List<_i4.CatchHistoryResponseSchemaResultsArrayModel>? results,
  });
  _i3.int get catchCount;
  _i3.Uri? get next;
  _i3.Uri? get previous;
  _i3.List<_i4.CatchHistoryResponseSchemaResultsArrayModel> get results;
}

class _CatchHistoryResponseSchemaCopyWith<$Res>
    implements $$CatchHistoryResponseSchemaCopyWith<$Res> {
  _CatchHistoryResponseSchemaCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchHistoryResponseSchema _value;

  @_i3.override
  _i3.int get catchCount => _value.catchCount;

  @_i3.override
  _i3.Uri? get next => _value.next;

  @_i3.override
  _i3.Uri? get previous => _value.previous;

  @_i3.override
  _i3.List<_i4.CatchHistoryResponseSchemaResultsArrayModel> get results =>
      _value.results;

  @_i3.override
  $Res call({
    _i3.Object? catchCount = _sentinel,
    _i3.Object? next = _sentinel,
    _i3.Object? previous = _sentinel,
    _i3.Object? results = _sentinel,
  }) {
    return (CatchHistoryResponseSchema(
      catchCount: _i3.identical(catchCount, _sentinel)
          ? this.catchCount
          : (catchCount as _i3.int),
      next: _i3.identical(next, _sentinel) ? this.next : (next as _i3.Uri?),
      previous: _i3.identical(previous, _sentinel)
          ? this.previous
          : (previous as _i3.Uri?),
      results: _i3.identical(results, _sentinel)
          ? this.results
          : (results
                as _i3.List<_i4.CatchHistoryResponseSchemaResultsArrayModel>),
    ) as $Res);
  }
}
