// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_action_error.dart' as _i5;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i6;
import 'package:tailtag_api/src/model/detail_error.dart' as _i4;
import 'package:tailtag_api/src/model/owner_approval.dart' as _i2;

sealed class CatchIncomingRequestsApproveResponse {
  const CatchIncomingRequestsApproveResponse();
}

@_i1.immutable
class CatchIncomingRequestsApproveResponse200
    extends CatchIncomingRequestsApproveResponse {
  const CatchIncomingRequestsApproveResponse200({required this.body});

  final _i2.OwnerApproval body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsApproveResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsApproveResponse401
    extends CatchIncomingRequestsApproveResponse {
  const CatchIncomingRequestsApproveResponse401({required this.body});

  final _i4.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsApproveResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsApproveResponse403
    extends CatchIncomingRequestsApproveResponse {
  const CatchIncomingRequestsApproveResponse403({required this.body});

  final _i4.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsApproveResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsApproveResponse404
    extends CatchIncomingRequestsApproveResponse {
  const CatchIncomingRequestsApproveResponse404({required this.body});

  final _i5.CatchRequestActionError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsApproveResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsApproveResponse409
    extends CatchIncomingRequestsApproveResponse {
  const CatchIncomingRequestsApproveResponse409({required this.body});

  final _i5.CatchRequestActionError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsApproveResponse409 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsApproveResponse500
    extends CatchIncomingRequestsApproveResponse {
  const CatchIncomingRequestsApproveResponse500({required this.body});

  final _i6.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsApproveResponse500 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
