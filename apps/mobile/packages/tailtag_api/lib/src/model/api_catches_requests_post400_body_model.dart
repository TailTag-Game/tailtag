// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:collection/collection.dart' as _i4;
import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesRequestsPost400BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesRequestsPost400BodyModel({required this.payload});

  factory ApiCatchesRequestsPost400BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'payload'},
      listKeys: {r'payload'},
      context: r'ApiCatchesRequestsPost400BodyModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return ApiCatchesRequestsPost400BodyModel(
      payload: _$values[r'payload'].decodeSimpleStringList(
        context: r'ApiCatchesRequestsPost400BodyModel.payload',
        isHeader: isHeader,
      ),
    );
  }

  factory ApiCatchesRequestsPost400BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiCatchesRequestsPost400BodyModel',
    );
    return ApiCatchesRequestsPost400BodyModel(
      payload: _$map[r'payload'].decodeJsonList<_i3.String>(
        context: r'ApiCatchesRequestsPost400BodyModel.payload',
      ),
    );
  }

  factory ApiCatchesRequestsPost400BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'payload'},
      listKeys: {r'payload'},
      context: r'ApiCatchesRequestsPost400BodyModel',
    );
    return ApiCatchesRequestsPost400BodyModel(
      payload: _$values[r'payload'].decodeFormStringList(
        context: r'ApiCatchesRequestsPost400BodyModel.payload',
      ),
    );
  }

  final _i3.List<_i3.String> payload;

  @_i3.override
  _i3.Object? toJson() => {r'payload': this.payload};

  ApiCatchesRequestsPost400BodyModel Function({_i3.List<_i3.String>? payload})
  get copyWith {
    return ({_i3.List<_i3.String>? payload}) =>
        ApiCatchesRequestsPost400BodyModel(payload: payload ?? this.payload);
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    const _$deepEquals = _i4.DeepCollectionEquality();
    return other is ApiCatchesRequestsPost400BodyModel &&
        _$deepEquals.equals(other.payload, this.payload);
  }

  @_i3.override
  _i3.int get hashCode {
    const deepEquals = _i4.DeepCollectionEquality();
    return deepEquals.hash(this.payload);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'payload'] = _i1.PropertyValue.array(this.payload);
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
      r'Cannot uriEncode ApiCatchesRequestsPost400BodyModel: complex types cannot be URI-encoded',
    );
  }
}
