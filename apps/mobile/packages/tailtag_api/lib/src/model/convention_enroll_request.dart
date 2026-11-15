// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// Request serializer for enrolling into an active convention.
@_i2.immutable
class ConventionEnrollRequest extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ConventionEnrollRequest({
    required this.conventionId,
    this.setActive = setActiveDefault,
  });

  factory ConventionEnrollRequest.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'convention_id', r'set_active'},
      listKeys: {},
      context: r'ConventionEnrollRequest',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return ConventionEnrollRequest(
      conventionId: _$values[r'convention_id'].decodeSimpleInt(
        context: r'ConventionEnrollRequest.convention_id',
      ),
      setActive: _$values.containsKey(r'set_active')
          ? _$values[r'set_active'].decodeSimpleBool(
              context: r'ConventionEnrollRequest.set_active',
            )
          : setActiveDefault,
    );
  }

  factory ConventionEnrollRequest.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ConventionEnrollRequest');
    return ConventionEnrollRequest(
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'ConventionEnrollRequest.convention_id',
      ),
      setActive: _$map.containsKey(r'set_active')
          ? _$map[r'set_active'].decodeJsonBool(
              context: r'ConventionEnrollRequest.set_active',
            )
          : setActiveDefault,
    );
  }

  factory ConventionEnrollRequest.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'convention_id', r'set_active'},
      listKeys: {},
      context: r'ConventionEnrollRequest',
    );
    return ConventionEnrollRequest(
      conventionId: _$values[r'convention_id'].decodeFormInt(
        context: r'ConventionEnrollRequest.convention_id',
      ),
      setActive: _$values.containsKey(r'set_active')
          ? _$values[r'set_active'].decodeFormBool(
              context: r'ConventionEnrollRequest.set_active',
            )
          : setActiveDefault,
    );
  }

  static const _i3.bool setActiveDefault = false;

  final _i3.int conventionId;

  final _i3.bool? setActive;

  @_i3.override
  _i3.Object? toJson() => {
    r'convention_id': this.conventionId,
    if (this.setActive != null) r'set_active': this.setActive,
  };

  ConventionEnrollRequest Function({_i3.int? conventionId, _i3.bool? setActive})
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({_i3.int? conventionId, _i3.Object? setActive = _sentinel}) =>
        ConventionEnrollRequest(
          conventionId: conventionId ?? this.conventionId,
          setActive: _i3.identical(setActive, _sentinel)
              ? this.setActive
              : (setActive as _i3.bool?),
        );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionEnrollRequest &&
        other.conventionId == this.conventionId &&
        other.setActive == this.setActive;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([this.conventionId, this.setActive]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'convention_id'] = _i1.PropertyValue.scalar(
      this.conventionId.toString(),
    );
    if (this.setActive != null) {
      _$result[r'set_active'] = _i1.PropertyValue.scalar(
        this.setActive!.toString(),
      );
    }
    return _$result;
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i4.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ConventionEnrollRequest: complex types cannot be URI-encoded',
    );
  }
}
