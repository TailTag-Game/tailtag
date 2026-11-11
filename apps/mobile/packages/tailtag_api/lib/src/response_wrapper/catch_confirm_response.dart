// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_catches_confirm_post400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_catches_confirm_post401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_catches_confirm_post403_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_catches_confirm_post404_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/api_catches_confirm_post409_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_catches_confirm_post500_body_model.dart'
    as _i9;
import 'package:tailtag_api/src/model/catch_confirmation_response_schema.dart'
    as _i2;

sealed class CatchConfirmResponse {
  const CatchConfirmResponse();
}

@_i1.immutable
class CatchConfirmResponse200 extends CatchConfirmResponse {
  const CatchConfirmResponse200({required this.body});

  final _i2.CatchConfirmationResponseSchema body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchConfirmResponse201 extends CatchConfirmResponse {
  const CatchConfirmResponse201({required this.body});

  final _i2.CatchConfirmationResponseSchema body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmResponse201 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchConfirmResponse400 extends CatchConfirmResponse {
  const CatchConfirmResponse400({required this.body});

  final _i4.ApiCatchesConfirmPost400BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmResponse400 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchConfirmResponse401 extends CatchConfirmResponse {
  const CatchConfirmResponse401({required this.body});

  final _i5.ApiCatchesConfirmPost401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmResponse401 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchConfirmResponse403 extends CatchConfirmResponse {
  const CatchConfirmResponse403({required this.body});

  final _i6.ApiCatchesConfirmPost403BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmResponse403 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchConfirmResponse404 extends CatchConfirmResponse {
  const CatchConfirmResponse404({required this.body});

  final _i7.ApiCatchesConfirmPost404BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchConfirmResponse409 extends CatchConfirmResponse {
  const CatchConfirmResponse409({required this.body});

  final _i8.ApiCatchesConfirmPost409BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmResponse409 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchConfirmResponse500 extends CatchConfirmResponse {
  const CatchConfirmResponse500({required this.body});

  final _i9.ApiCatchesConfirmPost500BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmResponse500 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
