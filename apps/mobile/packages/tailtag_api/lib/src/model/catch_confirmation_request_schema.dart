// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchConfirmationRequestSchema extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchConfirmationRequestSchema({required this.payload});

  factory CatchConfirmationRequestSchema.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'payload'},
      listKeys: {},
      context: r'CatchConfirmationRequestSchema',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return CatchConfirmationRequestSchema(
      payload: _$values[r'payload'].decodeSimpleString(
        context: r'CatchConfirmationRequestSchema.payload',
      ),
    );
  }

  factory CatchConfirmationRequestSchema.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchConfirmationRequestSchema');
    return CatchConfirmationRequestSchema(
      payload: _$map[r'payload'].decodeJsonString(
        context: r'CatchConfirmationRequestSchema.payload',
      ),
    );
  }

  factory CatchConfirmationRequestSchema.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'payload'},
      listKeys: {},
      context: r'CatchConfirmationRequestSchema',
    );
    return CatchConfirmationRequestSchema(
      payload: _$values[r'payload'].decodeFormString(
        context: r'CatchConfirmationRequestSchema.payload',
      ),
    );
  }

  final _i3.String payload;

  @_i3.override
  _i3.Object? toJson() => {r'payload': this.payload};

  CatchConfirmationRequestSchema Function({_i3.String? payload}) get copyWith {
    return ({_i3.String? payload}) =>
        CatchConfirmationRequestSchema(payload: payload ?? this.payload);
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchConfirmationRequestSchema &&
        other.payload == this.payload;
  }

  @_i3.override
  _i3.int get hashCode => this.payload.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'payload'] = _i1.PropertyValue.scalar(this.payload);
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
      r'Cannot uriEncode CatchConfirmationRequestSchema: complex types cannot be URI-encoded',
    );
  }
}
