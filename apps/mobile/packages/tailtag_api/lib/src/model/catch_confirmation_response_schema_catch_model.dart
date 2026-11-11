// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_confirmation_response_schema_catch_fursuit_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchConfirmationResponseSchemaCatchModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchConfirmationResponseSchemaCatchModel({
    this.id,
    this.caughtAt,
    this.conventionId,
    this.fursuit,
  });

  factory CatchConfirmationResponseSchemaCatchModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for CatchConfirmationResponseSchemaCatchModel: contains complex types',
    );
  }

  factory CatchConfirmationResponseSchemaCatchModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'CatchConfirmationResponseSchemaCatchModel',
    );
    return CatchConfirmationResponseSchemaCatchModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'CatchConfirmationResponseSchemaCatchModel.id',
      ),
      caughtAt: _$map[r'caught_at'].decodeJsonDateTime(
        context: r'CatchConfirmationResponseSchemaCatchModel.caught_at',
      ),
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'CatchConfirmationResponseSchemaCatchModel.convention_id',
      ),
      fursuit: _i4.CatchConfirmationResponseSchemaCatchFursuitModel.fromJson(
        _$map[r'fursuit'],
      ),
    );
  }

  factory CatchConfirmationResponseSchemaCatchModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for CatchConfirmationResponseSchemaCatchModel: contains complex types',
    );
  }

  final _i3.int? id;

  final _i3.DateTime? caughtAt;

  final _i3.int? conventionId;

  final _i4.CatchConfirmationResponseSchemaCatchFursuitModel? fursuit;

  @_i3.override
  _i3.Object? toJson() => throw _i1.EncodingException(
    r'CatchConfirmationResponseSchemaCatchModel is read-only and cannot be encoded.',
  );

  $$CatchConfirmationResponseSchemaCatchModelCopyWith<
    CatchConfirmationResponseSchemaCatchModel
  >
  get copyWith => _CatchConfirmationResponseSchemaCatchModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmationResponseSchemaCatchModel &&
        other.id == this.id &&
        other.caughtAt == this.caughtAt &&
        other.conventionId == this.conventionId &&
        other.fursuit == this.fursuit;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([id, caughtAt, conventionId, fursuit]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'CatchConfirmationResponseSchemaCatchModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode CatchConfirmationResponseSchemaCatchModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchConfirmationResponseSchemaCatchModelCopyWith<$Res> {
  factory $$CatchConfirmationResponseSchemaCatchModelCopyWith(
    CatchConfirmationResponseSchemaCatchModel value,
  ) = _CatchConfirmationResponseSchemaCatchModelCopyWith<$Res>;

  $Res call({
    _i3.int? id,
    _i3.DateTime? caughtAt,
    _i3.int? conventionId,
    _i4.CatchConfirmationResponseSchemaCatchFursuitModel? fursuit,
  });
  _i3.int? get id;
  _i3.DateTime? get caughtAt;
  _i3.int? get conventionId;
  _i4.CatchConfirmationResponseSchemaCatchFursuitModel? get fursuit;
}

class _CatchConfirmationResponseSchemaCatchModelCopyWith<$Res>
    implements $$CatchConfirmationResponseSchemaCatchModelCopyWith<$Res> {
  _CatchConfirmationResponseSchemaCatchModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchConfirmationResponseSchemaCatchModel _value;

  @_i3.override
  _i3.int? get id => _value.id;

  @_i3.override
  _i3.DateTime? get caughtAt => _value.caughtAt;

  @_i3.override
  _i3.int? get conventionId => _value.conventionId;

  @_i3.override
  _i4.CatchConfirmationResponseSchemaCatchFursuitModel? get fursuit =>
      _value.fursuit;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? caughtAt = _sentinel,
    _i3.Object? conventionId = _sentinel,
    _i3.Object? fursuit = _sentinel,
  }) {
    return (CatchConfirmationResponseSchemaCatchModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      caughtAt: _i3.identical(caughtAt, _sentinel)
          ? this.caughtAt
          : (caughtAt as _i3.DateTime?),
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int?),
      fursuit: _i3.identical(fursuit, _sentinel)
          ? this.fursuit
          : (fursuit as _i4.CatchConfirmationResponseSchemaCatchFursuitModel?),
    ) as $Res);
  }
}
