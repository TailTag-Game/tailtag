// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// catch_target_unavailable carries code and detail. While the gate is off, the generic not-found body carries detail only.
@_i2.immutable
class CatchRequestNotFound extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchRequestNotFound({required this.detail, this.code});

  factory CatchRequestNotFound.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'CatchRequestNotFound',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return CatchRequestNotFound(
      code: _$values[r'code'].decodeSimpleNullableString(
        context: r'CatchRequestNotFound.code',
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'CatchRequestNotFound.detail',
      ),
    );
  }

  factory CatchRequestNotFound.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchRequestNotFound');
    return CatchRequestNotFound(
      code: _$map[r'code'].decodeJsonNullableString(
        context: r'CatchRequestNotFound.code',
      ),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'CatchRequestNotFound.detail',
      ),
    );
  }

  factory CatchRequestNotFound.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'CatchRequestNotFound',
    );
    return CatchRequestNotFound(
      code: _$values[r'code'].decodeFormNullableString(
        context: r'CatchRequestNotFound.code',
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'CatchRequestNotFound.detail',
      ),
    );
  }

  final _i3.String? code;

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {
    if (this.code != null) r'code': this.code,
    r'detail': this.detail,
  };

  CatchRequestNotFound Function({_i3.String? code, _i3.String? detail})
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({_i3.Object? code = _sentinel, _i3.String? detail}) =>
        CatchRequestNotFound(
          code: _i3.identical(code, _sentinel)
              ? this.code
              : (code as _i3.String?),
          detail: detail ?? this.detail,
        );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestNotFound &&
        other.code == this.code &&
        other.detail == this.detail;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([this.code, this.detail]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    if (this.code != null) {
      _$result[r'code'] = _i1.PropertyValue.scalar(this.code!);
    }
    _$result[r'detail'] = _i1.PropertyValue.scalar(this.detail);
    return _$result;
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i4.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode CatchRequestNotFound: complex types cannot be URI-encoded',
    );
  }
}
