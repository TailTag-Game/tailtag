// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_action_error.dart' as _i7;
import 'package:tailtag_api/src/model/catch_request_action_not_found.dart'
    as _i6;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i4;
import 'package:tailtag_api/src/model/detail_error.dart' as _i5;
import 'package:tailtag_api/src/model/owner_request.dart' as _i2;

sealed class CatchIncomingRequestsDeclineResponse {
  const CatchIncomingRequestsDeclineResponse();
}

@_i1.immutable
class CatchIncomingRequestsDeclineResponse200
    extends CatchIncomingRequestsDeclineResponse {
  const CatchIncomingRequestsDeclineResponse200({required this.body});

  final _i2.OwnerRequest body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsDeclineResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsDeclineResponse400
    extends CatchIncomingRequestsDeclineResponse {
  const CatchIncomingRequestsDeclineResponse400({required this.body});

  final _i4.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsDeclineResponse400 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsDeclineResponse401
    extends CatchIncomingRequestsDeclineResponse {
  const CatchIncomingRequestsDeclineResponse401({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsDeclineResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsDeclineResponse403
    extends CatchIncomingRequestsDeclineResponse {
  const CatchIncomingRequestsDeclineResponse403({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsDeclineResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsDeclineResponse404
    extends CatchIncomingRequestsDeclineResponse {
  const CatchIncomingRequestsDeclineResponse404({required this.body});

  final _i6.CatchRequestActionNotFound body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsDeclineResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsDeclineResponse409
    extends CatchIncomingRequestsDeclineResponse {
  const CatchIncomingRequestsDeclineResponse409({required this.body});

  final _i7.CatchRequestActionError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsDeclineResponse409 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsDeclineResponse500
    extends CatchIncomingRequestsDeclineResponse {
  const CatchIncomingRequestsDeclineResponse500({required this.body});

  final _i4.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsDeclineResponse500 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
