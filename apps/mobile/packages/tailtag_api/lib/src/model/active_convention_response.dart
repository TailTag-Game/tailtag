// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/active_convention_response_enrollment_all_of_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// Response wrapper for active convention enrollment query.
@_i2.immutable
class ActiveConventionResponse extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ActiveConventionResponse({required this.enrollment});

  factory ActiveConventionResponse.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ActiveConventionResponse: contains complex types',
    );
  }

  factory ActiveConventionResponse.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ActiveConventionResponse');
    return ActiveConventionResponse(
      enrollment: _$map[r'enrollment'] == null
          ? null
          : _i4.ActiveConventionResponseEnrollmentAllOfModel.fromJson(
              _$map[r'enrollment'],
            ),
    );
  }

  factory ActiveConventionResponse.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ActiveConventionResponse: contains complex types',
    );
  }

  final _i4.ActiveConventionResponseEnrollmentAllOfModel? enrollment;

  @_i3.override
  _i3.Object? toJson() => {r'enrollment': this.enrollment?.toJson()};

  ActiveConventionResponse Function({
    _i4.ActiveConventionResponseEnrollmentAllOfModel? enrollment,
  })
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({_i3.Object? enrollment = _sentinel}) => ActiveConventionResponse(
      enrollment: _i3.identical(enrollment, _sentinel)
          ? this.enrollment
          : (enrollment as _i4.ActiveConventionResponseEnrollmentAllOfModel?),
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ActiveConventionResponse &&
        other.enrollment == this.enrollment;
  }

  @_i3.override
  _i3.int get hashCode => this.enrollment.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    if (this.enrollment != null) {
      _$result[r'enrollment'] = _i1.encodeAnyValueToPropertyValue(
        this.enrollment!.toJson(),
        allowEmpty: allowEmpty,
      );
    }
    return _$result;
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ActiveConventionResponse: complex types cannot be URI-encoded',
    );
  }
}
