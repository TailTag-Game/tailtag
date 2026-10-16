// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/api_conventions_id_get401_body_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_conventions_id_get404_body_model.dart'
    as _i5;
import 'package:tailtag_api/src/model/convention.dart' as _i2;

sealed class ConventionsRetrieveResponse {
  const ConventionsRetrieveResponse();
}

@_i1.immutable
class ConventionsRetrieveResponse200 extends ConventionsRetrieveResponse {
  const ConventionsRetrieveResponse200({required this.body});

  final _i2.Convention body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsRetrieveResponse200 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsRetrieveResponse401 extends ConventionsRetrieveResponse {
  const ConventionsRetrieveResponse401({required this.body});

  final _i4.ApiConventionsIdGet401BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsRetrieveResponse401 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}

@_i1.immutable
class ConventionsRetrieveResponse404 extends ConventionsRetrieveResponse {
  const ConventionsRetrieveResponse404({required this.body});

  final _i5.ApiConventionsIdGet404BodyModel body;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ConventionsRetrieveResponse404 && other.body == this.body;
  }

  @_i3.override
  _i3.int get hashCode => body.hashCode;
}
