// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_confirmation_response_schema_catch_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/catch_confirmation_response_schema_outcome_all_of_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchConfirmationResponseSchema extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchConfirmationResponseSchema({this.outcome, this.$catch});

  factory CatchConfirmationResponseSchema.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for CatchConfirmationResponseSchema: contains complex types',
    );
  }

  factory CatchConfirmationResponseSchema.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchConfirmationResponseSchema');
    return CatchConfirmationResponseSchema(
      outcome: _i4.CatchConfirmationResponseSchemaOutcomeAllOfModel.fromJson(
        _$map[r'outcome'],
      ),
      $catch: _i5.CatchConfirmationResponseSchemaCatchModel.fromJson(
        _$map[r'catch'],
      ),
    );
  }

  factory CatchConfirmationResponseSchema.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for CatchConfirmationResponseSchema: contains complex types',
    );
  }

  final _i4.CatchConfirmationResponseSchemaOutcomeAllOfModel? outcome;

  final _i5.CatchConfirmationResponseSchemaCatchModel? $catch;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$CatchConfirmationResponseSchemaCopyWith<CatchConfirmationResponseSchema>
  get copyWith => _CatchConfirmationResponseSchemaCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmationResponseSchema &&
        other.outcome == this.outcome &&
        other.$catch == this.$catch;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([outcome, $catch]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    return <_i3.String, _i1.PropertyValue>{};
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode CatchConfirmationResponseSchema: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchConfirmationResponseSchemaCopyWith<$Res> {
  factory $$CatchConfirmationResponseSchemaCopyWith(
    CatchConfirmationResponseSchema value,
  ) = _CatchConfirmationResponseSchemaCopyWith<$Res>;

  $Res call({
    _i4.CatchConfirmationResponseSchemaOutcomeAllOfModel? outcome,
    _i5.CatchConfirmationResponseSchemaCatchModel? $catch,
  });
  _i4.CatchConfirmationResponseSchemaOutcomeAllOfModel? get outcome;
  _i5.CatchConfirmationResponseSchemaCatchModel? get $catch;
}

class _CatchConfirmationResponseSchemaCopyWith<$Res>
    implements $$CatchConfirmationResponseSchemaCopyWith<$Res> {
  _CatchConfirmationResponseSchemaCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchConfirmationResponseSchema _value;

  @_i3.override
  _i4.CatchConfirmationResponseSchemaOutcomeAllOfModel? get outcome =>
      _value.outcome;

  @_i3.override
  _i5.CatchConfirmationResponseSchemaCatchModel? get $catch => _value.$catch;

  @_i3.override
  $Res call({_i3.Object? outcome = _sentinel, _i3.Object? $catch = _sentinel}) {
    return (CatchConfirmationResponseSchema(
      outcome: _i3.identical(outcome, _sentinel)
          ? this.outcome
          : (outcome as _i4.CatchConfirmationResponseSchemaOutcomeAllOfModel?),
      $catch: _i3.identical($catch, _sentinel)
          ? this.$catch
          : ($catch as _i5.CatchConfirmationResponseSchemaCatchModel?),
    ) as $Res);
  }
}
