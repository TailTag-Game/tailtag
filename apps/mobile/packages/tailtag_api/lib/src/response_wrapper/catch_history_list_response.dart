// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_catches_get400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_catches_get401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_catches_get404_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_catches_get500_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/catch_history_response_schema.dart'
    as _i2;

sealed class CatchHistoryListResponse {
  const CatchHistoryListResponse();
}

@_i1.immutable
class CatchHistoryListResponse200 extends CatchHistoryListResponse {
  const CatchHistoryListResponse200({required this.body});

  final _i2.CatchHistoryResponseSchema body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchHistoryListResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchHistoryListResponse400 extends CatchHistoryListResponse {
  const CatchHistoryListResponse400({required this.body});

  final _i4.ApiCatchesGet400BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchHistoryListResponse400 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchHistoryListResponse401 extends CatchHistoryListResponse {
  const CatchHistoryListResponse401({required this.body});

  final _i5.ApiCatchesGet401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchHistoryListResponse401 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchHistoryListResponse404 extends CatchHistoryListResponse {
  const CatchHistoryListResponse404({required this.body});

  final _i6.ApiCatchesGet404BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchHistoryListResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchHistoryListResponse500 extends CatchHistoryListResponse {
  const CatchHistoryListResponse500({required this.body});

  final _i7.ApiCatchesGet500BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchHistoryListResponse500 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
