// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i2;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_fursuits_get200_body_array_model.dart'
    as _i3;

sealed class FursuitsListResponse {
  const FursuitsListResponse();
}

@_i1.immutable
class FursuitsListResponse200 extends FursuitsListResponse {
  const FursuitsListResponse200({required this.body});

  final _i2.List<_i3.ApiFursuitsGet200BodyArrayModel> body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is FursuitsListResponse200 && other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitsListResponse401 extends FursuitsListResponse {
  const FursuitsListResponse401();

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is FursuitsListResponse401;
  }

  @_i2.override
  _i2.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsListResponse405 extends FursuitsListResponse {
  const FursuitsListResponse405();

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is FursuitsListResponse405;
  }

  @_i2.override
  _i2.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsListResponse500 extends FursuitsListResponse {
  const FursuitsListResponse500();

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is FursuitsListResponse500;
  }

  @_i2.override
  _i2.int get hashCode => runtimeType.hashCode;
}
