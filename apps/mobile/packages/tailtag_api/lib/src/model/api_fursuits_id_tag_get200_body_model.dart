// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_fursuits_id_tag_get200_body_state_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiFursuitsIdTagGet200BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsIdTagGet200BodyModel({
    required this.fursuitId,
    required this.state,
    required this.tagVersion,
    required this.payload,
  });

  factory ApiFursuitsIdTagGet200BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'fursuit_id', r'state', r'tag_version', r'payload'},
      listKeys: {},
      context: r'ApiFursuitsIdTagGet200BodyModel',
    );
    return ApiFursuitsIdTagGet200BodyModel(
      fursuitId: _$values[r'fursuit_id'].decodeSimpleInt(
        context: r'ApiFursuitsIdTagGet200BodyModel.fursuit_id',
      ),
      state: _i4.ApiFursuitsIdTagGet200BodyStateModel.fromSimple(
        _$values[r'state'],
        explode: explode,
      ),
      tagVersion: _$values[r'tag_version'].decodeSimpleInt(
        context: r'ApiFursuitsIdTagGet200BodyModel.tag_version',
      ),
      payload: _$values[r'payload'].decodeSimpleNullableString(
        context: r'ApiFursuitsIdTagGet200BodyModel.payload',
      ),
    );
  }

  factory ApiFursuitsIdTagGet200BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'ApiFursuitsIdTagGet200BodyModel');
    return ApiFursuitsIdTagGet200BodyModel(
      fursuitId: _$map[r'fursuit_id'].decodeJsonInt(
        context: r'ApiFursuitsIdTagGet200BodyModel.fursuit_id',
      ),
      state: _i4.ApiFursuitsIdTagGet200BodyStateModel.fromJson(_$map[r'state']),
      tagVersion: _$map[r'tag_version'].decodeJsonInt(
        context: r'ApiFursuitsIdTagGet200BodyModel.tag_version',
      ),
      payload: _$map[r'payload'].decodeJsonNullableString(
        context: r'ApiFursuitsIdTagGet200BodyModel.payload',
      ),
    );
  }

  factory ApiFursuitsIdTagGet200BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'fursuit_id', r'state', r'tag_version', r'payload'},
      listKeys: {},
      context: r'ApiFursuitsIdTagGet200BodyModel',
    );
    return ApiFursuitsIdTagGet200BodyModel(
      fursuitId: _$values[r'fursuit_id'].decodeFormInt(
        context: r'ApiFursuitsIdTagGet200BodyModel.fursuit_id',
      ),
      state: _i4.ApiFursuitsIdTagGet200BodyStateModel.fromForm(
        _$values[r'state'],
        explode: explode,
      ),
      tagVersion: _$values[r'tag_version'].decodeFormInt(
        context: r'ApiFursuitsIdTagGet200BodyModel.tag_version',
      ),
      payload: _$values[r'payload'].decodeFormNullableString(
        context: r'ApiFursuitsIdTagGet200BodyModel.payload',
      ),
    );
  }

  final _i3.int fursuitId;

  final _i4.ApiFursuitsIdTagGet200BodyStateModel state;

  final _i3.int tagVersion;

  /// The printed tag payload. Null when state is revoked.
  final _i3.String? payload;

  @_i3.override
  _i3.Object? toJson() => {
    r'fursuit_id': fursuitId,
    r'state': state.toJson(),
    r'tag_version': tagVersion,
    r'payload': payload,
  };

  $$ApiFursuitsIdTagGet200BodyModelCopyWith<ApiFursuitsIdTagGet200BodyModel>
  get copyWith => _ApiFursuitsIdTagGet200BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsIdTagGet200BodyModel &&
        other.fursuitId == this.fursuitId &&
        other.state == this.state &&
        other.tagVersion == this.tagVersion &&
        other.payload == this.payload;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([fursuitId, state, tagVersion, payload]);
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
    if (payload != null) {
      _$result[r'payload'] = _i1.PropertyValue.scalar(payload!);
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
      r'Cannot uriEncode ApiFursuitsIdTagGet200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiFursuitsIdTagGet200BodyModelCopyWith<$Res> {
  factory $$ApiFursuitsIdTagGet200BodyModelCopyWith(
    ApiFursuitsIdTagGet200BodyModel value,
  ) = _ApiFursuitsIdTagGet200BodyModelCopyWith<$Res>;

  $Res call({
    _i3.int? fursuitId,
    _i4.ApiFursuitsIdTagGet200BodyStateModel? state,
    _i3.int? tagVersion,
    _i3.String? payload,
  });
  _i3.int get fursuitId;
  _i4.ApiFursuitsIdTagGet200BodyStateModel get state;
  _i3.int get tagVersion;
  _i3.String? get payload;
}

class _ApiFursuitsIdTagGet200BodyModelCopyWith<$Res>
    implements $$ApiFursuitsIdTagGet200BodyModelCopyWith<$Res> {
  _ApiFursuitsIdTagGet200BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiFursuitsIdTagGet200BodyModel _value;

  @_i3.override
  _i3.int get fursuitId => _value.fursuitId;

  @_i3.override
  _i4.ApiFursuitsIdTagGet200BodyStateModel get state => _value.state;

  @_i3.override
  _i3.int get tagVersion => _value.tagVersion;

  @_i3.override
  _i3.String? get payload => _value.payload;

  @_i3.override
  $Res call({
    _i3.Object? fursuitId = _sentinel,
    _i3.Object? state = _sentinel,
    _i3.Object? tagVersion = _sentinel,
    _i3.Object? payload = _sentinel,
  }) {
    return (ApiFursuitsIdTagGet200BodyModel(
      fursuitId: _i3.identical(fursuitId, _sentinel)
          ? this.fursuitId
          : (fursuitId as _i3.int),
      state: _i3.identical(state, _sentinel)
          ? this.state
          : (state as _i4.ApiFursuitsIdTagGet200BodyStateModel),
      tagVersion: _i3.identical(tagVersion, _sentinel)
          ? this.tagVersion
          : (tagVersion as _i3.int),
      payload: _i3.identical(payload, _sentinel)
          ? this.payload
          : (payload as _i3.String?),
    ) as $Res);
  }
}
