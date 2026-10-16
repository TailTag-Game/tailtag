// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel({
    required this.payload,
  });

  factory ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'payload'},
      listKeys: {},
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel(
      payload: _$values[r'payload'].decodeSimpleString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel.payload',
      ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel(
      payload: _$map[r'payload'].decodeJsonString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel.payload',
      ),
    );
  }

  factory ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'payload'},
      listKeys: {},
      context:
          r'ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel',
    );
    return ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel(
      payload: _$values[r'payload'].decodeFormString(
        context: r'ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel.payload',
      ),
    );
  }

  final _i3.String payload;

  @_i3.override
  _i3.Object? toJson() => {r'payload': payload};

  $$ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModelCopyWith<
    ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel &&
        other.payload == this.payload;
  }

  @_i3.override
  _i3.int get hashCode => payload.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'payload'] = _i1.PropertyValue.scalar(payload);
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
      r'Cannot uriEncode ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModelCopyWith(
    ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel value,
  ) =
      _ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModelCopyWith<
        $Res
      >;

  $Res call({_i3.String? payload});
  _i3.String get payload;
}

class _ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel
  _value;

  @_i3.override
  _i3.String get payload => _value.payload;

  @_i3.override
  $Res call({_i3.Object? payload = _sentinel}) {
    return (ApiConventionsConventionIdCatchCredentialsResolvePostBodyBodyModel(
      payload: _i3.identical(payload, _sentinel)
          ? this.payload
          : (payload as _i3.String),
    ) as $Res);
  }
}
