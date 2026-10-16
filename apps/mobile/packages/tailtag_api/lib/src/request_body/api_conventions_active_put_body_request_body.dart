// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/select_active_convention_request.dart'
    as _i2;

@_i1.immutable
sealed class ApiConventionsActivePutBodyRequestBody {
  const ApiConventionsActivePutBodyRequestBody();
}

@_i1.immutable
class ApiConventionsActivePutBodyRequestBodyJson
    extends ApiConventionsActivePutBodyRequestBody {
  const ApiConventionsActivePutBodyRequestBodyJson(this.value);

  final _i2.SelectActiveConventionRequest value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiConventionsActivePutBodyRequestBodyJson &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}

@_i1.immutable
class ApiConventionsActivePutBodyRequestBodyXWwwFormUrlencoded
    extends ApiConventionsActivePutBodyRequestBody {
  const ApiConventionsActivePutBodyRequestBodyXWwwFormUrlencoded(this.value);

  final _i2.SelectActiveConventionRequest value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiConventionsActivePutBodyRequestBodyXWwwFormUrlencoded &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}

@_i1.immutable
class ApiConventionsActivePutBodyRequestBodyFormData
    extends ApiConventionsActivePutBodyRequestBody {
  const ApiConventionsActivePutBodyRequestBodyFormData(this.value);

  final _i2.SelectActiveConventionRequest value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiConventionsActivePutBodyRequestBodyFormData &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}
