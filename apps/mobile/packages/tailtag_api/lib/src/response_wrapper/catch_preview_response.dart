// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_catches_preview_post200_body_model.dart'
    as _i2;
import 'package:tailtag_api/src/model/api_catches_preview_post400_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_catches_preview_post401_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/api_catches_preview_post403_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_catches_preview_post404_body_model.dart'
    as _i7;
import 'package:tailtag_api/src/model/api_catches_preview_post409_body_model.dart'
    as _i8;
import 'package:tailtag_api/src/model/api_catches_preview_post500_body_model.dart'
    as _i9;

sealed class CatchPreviewResponse {
  const CatchPreviewResponse();
}

@_i1.immutable
class CatchPreviewResponse200 extends CatchPreviewResponse {
  const CatchPreviewResponse200({required this.body});

  final _i2.ApiCatchesPreviewPost200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchPreviewResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchPreviewResponse400 extends CatchPreviewResponse {
  const CatchPreviewResponse400({required this.body});

  final _i4.ApiCatchesPreviewPost400BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchPreviewResponse400 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchPreviewResponse401 extends CatchPreviewResponse {
  const CatchPreviewResponse401({required this.body});

  final _i5.ApiCatchesPreviewPost401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchPreviewResponse401 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchPreviewResponse403 extends CatchPreviewResponse {
  const CatchPreviewResponse403({required this.body});

  final _i6.ApiCatchesPreviewPost403BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchPreviewResponse403 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchPreviewResponse404 extends CatchPreviewResponse {
  const CatchPreviewResponse404({required this.body});

  final _i7.ApiCatchesPreviewPost404BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchPreviewResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchPreviewResponse409 extends CatchPreviewResponse {
  const CatchPreviewResponse409({required this.body});

  final _i8.ApiCatchesPreviewPost409BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchPreviewResponse409 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class CatchPreviewResponse500 extends CatchPreviewResponse {
  const CatchPreviewResponse500({required this.body});

  final _i9.ApiCatchesPreviewPost500BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchPreviewResponse500 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
