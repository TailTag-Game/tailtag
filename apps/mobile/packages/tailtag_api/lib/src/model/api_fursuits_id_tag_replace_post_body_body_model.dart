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
    _i3.bool isHeader = false,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'expected_version'},
      listKeys: {},
      context: r'ApiFursuitsIdTagReplacePostBodyBodyModel',
      isHeader: isHeader,
      percentDecodeKeys: false,
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
  _i3.Object? toJson() => {r'expected_version': this.expectedVersion};

  ApiFursuitsIdTagReplacePostBodyBodyModel Function({_i3.int? expectedVersion})
  get copyWith {
    return ({_i3.int? expectedVersion}) =>
        ApiFursuitsIdTagReplacePostBodyBodyModel(
          expectedVersion: expectedVersion ?? this.expectedVersion,
        );
  }

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiFursuitsIdTagReplacePostBodyBodyModel &&
        other.expectedVersion == this.expectedVersion;
  }

  @_i3.override
  _i3.int get hashCode => this.expectedVersion.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'expected_version'] = _i1.PropertyValue.scalar(
      this.expectedVersion.toString(),
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
