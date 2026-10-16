// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/active_convention_response.dart' as _i2;
import 'package:tailtag_api/src/model/api_conventions_active_put400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_conventions_active_put401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_conventions_active_put403_body_model.dart'
    as _i6;

sealed class ConventionsActiveUpdateResponse {
  const ConventionsActiveUpdateResponse();
}

@_i1.immutable
class ConventionsActiveUpdateResponse200
    extends ConventionsActiveUpdateResponse {
  const ConventionsActiveUpdateResponse200({required this.body});

  final _i2.ActiveConventionResponse body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsActiveUpdateResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsActiveUpdateResponse400
    extends ConventionsActiveUpdateResponse {
  const ConventionsActiveUpdateResponse400({required this.body});

  final _i4.ApiConventionsActivePut400BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsActiveUpdateResponse400 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsActiveUpdateResponse401
    extends ConventionsActiveUpdateResponse {
  const ConventionsActiveUpdateResponse401({required this.body});

  final _i5.ApiConventionsActivePut401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsActiveUpdateResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsActiveUpdateResponse403
    extends ConventionsActiveUpdateResponse {
  const ConventionsActiveUpdateResponse403({required this.body});

  final _i6.ApiConventionsActivePut403BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsActiveUpdateResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
