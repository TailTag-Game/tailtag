// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/convention_enrollment_convention_all_of_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// Serializer for convention enrollments.
@_i2.immutable
class ConventionEnrollment extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ConventionEnrollment({
    this.id,
    this.convention,
    this.isActive,
    this.createdAt,
  });

  factory ConventionEnrollment.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ConventionEnrollment: contains complex types',
    );
  }

  factory ConventionEnrollment.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ConventionEnrollment');
    return ConventionEnrollment(
      id: _$map[r'id'].decodeJsonInt(context: r'ConventionEnrollment.id'),
      convention: _i4.ConventionEnrollmentConventionAllOfModel.fromJson(
        _$map[r'convention'],
      ),
      isActive: _$map[r'is_active'].decodeJsonBool(
        context: r'ConventionEnrollment.is_active',
      ),
      createdAt: _$map[r'created_at'].decodeJsonDateTime(
        context: r'ConventionEnrollment.created_at',
      ),
    );
  }

  factory ConventionEnrollment.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ConventionEnrollment: contains complex types',
    );
  }

  final _i3.int? id;

  final _i4.ConventionEnrollmentConventionAllOfModel? convention;

  /// Whether this convention is the player's selected active gameplay convention.
  final _i3.bool? isActive;

  final _i3.DateTime? createdAt;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$ConventionEnrollmentCopyWith<ConventionEnrollment> get copyWith =>
      _ConventionEnrollmentCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionEnrollment &&
        other.id == this.id &&
        other.convention == this.convention &&
        other.isActive == this.isActive &&
        other.createdAt == this.createdAt;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([id, convention, isActive, createdAt]);
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
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ConventionEnrollment: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ConventionEnrollmentCopyWith<$Res> {
  factory $$ConventionEnrollmentCopyWith(ConventionEnrollment value) =
      _ConventionEnrollmentCopyWith<$Res>;

  $Res call({
    _i3.int? id,
    _i4.ConventionEnrollmentConventionAllOfModel? convention,
    _i3.bool? isActive,
    _i3.DateTime? createdAt,
  });
  _i3.int? get id;
  _i4.ConventionEnrollmentConventionAllOfModel? get convention;
  _i3.bool? get isActive;
  _i3.DateTime? get createdAt;
}

class _ConventionEnrollmentCopyWith<$Res>
    implements $$ConventionEnrollmentCopyWith<$Res> {
  _ConventionEnrollmentCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ConventionEnrollment _value;

  @_i3.override
  _i3.int? get id => _value.id;

  @_i3.override
  _i4.ConventionEnrollmentConventionAllOfModel? get convention =>
      _value.convention;

  @_i3.override
  _i3.bool? get isActive => _value.isActive;

  @_i3.override
  _i3.DateTime? get createdAt => _value.createdAt;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? convention = _sentinel,
    _i3.Object? isActive = _sentinel,
    _i3.Object? createdAt = _sentinel,
  }) {
    return (ConventionEnrollment(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      convention: _i3.identical(convention, _sentinel)
          ? this.convention
          : (convention as _i4.ConventionEnrollmentConventionAllOfModel?),
      isActive: _i3.identical(isActive, _sentinel)
          ? this.isActive
          : (isActive as _i3.bool?),
      createdAt: _i3.identical(createdAt, _sentinel)
          ? this.createdAt
          : (createdAt as _i3.DateTime?),
    ) as $Res);
  }
}
