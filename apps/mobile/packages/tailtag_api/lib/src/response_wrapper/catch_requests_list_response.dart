// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_catches_requests_get200_body_model.dart'
    as _i2;
import 'package:tailtag_api/src/model/api_catches_requests_get400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_catches_requests_get401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_catches_requests_get403_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_catches_requests_get404_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/api_catches_requests_get500_body_model.dart'
    as _i8;

sealed class CatchRequestsListResponse {
  const CatchRequestsListResponse();
}

@_i1.immutable
class CatchRequestsListResponse200 extends CatchRequestsListResponse {
  const CatchRequestsListResponse200({required this.body});

  final _i2.ApiCatchesRequestsGet200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsListResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsListResponse400 extends CatchRequestsListResponse {
  const CatchRequestsListResponse400({required this.body});

  final _i4.ApiCatchesRequestsGet400BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsListResponse400 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsListResponse401 extends CatchRequestsListResponse {
  const CatchRequestsListResponse401({required this.body});

  final _i5.ApiCatchesRequestsGet401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsListResponse401 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsListResponse403 extends CatchRequestsListResponse {
  const CatchRequestsListResponse403({required this.body});

  final _i6.ApiCatchesRequestsGet403BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsListResponse403 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsListResponse404 extends CatchRequestsListResponse {
  const CatchRequestsListResponse404({required this.body});

  final _i7.ApiCatchesRequestsGet404BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsListResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsListResponse500 extends CatchRequestsListResponse {
  const CatchRequestsListResponse500({required this.body});

  final _i8.ApiCatchesRequestsGet500BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsListResponse500 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
