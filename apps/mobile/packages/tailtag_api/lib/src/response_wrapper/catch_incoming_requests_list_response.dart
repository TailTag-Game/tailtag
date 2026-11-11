// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i4;
import 'package:tailtag_api/src/model/detail_error.dart' as _i5;
import 'package:tailtag_api/src/model/owner_request_list.dart' as _i2;

sealed class CatchIncomingRequestsListResponse {
  const CatchIncomingRequestsListResponse();
}

@_i1.immutable
class CatchIncomingRequestsListResponse200
    extends CatchIncomingRequestsListResponse {
  const CatchIncomingRequestsListResponse200({required this.body});

  final _i2.OwnerRequestList body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsListResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsListResponse400
    extends CatchIncomingRequestsListResponse {
  const CatchIncomingRequestsListResponse400({required this.body});

  final _i4.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsListResponse400 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsListResponse401
    extends CatchIncomingRequestsListResponse {
  const CatchIncomingRequestsListResponse401({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsListResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsListResponse403
    extends CatchIncomingRequestsListResponse {
  const CatchIncomingRequestsListResponse403({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsListResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsListResponse404
    extends CatchIncomingRequestsListResponse {
  const CatchIncomingRequestsListResponse404({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsListResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsListResponse500
    extends CatchIncomingRequestsListResponse {
  const CatchIncomingRequestsListResponse500({required this.body});

  final _i4.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsListResponse500 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
