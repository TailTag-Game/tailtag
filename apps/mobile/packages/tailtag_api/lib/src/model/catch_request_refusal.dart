// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_request_refusal_code_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// cooldown_active or rate_limited. The Retry-After header carries the same number of seconds.
@_i2.immutable
class CatchRequestRefusal extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchRequestRefusal({
    required this.code,
    required this.detail,
    required this.retryAfterSeconds,
  });

  factory CatchRequestRefusal.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail', r'retry_after_seconds'},
      listKeys: {},
      context: r'CatchRequestRefusal',
    );
    return CatchRequestRefusal(
      code: _i4.CatchRequestRefusalCodeModel.fromSimple(
        _$values[r'code'],
        explode: explode,
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'CatchRequestRefusal.detail',
      ),
      retryAfterSeconds: _$values[r'retry_after_seconds'].decodeSimpleInt(
        context: r'CatchRequestRefusal.retry_after_seconds',
      ),
    );
  }

  factory CatchRequestRefusal.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchRequestRefusal');
    return CatchRequestRefusal(
      code: _i4.CatchRequestRefusalCodeModel.fromJson(_$map[r'code']),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'CatchRequestRefusal.detail',
      ),
      retryAfterSeconds: _$map[r'retry_after_seconds'].decodeJsonInt(
        context: r'CatchRequestRefusal.retry_after_seconds',
      ),
    );
  }

  factory CatchRequestRefusal.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail', r'retry_after_seconds'},
      listKeys: {},
      context: r'CatchRequestRefusal',
    );
    return CatchRequestRefusal(
      code: _i4.CatchRequestRefusalCodeModel.fromForm(
        _$values[r'code'],
        explode: explode,
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'CatchRequestRefusal.detail',
      ),
      retryAfterSeconds: _$values[r'retry_after_seconds'].decodeFormInt(
        context: r'CatchRequestRefusal.retry_after_seconds',
      ),
    );
  }

  final _i4.CatchRequestRefusalCodeModel code;

  final _i3.String detail;

  final _i3.int retryAfterSeconds;

  @_i3.override
  _i3.Object? toJson() => {
    r'code': code.toJson(),
    r'detail': detail,
    r'retry_after_seconds': retryAfterSeconds,
  };

  $$CatchRequestRefusalCopyWith<CatchRequestRefusal> get copyWith =>
      _CatchRequestRefusalCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestRefusal &&
        other.code == this.code &&
        other.detail == this.detail &&
        other.retryAfterSeconds == this.retryAfterSeconds;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([code, detail, retryAfterSeconds]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'code'] = _i1.PropertyValue.scalar(code.toJson());
    _$result[r'detail'] = _i1.PropertyValue.scalar(detail);
    _$result[r'retry_after_seconds'] = _i1.PropertyValue.scalar(
      retryAfterSeconds.toString(),
    );
    return _$result;
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode CatchRequestRefusal: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchRequestRefusalCopyWith<$Res> {
  factory $$CatchRequestRefusalCopyWith(CatchRequestRefusal value) =
      _CatchRequestRefusalCopyWith<$Res>;

  $Res call({
    _i4.CatchRequestRefusalCodeModel? code,
    _i3.String? detail,
    _i3.int? retryAfterSeconds,
  });
  _i4.CatchRequestRefusalCodeModel get code;
  _i3.String get detail;
  _i3.int get retryAfterSeconds;
}

class _CatchRequestRefusalCopyWith<$Res>
    implements $$CatchRequestRefusalCopyWith<$Res> {
  _CatchRequestRefusalCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchRequestRefusal _value;

  @_i3.override
  _i4.CatchRequestRefusalCodeModel get code => _value.code;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  _i3.int get retryAfterSeconds => _value.retryAfterSeconds;

  @_i3.override
  $Res call({
    _i3.Object? code = _sentinel,
    _i3.Object? detail = _sentinel,
    _i3.Object? retryAfterSeconds = _sentinel,
  }) {
    return (CatchRequestRefusal(
      code: _i3.identical(code, _sentinel)
          ? this.code
          : (code as _i4.CatchRequestRefusalCodeModel),
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
      retryAfterSeconds: _i3.identical(retryAfterSeconds, _sentinel)
          ? this.retryAfterSeconds
          : (retryAfterSeconds as _i3.int),
    ) as $Res);
  }
}
