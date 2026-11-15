// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class OwnerRequestPlayerModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const OwnerRequestPlayerModel({
    required this.displayName,
    required this.handle,
  });

  factory OwnerRequestPlayerModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'display_name', r'handle'},
      listKeys: {},
      context: r'OwnerRequestPlayerModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return OwnerRequestPlayerModel(
      displayName: _$values[r'display_name'].decodeSimpleString(
        context: r'OwnerRequestPlayerModel.display_name',
      ),
      handle: _$values[r'handle'].decodeSimpleString(
        context: r'OwnerRequestPlayerModel.handle',
      ),
    );
  }

  factory OwnerRequestPlayerModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'OwnerRequestPlayerModel');
    return OwnerRequestPlayerModel(
      displayName: _$map[r'display_name'].decodeJsonString(
        context: r'OwnerRequestPlayerModel.display_name',
      ),
      handle: _$map[r'handle'].decodeJsonString(
        context: r'OwnerRequestPlayerModel.handle',
      ),
    );
  }

  factory OwnerRequestPlayerModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'display_name', r'handle'},
      listKeys: {},
      context: r'OwnerRequestPlayerModel',
    );
    return OwnerRequestPlayerModel(
      displayName: _$values[r'display_name'].decodeFormString(
        context: r'OwnerRequestPlayerModel.display_name',
      ),
      handle: _$values[r'handle'].decodeFormString(
        context: r'OwnerRequestPlayerModel.handle',
      ),
    );
  }

  final _i3.String displayName;

  final _i3.String handle;

  @_i3.override
  _i3.Object? toJson() => {
    r'display_name': this.displayName,
    r'handle': this.handle,
  };

  OwnerRequestPlayerModel Function({
    _i3.String? displayName,
    _i3.String? handle,
  })
  get copyWith {
    return ({_i3.String? displayName, _i3.String? handle}) =>
        OwnerRequestPlayerModel(
          displayName: displayName ?? this.displayName,
          handle: handle ?? this.handle,
        );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is OwnerRequestPlayerModel &&
        other.displayName == this.displayName &&
        other.handle == this.handle;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([this.displayName, this.handle]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'display_name'] = _i1.PropertyValue.scalar(this.displayName);
    _$result[r'handle'] = _i1.PropertyValue.scalar(this.handle);
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
      r'Cannot uriEncode OwnerRequestPlayerModel: complex types cannot be URI-encoded',
    );
  }
}
