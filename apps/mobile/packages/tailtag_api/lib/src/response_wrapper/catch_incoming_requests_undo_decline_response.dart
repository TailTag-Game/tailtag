// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_action_error.dart' as _i6;
import 'package:tailtag_api/src/model/catch_request_action_not_found.dart'
    as _i5;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i7;
import 'package:tailtag_api/src/model/detail_error.dart' as _i4;
import 'package:tailtag_api/src/model/owner_request.dart' as _i2;

sealed class CatchIncomingRequestsUndoDeclineResponse {
  const CatchIncomingRequestsUndoDeclineResponse();
}

@_i1.immutable
class CatchIncomingRequestsUndoDeclineResponse200
    extends CatchIncomingRequestsUndoDeclineResponse {
  const CatchIncomingRequestsUndoDeclineResponse200({required this.body});

  final _i2.OwnerRequest body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsUndoDeclineResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUndoDeclineResponse401
    extends CatchIncomingRequestsUndoDeclineResponse {
  const CatchIncomingRequestsUndoDeclineResponse401({required this.body});

  final _i4.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsUndoDeclineResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUndoDeclineResponse403
    extends CatchIncomingRequestsUndoDeclineResponse {
  const CatchIncomingRequestsUndoDeclineResponse403({required this.body});

  final _i4.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsUndoDeclineResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUndoDeclineResponse404
    extends CatchIncomingRequestsUndoDeclineResponse {
  const CatchIncomingRequestsUndoDeclineResponse404({required this.body});

  final _i5.CatchRequestActionNotFound body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsUndoDeclineResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUndoDeclineResponse409
    extends CatchIncomingRequestsUndoDeclineResponse {
  const CatchIncomingRequestsUndoDeclineResponse409({required this.body});

  final _i6.CatchRequestActionError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsUndoDeclineResponse409 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUndoDeclineResponse500
    extends CatchIncomingRequestsUndoDeclineResponse {
  const CatchIncomingRequestsUndoDeclineResponse500({required this.body});

  final _i7.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsUndoDeclineResponse500 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
