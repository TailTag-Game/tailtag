// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_action_error.dart' as _i6;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i5;
import 'package:tailtag_api/src/model/detail_error.dart' as _i4;
import 'package:tailtag_api/src/model/player_request.dart' as _i2;

sealed class CatchRequestsWithdrawResponse {
  const CatchRequestsWithdrawResponse();
}

@_i1.immutable
class CatchRequestsWithdrawResponse200 extends CatchRequestsWithdrawResponse {
  const CatchRequestsWithdrawResponse200({required this.body});

  final _i2.PlayerRequest body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsWithdrawResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsWithdrawResponse401 extends CatchRequestsWithdrawResponse {
  const CatchRequestsWithdrawResponse401({required this.body});

  final _i4.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsWithdrawResponse401 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsWithdrawResponse403 extends CatchRequestsWithdrawResponse {
  const CatchRequestsWithdrawResponse403({required this.body});

  final _i5.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsWithdrawResponse403 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsWithdrawResponse404 extends CatchRequestsWithdrawResponse {
  const CatchRequestsWithdrawResponse404({required this.body});

  final _i6.CatchRequestActionError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsWithdrawResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsWithdrawResponse409 extends CatchRequestsWithdrawResponse {
  const CatchRequestsWithdrawResponse409({required this.body});

  final _i6.CatchRequestActionError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsWithdrawResponse409 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchRequestsWithdrawResponse500 extends CatchRequestsWithdrawResponse {
  const CatchRequestsWithdrawResponse500({required this.body});

  final _i5.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsWithdrawResponse500 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
