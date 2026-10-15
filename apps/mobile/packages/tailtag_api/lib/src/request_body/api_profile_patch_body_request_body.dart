// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/patched_profile_patch.dart' as _i2;

@_i1.immutable
sealed class ApiProfilePatchBodyRequestBody {
  const ApiProfilePatchBodyRequestBody();
}

@_i1.immutable
class ApiProfilePatchBodyRequestBodyJson
    extends ApiProfilePatchBodyRequestBody {
  const ApiProfilePatchBodyRequestBodyJson(this.value);

  final _i2.PatchedProfilePatch value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiProfilePatchBodyRequestBodyJson &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}

@_i1.immutable
class ApiProfilePatchBodyRequestBodyXWwwFormUrlencoded
    extends ApiProfilePatchBodyRequestBody {
  const ApiProfilePatchBodyRequestBodyXWwwFormUrlencoded(this.value);

  final _i2.PatchedProfilePatch value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiProfilePatchBodyRequestBodyXWwwFormUrlencoded &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}

@_i1.immutable
class ApiProfilePatchBodyRequestBodyFormData
    extends ApiProfilePatchBodyRequestBody {
  const ApiProfilePatchBodyRequestBodyFormData(this.value);

  final _i2.PatchedProfilePatch value;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiProfilePatchBodyRequestBodyFormData &&
        other.value == this.value;
  }

  @_i3.override
  _i3.int get hashCode => value.hashCode;
}
