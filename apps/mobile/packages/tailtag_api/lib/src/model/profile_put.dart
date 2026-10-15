// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ProfilePut extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ProfilePut({required this.handle, required this.displayName});

  factory ProfilePut.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'handle', r'display_name'},
      listKeys: {},
      context: r'ProfilePut',
    );
    return ProfilePut(
      handle: _$values[r'handle'].decodeSimpleString(
        context: r'ProfilePut.handle',
      ),
      displayName: _$values[r'display_name'].decodeSimpleString(
        context: r'ProfilePut.display_name',
      ),
    );
  }

  factory ProfilePut.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ProfilePut');
    return ProfilePut(
      handle: _$map[r'handle'].decodeJsonString(context: r'ProfilePut.handle'),
      displayName: _$map[r'display_name'].decodeJsonString(
        context: r'ProfilePut.display_name',
      ),
    );
  }

  factory ProfilePut.fromForm(_i3.String? value, {required _i3.bool explode}) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'handle', r'display_name'},
      listKeys: {},
      context: r'ProfilePut',
    );
    return ProfilePut(
      handle: _$values[r'handle'].decodeFormString(
        context: r'ProfilePut.handle',
      ),
      displayName: _$values[r'display_name'].decodeFormString(
        context: r'ProfilePut.display_name',
      ),
    );
  }

  final _i3.String handle;

  final _i3.String displayName;

  @_i3.override
  _i3.Object? toJson() => {r'handle': handle, r'display_name': displayName};

  $$ProfilePutCopyWith<ProfilePut> get copyWith => _ProfilePutCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ProfilePut &&
        other.handle == this.handle &&
        other.displayName == this.displayName;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([handle, displayName]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'handle'] = _i1.PropertyValue.scalar(handle);
    _$result[r'display_name'] = _i1.PropertyValue.scalar(displayName);
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
      r'Cannot uriEncode ProfilePut: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ProfilePutCopyWith<$Res> {
  factory $$ProfilePutCopyWith(ProfilePut value) = _ProfilePutCopyWith<$Res>;

  $Res call({_i3.String? handle, _i3.String? displayName});
  _i3.String get handle;
  _i3.String get displayName;
}

class _ProfilePutCopyWith<$Res> implements $$ProfilePutCopyWith<$Res> {
  _ProfilePutCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ProfilePut _value;

  @_i3.override
  _i3.String get handle => _value.handle;

  @_i3.override
  _i3.String get displayName => _value.displayName;

  @_i3.override
  $Res call({
    _i3.Object? handle = _sentinel,
    _i3.Object? displayName = _sentinel,
  }) {
    return (ProfilePut(
      handle: _i3.identical(handle, _sentinel)
          ? this.handle
          : (handle as _i3.String),
      displayName: _i3.identical(displayName, _sentinel)
          ? this.displayName
          : (displayName as _i3.String),
    ) as $Res);
  }
}
