// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/convention.dart' as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ConventionEnrollmentConventionAllOfModel
    implements _i1.ParameterEncodable, _i1.UriEncodable {
  const ConventionEnrollmentConventionAllOfModel({this.convention});

  factory ConventionEnrollmentConventionAllOfModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    return ConventionEnrollmentConventionAllOfModel(
      convention: _i4.Convention.fromSimple(value, explode: explode),
    );
  }

  factory ConventionEnrollmentConventionAllOfModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    return ConventionEnrollmentConventionAllOfModel(
      convention: _i4.Convention.fromForm(value, explode: explode),
    );
  }

  factory ConventionEnrollmentConventionAllOfModel.fromJson(_i3.Object? json) {
    return ConventionEnrollmentConventionAllOfModel(
      convention: _i4.Convention.fromJson(json),
    );
  }

  final _i4.Convention? convention;

  _i1.EncodingShape get currentEncodingShape => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.Object? toJson() => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String toSimple({
    required _i3.bool explode,
    required _i3.bool allowEmpty,
    _i3.bool literal = false,
  }) => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
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
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String toLabel({
    required _i3.bool explode,
    required _i3.bool allowEmpty,
  }) => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String toMatrix(
    _i3.String paramName, {
    required _i3.bool explode,
    required _i3.bool allowEmpty,
  }) => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.List<_i1.ParameterEntry> toDeepObject(
    _i3.String paramName, {
    required _i3.bool explode,
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.List<_i1.ParameterEntry> toPipeDelimited(
    _i3.String paramName, {
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.List<_i1.ParameterEntry> toSpaceDelimited(
    _i3.String paramName, {
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) => throw _i1.EncodingException(
    r'ConventionEnrollmentConventionAllOfModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionEnrollmentConventionAllOfModel &&
        other.convention == this.convention;
  }

  @_i3.override
  _i3.int get hashCode => convention.hashCode;

  $$ConventionEnrollmentConventionAllOfModelCopyWith<
    ConventionEnrollmentConventionAllOfModel
  >
  get copyWith => _ConventionEnrollmentConventionAllOfModelCopyWith(this);
}

abstract class $$ConventionEnrollmentConventionAllOfModelCopyWith<$Res> {
  factory $$ConventionEnrollmentConventionAllOfModelCopyWith(
    ConventionEnrollmentConventionAllOfModel value,
  ) = _ConventionEnrollmentConventionAllOfModelCopyWith<$Res>;

  $Res call({_i4.Convention? convention});
  _i4.Convention? get convention;
}

class _ConventionEnrollmentConventionAllOfModelCopyWith<$Res>
    implements $$ConventionEnrollmentConventionAllOfModelCopyWith<$Res> {
  _ConventionEnrollmentConventionAllOfModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ConventionEnrollmentConventionAllOfModel _value;

  @_i3.override
  _i4.Convention? get convention => _value.convention;

  @_i3.override
  $Res call({_i3.Object? convention = _sentinel}) {
    return (ConventionEnrollmentConventionAllOfModel(
      convention: _i3.identical(convention, _sentinel)
          ? this.convention
          : (convention as _i4.Convention?),
    ) as $Res);
  }
}
