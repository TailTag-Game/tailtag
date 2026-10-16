// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_profile_put200_body_model.dart'
    as _i2;

sealed class ProfileUpdateResponse {
  const ProfileUpdateResponse();
}

@_i1.immutable
class ProfileUpdateResponse200 extends ProfileUpdateResponse {
  const ProfileUpdateResponse200({required this.body});

  final _i2.ApiProfilePut200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileUpdateResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ProfileUpdateResponse400 extends ProfileUpdateResponse {
  const ProfileUpdateResponse400();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileUpdateResponse400;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ProfileUpdateResponse401 extends ProfileUpdateResponse {
  const ProfileUpdateResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileUpdateResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ProfileUpdateResponse403 extends ProfileUpdateResponse {
  const ProfileUpdateResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileUpdateResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
