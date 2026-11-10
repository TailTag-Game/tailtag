// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post200_body_model.dart'
    as _i2;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post400_body_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post404_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_replace_post409_body_model.dart'
    as _i5;

sealed class FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse();
}

@_i1.immutable
class FursuitTagReplaceResponse200 extends FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse200({required this.body});

  final _i2.ApiFursuitsIdTagReplacePost200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagReplaceResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitTagReplaceResponse401 extends FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagReplaceResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitTagReplaceResponse403 extends FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagReplaceResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitTagReplaceResponse404 extends FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse404({required this.body});

  final _i4.ApiFursuitsIdTagReplacePost404BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagReplaceResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitTagReplaceResponse405 extends FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse405();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagReplaceResponse405;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitTagReplaceResponse409 extends FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse409({required this.body});

  final _i5.ApiFursuitsIdTagReplacePost409BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagReplaceResponse409 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitTagReplaceResponse500 extends FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse500();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagReplaceResponse500;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitTagReplaceResponse400 extends FursuitTagReplaceResponse {
  const FursuitTagReplaceResponse400({required this.body});

  final _i6.ApiFursuitsIdTagReplacePost400BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitTagReplaceResponse400 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
