// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_profile_get200_body_model.dart'
    as _i2;

sealed class ProfileRetrieveResponse {
  const ProfileRetrieveResponse();
}

@_i1.immutable
class ProfileRetrieveResponse200 extends ProfileRetrieveResponse {
  const ProfileRetrieveResponse200({required this.body});

  final _i2.ApiProfileGet200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileRetrieveResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ProfileRetrieveResponse401 extends ProfileRetrieveResponse {
  const ProfileRetrieveResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileRetrieveResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ProfileRetrieveResponse403 extends ProfileRetrieveResponse {
  const ProfileRetrieveResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfileRetrieveResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
