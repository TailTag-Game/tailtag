// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchHistoryResponseSchemaResultsArrayConventionModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchHistoryResponseSchemaResultsArrayConventionModel({
    this.id,
    this.name,
  });

  factory CatchHistoryResponseSchemaResultsArrayConventionModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'id', r'name'},
      listKeys: {},
      context: r'CatchHistoryResponseSchemaResultsArrayConventionModel',
    );
    return CatchHistoryResponseSchemaResultsArrayConventionModel(
      id: _$values[r'id'].decodeSimpleInt(
        context: r'CatchHistoryResponseSchemaResultsArrayConventionModel.id',
      ),
      name: _$values[r'name'].decodeSimpleString(
        context: r'CatchHistoryResponseSchemaResultsArrayConventionModel.name',
      ),
    );
  }

  factory CatchHistoryResponseSchemaResultsArrayConventionModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'CatchHistoryResponseSchemaResultsArrayConventionModel',
    );
    return CatchHistoryResponseSchemaResultsArrayConventionModel(
      id: _$map[r'id'].decodeJsonInt(
        context: r'CatchHistoryResponseSchemaResultsArrayConventionModel.id',
      ),
      name: _$map[r'name'].decodeJsonString(
        context: r'CatchHistoryResponseSchemaResultsArrayConventionModel.name',
      ),
    );
  }

  factory CatchHistoryResponseSchemaResultsArrayConventionModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'id', r'name'},
      listKeys: {},
      context: r'CatchHistoryResponseSchemaResultsArrayConventionModel',
    );
    return CatchHistoryResponseSchemaResultsArrayConventionModel(
      id: _$values[r'id'].decodeFormInt(
        context: r'CatchHistoryResponseSchemaResultsArrayConventionModel.id',
      ),
      name: _$values[r'name'].decodeFormString(
        context: r'CatchHistoryResponseSchemaResultsArrayConventionModel.name',
      ),
    );
  }

  final _i3.int? id;

  final _i3.String? name;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$CatchHistoryResponseSchemaResultsArrayConventionModelCopyWith<
    CatchHistoryResponseSchemaResultsArrayConventionModel
  >
  get copyWith =>
      _CatchHistoryResponseSchemaResultsArrayConventionModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchHistoryResponseSchemaResultsArrayConventionModel &&
        other.id == this.id &&
        other.name == this.name;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([id, name]);
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
      r'Cannot uriEncode CatchHistoryResponseSchemaResultsArrayConventionModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchHistoryResponseSchemaResultsArrayConventionModelCopyWith<
  $Res
> {
  factory $$CatchHistoryResponseSchemaResultsArrayConventionModelCopyWith(
    CatchHistoryResponseSchemaResultsArrayConventionModel value,
  ) = _CatchHistoryResponseSchemaResultsArrayConventionModelCopyWith<$Res>;

  $Res call({_i3.int? id, _i3.String? name});
  _i3.int? get id;
  _i3.String? get name;
}

class _CatchHistoryResponseSchemaResultsArrayConventionModelCopyWith<$Res>
    implements
        $$CatchHistoryResponseSchemaResultsArrayConventionModelCopyWith<$Res> {
  _CatchHistoryResponseSchemaResultsArrayConventionModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchHistoryResponseSchemaResultsArrayConventionModel _value;

  @_i3.override
  _i3.int? get id => _value.id;

  @_i3.override
  _i3.String? get name => _value.name;

  @_i3.override
  $Res call({_i3.Object? id = _sentinel, _i3.Object? name = _sentinel}) {
    return (CatchHistoryResponseSchemaResultsArrayConventionModel(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      name: _i3.identical(name, _sentinel) ? this.name : (name as _i3.String?),
    ) as $Res);
  }
}
