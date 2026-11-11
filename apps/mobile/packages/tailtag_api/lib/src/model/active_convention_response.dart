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
  _i3.Object? toJson() => {r'enrollment': enrollment?.toJson()};

  $$ActiveConventionResponseCopyWith<ActiveConventionResponse> get copyWith =>
      _ActiveConventionResponseCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ActiveConventionResponse &&
        other.enrollment == this.enrollment;
  }

  @_i3.override
  _i3.int get hashCode => enrollment.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for ActiveConventionResponse: contains complex types',
  );

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

abstract class $$ActiveConventionResponseCopyWith<$Res> {
  factory $$ActiveConventionResponseCopyWith(ActiveConventionResponse value) =
      _ActiveConventionResponseCopyWith<$Res>;

  $Res call({_i4.ActiveConventionResponseEnrollmentAllOfModel? enrollment});
  _i4.ActiveConventionResponseEnrollmentAllOfModel? get enrollment;
}

class _ActiveConventionResponseCopyWith<$Res>
    implements $$ActiveConventionResponseCopyWith<$Res> {
  _ActiveConventionResponseCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ActiveConventionResponse _value;

  @_i3.override
  _i4.ActiveConventionResponseEnrollmentAllOfModel? get enrollment =>
      _value.enrollment;

  @_i3.override
  $Res call({_i3.Object? enrollment = _sentinel}) {
    return (ActiveConventionResponse(
      enrollment: _i3.identical(enrollment, _sentinel)
          ? this.enrollment
          : (enrollment as _i4.ActiveConventionResponseEnrollmentAllOfModel?),
    ) as $Res);
  }
}
