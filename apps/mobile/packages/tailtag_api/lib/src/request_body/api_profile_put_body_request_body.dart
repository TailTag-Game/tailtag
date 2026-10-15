// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/profile_put.dart' as _i2;

@_i1.immutable
sealed class ApiProfilePutBodyRequestBody {
  const ApiProfilePutBodyRequestBody();
}

@_i1.immutable
class ApiProfilePutBodyRequestBodyJson extends ApiProfilePutBodyRequestBody {
  const ApiProfilePutBodyRequestBodyJson(this.value);

  final _i2.ProfilePut value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiProfilePutBodyRequestBodyJson &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}

@_i1.immutable
class ApiProfilePutBodyRequestBodyXWwwFormUrlencoded
    extends ApiProfilePutBodyRequestBody {
  const ApiProfilePutBodyRequestBodyXWwwFormUrlencoded(this.value);

  final _i2.ProfilePut value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiProfilePutBodyRequestBodyXWwwFormUrlencoded &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}

@_i1.immutable
class ApiProfilePutBodyRequestBodyFormData
    extends ApiProfilePutBodyRequestBody {
  const ApiProfilePutBodyRequestBodyFormData(this.value);

  final _i2.ProfilePut value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiProfilePutBodyRequestBodyFormData &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}
