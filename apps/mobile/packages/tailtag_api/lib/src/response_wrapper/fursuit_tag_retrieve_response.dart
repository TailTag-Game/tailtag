// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_get200_body_model.dart'
    as _i2;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_get404_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_get409_body_model.dart'
    as _i5;

sealed class FursuitTagRetrieveResponse {
  const FursuitTagRetrieveResponse();
}

@_i1.immutable
class FursuitTagRetrieveResponse200 extends FursuitTagRetrieveResponse {
  const FursuitTagRetrieveResponse200({required this.body});

  final _i2.ApiFursuitsIdTagGet200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagRetrieveResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitTagRetrieveResponse401 extends FursuitTagRetrieveResponse {
  const FursuitTagRetrieveResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagRetrieveResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitTagRetrieveResponse403 extends FursuitTagRetrieveResponse {
  const FursuitTagRetrieveResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagRetrieveResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitTagRetrieveResponse404 extends FursuitTagRetrieveResponse {
  const FursuitTagRetrieveResponse404({required this.body});

  final _i4.ApiFursuitsIdTagGet404BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagRetrieveResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitTagRetrieveResponse405 extends FursuitTagRetrieveResponse {
  const FursuitTagRetrieveResponse405();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagRetrieveResponse405;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitTagRetrieveResponse409 extends FursuitTagRetrieveResponse {
  const FursuitTagRetrieveResponse409({required this.body});

  final _i5.ApiFursuitsIdTagGet409BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagRetrieveResponse409 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitTagRetrieveResponse500 extends FursuitTagRetrieveResponse {
  const FursuitTagRetrieveResponse500();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagRetrieveResponse500;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
