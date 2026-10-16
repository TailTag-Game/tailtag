// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i3;
import 'dart:core' as _i2;

import 'package:tonik_util/tonik_util.dart' as _i1;

enum ApiCatchesGet500BodyCodeModel
    implements
        _i1.MatrixEncodable,
        _i1.LabelEncodable,
        _i1.SimpleEncodable,
        _i1.FormEncodable,
        _i1.JsonEncodable,
        _i1.UriEncodable {
  serverError(r'server_error');

  const ApiCatchesGet500BodyCodeModel(this._$rawValue);

  factory ApiCatchesGet500BodyCodeModel.fromJson(_i2.dynamic value) {
    if (value is! _i2.String) {
      throw _i1.JsonDecodingException(
        r'Expected String for ApiCatchesGet500BodyCodeModel, got ${value.runtimeType}',
      );
    }
    return values.firstWhere(
      (e) => e._$rawValue == value,
      orElse: () => throw _i1.JsonDecodingException(
        r'No matching ApiCatchesGet500BodyCodeModel for value: $value',
      ),
    );
  }

  factory ApiCatchesGet500BodyCodeModel.fromSimple(
    _i2.String? value, {
    required _i2.bool explode,
    _i2.String? context,
  }) {
    return ApiCatchesGet500BodyCodeModel.fromJson(
      value.decodeSimpleString(context: context),
    );
  }

  factory ApiCatchesGet500BodyCodeModel.fromForm(
    _i2.String? value, {
    required _i2.bool explode,
    _i2.String? context,
  }) {
    return ApiCatchesGet500BodyCodeModel.fromJson(
      value.decodeFormString(context: context),
    );
  }

  final _i2.String _$rawValue;

  @_i2.override
  _i2.String toJson() => _$rawValue;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.simple;

  @_i2.override
  _i2.String toSimple({
    required _i2.bool explode,
    required _i2.bool allowEmpty,
    _i2.bool literal = false,
  }) => _$rawValue.toSimple(
    explode: explode,
    allowEmpty: allowEmpty,
    literal: literal,
  );

  @_i2.override
  _i2.List<_i1.ParameterEntry> toForm(
    _i2.String paramName, {
    required _i2.bool explode,
    required _i2.bool allowEmpty,
    required _i3.Encoding textEncoding,
    _i2.bool useQueryComponent = false,
    _i2.bool allowReserved = false,
    _i2.Map<_i2.String, _i1.FormFieldEncoding> fieldEncodings = const {},
  }) => _$rawValue.toForm(
    paramName,
    explode: explode,
    allowEmpty: allowEmpty,
    useQueryComponent: useQueryComponent,
    allowReserved: allowReserved,
    textEncoding: textEncoding,
  );

  @_i2.override
  _i2.String toLabel({
    required _i2.bool explode,
    required _i2.bool allowEmpty,
  }) => _$rawValue.toLabel(explode: explode, allowEmpty: allowEmpty);

  @_i2.override
  _i2.String uriEncode({
    required _i2.bool allowEmpty,
    required _i3.Encoding textEncoding,
    _i2.bool useQueryComponent = false,
    _i2.bool allowReserved = false,
  }) => _$rawValue.uriEncode(
    allowEmpty: allowEmpty,
    textEncoding: textEncoding,
    useQueryComponent: useQueryComponent,
    allowReserved: allowReserved,
  );

  @_i2.override
  _i2.String toMatrix(
    _i2.String paramName, {
    required _i2.bool explode,
    required _i2.bool allowEmpty,
  }) =>
      _$rawValue.toMatrix(paramName, explode: explode, allowEmpty: allowEmpty);
}
