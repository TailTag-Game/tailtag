// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i4;
import 'package:tailtag_api/src/model/detail_error.dart' as _i5;
import 'package:tailtag_api/src/model/player_request_list.dart' as _i2;

sealed class CatchRequestsListResponse {
  const CatchRequestsListResponse();
}

@_i1.immutable
class CatchRequestsListResponse200 extends CatchRequestsListResponse {
  const CatchRequestsListResponse200({required this.body});

  final _i2.PlayerRequestList body;

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

  final _i4.CatchRequestError body;

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

  final _i5.DetailError body;

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

  final _i4.CatchRequestError body;

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

  final _i5.DetailError body;

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

  final _i4.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestsListResponse500 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
