// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_fursuits_id_patch_body_body_catch_approval_mode_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// Send name, catch_approval_mode, or both.
@_i2.immutable
class ApiFursuitsIdPatchBodyBodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsIdPatchBodyBodyModel({this.name, this.catchApprovalMode});

  factory ApiFursuitsIdPatchBodyBodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'name', r'catch_approval_mode'},
      listKeys: {},
      context: r'ApiFursuitsIdPatchBodyBodyModel',
    );
    return ApiFursuitsIdPatchBodyBodyModel(
      name: _$values[r'name'].decodeSimpleNullableString(
        context: r'ApiFursuitsIdPatchBodyBodyModel.name',
      ),
      catchApprovalMode: _$values[r'catch_approval_mode'] == null
          ? null
          : _i4.ApiFursuitsIdPatchBodyBodyCatchApprovalModeModel.fromSimple(
              _$values[r'catch_approval_mode'],
              explode: explode,
            ),
    );
  }

  factory ApiFursuitsIdPatchBodyBodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiFursuitsIdPatchBodyBodyModel');
    return ApiFursuitsIdPatchBodyBodyModel(
      name: _$map[r'name'].decodeJsonNullableString(
        context: r'ApiFursuitsIdPatchBodyBodyModel.name',
      ),
      catchApprovalMode: _$map[r'catch_approval_mode'] == null
          ? null
          : _i4.ApiFursuitsIdPatchBodyBodyCatchApprovalModeModel.fromJson(
              _$map[r'catch_approval_mode'],
            ),
    );
  }

  factory ApiFursuitsIdPatchBodyBodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'name', r'catch_approval_mode'},
      listKeys: {},
      context: r'ApiFursuitsIdPatchBodyBodyModel',
    );
    return ApiFursuitsIdPatchBodyBodyModel(
      name: _$values[r'name'].decodeFormNullableString(
        context: r'ApiFursuitsIdPatchBodyBodyModel.name',
      ),
      catchApprovalMode: _$values[r'catch_approval_mode'] == null
          ? null
          : _i4.ApiFursuitsIdPatchBodyBodyCatchApprovalModeModel.fromForm(
              _$values[r'catch_approval_mode'],
              explode: explode,
            ),
    );
  }

  final _i3.String? name;

  final _i4.ApiFursuitsIdPatchBodyBodyCatchApprovalModeModel? catchApprovalMode;

  @_i3.override
  _i3.Object? toJson() => {
    if (name != null) r'name': name,
    if (catchApprovalMode != null)
      r'catch_approval_mode': catchApprovalMode?.toJson(),
  };

  $$ApiFursuitsIdPatchBodyBodyModelCopyWith<ApiFursuitsIdPatchBodyBodyModel>
  get copyWith => _ApiFursuitsIdPatchBodyBodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsIdPatchBodyBodyModel &&
        other.name == this.name &&
        other.catchApprovalMode == this.catchApprovalMode;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([name, catchApprovalMode]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    if (name != null) {
      _$result[r'name'] = _i1.PropertyValue.scalar(name!);
    }
    if (catchApprovalMode != null) {
      _$result[r'catch_approval_mode'] = _i1.PropertyValue.scalar(
        catchApprovalMode!.toJson(),
      );
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
      r'Cannot uriEncode ApiFursuitsIdPatchBodyBodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiFursuitsIdPatchBodyBodyModelCopyWith<$Res> {
  factory $$ApiFursuitsIdPatchBodyBodyModelCopyWith(
    ApiFursuitsIdPatchBodyBodyModel value,
  ) = _ApiFursuitsIdPatchBodyBodyModelCopyWith<$Res>;

  $Res call({
    _i3.String? name,
    _i4.ApiFursuitsIdPatchBodyBodyCatchApprovalModeModel? catchApprovalMode,
  });
  _i3.String? get name;
  _i4.ApiFursuitsIdPatchBodyBodyCatchApprovalModeModel? get catchApprovalMode;
}

class _ApiFursuitsIdPatchBodyBodyModelCopyWith<$Res>
    implements $$ApiFursuitsIdPatchBodyBodyModelCopyWith<$Res> {
  _ApiFursuitsIdPatchBodyBodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiFursuitsIdPatchBodyBodyModel _value;

  @_i3.override
  _i3.String? get name => _value.name;

  @_i3.override
  _i4.ApiFursuitsIdPatchBodyBodyCatchApprovalModeModel? get catchApprovalMode =>
      _value.catchApprovalMode;

  @_i3.override
  $Res call({
    _i3.Object? name = _sentinel,
    _i3.Object? catchApprovalMode = _sentinel,
  }) {
    return (ApiFursuitsIdPatchBodyBodyModel(
      name: _i3.identical(name, _sentinel) ? this.name : (name as _i3.String?),
      catchApprovalMode: _i3.identical(catchApprovalMode, _sentinel)
          ? this.catchApprovalMode
          : (catchApprovalMode
                as _i4.ApiFursuitsIdPatchBodyBodyCatchApprovalModeModel?),
    ) as $Res);
  }
}
