// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i2;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_get200_body_array_model.dart'
    as _i3;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_get401_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_get404_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_get405_body_model.dart'
    as _i6;

sealed class ConventionFursuitActivationsListResponse {
  const ConventionFursuitActivationsListResponse();
}

@_i1.immutable
class ConventionFursuitActivationsListResponse200
    extends ConventionFursuitActivationsListResponse {
  const ConventionFursuitActivationsListResponse200({required this.body});

  final _i2.List<
    _i3.ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel
  >
  body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionFursuitActivationsListResponse200 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitActivationsListResponse401
    extends ConventionFursuitActivationsListResponse {
  const ConventionFursuitActivationsListResponse401({required this.body});

  final _i4.ApiConventionsConventionIdFursuitActivationsGet401BodyModel body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionFursuitActivationsListResponse401 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitActivationsListResponse404
    extends ConventionFursuitActivationsListResponse {
  const ConventionFursuitActivationsListResponse404({required this.body});

  final _i5.ApiConventionsConventionIdFursuitActivationsGet404BodyModel body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionFursuitActivationsListResponse404 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitActivationsListResponse405
    extends ConventionFursuitActivationsListResponse {
  const ConventionFursuitActivationsListResponse405({required this.body});

  final _i6.ApiConventionsConventionIdFursuitActivationsGet405BodyModel body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionFursuitActivationsListResponse405 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}
