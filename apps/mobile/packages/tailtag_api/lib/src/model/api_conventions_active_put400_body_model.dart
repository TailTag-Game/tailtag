// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:collection/collection.dart' as _i4;
import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsActivePut400BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsActivePut400BodyModel({this.conventionId});

  factory ApiConventionsActivePut400BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'convention_id'},
      listKeys: {r'convention_id'},
      context: r'ApiConventionsActivePut400BodyModel',
    );
    return ApiConventionsActivePut400BodyModel(
      conventionId: _$values[r'convention_id'].decodeSimpleNullableStringList(
        context: r'ApiConventionsActivePut400BodyModel.convention_id',
      ),
    );
  }

  factory ApiConventionsActivePut400BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsActivePut400BodyModel',
    );
    return ApiConventionsActivePut400BodyModel(
      conventionId: _$map[r'convention_id'].decodeJsonNullableList<_i3.String>(
        context: r'ApiConventionsActivePut400BodyModel.convention_id',
      ),
    );
  }

  factory ApiConventionsActivePut400BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'convention_id'},
      listKeys: {r'convention_id'},
      context: r'ApiConventionsActivePut400BodyModel',
    );
    return ApiConventionsActivePut400BodyModel(
      conventionId: _$values[r'convention_id'].decodeFormNullableStringList(
        context: r'ApiConventionsActivePut400BodyModel.convention_id',
      ),
    );
  }

  final _i3.List<_i3.String>? conventionId;

  @_i3.override
  _i3.Object? toJson() => {
    if (conventionId != null) r'convention_id': conventionId,
  };

  $$ApiConventionsActivePut400BodyModelCopyWith<
    ApiConventionsActivePut400BodyModel
  >
  get copyWith => _ApiConventionsActivePut400BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    const _$deepEquals = _i4.DeepCollectionEquality();
    return other is ApiConventionsActivePut400BodyModel &&
        _$deepEquals.equals(other.conventionId, this.conventionId);
  }

  @_i3.override
  _i3.int get hashCode {
    const deepEquals = _i4.DeepCollectionEquality();
    return deepEquals.hash(conventionId);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    if (conventionId != null) {
      _$result[r'convention_id'] = _i1.PropertyValue.array(conventionId!);
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
      r'Cannot uriEncode ApiConventionsActivePut400BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsActivePut400BodyModelCopyWith<$Res> {
  factory $$ApiConventionsActivePut400BodyModelCopyWith(
    ApiConventionsActivePut400BodyModel value,
  ) = _ApiConventionsActivePut400BodyModelCopyWith<$Res>;

  $Res call({_i3.List<_i3.String>? conventionId});
  _i3.List<_i3.String>? get conventionId;
}

class _ApiConventionsActivePut400BodyModelCopyWith<$Res>
    implements $$ApiConventionsActivePut400BodyModelCopyWith<$Res> {
  _ApiConventionsActivePut400BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiConventionsActivePut400BodyModel _value;

  @_i3.override
  _i3.List<_i3.String>? get conventionId => _value.conventionId;

  @_i3.override
  $Res call({_i3.Object? conventionId = _sentinel}) {
    return (ApiConventionsActivePut400BodyModel(
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.List<_i3.String>?),
    ) as $Res);
  }
}
