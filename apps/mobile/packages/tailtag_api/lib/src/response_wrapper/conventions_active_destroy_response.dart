// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i2;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_active_delete401_body_model.dart'
    as _i3;
import 'package:tailtag_api/src/model/api_conventions_active_delete403_body_model.dart'
    as _i4;

sealed class ConventionsActiveDestroyResponse {
  const ConventionsActiveDestroyResponse();
}

@_i1.immutable
class ConventionsActiveDestroyResponse204
    extends ConventionsActiveDestroyResponse {
  const ConventionsActiveDestroyResponse204();

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionsActiveDestroyResponse204;
  }

  @_i2.override
  _i2.int get hashCode => runtimeType.hashCode;
}

@_i1.immutable
class ConventionsActiveDestroyResponse401
    extends ConventionsActiveDestroyResponse {
  const ConventionsActiveDestroyResponse401({required this.body});

  final _i3.ApiConventionsActiveDelete401BodyModel body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionsActiveDestroyResponse401 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsActiveDestroyResponse403
    extends ConventionsActiveDestroyResponse {
  const ConventionsActiveDestroyResponse403({required this.body});

  final _i4.ApiConventionsActiveDelete403BodyModel body;

  @_i2.override
  _i2.bool operator ==(_i2.Object other) {
    if (_i2.identical(this, other)) return true;
    return other is ConventionsActiveDestroyResponse403 &&
        other.body == this.body;
  }

  @_i2.override
  _i2.int get hashCode => body.hashCode;
}
