// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel({
    this.tailtagId,
    this.name,
    this.photoUrl,
  });

  factory ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'tailtag_id', r'name', r'photo_url'},
      listKeys: {},
      context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel(
      tailtagId: _$values[r'tailtag_id'].decodeSimpleString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.tailtag_id',
      ),
      name: _$values[r'name'].decodeSimpleString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeSimpleUri(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.photo_url',
      ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel(
      tailtagId: _$map[r'tailtag_id'].decodeJsonString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.tailtag_id',
      ),
      name: _$map[r'name'].decodeJsonString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.name',
      ),
      photoUrl: _$map[r'photo_url'].decodeJsonUri(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.photo_url',
      ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'tailtag_id', r'name', r'photo_url'},
      listKeys: {},
      context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel(
      tailtagId: _$values[r'tailtag_id'].decodeFormString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.tailtag_id',
      ),
      name: _$values[r'name'].decodeFormString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeFormUri(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel.photo_url',
      ),
    );
  }

  final _i3.String? tailtagId;

  final _i3.String? name;

  final _i3.Uri? photoUrl;

  @_i3.override
  _i3.Object? toJson() => throw _i1.EncodingException(
    r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel is read-only and cannot be encoded.',
  );

  ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel
  Function({_i3.String? tailtagId, _i3.String? name, _i3.Uri? photoUrl})
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({
      _i3.Object? tailtagId = _sentinel,
      _i3.Object? name = _sentinel,
      _i3.Object? photoUrl = _sentinel,
    }) =>
        ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel(
          tailtagId: _i3.identical(tailtagId, _sentinel)
              ? this.tailtagId
              : (tailtagId as _i3.String?),
          name: _i3.identical(name, _sentinel)
              ? this.name
              : (name as _i3.String?),
          photoUrl: _i3.identical(photoUrl, _sentinel)
              ? this.photoUrl
              : (photoUrl as _i3.Uri?),
        );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel &&
        other.tailtagId == this.tailtagId &&
        other.name == this.name &&
        other.photoUrl == this.photoUrl;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([this.tailtagId, this.name, this.photoUrl]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel is read-only and cannot be encoded.',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i4.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiConventionsConventionIdCatchCredentialsResolvePost200BodyFursuitModel: complex types cannot be URI-encoded',
    );
  }
}
