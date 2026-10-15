// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/convention_enrollment.dart' as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class $RawActiveConventionResponseEnrollmentAllOfModel
    implements _i1.ParameterEncodable, _i1.UriEncodable {
  const $RawActiveConventionResponseEnrollmentAllOfModel({
    required this.conventionEnrollment,
  });

  factory $RawActiveConventionResponseEnrollmentAllOfModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    return $RawActiveConventionResponseEnrollmentAllOfModel(
      conventionEnrollment: _i4.ConventionEnrollment.fromSimple(
        value,
        explode: explode,
      ),
    );
  }

  factory $RawActiveConventionResponseEnrollmentAllOfModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    return $RawActiveConventionResponseEnrollmentAllOfModel(
      conventionEnrollment: _i4.ConventionEnrollment.fromForm(
        value,
        explode: explode,
      ),
    );
  }

  factory $RawActiveConventionResponseEnrollmentAllOfModel.fromJson(
    _i3.Object? json,
  ) {
    return $RawActiveConventionResponseEnrollmentAllOfModel(
      conventionEnrollment: _i4.ConventionEnrollment.fromJson(json),
    );
  }

  final _i4.ConventionEnrollment conventionEnrollment;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Object? toJson() {
    final _$map = <_i3.String, _i3.Object?>{};
    final _$conventionEnrollmentJson = conventionEnrollment.toJson();
    if (_$conventionEnrollmentJson is! _i3.Map<_i3.String, _i3.Object?>) {
      throw _i1.EncodingException(
        'Expected conventionEnrollment.toJson() to return Map<String, Object?>, got ${_$conventionEnrollmentJson.runtimeType}',
      );
    }
    _$map.addAll(_$conventionEnrollmentJson);
    return _$map;
  }

  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$mergedProperties = <_i3.String, _i1.PropertyValue>{};
    _$mergedProperties.addAll(
      conventionEnrollment.parameterProperties(allowEmpty: allowEmpty),
    );
    return _$mergedProperties;
  }

  @_i3.override
  _i3.String toSimple({
    required _i3.bool explode,
    required _i3.bool allowEmpty,
    _i3.bool literal = false,
  }) {
    return parameterProperties(allowEmpty: allowEmpty)
        .toSimple(explode: explode, allowEmpty: allowEmpty, literal: literal);
  }

  @_i3.override
  _i3.List<_i1.ParameterEntry> toForm(
    _i3.String paramName, {
    required _i3.bool explode,
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
    _i3.Map<_i3.String, _i1.FormFieldEncoding> fieldEncodings = const {},
  }) {
    return parameterProperties(allowEmpty: allowEmpty).toForm(
      paramName,
      explode: explode,
      allowEmpty: allowEmpty,
      useQueryComponent: useQueryComponent,
      allowReserved: allowReserved,
      fieldEncodings: fieldEncodings,
      textEncoding: textEncoding,
    );
  }

  @_i3.override
  _i3.String toLabel({
    required _i3.bool explode,
    required _i3.bool allowEmpty,
  }) {
    return parameterProperties(allowEmpty: allowEmpty)
        .toLabel(explode: explode, allowEmpty: allowEmpty);
  }

  @_i3.override
  _i3.String toMatrix(
    _i3.String paramName, {
    required _i3.bool explode,
    required _i3.bool allowEmpty,
  }) {
    return parameterProperties(allowEmpty: allowEmpty)
        .toMatrix(paramName, explode: explode, allowEmpty: allowEmpty);
  }

  @_i3.override
  _i3.List<_i1.ParameterEntry> toDeepObject(
    _i3.String paramName, {
    required _i3.bool explode,
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) {
    return parameterProperties(allowEmpty: allowEmpty).toDeepObject(
      paramName,
      explode: explode,
      allowEmpty: allowEmpty,
      allowReserved: allowReserved,
    );
  }

  @_i3.override
  _i3.List<_i1.ParameterEntry> toPipeDelimited(
    _i3.String paramName, {
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) {
    return parameterProperties(allowEmpty: allowEmpty).toPipeDelimited(
      paramName,
      allowEmpty: allowEmpty,
      allowReserved: allowReserved,
    );
  }

  @_i3.override
  _i3.List<_i1.ParameterEntry> toSpaceDelimited(
    _i3.String paramName, {
    required _i3.bool allowEmpty,
    _i3.bool allowReserved = false,
  }) {
    return parameterProperties(allowEmpty: allowEmpty).toSpaceDelimited(
      paramName,
      allowEmpty: allowEmpty,
      allowReserved: allowReserved,
    );
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode $RawActiveConventionResponseEnrollmentAllOfModel: contains complex types',
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is $RawActiveConventionResponseEnrollmentAllOfModel &&
        other.conventionEnrollment == this.conventionEnrollment;
  }

  @_i3.override
  _i3.int get hashCode => conventionEnrollment.hashCode;

  $$$RawActiveConventionResponseEnrollmentAllOfModelCopyWith<
    $RawActiveConventionResponseEnrollmentAllOfModel
  >
  get copyWith =>
      _$RawActiveConventionResponseEnrollmentAllOfModelCopyWith(this);
}

abstract class $$$RawActiveConventionResponseEnrollmentAllOfModelCopyWith<
  $Res
> {
  factory $$$RawActiveConventionResponseEnrollmentAllOfModelCopyWith(
    $RawActiveConventionResponseEnrollmentAllOfModel value,
  ) = _$RawActiveConventionResponseEnrollmentAllOfModelCopyWith<$Res>;

  $Res call({_i4.ConventionEnrollment? conventionEnrollment});
  _i4.ConventionEnrollment get conventionEnrollment;
}

class _$RawActiveConventionResponseEnrollmentAllOfModelCopyWith<$Res>
    implements
        $$$RawActiveConventionResponseEnrollmentAllOfModelCopyWith<$Res> {
  _$RawActiveConventionResponseEnrollmentAllOfModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final $RawActiveConventionResponseEnrollmentAllOfModel _value;

  @_i3.override
  _i4.ConventionEnrollment get conventionEnrollment =>
      _value.conventionEnrollment;

  @_i3.override
  $Res call({_i3.Object? conventionEnrollment = _sentinel}) {
    return ($RawActiveConventionResponseEnrollmentAllOfModel(
      conventionEnrollment: _i3.identical(conventionEnrollment, _sentinel)
          ? this.conventionEnrollment
          : (conventionEnrollment as _i4.ConventionEnrollment),
    ) as $Res);
  }
}

typedef ActiveConventionResponseEnrollmentAllOfModel =
    $RawActiveConventionResponseEnrollmentAllOfModel?;
