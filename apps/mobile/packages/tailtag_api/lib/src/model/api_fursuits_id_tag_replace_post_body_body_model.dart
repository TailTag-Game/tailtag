// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiFursuitsIdTagReplacePostBodyBodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiFursuitsIdTagReplacePostBodyBodyModel({
    required this.expectedVersion,
  });

  factory ApiFursuitsIdTagReplacePostBodyBodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'expected_version'},
      listKeys: {},
      context: r'ApiFursuitsIdTagReplacePostBodyBodyModel',
    );
    return ApiFursuitsIdTagReplacePostBodyBodyModel(
      expectedVersion: _$values[r'expected_version'].decodeSimpleInt(
        context: r'ApiFursuitsIdTagReplacePostBodyBodyModel.expected_version',
      ),
    );
  }

  factory ApiFursuitsIdTagReplacePostBodyBodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiFursuitsIdTagReplacePostBodyBodyModel',
    );
    return ApiFursuitsIdTagReplacePostBodyBodyModel(
      expectedVersion: _$map[r'expected_version'].decodeJsonInt(
        context: r'ApiFursuitsIdTagReplacePostBodyBodyModel.expected_version',
      ),
    );
  }

  factory ApiFursuitsIdTagReplacePostBodyBodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'expected_version'},
      listKeys: {},
      context: r'ApiFursuitsIdTagReplacePostBodyBodyModel',
    );
    return ApiFursuitsIdTagReplacePostBodyBodyModel(
      expectedVersion: _$values[r'expected_version'].decodeFormInt(
        context: r'ApiFursuitsIdTagReplacePostBodyBodyModel.expected_version',
      ),
    );
  }

  final _i3.int expectedVersion;

  @_i3.override
  _i3.Object? toJson() => {r'expected_version': expectedVersion};

  $$ApiFursuitsIdTagReplacePostBodyBodyModelCopyWith<
    ApiFursuitsIdTagReplacePostBodyBodyModel
  >
  get copyWith => _ApiFursuitsIdTagReplacePostBodyBodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsIdTagReplacePostBodyBodyModel &&
        other.expectedVersion == this.expectedVersion;
  }

  @_i3.override
  _i3.int get hashCode => expectedVersion.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'expected_version'] = _i1.PropertyValue.scalar(
      expectedVersion.toString(),
    );
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
      r'Cannot uriEncode ApiFursuitsIdTagReplacePostBodyBodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiFursuitsIdTagReplacePostBodyBodyModelCopyWith<$Res> {
  factory $$ApiFursuitsIdTagReplacePostBodyBodyModelCopyWith(
    ApiFursuitsIdTagReplacePostBodyBodyModel value,
  ) = _ApiFursuitsIdTagReplacePostBodyBodyModelCopyWith<$Res>;

  $Res call({_i3.int? expectedVersion});
  _i3.int get expectedVersion;
}

class _ApiFursuitsIdTagReplacePostBodyBodyModelCopyWith<$Res>
    implements $$ApiFursuitsIdTagReplacePostBodyBodyModelCopyWith<$Res> {
  _ApiFursuitsIdTagReplacePostBodyBodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiFursuitsIdTagReplacePostBodyBodyModel _value;

  @_i3.override
  _i3.int get expectedVersion => _value.expectedVersion;

  @_i3.override
  $Res call({_i3.Object? expectedVersion = _sentinel}) {
    return (ApiFursuitsIdTagReplacePostBodyBodyModel(
      expectedVersion: _i3.identical(expectedVersion, _sentinel)
          ? this.expectedVersion
          : (expectedVersion as _i3.int),
    ) as $Res);
  }
}
