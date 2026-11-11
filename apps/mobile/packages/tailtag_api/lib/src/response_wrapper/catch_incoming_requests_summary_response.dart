// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_error.dart' as _i4;
import 'package:tailtag_api/src/model/detail_error.dart' as _i5;
import 'package:tailtag_api/src/model/owner_request_summary.dart' as _i2;

sealed class CatchIncomingRequestsSummaryResponse {
  const CatchIncomingRequestsSummaryResponse();
}

@_i1.immutable
class CatchIncomingRequestsSummaryResponse200
    extends CatchIncomingRequestsSummaryResponse {
  const CatchIncomingRequestsSummaryResponse200({required this.body});

  final _i2.OwnerRequestSummary body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsSummaryResponse200 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsSummaryResponse400
    extends CatchIncomingRequestsSummaryResponse {
  const CatchIncomingRequestsSummaryResponse400({required this.body});

  final _i4.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsSummaryResponse400 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsSummaryResponse401
    extends CatchIncomingRequestsSummaryResponse {
  const CatchIncomingRequestsSummaryResponse401({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsSummaryResponse401 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsSummaryResponse403
    extends CatchIncomingRequestsSummaryResponse {
  const CatchIncomingRequestsSummaryResponse403({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsSummaryResponse403 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsSummaryResponse404
    extends CatchIncomingRequestsSummaryResponse {
  const CatchIncomingRequestsSummaryResponse404({required this.body});

  final _i5.DetailError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsSummaryResponse404 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchIncomingRequestsSummaryResponse500
    extends CatchIncomingRequestsSummaryResponse {
  const CatchIncomingRequestsSummaryResponse500({required this.body});

  final _i4.CatchRequestError body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchIncomingRequestsSummaryResponse500 &&
        other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
