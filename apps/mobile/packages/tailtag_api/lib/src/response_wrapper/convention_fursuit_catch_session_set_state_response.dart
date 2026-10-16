// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_convention_id_fursuit_activations_fursuit_id_catch_session_put200_body_model.dart'
    as _i2;

sealed class ConventionFursuitCatchSessionSetStateResponse {
  const ConventionFursuitCatchSessionSetStateResponse();
}

@_i1.immutable
class ConventionFursuitCatchSessionSetStateResponse200
    extends ConventionFursuitCatchSessionSetStateResponse {
  const ConventionFursuitCatchSessionSetStateResponse200({required this.body});

  final _i2.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPut200BodyModel
  body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchSessionSetStateResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchSessionSetStateResponse400
    extends ConventionFursuitCatchSessionSetStateResponse {
  const ConventionFursuitCatchSessionSetStateResponse400();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchSessionSetStateResponse400;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchSessionSetStateResponse401
    extends ConventionFursuitCatchSessionSetStateResponse {
  const ConventionFursuitCatchSessionSetStateResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchSessionSetStateResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchSessionSetStateResponse403
    extends ConventionFursuitCatchSessionSetStateResponse {
  const ConventionFursuitCatchSessionSetStateResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchSessionSetStateResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchSessionSetStateResponse404
    extends ConventionFursuitCatchSessionSetStateResponse {
  const ConventionFursuitCatchSessionSetStateResponse404();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchSessionSetStateResponse404;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ConventionFursuitCatchSessionSetStateResponse405
    extends ConventionFursuitCatchSessionSetStateResponse {
  const ConventionFursuitCatchSessionSetStateResponse405();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionFursuitCatchSessionSetStateResponse405;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
