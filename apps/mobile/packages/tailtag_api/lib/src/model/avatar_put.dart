// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class AvatarPut extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const AvatarPut({required this.avatar});

  factory AvatarPut.fromSimple(_i3.String? value, {required _i3.bool explode}) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'avatar'},
      listKeys: {},
      context: r'AvatarPut',
    );
    return AvatarPut(
      avatar: _i1.TonikFileBytes(
        _$values[r'avatar'].decodeSimpleBinary(context: r'AvatarPut.avatar'),
      ),
    );
  }

  factory AvatarPut.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'AvatarPut');
    return AvatarPut(
      avatar: _i1.TonikFileBytes(
        _$map[r'avatar'].decodeJsonBinary(context: r'AvatarPut.avatar'),
      ),
    );
  }

  factory AvatarPut.fromForm(_i3.String? value, {required _i3.bool explode}) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'avatar'},
      listKeys: {},
      context: r'AvatarPut',
    );
    return AvatarPut(
      avatar: _i1.TonikFileBytes(
        _$values[r'avatar'].decodeFormBinary(context: r'AvatarPut.avatar'),
      ),
    );
  }

  final _i1.TonikFile avatar;

  @_i3.override
  _i3.Object? toJson() => {r'avatar': avatar.toBytes().decodeToString()};

  $$AvatarPutCopyWith<AvatarPut> get copyWith => _AvatarPutCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is AvatarPut && other.avatar == this.avatar;
  }

  @_i3.override
  _i3.int get hashCode => avatar.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'avatar'] = _i1.PropertyValue.scalar(
      avatar.toBytes().decodeToString(),
    );
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
      r'Cannot uriEncode AvatarPut: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$AvatarPutCopyWith<$Res> {
  factory $$AvatarPutCopyWith(AvatarPut value) = _AvatarPutCopyWith<$Res>;

  $Res call({_i1.TonikFile? avatar});
  _i1.TonikFile get avatar;
}

class _AvatarPutCopyWith<$Res> implements $$AvatarPutCopyWith<$Res> {
  _AvatarPutCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final AvatarPut _value;

  @_i3.override
  _i1.TonikFile get avatar => _value.avatar;

  @_i3.override
  $Res call({_i3.Object? avatar = _sentinel}) {
    return (AvatarPut(
      avatar: _i3.identical(avatar, _sentinel)
          ? this.avatar
          : (avatar as _i1.TonikFile),
    ) as $Res);
  }
}
