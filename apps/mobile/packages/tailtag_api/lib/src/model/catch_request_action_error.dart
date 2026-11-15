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
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'code', r'detail', r'state'},
      listKeys: {},
      context: r'CatchRequestActionError',
      isHeader: isHeader,
      percentDecodeKeys: false,
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
    r'code': this.code,
    r'detail': this.detail,
    if (this.state != null) r'state': this.state?.toJson(),
  };

  CatchRequestActionError Function({
    _i3.String? code,
    _i3.String? detail,
    _i4.CatchRequestState? state,
  })
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({
      _i3.String? code,
      _i3.String? detail,
      _i3.Object? state = _sentinel,
    }) => CatchRequestActionError(
      code: code ?? this.code,
      detail: detail ?? this.detail,
      state: _i3.identical(state, _sentinel)
          ? this.state
          : (state as _i4.CatchRequestState?),
    );
  }

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
    return _i3.Object.hashAll([this.code, this.detail, this.state]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'code'] = _i1.PropertyValue.scalar(this.code);
    _$result[r'detail'] = _i1.PropertyValue.scalar(this.detail);
    if (this.state != null) {
      _$result[r'state'] = _i1.PropertyValue.scalar(this.state!.toJson());
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
