// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_put200_body_model.dart'
    as _i2;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_put400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_put401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_put403_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_put404_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_put405_body_model.dart'
    as _i8;

sealed class ConventionFursuitActivationsSetStateResponse {
  const ConventionFursuitActivationsSetStateResponse();
}

@_i1.immutable
class ConventionFursuitActivationsSetStateResponse200
    extends ConventionFursuitActivationsSetStateResponse {
  const ConventionFursuitActivationsSetStateResponse200({required this.body});

  final _i2.ApiConventionsConventionIdFursuitActivationsFursuitIdPut200BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitActivationsSetStateResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitActivationsSetStateResponse400
    extends ConventionFursuitActivationsSetStateResponse {
  const ConventionFursuitActivationsSetStateResponse400({required this.body});

  final _i4.ApiConventionsConventionIdFursuitActivationsFursuitIdPut400BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitActivationsSetStateResponse400 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitActivationsSetStateResponse401
    extends ConventionFursuitActivationsSetStateResponse {
  const ConventionFursuitActivationsSetStateResponse401({required this.body});

  final _i5.ApiConventionsConventionIdFursuitActivationsFursuitIdPut401BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitActivationsSetStateResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitActivationsSetStateResponse403
    extends ConventionFursuitActivationsSetStateResponse {
  const ConventionFursuitActivationsSetStateResponse403({required this.body});

  final _i6.ApiConventionsConventionIdFursuitActivationsFursuitIdPut403BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitActivationsSetStateResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitActivationsSetStateResponse404
    extends ConventionFursuitActivationsSetStateResponse {
  const ConventionFursuitActivationsSetStateResponse404({required this.body});

  final _i7.ApiConventionsConventionIdFursuitActivationsFursuitIdPut404BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitActivationsSetStateResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitActivationsSetStateResponse405
    extends ConventionFursuitActivationsSetStateResponse {
  const ConventionFursuitActivationsSetStateResponse405({required this.body});

  final _i8.ApiConventionsConventionIdFursuitActivationsFursuitIdPut405BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitActivationsSetStateResponse405 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
