// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_enrollments_post400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_conventions_enrollments_post401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_conventions_enrollments_post403_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_conventions_enrollments_post404_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/convention_enrollment.dart' as _i2;

sealed class ConventionsEnrollmentsCreateResponse {
  const ConventionsEnrollmentsCreateResponse();
}

@_i1.immutable
class ConventionsEnrollmentsCreateResponse200
    extends ConventionsEnrollmentsCreateResponse {
  const ConventionsEnrollmentsCreateResponse200({required this.body});

  final _i2.ConventionEnrollment body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsEnrollmentsCreateResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsEnrollmentsCreateResponse201
    extends ConventionsEnrollmentsCreateResponse {
  const ConventionsEnrollmentsCreateResponse201({required this.body});

  final _i2.ConventionEnrollment body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsEnrollmentsCreateResponse201 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsEnrollmentsCreateResponse400
    extends ConventionsEnrollmentsCreateResponse {
  const ConventionsEnrollmentsCreateResponse400({required this.body});

  final _i4.ApiConventionsEnrollmentsPost400BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsEnrollmentsCreateResponse400 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsEnrollmentsCreateResponse401
    extends ConventionsEnrollmentsCreateResponse {
  const ConventionsEnrollmentsCreateResponse401({required this.body});

  final _i5.ApiConventionsEnrollmentsPost401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsEnrollmentsCreateResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsEnrollmentsCreateResponse403
    extends ConventionsEnrollmentsCreateResponse {
  const ConventionsEnrollmentsCreateResponse403({required this.body});

  final _i6.ApiConventionsEnrollmentsPost403BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsEnrollmentsCreateResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsEnrollmentsCreateResponse404
    extends ConventionsEnrollmentsCreateResponse {
  const ConventionsEnrollmentsCreateResponse404({required this.body});

  final _i7.ApiConventionsEnrollmentsPost404BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsEnrollmentsCreateResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
