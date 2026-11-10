// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_get409_body_current_state_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// Present only for tag_version_conflict. It never carries a payload. State none means the suit never had a tag.
@_i2.immutable
class ApiFursuitsIdTagGet409BodyCurrentModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsIdTagGet409BodyCurrentModel({
    required this.fursuitId,
    required this.state,
    required this.tagVersion,
  });

  factory ApiFursuitsIdTagGet409BodyCurrentModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'fursuit_id', r'state', r'tag_version'},
      listKeys: {},
      context: r'ApiFursuitsIdTagGet409BodyCurrentModel',
    );
    return ApiFursuitsIdTagGet409BodyCurrentModel(
      fursuitId: _$values[r'fursuit_id'].decodeSimpleInt(
        context: r'ApiFursuitsIdTagGet409BodyCurrentModel.fursuit_id',
      ),
      state: _i4.ApiFursuitsIdTagGet409BodyCurrentStateModel.fromSimple(
        _$values[r'state'],
        explode: explode,
      ),
      tagVersion: _$values[r'tag_version'].decodeSimpleInt(
        context: r'ApiFursuitsIdTagGet409BodyCurrentModel.tag_version',
      ),
    );
  }

  factory ApiFursuitsIdTagGet409BodyCurrentModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiFursuitsIdTagGet409BodyCurrentModel',
    );
    return ApiFursuitsIdTagGet409BodyCurrentModel(
      fursuitId: _$map[r'fursuit_id'].decodeJsonInt(
        context: r'ApiFursuitsIdTagGet409BodyCurrentModel.fursuit_id',
      ),
      state: _i4.ApiFursuitsIdTagGet409BodyCurrentStateModel.fromJson(
        _$map[r'state'],
      ),
      tagVersion: _$map[r'tag_version'].decodeJsonInt(
        context: r'ApiFursuitsIdTagGet409BodyCurrentModel.tag_version',
      ),
    );
  }

  factory ApiFursuitsIdTagGet409BodyCurrentModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'fursuit_id', r'state', r'tag_version'},
      listKeys: {},
      context: r'ApiFursuitsIdTagGet409BodyCurrentModel',
    );
    return ApiFursuitsIdTagGet409BodyCurrentModel(
      fursuitId: _$values[r'fursuit_id'].decodeFormInt(
        context: r'ApiFursuitsIdTagGet409BodyCurrentModel.fursuit_id',
      ),
      state: _i4.ApiFursuitsIdTagGet409BodyCurrentStateModel.fromForm(
        _$values[r'state'],
        explode: explode,
      ),
      tagVersion: _$values[r'tag_version'].decodeFormInt(
        context: r'ApiFursuitsIdTagGet409BodyCurrentModel.tag_version',
      ),
    );
  }

  final _i3.int fursuitId;

  final _i4.ApiFursuitsIdTagGet409BodyCurrentStateModel state;

  final _i3.int tagVersion;

  @_i3.override
  _i3.Object? toJson() => {
    r'fursuit_id': fursuitId,
    r'state': state.toJson(),
    r'tag_version': tagVersion,
  };

  $$ApiFursuitsIdTagGet409BodyCurrentModelCopyWith<
    ApiFursuitsIdTagGet409BodyCurrentModel
  >
  get copyWith => _ApiFursuitsIdTagGet409BodyCurrentModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsIdTagGet409BodyCurrentModel &&
        other.fursuitId == this.fursuitId &&
        other.state == this.state &&
        other.tagVersion == this.tagVersion;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([fursuitId, state, tagVersion]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'fursuit_id'] = _i1.PropertyValue.scalar(fursuitId.toString());
    _$result[r'state'] = _i1.PropertyValue.scalar(state.toJson());
    _$result[r'tag_version'] = _i1.PropertyValue.scalar(tagVersion.toString());
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
      r'Cannot uriEncode ApiFursuitsIdTagGet409BodyCurrentModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiFursuitsIdTagGet409BodyCurrentModelCopyWith<$Res> {
  factory $$ApiFursuitsIdTagGet409BodyCurrentModelCopyWith(
    ApiFursuitsIdTagGet409BodyCurrentModel value,
  ) = _ApiFursuitsIdTagGet409BodyCurrentModelCopyWith<$Res>;

  $Res call({
    _i3.int? fursuitId,
    _i4.ApiFursuitsIdTagGet409BodyCurrentStateModel? state,
    _i3.int? tagVersion,
  });
  _i3.int get fursuitId;
  _i4.ApiFursuitsIdTagGet409BodyCurrentStateModel get state;
  _i3.int get tagVersion;
}

class _ApiFursuitsIdTagGet409BodyCurrentModelCopyWith<$Res>
    implements $$ApiFursuitsIdTagGet409BodyCurrentModelCopyWith<$Res> {
  _ApiFursuitsIdTagGet409BodyCurrentModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiFursuitsIdTagGet409BodyCurrentModel _value;

  @_i3.override
  _i3.int get fursuitId => _value.fursuitId;

  @_i3.override
  _i4.ApiFursuitsIdTagGet409BodyCurrentStateModel get state => _value.state;

  @_i3.override
  _i3.int get tagVersion => _value.tagVersion;

  @_i3.override
  $Res call({
    _i3.Object? fursuitId = _sentinel,
    _i3.Object? state = _sentinel,
    _i3.Object? tagVersion = _sentinel,
  }) {
    return (ApiFursuitsIdTagGet409BodyCurrentModel(
      fursuitId: _i3.identical(fursuitId, _sentinel)
          ? this.fursuitId
          : (fursuitId as _i3.int),
      state: _i3.identical(state, _sentinel)
          ? this.state
          : (state as _i4.ApiFursuitsIdTagGet409BodyCurrentStateModel),
      tagVersion: _i3.identical(tagVersion, _sentinel)
          ? this.tagVersion
          : (tagVersion as _i3.int),
    ) as $Res);
  }
}
