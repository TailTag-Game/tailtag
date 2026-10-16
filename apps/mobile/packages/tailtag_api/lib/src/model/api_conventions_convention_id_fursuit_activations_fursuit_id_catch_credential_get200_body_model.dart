// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel
    extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel({
    required this.payload,
  });

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'payload'},
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel(
      payload: _$values[r'payload'].decodeSimpleString(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel.payload',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel.fromJson(
    _i3.Object? json,
  ) {
    final _$map = json.decodeMap(
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel(
      payload: _$map[r'payload'].decodeJsonString(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel.payload',
      ),
    );
  }

  factory ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'payload'},
      listKeys: {},
      context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel',
    );
    return ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel(
      payload: _$values[r'payload'].decodeFormString(
        context: r'ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel.payload',
      ),
    );
  }

  final _i3.String payload;

  @_i3.override
  _i3.Object? toJson() => {r'payload': payload};

  $$ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModelCopyWith<
    ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel
  >
  get copyWith =>
      _ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModelCopyWith(
        this,
      );

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other
            is ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel &&
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
      r'Cannot uriEncode ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModelCopyWith<
  $Res
> {
  factory $$ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModelCopyWith(
    ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel
    value,
  ) =
      _ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModelCopyWith<
        $Res
      >;

  $Res call({_i3.String? payload});
  _i3.String get payload;
}

class _ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModelCopyWith<
  $Res
>
    implements
        $$ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModelCopyWith<
          $Res
        > {
  _ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModelCopyWith(
    this._value,
  );

  static const _sentinel = _i3.Object();

  final ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel
  _value;

  @_i3.override
  _i3.String get payload => _value.payload;

  @_i3.override
  $Res call({_i3.Object? payload = _sentinel}) {
    return (ApiConventionsConventionIdFursuitActivationsFursuitIdCatchCredentialGet200BodyModel(
      payload: _i3.identical(payload, _sentinel)
          ? this.payload
          : (payload as _i3.String),
    ) as $Res);
  }
}
