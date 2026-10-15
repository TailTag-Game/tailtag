// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_fursuits_id_get200_body_model.dart'
    as _i2;

sealed class FursuitsRetrieveResponse {
  const FursuitsRetrieveResponse();
}

@_i1.immutable
class FursuitsRetrieveResponse200 extends FursuitsRetrieveResponse {
  const FursuitsRetrieveResponse200({required this.body});

  final _i2.ApiFursuitsIdGet200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsRetrieveResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitsRetrieveResponse401 extends FursuitsRetrieveResponse {
  const FursuitsRetrieveResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsRetrieveResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsRetrieveResponse404 extends FursuitsRetrieveResponse {
  const FursuitsRetrieveResponse404();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsRetrieveResponse404;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsRetrieveResponse405 extends FursuitsRetrieveResponse {
  const FursuitsRetrieveResponse405();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsRetrieveResponse405;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsRetrieveResponse500 extends FursuitsRetrieveResponse {
  const FursuitsRetrieveResponse500();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsRetrieveResponse500;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
