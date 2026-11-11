// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_fursuits_id_photo_put200_body_model.dart'
    as _i2;

sealed class FursuitsReplacePhotoResponse {
  const FursuitsReplacePhotoResponse();
}

@_i1.immutable
class FursuitsReplacePhotoResponse200 extends FursuitsReplacePhotoResponse {
  const FursuitsReplacePhotoResponse200({required this.body});

  final _i2.ApiFursuitsIdPhotoPut200BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsReplacePhotoResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class FursuitsReplacePhotoResponse400 extends FursuitsReplacePhotoResponse {
  const FursuitsReplacePhotoResponse400();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsReplacePhotoResponse400;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsReplacePhotoResponse401 extends FursuitsReplacePhotoResponse {
  const FursuitsReplacePhotoResponse401();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsReplacePhotoResponse401;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsReplacePhotoResponse403 extends FursuitsReplacePhotoResponse {
  const FursuitsReplacePhotoResponse403();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsReplacePhotoResponse403;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsReplacePhotoResponse404 extends FursuitsReplacePhotoResponse {
  const FursuitsReplacePhotoResponse404();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsReplacePhotoResponse404;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsReplacePhotoResponse405 extends FursuitsReplacePhotoResponse {
  const FursuitsReplacePhotoResponse405();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsReplacePhotoResponse405;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class FursuitsReplacePhotoResponse500 extends FursuitsReplacePhotoResponse {
  const FursuitsReplacePhotoResponse500();

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is FursuitsReplacePhotoResponse500;
  }

  @_i3.override
  _i3.int get hashCode => runtimeType.hashCode;
}
