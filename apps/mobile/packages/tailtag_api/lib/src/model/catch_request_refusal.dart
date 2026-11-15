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
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail', r'retry_after_seconds'},
      listKeys: {},
      context: r'CatchRequestRefusal',
      isHeader: isHeader,
      percentDecodeKeys: false,
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
    r'code': this.code.toJson(),
    r'detail': this.detail,
    r'retry_after_seconds': this.retryAfterSeconds,
  };

  CatchRequestRefusal Function({
    _i4.CatchRequestRefusalCodeModel? code,
    _i3.String? detail,
    _i3.int? retryAfterSeconds,
  })
  get copyWith {
    return ({
      _i4.CatchRequestRefusalCodeModel? code,
      _i3.String? detail,
      _i3.int? retryAfterSeconds,
    }) => CatchRequestRefusal(
      code: code ?? this.code,
      detail: detail ?? this.detail,
      retryAfterSeconds: retryAfterSeconds ?? this.retryAfterSeconds,
    );
  }

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
    return _i3.Object.hashAll([this.code, this.detail, this.retryAfterSeconds]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'code'] = _i1.PropertyValue.scalar(this.code.toJson());
    _$result[r'detail'] = _i1.PropertyValue.scalar(this.detail);
    _$result[r'retry_after_seconds'] = _i1.PropertyValue.scalar(
      this.retryAfterSeconds.toString(),
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
