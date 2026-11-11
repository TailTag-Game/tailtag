// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post200_body_model.dart'
    as _i2;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post403_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post404_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/api_conventions_convention_id_catch_credentials_resolve_post405_body_model.dart'
    as _i8;

sealed class ConventionFursuitCatchCredentialResolveResponse {
  const ConventionFursuitCatchCredentialResolveResponse();
}

@_i1.immutable
class ConventionFursuitCatchCredentialResolveResponse200
    extends ConventionFursuitCatchCredentialResolveResponse {
  const ConventionFursuitCatchCredentialResolveResponse200({
    required this.body,
  });

  final _i2.ApiConventionsConventionIdCatchCredentialsResolvePost200BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialResolveResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialResolveResponse400
    extends ConventionFursuitCatchCredentialResolveResponse {
  const ConventionFursuitCatchCredentialResolveResponse400({
    required this.body,
  });

  final _i4.ApiConventionsConventionIdCatchCredentialsResolvePost400BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialResolveResponse400 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialResolveResponse401
    extends ConventionFursuitCatchCredentialResolveResponse {
  const ConventionFursuitCatchCredentialResolveResponse401({
    required this.body,
  });

  final _i5.ApiConventionsConventionIdCatchCredentialsResolvePost401BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialResolveResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialResolveResponse403
    extends ConventionFursuitCatchCredentialResolveResponse {
  const ConventionFursuitCatchCredentialResolveResponse403({
    required this.body,
  });

  final _i6.ApiConventionsConventionIdCatchCredentialsResolvePost403BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialResolveResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialResolveResponse404
    extends ConventionFursuitCatchCredentialResolveResponse {
  const ConventionFursuitCatchCredentialResolveResponse404({
    required this.body,
  });

  final _i7.ApiConventionsConventionIdCatchCredentialsResolvePost404BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialResolveResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialResolveResponse405
    extends ConventionFursuitCatchCredentialResolveResponse {
  const ConventionFursuitCatchCredentialResolveResponse405({
    required this.body,
  });

  final _i8.ApiConventionsConventionIdCatchCredentialsResolvePost405BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialResolveResponse405 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
