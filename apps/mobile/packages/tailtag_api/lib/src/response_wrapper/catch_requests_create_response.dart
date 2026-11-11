// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_catches_requests_post400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i6;
import 'package:tailtag_api/src/model/catch_request_not_found.dart' as _i7;
import 'package:tailtag_api/src/model/catch_request_submission.dart' as _i2;
import 'package:tailtag_api/src/model/detail_error.dart' as _i5;
import 'package:tailtag_api/src/response/api_catches_requests_post429_response.dart'
    as _i8;

sealed class CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse();
}

@_i1.immutable
class CatchRequestsCreateResponse200 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse200({required this.body});

  final _i2.CatchRequestSubmission body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsCreateResponse201 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse201({required this.body});

  final _i2.CatchRequestSubmission body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse201 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsCreateResponse400 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse400({required this.body});

  final _i4.ApiCatchesRequestsPost400BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse400 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsCreateResponse401 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse401({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse401 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsCreateResponse403 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse403({required this.body});

  final _i6.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse403 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsCreateResponse404 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse404({required this.body});

  final _i7.CatchRequestNotFound body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsCreateResponse409 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse409({required this.body});

  final _i6.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse409 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsCreateResponse429 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse429({required this.body});

  final _i8.ApiCatchesRequestsPost429Response body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse429 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsCreateResponse500 extends CatchRequestsCreateResponse {
  const CatchRequestsCreateResponse500({required this.body});

  final _i6.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsCreateResponse500 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
