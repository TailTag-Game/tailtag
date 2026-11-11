// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchHistoryResponseSchemaResultsArrayFursuitModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchHistoryResponseSchemaResultsArrayFursuitModel({
    this.id,
    this.name,
    this.photoUrl,
  });

  factory CatchHistoryResponseSchemaResultsArrayFursuitModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'id', r'name', r'photo_url'},
      listKeys: {},
      context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel',
    );
    return CatchHistoryResponseSchemaResultsArrayFursuitModel(
      id: _$values[r'id'].decodeSimpleInt(
        context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel.id',
      ),
      name: _$values[r'name'].decodeSimpleString(
        context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeSimpleUri(
        context:
            r'CatchHistoryResponseSchemaResultsArrayFursuitModel.photo_url',
      ),
    );
  }

  factory CatchHistoryResponseSchemaResultsArrayFursuitModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel',
    );
    return CatchHistoryResponseSchemaResultsArrayFursuitModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel.id',
      ),
      name: _$map[r'name'].decodeJsonString(
        context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel.name',
      ),
      photoUrl: _$map[r'photo_url'].decodeJsonUri(
        context:
            r'CatchHistoryResponseSchemaResultsArrayFursuitModel.photo_url',
      ),
    );
  }

  factory CatchHistoryResponseSchemaResultsArrayFursuitModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'id', r'name', r'photo_url'},
      listKeys: {},
      context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel',
    );
    return CatchHistoryResponseSchemaResultsArrayFursuitModel(
      id: _$values[r'id'].decodeFormInt(
        context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel.id',
      ),
      name: _$values[r'name'].decodeFormString(
        context: r'CatchHistoryResponseSchemaResultsArrayFursuitModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeFormUri(
        context:
            r'CatchHistoryResponseSchemaResultsArrayFursuitModel.photo_url',
      ),
    );
  }

  final _i3.int? id;

  final _i3.String? name;

  final _i3.Uri? photoUrl;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$CatchHistoryResponseSchemaResultsArrayFursuitModelCopyWith<
    CatchHistoryResponseSchemaResultsArrayFursuitModel
  >
  get copyWith =>
      _CatchHistoryResponseSchemaResultsArrayFursuitModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchHistoryResponseSchemaResultsArrayFursuitModel &&
        other.id == this.id &&
        other.name == this.name &&
        other.photoUrl == this.photoUrl;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([id, name, photoUrl]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    return <_i3.String, _i1.PropertyValue>{};
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i4.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode CatchHistoryResponseSchemaResultsArrayFursuitModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchHistoryResponseSchemaResultsArrayFursuitModelCopyWith<
  $Res
> {
  factory $$CatchHistoryResponseSchemaResultsArrayFursuitModelCopyWith(
    CatchHistoryResponseSchemaResultsArrayFursuitModel value,
  ) = _CatchHistoryResponseSchemaResultsArrayFursuitModelCopyWith<$Res>;

  $Res call({_i3.int? id, _i3.String? name, _i3.Uri? photoUrl});
  _i3.int? get id;
  _i3.String? get name;
  _i3.Uri? get photoUrl;
}

class _CatchHistoryResponseSchemaResultsArrayFursuitModelCopyWith<$Res>
    implements
        $$CatchHistoryResponseSchemaResultsArrayFursuitModelCopyWith<$Res> {
  _CatchHistoryResponseSchemaResultsArrayFursuitModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchHistoryResponseSchemaResultsArrayFursuitModel _value;

  @_i3.override
  _i3.int? get id => _value.id;

  @_i3.override
  _i3.String? get name => _value.name;

  @_i3.override
  _i3.Uri? get photoUrl => _value.photoUrl;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? name = _sentinel,
    _i3.Object? photoUrl = _sentinel,
  }) {
    return (CatchHistoryResponseSchemaResultsArrayFursuitModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      name: _i3.identical(name, _sentinel) ? this.name : (name as _i3.String?),
      photoUrl: _i3.identical(photoUrl, _sentinel)
          ? this.photoUrl
          : (photoUrl as _i3.Uri?),
    ) as $Res);
  }
}
