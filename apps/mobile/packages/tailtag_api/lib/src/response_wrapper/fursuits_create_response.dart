// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_fursuits_post201_body_model.dart'
    as _i2;

sealed class FursuitsCreateResponse {
  const FursuitsCreateResponse();
}

@_i1.immutable
class FursuitsCreateResponse201 extends FursuitsCreateResponse {
  const FursuitsCreateResponse201({required this.body});

  final _i2.ApiFursuitsPost201BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsCreateResponse201 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitsCreateResponse400 extends FursuitsCreateResponse {
  const FursuitsCreateResponse400();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsCreateResponse400;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsCreateResponse401 extends FursuitsCreateResponse {
  const FursuitsCreateResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsCreateResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsCreateResponse403 extends FursuitsCreateResponse {
  const FursuitsCreateResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsCreateResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsCreateResponse405 extends FursuitsCreateResponse {
  const FursuitsCreateResponse405();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsCreateResponse405;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsCreateResponse500 extends FursuitsCreateResponse {
  const FursuitsCreateResponse500();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsCreateResponse500;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
