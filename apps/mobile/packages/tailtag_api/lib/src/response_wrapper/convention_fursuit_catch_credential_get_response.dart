// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get200_body_model.dart'
    as _i2;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get403_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get404_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_credential_get405_body_model.dart'
    as _i8;

sealed class ConventionFursuitCatchCredentialGetResponse {
  const ConventionFursuitCatchCredentialGetResponse();
}

@_i1.immutable
class ConventionFursuitCatchCredentialGetResponse200
    extends ConventionFursuitCatchCredentialGetResponse {
  const ConventionFursuitCatchCredentialGetResponse200({required this.body});

  final _i2.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialGetResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialGetResponse400
    extends ConventionFursuitCatchCredentialGetResponse {
  const ConventionFursuitCatchCredentialGetResponse400({required this.body});

  final _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet400BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialGetResponse400 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialGetResponse401
    extends ConventionFursuitCatchCredentialGetResponse {
  const ConventionFursuitCatchCredentialGetResponse401({required this.body});

  final _i5.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet401BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialGetResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialGetResponse403
    extends ConventionFursuitCatchCredentialGetResponse {
  const ConventionFursuitCatchCredentialGetResponse403({required this.body});

  final _i6.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet403BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialGetResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialGetResponse404
    extends ConventionFursuitCatchCredentialGetResponse {
  const ConventionFursuitCatchCredentialGetResponse404({required this.body});

  final _i7.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet404BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialGetResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchCredentialGetResponse405
    extends ConventionFursuitCatchCredentialGetResponse {
  const ConventionFursuitCatchCredentialGetResponse405({required this.body});

  final _i8.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet405BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchCredentialGetResponse405 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
