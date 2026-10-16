// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiMeGet200BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiMeGet200BodyModel({required this.id});

  factory ApiMeGet200BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'id'},
      listKeys: {},
      context: r'ApiMeGet200BodyModel',
    );
    return ApiMeGet200BodyModel(
      id: _$values[r'id'].decodeSimpleInt(context: r'ApiMeGet200BodyModel.id'),
    );
  }

  factory ApiMeGet200BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiMeGet200BodyModel');
    return ApiMeGet200BodyModel(
      id: _$map[r'id'].decodeJsonInt(context: r'ApiMeGet200BodyModel.id'),
    );
  }

  factory ApiMeGet200BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'id'},
      listKeys: {},
      context: r'ApiMeGet200BodyModel',
    );
    return ApiMeGet200BodyModel(
      id: _$values[r'id'].decodeFormInt(context: r'ApiMeGet200BodyModel.id'),
    );
  }

  final _i3.int id;

  @_i3.override
  _i3.Object? toJson() => {r'id': id};

  $$ApiMeGet200BodyModelCopyWith<ApiMeGet200BodyModel> get copyWith =>
      _ApiMeGet200BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiMeGet200BodyModel && other.id == this.id;
  }

  @_i3.override
  _i3.int get hashCode => id.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'id'] = _i1.PropertyValue.scalar(id.toString());
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
      r'Cannot uriEncode ApiMeGet200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiMeGet200BodyModelCopyWith<$Res> {
  factory $$ApiMeGet200BodyModelCopyWith(ApiMeGet200BodyModel value) =
      _ApiMeGet200BodyModelCopyWith<$Res>;

  $Res call({_i3.int? id});
  _i3.int get id;
}

class _ApiMeGet200BodyModelCopyWith<$Res>
    implements $$ApiMeGet200BodyModelCopyWith<$Res> {
  _ApiMeGet200BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiMeGet200BodyModel _value;

  @_i3.override
  _i3.int get id => _value.id;

  @_i3.override
  $Res call({_i3.Object? id = _sentinel}) {
    return (ApiMeGet200BodyModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int),
    ) as $Res);
  }
}
