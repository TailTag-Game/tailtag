// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_profile_avatar_put200_body_model.dart'
    as _i2;

sealed class ProfileAvatarUpdateResponse {
  const ProfileAvatarUpdateResponse();
}

@_i1.immutable
class ProfileAvatarUpdateResponse200 extends ProfileAvatarUpdateResponse {
  const ProfileAvatarUpdateResponse200({required this.body});

  final _i2.ApiProfileAvatarPut200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileAvatarUpdateResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ProfileAvatarUpdateResponse400 extends ProfileAvatarUpdateResponse {
  const ProfileAvatarUpdateResponse400();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileAvatarUpdateResponse400;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ProfileAvatarUpdateResponse401 extends ProfileAvatarUpdateResponse {
  const ProfileAvatarUpdateResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileAvatarUpdateResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ProfileAvatarUpdateResponse403 extends ProfileAvatarUpdateResponse {
  const ProfileAvatarUpdateResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileAvatarUpdateResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
