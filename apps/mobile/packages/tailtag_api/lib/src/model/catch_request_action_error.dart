// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_request_state.dart' as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// request_state_changed carries the current state. Other codes carry code and detail only.
@_i2.immutable
class CatchRequestActionError extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchRequestActionError({
    required this.code,
    required this.detail,
    this.state,
  });

  factory CatchRequestActionError.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail', r'state'},
      listKeys: {},
      context: r'CatchRequestActionError',
    );
    return CatchRequestActionError(
      code: _$values[r'code'].decodeSimpleString(
        context: r'CatchRequestActionError.code',
      ),
      detail: _$values[r'detail'].decodeSimpleString(
        context: r'CatchRequestActionError.detail',
      ),
      state: _$values[r'state'] == null
          ? null
          : _i4.CatchRequestState.fromSimple(
              _$values[r'state'],
              explode: explode,
            ),
    );
  }

  factory CatchRequestActionError.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchRequestActionError');
    return CatchRequestActionError(
      code: _$map[r'code'].decodeJsonString(
        context: r'CatchRequestActionError.code',
      ),
      detail: _$map[r'detail'].decodeJsonString(
        context: r'CatchRequestActionError.detail',
      ),
      state: _$map[r'state'] == null
          ? null
          : _i4.CatchRequestState.fromJson(_$map[r'state']),
    );
  }

  factory CatchRequestActionError.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'code', r'detail', r'state'},
      listKeys: {},
      context: r'CatchRequestActionError',
    );
    return CatchRequestActionError(
      code: _$values[r'code'].decodeFormString(
        context: r'CatchRequestActionError.code',
      ),
      detail: _$values[r'detail'].decodeFormString(
        context: r'CatchRequestActionError.detail',
      ),
      state: _$values[r'state'] == null
          ? null
          : _i4.CatchRequestState.fromForm(
              _$values[r'state'],
              explode: explode,
            ),
    );
  }

  final _i3.String code;

  final _i3.String detail;

  final _i4.CatchRequestState? state;

  @_i3.override
  _i3.Object? toJson() => {
    r'code': code,
    r'detail': detail,
    if (state != null) r'state': state?.toJson(),
  };

  $$CatchRequestActionErrorCopyWith<CatchRequestActionError> get copyWith =>
      _CatchRequestActionErrorCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestActionError &&
        other.code == this.code &&
        other.detail == this.detail &&
        other.state == this.state;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([code, detail, state]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'code'] = _i1.PropertyValue.scalar(code);
    _$result[r'detail'] = _i1.PropertyValue.scalar(detail);
    if (state != null) {
      _$result[r'state'] = _i1.PropertyValue.scalar(state!.toJson());
    }
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
      r'Cannot uriEncode CatchRequestActionError: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchRequestActionErrorCopyWith<$Res> {
  factory $$CatchRequestActionErrorCopyWith(CatchRequestActionError value) =
      _CatchRequestActionErrorCopyWith<$Res>;

  $Res call({
    _i3.String? code,
    _i3.String? detail,
    _i4.CatchRequestState? state,
  });
  _i3.String get code;
  _i3.String get detail;
  _i4.CatchRequestState? get state;
}

class _CatchRequestActionErrorCopyWith<$Res>
    implements $$CatchRequestActionErrorCopyWith<$Res> {
  _CatchRequestActionErrorCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchRequestActionError _value;

  @_i3.override
  _i3.String get code => _value.code;

  @_i3.override
  _i3.String get detail => _value.detail;

  @_i3.override
  _i4.CatchRequestState? get state => _value.state;

  @_i3.override
  $Res call({
    _i3.Object? code = _sentinel,
    _i3.Object? detail = _sentinel,
    _i3.Object? state = _sentinel,
  }) {
    return (CatchRequestActionError(
      code: _i3.identical(code, _sentinel) ? this.code : (code as _i3.String),
      detail: _i3.identical(detail, _sentinel)
          ? this.detail
          : (detail as _i3.String),
      state: _i3.identical(state, _sentinel)
          ? this.state
          : (state as _i4.CatchRequestState?),
    ) as $Res);
  }
}
