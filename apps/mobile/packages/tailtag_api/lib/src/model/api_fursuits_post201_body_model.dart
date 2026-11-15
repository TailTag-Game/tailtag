// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_approval_mode.dart' as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiFursuitsPost201BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsPost201BodyModel({
    required this.name,
    required this.catchApprovalMode,
    this.id,
    this.tailtagId,
    this.photoUrl,
    this.isEnabled,
  });

  factory ApiFursuitsPost201BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {
        r'id',
        r'tailtag_id',
        r'name',
        r'photo_url',
        r'is_enabled',
        r'catch_approval_mode',
      },
      listKeys: {},
      context: r'ApiFursuitsPost201BodyModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
    );
    return ApiFursuitsPost201BodyModel(
      id: _$values[r'id'].decodeSimpleInt(
        context: r'ApiFursuitsPost201BodyModel.id',
      ),
      tailtagId: _$values[r'tailtag_id'].decodeSimpleString(
        context: r'ApiFursuitsPost201BodyModel.tailtag_id',
      ),
      name: _$values[r'name'].decodeSimpleString(
        context: r'ApiFursuitsPost201BodyModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeSimpleUri(
        context: r'ApiFursuitsPost201BodyModel.photo_url',
      ),
      isEnabled: _$values[r'is_enabled'].decodeSimpleBool(
        context: r'ApiFursuitsPost201BodyModel.is_enabled',
      ),
      catchApprovalMode: _i4.CatchApprovalMode.fromSimple(
        _$values[r'catch_approval_mode'],
        explode: explode,
      ),
    );
  }

  factory ApiFursuitsPost201BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiFursuitsPost201BodyModel');
    return ApiFursuitsPost201BodyModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'ApiFursuitsPost201BodyModel.id',
      ),
      tailtagId: _$map[r'tailtag_id'].decodeJsonString(
        context: r'ApiFursuitsPost201BodyModel.tailtag_id',
      ),
      name: _$map[r'name'].decodeJsonString(
        context: r'ApiFursuitsPost201BodyModel.name',
      ),
      photoUrl: _$map[r'photo_url'].decodeJsonUri(
        context: r'ApiFursuitsPost201BodyModel.photo_url',
      ),
      isEnabled: _$map[r'is_enabled'].decodeJsonBool(
        context: r'ApiFursuitsPost201BodyModel.is_enabled',
      ),
      catchApprovalMode: _i4.CatchApprovalMode.fromJson(
        _$map[r'catch_approval_mode'],
      ),
    );
  }

  factory ApiFursuitsPost201BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {
        r'id',
        r'tailtag_id',
        r'name',
        r'photo_url',
        r'is_enabled',
        r'catch_approval_mode',
      },
      listKeys: {},
      context: r'ApiFursuitsPost201BodyModel',
    );
    return ApiFursuitsPost201BodyModel(
      id: _$values[r'id'].decodeFormInt(
        context: r'ApiFursuitsPost201BodyModel.id',
      ),
      tailtagId: _$values[r'tailtag_id'].decodeFormString(
        context: r'ApiFursuitsPost201BodyModel.tailtag_id',
      ),
      name: _$values[r'name'].decodeFormString(
        context: r'ApiFursuitsPost201BodyModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeFormUri(
        context: r'ApiFursuitsPost201BodyModel.photo_url',
      ),
      isEnabled: _$values[r'is_enabled'].decodeFormBool(
        context: r'ApiFursuitsPost201BodyModel.is_enabled',
      ),
      catchApprovalMode: _i4.CatchApprovalMode.fromForm(
        _$values[r'catch_approval_mode'],
        explode: explode,
      ),
    );
  }

  final _i3.int? id;

  final _i3.String? tailtagId;

  final _i3.String name;

  final _i3.Uri? photoUrl;

  final _i3.bool? isEnabled;

  final _i4.CatchApprovalMode catchApprovalMode;

  @_i3.override
  _i3.Object? toJson() => {
    r'name': this.name,
    r'catch_approval_mode': this.catchApprovalMode.toJson(),
  };

  ApiFursuitsPost201BodyModel Function({
    _i3.int? id,
    _i3.String? tailtagId,
    _i3.String? name,
    _i3.Uri? photoUrl,
    _i3.bool? isEnabled,
    _i4.CatchApprovalMode? catchApprovalMode,
  })
  get copyWith {
    const _i3.Object _sentinel = _i3.Object();
    return ({
      _i3.Object? id = _sentinel,
      _i3.Object? tailtagId = _sentinel,
      _i3.String? name,
      _i3.Object? photoUrl = _sentinel,
      _i3.Object? isEnabled = _sentinel,
      _i4.CatchApprovalMode? catchApprovalMode,
    }) => ApiFursuitsPost201BodyModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      tailtagId: _i3.identical(tailtagId, _sentinel)
          ? this.tailtagId
          : (tailtagId as _i3.String?),
      name: name ?? this.name,
      photoUrl: _i3.identical(photoUrl, _sentinel)
          ? this.photoUrl
          : (photoUrl as _i3.Uri?),
      isEnabled: _i3.identical(isEnabled, _sentinel)
          ? this.isEnabled
          : (isEnabled as _i3.bool?),
      catchApprovalMode: catchApprovalMode ?? this.catchApprovalMode,
    );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsPost201BodyModel &&
        other.id == this.id &&
        other.tailtagId == this.tailtagId &&
        other.name == this.name &&
        other.photoUrl == this.photoUrl &&
        other.isEnabled == this.isEnabled &&
        other.catchApprovalMode == this.catchApprovalMode;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([
      this.id,
      this.tailtagId,
      this.name,
      this.photoUrl,
      this.isEnabled,
      this.catchApprovalMode,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'name'] = _i1.PropertyValue.scalar(this.name);
    _$result[r'catch_approval_mode'] = _i1.PropertyValue.scalar(
      this.catchApprovalMode.toJson(),
    );
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
      r'Cannot uriEncode ApiFursuitsPost201BodyModel: complex types cannot be URI-encoded',
    );
  }
}
