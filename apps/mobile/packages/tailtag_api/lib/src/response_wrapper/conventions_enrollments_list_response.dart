// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i2;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_enrollments_get401_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/convention_enrollment.dart' as _i3;

sealed class ConventionsEnrollmentsListResponse {
  const ConventionsEnrollmentsListResponse();
}

@_i1.immutable
class ConventionsEnrollmentsListResponse200
    extends ConventionsEnrollmentsListResponse {
  const ConventionsEnrollmentsListResponse200({required this.body});

  final _i2.List<_i3.ConventionEnrollment> body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionsEnrollmentsListResponse200 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsEnrollmentsListResponse401
    extends ConventionsEnrollmentsListResponse {
  const ConventionsEnrollmentsListResponse401({required this.body});

  final _i4.ApiConventionsEnrollmentsGet401BodyModel body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionsEnrollmentsListResponse401 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}
