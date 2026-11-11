// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i2;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_action_error.dart' as _i4;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i5;
import 'package:tailtag_api/src/model/detail_error.dart' as _i3;

sealed class CatchIncomingRequestsUnblockResponse {
  const CatchIncomingRequestsUnblockResponse();
}

@_i1.immutable
class CatchIncomingRequestsUnblockResponse204
    extends CatchIncomingRequestsUnblockResponse {
  const CatchIncomingRequestsUnblockResponse204();

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is CatchIncomingRequestsUnblockResponse204;
  }

  @_i2.override
  _i2.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUnblockResponse401
    extends CatchIncomingRequestsUnblockResponse {
  const CatchIncomingRequestsUnblockResponse401({required this.body});

  final _i3.DetailError body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is CatchIncomingRequestsUnblockResponse401 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUnblockResponse403
    extends CatchIncomingRequestsUnblockResponse {
  const CatchIncomingRequestsUnblockResponse403({required this.body});

  final _i3.DetailError body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is CatchIncomingRequestsUnblockResponse403 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUnblockResponse404
    extends CatchIncomingRequestsUnblockResponse {
  const CatchIncomingRequestsUnblockResponse404({required this.body});

  final _i4.CatchRequestActionError body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is CatchIncomingRequestsUnblockResponse404 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUnblockResponse409
    extends CatchIncomingRequestsUnblockResponse {
  const CatchIncomingRequestsUnblockResponse409({required this.body});

  final _i4.CatchRequestActionError body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is CatchIncomingRequestsUnblockResponse409 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsUnblockResponse500
    extends CatchIncomingRequestsUnblockResponse {
  const CatchIncomingRequestsUnblockResponse500({required this.body});

  final _i5.CatchRequestError body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is CatchIncomingRequestsUnblockResponse500 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}
