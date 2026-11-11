// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiFursuitsIdPhotoPutBodyBodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsIdPhotoPutBodyBodyModel({required this.photo});

  factory ApiFursuitsIdPhotoPutBodyBodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'photo'},
      listKeys: {},
      context: r'ApiFursuitsIdPhotoPutBodyBodyModel',
    );
    return ApiFursuitsIdPhotoPutBodyBodyModel(
      photo: _i1.TonikFileBytes(
        _$values[r'photo'].decodeSimpleBinary(
          context: r'ApiFursuitsIdPhotoPutBodyBodyModel.photo',
        ),
      ),
    );
  }

  factory ApiFursuitsIdPhotoPutBodyBodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiFursuitsIdPhotoPutBodyBodyModel',
    );
    return ApiFursuitsIdPhotoPutBodyBodyModel(
      photo: _i1.TonikFileBytes(
        _$map[r'photo'].decodeJsonBinary(
          context: r'ApiFursuitsIdPhotoPutBodyBodyModel.photo',
        ),
      ),
    );
  }

  factory ApiFursuitsIdPhotoPutBodyBodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'photo'},
      listKeys: {},
      context: r'ApiFursuitsIdPhotoPutBodyBodyModel',
    );
    return ApiFursuitsIdPhotoPutBodyBodyModel(
      photo: _i1.TonikFileBytes(
        _$values[r'photo'].decodeFormBinary(
          context: r'ApiFursuitsIdPhotoPutBodyBodyModel.photo',
        ),
      ),
    );
  }

  final _i1.TonikFile photo;

  @_i3.override
  _i3.Object? toJson() => {r'photo': photo.toBytes().decodeToString()};

  $$ApiFursuitsIdPhotoPutBodyBodyModelCopyWith<
    ApiFursuitsIdPhotoPutBodyBodyModel
  >
  get copyWith => _ApiFursuitsIdPhotoPutBodyBodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsIdPhotoPutBodyBodyModel &&
        other.photo == this.photo;
  }

  @_i3.override
  _i3.int get hashCode => photo.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
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
      r'Cannot uriEncode ApiFursuitsIdPhotoPutBodyBodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiFursuitsIdPhotoPutBodyBodyModelCopyWith<$Res> {
  factory $$ApiFursuitsIdPhotoPutBodyBodyModelCopyWith(
    ApiFursuitsIdPhotoPutBodyBodyModel value,
  ) = _ApiFursuitsIdPhotoPutBodyBodyModelCopyWith<$Res>;

  $Res call({_i1.TonikFile? photo});
  _i1.TonikFile get photo;
}

class _ApiFursuitsIdPhotoPutBodyBodyModelCopyWith<$Res>
    implements $$ApiFursuitsIdPhotoPutBodyBodyModelCopyWith<$Res> {
  _ApiFursuitsIdPhotoPutBodyBodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiFursuitsIdPhotoPutBodyBodyModel _value;

  @_i3.override
  _i1.TonikFile get photo => _value.photo;

  @_i3.override
  $Res call({_i3.Object? photo = _sentinel}) {
    return (ApiFursuitsIdPhotoPutBodyBodyModel(
      photo: _i3.identical(photo, _sentinel)
          ? this.photo
          : (photo as _i1.TonikFile),
    ) as $Res);
  }
}
