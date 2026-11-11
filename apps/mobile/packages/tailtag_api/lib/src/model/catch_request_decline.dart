// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchRequestDecline extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchRequestDecline({required this.block});

  factory CatchRequestDecline.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'block'},
      listKeys: {},
      context: r'CatchRequestDecline',
    );
    return CatchRequestDecline(
      block: _$values[r'block'].decodeSimpleBool(
        context: r'CatchRequestDecline.block',
      ),
    );
  }

  factory CatchRequestDecline.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchRequestDecline');
    return CatchRequestDecline(
      block: _$map[r'block'].decodeJsonBool(
        context: r'CatchRequestDecline.block',
      ),
    );
  }

  factory CatchRequestDecline.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'block'},
      listKeys: {},
      context: r'CatchRequestDecline',
    );
    return CatchRequestDecline(
      block: _$values[r'block'].decodeFormBool(
        context: r'CatchRequestDecline.block',
      ),
    );
  }

  /// True also blocks the player for this suit here.
  final _i3.bool block;

  @_i3.override
  _i3.Object? toJson() => {r'block': block};

  $$CatchRequestDeclineCopyWith<CatchRequestDecline> get copyWith =>
      _CatchRequestDeclineCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestDecline && other.block == this.block;
  }

  @_i3.override
  _i3.int get hashCode => block.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'block'] = _i1.PropertyValue.scalar(block.toString());
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
      r'Cannot uriEncode CatchRequestDecline: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchRequestDeclineCopyWith<$Res> {
  factory $$CatchRequestDeclineCopyWith(CatchRequestDecline value) =
      _CatchRequestDeclineCopyWith<$Res>;

  $Res call({_i3.bool? block});
  _i3.bool get block;
}

class _CatchRequestDeclineCopyWith<$Res>
    implements $$CatchRequestDeclineCopyWith<$Res> {
  _CatchRequestDeclineCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchRequestDecline _value;

  @_i3.override
  _i3.bool get block => _value.block;

  @_i3.override
  $Res call({_i3.Object? block = _sentinel}) {
    return (CatchRequestDecline(
      block: _i3.identical(block, _sentinel) ? this.block : (block as _i3.bool),
    ) as $Res);
  }
}
