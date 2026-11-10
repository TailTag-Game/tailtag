// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_fursuits_id_patch200_body_model.dart'
    as _i2;

sealed class FursuitsUpdateResponse {
  const FursuitsUpdateResponse();
}

@_i1.immutable
class FursuitsUpdateResponse200 extends FursuitsUpdateResponse {
  const FursuitsUpdateResponse200({required this.body});

  final _i2.ApiFursuitsIdPatch200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitsUpdateResponse400 extends FursuitsUpdateResponse {
  const FursuitsUpdateResponse400();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateResponse400;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateResponse401 extends FursuitsUpdateResponse {
  const FursuitsUpdateResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateResponse403 extends FursuitsUpdateResponse {
  const FursuitsUpdateResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateResponse404 extends FursuitsUpdateResponse {
  const FursuitsUpdateResponse404();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateResponse404;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateResponse405 extends FursuitsUpdateResponse {
  const FursuitsUpdateResponse405();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateResponse405;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateResponse500 extends FursuitsUpdateResponse {
  const FursuitsUpdateResponse500();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateResponse500;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
