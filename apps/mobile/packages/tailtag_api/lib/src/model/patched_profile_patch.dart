// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class PatchedProfilePatch extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const PatchedProfilePatch({this.handle, this.displayName});

  factory PatchedProfilePatch.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'handle', r'display_name'},
      listKeys: {},
      context: r'PatchedProfilePatch',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return PatchedProfilePatch(
      handle: _$values[r'handle'].decodeSimpleNullableString(
        context: r'PatchedProfilePatch.handle',
      ),
      displayName: _$values[r'display_name'].decodeSimpleNullableString(
        context: r'PatchedProfilePatch.display_name',
      ),
    );
  }

  factory PatchedProfilePatch.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'PatchedProfilePatch');
    return PatchedProfilePatch(
      handle: _$map[r'handle'].decodeJsonNullableString(
        context: r'PatchedProfilePatch.handle',
      ),
      displayName: _$map[r'display_name'].decodeJsonNullableString(
        context: r'PatchedProfilePatch.display_name',
      ),
    );
  }

  factory PatchedProfilePatch.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'handle', r'display_name'},
      listKeys: {},
      context: r'PatchedProfilePatch',
    );
    return PatchedProfilePatch(
      handle: _$values[r'handle'].decodeFormNullableString(
        context: r'PatchedProfilePatch.handle',
      ),
      displayName: _$values[r'display_name'].decodeFormNullableString(
        context: r'PatchedProfilePatch.display_name',
      ),
    );
  }

  final _i3.String? handle;

  final _i3.String? displayName;

  @_i3.override
  _i3.Object? toJson() => {
    if (this.handle != null) r'handle': this.handle,
    if (this.displayName != null) r'display_name': this.displayName,
  };

  PatchedProfilePatch Function({_i3.String? handle, _i3.String? displayName})
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({
      _i3.Object? handle = _sentinel,
      _i3.Object? displayName = _sentinel,
    }) => PatchedProfilePatch(
      handle: _i3.identical(handle, _sentinel)
          ? this.handle
          : (handle as _i3.String?),
      displayName: _i3.identical(displayName, _sentinel)
          ? this.displayName
          : (displayName as _i3.String?),
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is PatchedProfilePatch &&
        other.handle == this.handle &&
        other.displayName == this.displayName;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([this.handle, this.displayName]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    if (this.handle != null) {
      _$result[r'handle'] = _i1.PropertyValue.scalar(this.handle!);
    }
    if (this.displayName != null) {
      _$result[r'display_name'] = _i1.PropertyValue.scalar(this.displayName!);
    }
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
      r'Cannot uriEncode PatchedProfilePatch: complex types cannot be URI-encoded',
    );
  }
}
