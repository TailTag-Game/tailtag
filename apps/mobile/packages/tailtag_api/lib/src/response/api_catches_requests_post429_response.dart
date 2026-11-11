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
    return _i3.Object.hashAll([body, retryAfter]);
  }

  $$ApiCatchesRequestsPost429ResponseCopyWith<ApiCatchesRequestsPost429Response>
  get copyWith => _ApiCatchesRequestsPost429ResponseCopyWith(this);
}

abstract class $$ApiCatchesRequestsPost429ResponseCopyWith<$Res> {
  factory $$ApiCatchesRequestsPost429ResponseCopyWith(
    ApiCatchesRequestsPost429Response value,
  ) = _ApiCatchesRequestsPost429ResponseCopyWith<$Res>;

  $Res call({_i2.CatchRequestRefusal? body, _i3.int? retryAfter});
  _i2.CatchRequestRefusal get body;
  _i3.int? get retryAfter;
}

class _ApiCatchesRequestsPost429ResponseCopyWith<$Res>
    implements $$ApiCatchesRequestsPost429ResponseCopyWith<$Res> {
  _ApiCatchesRequestsPost429ResponseCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesRequestsPost429Response _value;

  @_i3.override
  _i2.CatchRequestRefusal get body => _value.body;

  @_i3.override
  _i3.int? get retryAfter => _value.retryAfter;

  @_i3.override
  $Res call({
    _i3.Object? body = _sentinel,
    _i3.Object? retryAfter = _sentinel,
  }) {
    return (ApiCatchesRequestsPost429Response(
      body: _i3.identical(body, _sentinel)
          ? this.body
          : (body as _i2.CatchRequestRefusal),
      retryAfter: _i3.identical(retryAfter, _sentinel)
          ? this.retryAfter
          : (retryAfter as _i3.int?),
    ) as $Res);
  }
}
