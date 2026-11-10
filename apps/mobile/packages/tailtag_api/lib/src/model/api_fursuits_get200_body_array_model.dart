// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_fursuits_get200_body_array_catch_approval_mode_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiFursuitsGet200BodyArrayModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsGet200BodyArrayModel({
    required this.name,
    required this.catchApprovalMode,
    this.id,
    this.tailtagId,
    this.photoUrl,
    this.isEnabled,
  });

  factory ApiFursuitsGet200BodyArrayModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
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
      context: r'ApiFursuitsGet200BodyArrayModel',
    );
    return ApiFursuitsGet200BodyArrayModel(
      id: _$values[r'id'].decodeSimpleInt(
        context: r'ApiFursuitsGet200BodyArrayModel.id',
      ),
      tailtagId: _$values[r'tailtag_id'].decodeSimpleString(
        context: r'ApiFursuitsGet200BodyArrayModel.tailtag_id',
      ),
      name: _$values[r'name'].decodeSimpleString(
        context: r'ApiFursuitsGet200BodyArrayModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeSimpleUri(
        context: r'ApiFursuitsGet200BodyArrayModel.photo_url',
      ),
      isEnabled: _$values[r'is_enabled'].decodeSimpleBool(
        context: r'ApiFursuitsGet200BodyArrayModel.is_enabled',
      ),
      catchApprovalMode:
          _i4.ApiFursuitsGet200BodyArrayCatchApprovalModeModel.fromSimple(
            _$values[r'catch_approval_mode'],
            explode: explode,
          ),
    );
  }

  factory ApiFursuitsGet200BodyArrayModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiFursuitsGet200BodyArrayModel');
    return ApiFursuitsGet200BodyArrayModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'ApiFursuitsGet200BodyArrayModel.id',
      ),
      tailtagId: _$map[r'tailtag_id'].decodeJsonString(
        context: r'ApiFursuitsGet200BodyArrayModel.tailtag_id',
      ),
      name: _$map[r'name'].decodeJsonString(
        context: r'ApiFursuitsGet200BodyArrayModel.name',
      ),
      photoUrl: _$map[r'photo_url'].decodeJsonUri(
        context: r'ApiFursuitsGet200BodyArrayModel.photo_url',
      ),
      isEnabled: _$map[r'is_enabled'].decodeJsonBool(
        context: r'ApiFursuitsGet200BodyArrayModel.is_enabled',
      ),
      catchApprovalMode:
          _i4.ApiFursuitsGet200BodyArrayCatchApprovalModeModel.fromJson(
            _$map[r'catch_approval_mode'],
          ),
    );
  }

  factory ApiFursuitsGet200BodyArrayModel.fromForm(
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
      context: r'ApiFursuitsGet200BodyArrayModel',
    );
    return ApiFursuitsGet200BodyArrayModel(
      id: _$values[r'id'].decodeFormInt(
        context: r'ApiFursuitsGet200BodyArrayModel.id',
      ),
      tailtagId: _$values[r'tailtag_id'].decodeFormString(
        context: r'ApiFursuitsGet200BodyArrayModel.tailtag_id',
      ),
      name: _$values[r'name'].decodeFormString(
        context: r'ApiFursuitsGet200BodyArrayModel.name',
      ),
      photoUrl: _$values[r'photo_url'].decodeFormUri(
        context: r'ApiFursuitsGet200BodyArrayModel.photo_url',
      ),
      isEnabled: _$values[r'is_enabled'].decodeFormBool(
        context: r'ApiFursuitsGet200BodyArrayModel.is_enabled',
      ),
      catchApprovalMode:
          _i4.ApiFursuitsGet200BodyArrayCatchApprovalModeModel.fromForm(
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

  /// manual by default. A change applies only to new requests.
  final _i4.ApiFursuitsGet200BodyArrayCatchApprovalModeModel catchApprovalMode;

  @_i3.override
  _i3.Object? toJson() => {
    r'name': name,
    r'catch_approval_mode': catchApprovalMode.toJson(),
  };

  $$ApiFursuitsGet200BodyArrayModelCopyWith<ApiFursuitsGet200BodyArrayModel>
  get copyWith => _ApiFursuitsGet200BodyArrayModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsGet200BodyArrayModel &&
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
      id,
      tailtagId,
      name,
      photoUrl,
      isEnabled,
      catchApprovalMode,
    ]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'name'] = _i1.PropertyValue.scalar(name);
    _$result[r'catch_approval_mode'] = _i1.PropertyValue.scalar(
      catchApprovalMode.toJson(),
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
      r'Cannot uriEncode ApiFursuitsGet200BodyArrayModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiFursuitsGet200BodyArrayModelCopyWith<$Res> {
  factory $$ApiFursuitsGet200BodyArrayModelCopyWith(
    ApiFursuitsGet200BodyArrayModel value,
  ) = _ApiFursuitsGet200BodyArrayModelCopyWith<$Res>;

  $Res call({
    _i3.int? id,
    _i3.String? tailtagId,
    _i3.String? name,
    _i3.Uri? photoUrl,
    _i3.bool? isEnabled,
    _i4.ApiFursuitsGet200BodyArrayCatchApprovalModeModel? catchApprovalMode,
  });
  _i3.int? get id;
  _i3.String? get tailtagId;
  _i3.String get name;
  _i3.Uri? get photoUrl;
  _i3.bool? get isEnabled;
  _i4.ApiFursuitsGet200BodyArrayCatchApprovalModeModel get catchApprovalMode;
}

class _ApiFursuitsGet200BodyArrayModelCopyWith<$Res>
    implements $$ApiFursuitsGet200BodyArrayModelCopyWith<$Res> {
  _ApiFursuitsGet200BodyArrayModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiFursuitsGet200BodyArrayModel _value;

  @_i3.override
  _i3.int? get id => _value.id;

  @_i3.override
  _i3.String? get tailtagId => _value.tailtagId;

  @_i3.override
  _i3.String get name => _value.name;

  @_i3.override
  _i3.Uri? get photoUrl => _value.photoUrl;

  @_i3.override
  _i3.bool? get isEnabled => _value.isEnabled;

  @_i3.override
  _i4.ApiFursuitsGet200BodyArrayCatchApprovalModeModel get catchApprovalMode =>
      _value.catchApprovalMode;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? tailtagId = _sentinel,
    _i3.Object? name = _sentinel,
    _i3.Object? photoUrl = _sentinel,
    _i3.Object? isEnabled = _sentinel,
    _i3.Object? catchApprovalMode = _sentinel,
  }) {
    return (ApiFursuitsGet200BodyArrayModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      tailtagId: _i3.identical(tailtagId, _sentinel)
          ? this.tailtagId
          : (tailtagId as _i3.String?),
      name: _i3.identical(name, _sentinel) ? this.name : (name as _i3.String),
      photoUrl: _i3.identical(photoUrl, _sentinel)
          ? this.photoUrl
          : (photoUrl as _i3.Uri?),
      isEnabled: _i3.identical(isEnabled, _sentinel)
          ? this.isEnabled
          : (isEnabled as _i3.bool?),
      catchApprovalMode: _i3.identical(catchApprovalMode, _sentinel)
          ? this.catchApprovalMode
          : (catchApprovalMode
                as _i4.ApiFursuitsGet200BodyArrayCatchApprovalModeModel),
    ) as $Res);
  }
}
