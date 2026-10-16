// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiFursuitsPostBodyBodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsPostBodyBodyModel({required this.name, required this.photo});

  factory ApiFursuitsPostBodyBodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'name', r'photo'},
      listKeys: {},
      context: r'ApiFursuitsPostBodyBodyModel',
    );
    return ApiFursuitsPostBodyBodyModel(
      name: _$values[r'name'].decodeSimpleString(
        context: r'ApiFursuitsPostBodyBodyModel.name',
      ),
      photo: _i1.TonikFileBytes(
        _$values[r'photo'].decodeSimpleBinary(
          context: r'ApiFursuitsPostBodyBodyModel.photo',
        ),
      ),
    );
  }

  factory ApiFursuitsPostBodyBodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiFursuitsPostBodyBodyModel');
    return ApiFursuitsPostBodyBodyModel(
      name: _$map[r'name'].decodeJsonString(
        context: r'ApiFursuitsPostBodyBodyModel.name',
      ),
      photo: _i1.TonikFileBytes(
        _$map[r'photo'].decodeJsonBinary(
          context: r'ApiFursuitsPostBodyBodyModel.photo',
        ),
      ),
    );
  }

  factory ApiFursuitsPostBodyBodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'name', r'photo'},
      listKeys: {},
      context: r'ApiFursuitsPostBodyBodyModel',
    );
    return ApiFursuitsPostBodyBodyModel(
      name: _$values[r'name'].decodeFormString(
        context: r'ApiFursuitsPostBodyBodyModel.name',
      ),
      photo: _i1.TonikFileBytes(
        _$values[r'photo'].decodeFormBinary(
          context: r'ApiFursuitsPostBodyBodyModel.photo',
        ),
      ),
    );
  }

  final _i3.String name;

  final _i1.TonikFile photo;

  @_i3.override
  _i3.Object? toJson() => {
    r'name': name,
    r'photo': photo.toBytes().decodeToString(),
  };

  $$ApiFursuitsPostBodyBodyModelCopyWith<ApiFursuitsPostBodyBodyModel>
  get copyWith => _ApiFursuitsPostBodyBodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsPostBodyBodyModel &&
        other.name == this.name &&
        other.photo == this.photo;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([name, photo]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'name'] = _i1.PropertyValue.scalar(name);
    _$result[r'photo'] = _i1.PropertyValue.scalar(
      photo.toBytes().decodeToString(),
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
      r'Cannot uriEncode ApiFursuitsPostBodyBodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiFursuitsPostBodyBodyModelCopyWith<$Res> {
  factory $$ApiFursuitsPostBodyBodyModelCopyWith(
    ApiFursuitsPostBodyBodyModel value,
  ) = _ApiFursuitsPostBodyBodyModelCopyWith<$Res>;

  $Res call({_i3.String? name, _i1.TonikFile? photo});
  _i3.String get name;
  _i1.TonikFile get photo;
}

class _ApiFursuitsPostBodyBodyModelCopyWith<$Res>
    implements $$ApiFursuitsPostBodyBodyModelCopyWith<$Res> {
  _ApiFursuitsPostBodyBodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiFursuitsPostBodyBodyModel _value;

  @_i3.override
  _i3.String get name => _value.name;

  @_i3.override
  _i1.TonikFile get photo => _value.photo;

  @_i3.override
  $Res call({_i3.Object? name = _sentinel, _i3.Object? photo = _sentinel}) {
    return (ApiFursuitsPostBodyBodyModel(
      name: _i3.identical(name, _sentinel) ? this.name : (name as _i3.String),
      photo: _i3.identical(photo, _sentinel)
          ? this.photo
          : (photo as _i1.TonikFile),
    ) as $Res);
  }
}
