// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_fursuits_id_patch200_body_model.dart'
    as _i2;

sealed class FursuitsUpdateNameResponse {
  const FursuitsUpdateNameResponse();
}

@_i1.immutable
class FursuitsUpdateNameResponse200 extends FursuitsUpdateNameResponse {
  const FursuitsUpdateNameResponse200({required this.body});

  final _i2.ApiFursuitsIdPatch200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateNameResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitsUpdateNameResponse400 extends FursuitsUpdateNameResponse {
  const FursuitsUpdateNameResponse400();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateNameResponse400;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateNameResponse401 extends FursuitsUpdateNameResponse {
  const FursuitsUpdateNameResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateNameResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateNameResponse403 extends FursuitsUpdateNameResponse {
  const FursuitsUpdateNameResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateNameResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateNameResponse404 extends FursuitsUpdateNameResponse {
  const FursuitsUpdateNameResponse404();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateNameResponse404;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateNameResponse405 extends FursuitsUpdateNameResponse {
  const FursuitsUpdateNameResponse405();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateNameResponse405;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsUpdateNameResponse500 extends FursuitsUpdateNameResponse {
  const FursuitsUpdateNameResponse500();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsUpdateNameResponse500;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
