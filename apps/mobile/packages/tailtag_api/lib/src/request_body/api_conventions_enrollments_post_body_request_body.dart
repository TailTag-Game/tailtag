// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/convention_enroll_request.dart' as _i2;

@_i1.immutable
sealed class ApiConventionsEnrollmentsPostBodyRequestBody {
  const ApiConventionsEnrollmentsPostBodyRequestBody();
}

@_i1.immutable
class ApiConventionsEnrollmentsPostBodyRequestBodyJson
    extends ApiConventionsEnrollmentsPostBodyRequestBody {
  const ApiConventionsEnrollmentsPostBodyRequestBodyJson(this.value);

  final _i2.ConventionEnrollRequest value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiConventionsEnrollmentsPostBodyRequestBodyJson &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}

@_i1.immutable
class ApiConventionsEnrollmentsPostBodyRequestBodyXWwwFormUrlencoded
    extends ApiConventionsEnrollmentsPostBodyRequestBody {
  const ApiConventionsEnrollmentsPostBodyRequestBodyXWwwFormUrlencoded(
    this.value,
  );

  final _i2.ConventionEnrollRequest value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsEnrollmentsPostBodyRequestBodyXWwwFormUrlencoded &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}

@_i1.immutable
class ApiConventionsEnrollmentsPostBodyRequestBodyFormData
    extends ApiConventionsEnrollmentsPostBodyRequestBody {
  const ApiConventionsEnrollmentsPostBodyRequestBodyFormData(this.value);

  final _i2.ConventionEnrollRequest value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiConventionsEnrollmentsPostBodyRequestBodyFormData &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}
