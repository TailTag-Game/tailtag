// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_profile_patch200_body_model.dart'
    as _i2;

sealed class ProfilePartialUpdateResponse {
  const ProfilePartialUpdateResponse();
}

@_i1.immutable
class ProfilePartialUpdateResponse200 extends ProfilePartialUpdateResponse {
  const ProfilePartialUpdateResponse200({required this.body});

  final _i2.ApiProfilePatch200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfilePartialUpdateResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ProfilePartialUpdateResponse400 extends ProfilePartialUpdateResponse {
  const ProfilePartialUpdateResponse400();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfilePartialUpdateResponse400;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ProfilePartialUpdateResponse401 extends ProfilePartialUpdateResponse {
  const ProfilePartialUpdateResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfilePartialUpdateResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ProfilePartialUpdateResponse403 extends ProfilePartialUpdateResponse {
  const ProfilePartialUpdateResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfilePartialUpdateResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
