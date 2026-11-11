// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// request_not_found carries code and detail. While the gate is off, the generic not-found body carries detail only.
@_i2.immutable
class CatchRequestActionNotFound extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchRequestActionNotFound({required this.detail, this.code});

  factory CatchRequestActionNotFound.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'CatchRequestActionNotFound',
    );
    return CatchRequestActionNotFound(
      code: _$values[r'code'].decodeSimpleNullableString(
        context: r'CatchRequestActionNotFound.code',
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'CatchRequestActionNotFound.detail',
      ),
    );
  }

  factory CatchRequestActionNotFound.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchRequestActionNotFound');
    return CatchRequestActionNotFound(
      code: _$map[r'code'].decodeJsonNullableString(
        context: r'CatchRequestActionNotFound.code',
      ),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'CatchRequestActionNotFound.detail',
      ),
    );
  }

  factory CatchRequestActionNotFound.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail'},
      listKeys: {},
      context: r'CatchRequestActionNotFound',
    );
    return CatchRequestActionNotFound(
      code: _$values[r'code'].decodeFormNullableString(
        context: r'CatchRequestActionNotFound.code',
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'CatchRequestActionNotFound.detail',
      ),
    );
  }

  final _i3.String? code;

  final _i3.String detail;

  @_i3.override
  _i3.Object? toJson() => {if (code != null) r'code': code, r'detail': detail};

  $$CatchRequestActionNotFoundCopyWith<CatchRequestActionNotFound>
  get copyWith => _CatchRequestActionNotFoundCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestActionNotFound &&
        other.code == this.code &&
        other.detail == this.detail;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([code, detail]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    if (code != null) {
      _$result[r'code'] = _i1.PropertyValue.scalar(code!);
    }
    _$result[r'detail'] = _i1.PropertyValue.scalar(detail);
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
      r'Cannot uriEncode CatchRequestActionNotFound: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchRequestActionNotFoundCopyWith<$Res> {
  factory $$CatchRequestActionNotFoundCopyWith(
    CatchRequestActionNotFound value,
  ) = _CatchRequestActionNotFoundCopyWith<$Res>;

  $Res call({_i3.String? code, _i3.String? detail});
  _i3.String? get code;
  _i3.String get detail;
}

class _CatchRequestActionNotFoundCopyWith<$Res>
    implements $$CatchRequestActionNotFoundCopyWith<$Res> {
  _CatchRequestActionNotFoundCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchRequestActionNotFound _value;

  @_i3.override
  _i3.String? get code => _value.code;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  $Res call({_i3.Object? code = _sentinel, _i3.Object? detail = _sentinel}) {
    return (CatchRequestActionNotFound(
      code: _i3.identical(code, _sentinel) ? this.code : (code as _i3.String?),
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
    ) as $Res);
  }
}
