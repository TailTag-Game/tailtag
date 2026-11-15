// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i1;
import 'package:tailtag_api/src/model/catch_request_refusal.dart' as _i2;

@_i1.immutable
class ApiCatchesRequestsPost429Response {
  const ApiCatchesRequestsPost429Response({
    required this.body,
    this.retryAfter,
  });

  final _i2.CatchRequestRefusal body;

  final _i3.int? retryAfter;

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesRequestsPost429Response &&
        other.body == this.body &&
        other.retryAfter == this.retryAfter;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([this.body, this.retryAfter]);
  }

  ApiCatchesRequestsPost429Response Function({
    _i2.CatchRequestRefusal? body,
    _i3.int? retryAfter,
  })
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({
      _i2.CatchRequestRefusal? body,
      _i3.Object? retryAfter = _sentinel,
    }) => ApiCatchesRequestsPost429Response(
      body: body ?? this.body,
      retryAfter: _i3.identical(retryAfter, _sentinel)
          ? this.retryAfter
          : (retryAfter as _i3.int?),
    );
  }
}
