// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/active_convention_response.dart' as _i2;
import 'package:tailtag_api/src/model/api_conventions_active_get401_body_model.dart'
    as _i4;

sealed class ConventionsActiveRetrieveResponse {
  const ConventionsActiveRetrieveResponse();
}

@_i1.immutable
class ConventionsActiveRetrieveResponse200
    extends ConventionsActiveRetrieveResponse {
  const ConventionsActiveRetrieveResponse200({required this.body});

  final _i2.ActiveConventionResponse body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsActiveRetrieveResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsActiveRetrieveResponse401
    extends ConventionsActiveRetrieveResponse {
  const ConventionsActiveRetrieveResponse401({required this.body});

  final _i4.ApiConventionsActiveGet401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsActiveRetrieveResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
