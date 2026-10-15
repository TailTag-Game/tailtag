// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/status_enum.dart' as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// Operational lifecycle state of the convention.
///
/// * `draft` - Draft
/// * `active` - Active
/// * `paused` - Paused
/// * `completed` - Completed
/// * `cancelled` - Cancelled
@_i2.immutable
class ConventionStatusAllOfModel
    implements _i1.ParameterEncodable, _i1.UriEncodable {
  const ConventionStatusAllOfModel({this.statusEnum});

  factory ConventionStatusAllOfModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    return ConventionStatusAllOfModel(
      statusEnum: _i4.StatusEnum.fromSimple(value, explode: explode),
    );
  }

  factory ConventionStatusAllOfModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    return ConventionStatusAllOfModel(
      statusEnum: _i4.StatusEnum.fromForm(value, explode: explode),
    );
  }

  factory ConventionStatusAllOfModel.fromJson(_i3.Object? json) {
    return ConventionStatusAllOfModel(
      statusEnum: _i4.StatusEnum.fromJson(json),
    );
  }

  final _i4.StatusEnum? statusEnum;

  _i1.EncodingShape get currentEncodingShape => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.Object? toJson() => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String toSimple({
    required _i3.bool explode,
    required _i3.bool allowEmpty,
    _i3.bool literal = false,
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.List<_i1.ParameterEntry> toForm(
    _i3.String paramName, {
    required _i3.bool explode,
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
    _i3.Map<_i3.String, _i1.FormFieldEncoding> fieldEncodings = const {},
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String toLabel({
    required _i3.bool explode,
    required _i3.bool allowEmpty,
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String toMatrix(
    _i3.String paramName, {
    required _i3.bool explode,
    required _i3.bool allowEmpty,
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.List<_i1.ParameterEntry> toDeepObject(
    _i3.String paramName, {
    required _i3.bool explode,
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.List<_i1.ParameterEntry> toPipeDelimited(
    _i3.String paramName, {
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.List<_i1.ParameterEntry> toSpaceDelimited(
    _i3.String paramName, {
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) => throw _i1.EncodingException(
    r'ConventionStatusAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionStatusAllOfModel &&
        other.statusEnum == this.statusEnum;
  }

  @_i3.override
  _i3.int get hashCode => statusEnum.hashCode;

  $$ConventionStatusAllOfModelCopyWith<ConventionStatusAllOfModel>
  get copyWith => _ConventionStatusAllOfModelCopyWith(this);
}

abstract class $$ConventionStatusAllOfModelCopyWith<$Res> {
  factory $$ConventionStatusAllOfModelCopyWith(
    ConventionStatusAllOfModel value,
  ) = _ConventionStatusAllOfModelCopyWith<$Res>;

  $Res call({_i4.StatusEnum? statusEnum});
  _i4.StatusEnum? get statusEnum;
}

class _ConventionStatusAllOfModelCopyWith<$Res>
    implements $$ConventionStatusAllOfModelCopyWith<$Res> {
  _ConventionStatusAllOfModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ConventionStatusAllOfModel _value;

  @_i3.override
  _i4.StatusEnum? get statusEnum => _value.statusEnum;

  @_i3.override
  $Res call({_i3.Object? statusEnum = _sentinel}) {
    return (ConventionStatusAllOfModel(
      statusEnum: _i3.identical(statusEnum, _sentinel)
          ? this.statusEnum
          : (statusEnum as _i4.StatusEnum?),
    ) as $Res);
  }
}
