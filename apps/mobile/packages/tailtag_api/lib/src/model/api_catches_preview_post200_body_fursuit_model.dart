// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesPreviewPost200BodyFursuitModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesPreviewPost200BodyFursuitModel({
    required this.id,
    required this.tailtagId,
    required this.name,
    required this.photoUrl,
  });

  factory ApiCatchesPreviewPost200BodyFursuitModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'id', r'tailtag_id', r'name', r'photo_url'},
      listKeys: {},
      context: r'ApiCatchesPreviewPost200BodyFursuitModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return ApiCatchesPreviewPost200BodyFursuitModel(
      id: _$values[r'id'].decodeSimpleInt(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.id',
      ),
      tailtagId: _$values[r'tailtag_id'].decodeSimpleString(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.tailtag_id',
      ),
      name: _$values[r'name'].decodeSimpleString(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeSimpleUri(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.photo_url',
      ),
    );
  }

  factory ApiCatchesPreviewPost200BodyFursuitModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiCatchesPreviewPost200BodyFursuitModel',
    );
    return ApiCatchesPreviewPost200BodyFursuitModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.id',
      ),
      tailtagId: _$map[r'tailtag_id'].decodeJsonString(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.tailtag_id',
      ),
      name: _$map[r'name'].decodeJsonString(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.name',
      ),
      photoUrl: _$map[r'photo_url'].decodeJsonUri(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.photo_url',
      ),
    );
  }

  factory ApiCatchesPreviewPost200BodyFursuitModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'id', r'tailtag_id', r'name', r'photo_url'},
      listKeys: {},
      context: r'ApiCatchesPreviewPost200BodyFursuitModel',
    );
    return ApiCatchesPreviewPost200BodyFursuitModel(
      id: _$values[r'id'].decodeFormInt(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.id',
      ),
      tailtagId: _$values[r'tailtag_id'].decodeFormString(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.tailtag_id',
      ),
      name: _$values[r'name'].decodeFormString(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeFormUri(
        context: r'ApiCatchesPreviewPost200BodyFursuitModel.photo_url',
      ),
    );
  }

  final _i3.int id;

  final _i3.String tailtagId;

  final _i3.String name;

  final _i3.Uri photoUrl;

  @_i3.override
  _i3.Object? toJson() => {
    r'id': this.id,
    r'tailtag_id': this.tailtagId,
    r'name': this.name,
    r'photo_url': this.photoUrl.toString(),
  };

  ApiCatchesPreviewPost200BodyFursuitModel Function({
    _i3.int? id,
    _i3.String? tailtagId,
    _i3.String? name,
    _i3.Uri? photoUrl,
  })
  get copyWith {
    return ({
      _i3.int? id,
      _i3.String? tailtagId,
      _i3.String? name,
      _i3.Uri? photoUrl,
    }) => ApiCatchesPreviewPost200BodyFursuitModel(
      id: id ?? this.id,
      tailtagId: tailtagId ?? this.tailtagId,
      name: name ?? this.name,
      photoUrl: photoUrl ?? this.photoUrl,
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesPreviewPost200BodyFursuitModel &&
        other.id == this.id &&
        other.tailtagId == this.tailtagId &&
        other.name == this.name &&
        other.photoUrl == this.photoUrl;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      this.id,
      this.tailtagId,
      this.name,
      this.photoUrl,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'id'] = _i1.PropertyValue.scalar(this.id.toString());
    _$result[r'tailtag_id'] = _i1.PropertyValue.scalar(this.tailtagId);
    _$result[r'name'] = _i1.PropertyValue.scalar(this.name);
    _$result[r'photo_url'] = _i1.PropertyValue.scalar(this.photoUrl.toString());
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
      r'Cannot uriEncode ApiCatchesPreviewPost200BodyFursuitModel: complex types cannot be URI-encoded',
    );
  }
}
