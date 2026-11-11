// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_me_get200_body_model.dart' as _i2;
import 'package:tailtag_api/src/model/api_me_get401_body_model.dart' as _i4;

sealed class MeRetrieveResponse {
  const MeRetrieveResponse();
}

@_i1.immutable
class MeRetrieveResponse200 extends MeRetrieveResponse {
  const MeRetrieveResponse200({required this.body});

  final _i2.ApiMeGet200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is MeRetrieveResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class MeRetrieveResponse401 extends MeRetrieveResponse {
  const MeRetrieveResponse401({required this.body});

  final _i4.ApiMeGet401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is MeRetrieveResponse401 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
