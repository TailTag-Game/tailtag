// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_requests_post201_body_catch_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_catches_requests_post201_body_outcome_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_catches_requests_post201_body_request_model.dart'
    as _i5;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesRequestsPost201BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesRequestsPost201BodyModel({
    required this.outcome,
    required this.request,
    required this.$catch,
  });

  factory ApiCatchesRequestsPost201BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ApiCatchesRequestsPost201BodyModel: contains complex types',
    );
  }

  factory ApiCatchesRequestsPost201BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiCatchesRequestsPost201BodyModel',
    );
    return ApiCatchesRequestsPost201BodyModel(
      outcome: _i4.ApiCatchesRequestsPost201BodyOutcomeModel.fromJson(
        _$map[r'outcome'],
      ),
      request: _$map[r'request'] == null
          ? null
          : _i5.ApiCatchesRequestsPost201BodyRequestModel.fromJson(
              _$map[r'request'],
            ),
      $catch: _$map[r'catch'] == null
          ? null
          : _i6.ApiCatchesRequestsPost201BodyCatchModel.fromJson(
              _$map[r'catch'],
            ),
    );
  }

  factory ApiCatchesRequestsPost201BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ApiCatchesRequestsPost201BodyModel: contains complex types',
    );
  }

  final _i4.ApiCatchesRequestsPost201BodyOutcomeModel outcome;

  final _i5.ApiCatchesRequestsPost201BodyRequestModel? request;

  final _i6.ApiCatchesRequestsPost201BodyCatchModel? $catch;

  @_i3.override
  _i3.Object? toJson() => {
    r'outcome': outcome.toJson(),
    r'request': request?.toJson(),
    r'catch': $catch?.toJson(),
  };

  $$ApiCatchesRequestsPost201BodyModelCopyWith<
    ApiCatchesRequestsPost201BodyModel
  >
  get copyWith => _ApiCatchesRequestsPost201BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesRequestsPost201BodyModel &&
        other.outcome == this.outcome &&
        other.request == this.request &&
        other.$catch == this.$catch;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([outcome, request, $catch]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for ApiCatchesRequestsPost201BodyModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i7.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiCatchesRequestsPost201BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiCatchesRequestsPost201BodyModelCopyWith<$Res> {
  factory $$ApiCatchesRequestsPost201BodyModelCopyWith(
    ApiCatchesRequestsPost201BodyModel value,
  ) = _ApiCatchesRequestsPost201BodyModelCopyWith<$Res>;

  $Res call({
    _i4.ApiCatchesRequestsPost201BodyOutcomeModel? outcome,
    _i5.ApiCatchesRequestsPost201BodyRequestModel? request,
    _i6.ApiCatchesRequestsPost201BodyCatchModel? $catch,
  });
  _i4.ApiCatchesRequestsPost201BodyOutcomeModel get outcome;
  _i5.ApiCatchesRequestsPost201BodyRequestModel? get request;
  _i6.ApiCatchesRequestsPost201BodyCatchModel? get $catch;
}

class _ApiCatchesRequestsPost201BodyModelCopyWith<$Res>
    implements $$ApiCatchesRequestsPost201BodyModelCopyWith<$Res> {
  _ApiCatchesRequestsPost201BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesRequestsPost201BodyModel _value;

  @_i3.override
  _i4.ApiCatchesRequestsPost201BodyOutcomeModel get outcome => _value.outcome;

  @_i3.override
  _i5.ApiCatchesRequestsPost201BodyRequestModel? get request => _value.request;

  @_i3.override
  _i6.ApiCatchesRequestsPost201BodyCatchModel? get $catch => _value.$catch;

  @_i3.override
  $Res call({
    _i3.Object? outcome = _sentinel,
    _i3.Object? request = _sentinel,
    _i3.Object? $catch = _sentinel,
  }) {
    return (ApiCatchesRequestsPost201BodyModel(
      outcome: _i3.identical(outcome, _sentinel)
          ? this.outcome
          : (outcome as _i4.ApiCatchesRequestsPost201BodyOutcomeModel),
      request: _i3.identical(request, _sentinel)
          ? this.request
          : (request as _i5.ApiCatchesRequestsPost201BodyRequestModel?),
      $catch: _i3.identical($catch, _sentinel)
          ? this.$catch
          : ($catch as _i6.ApiCatchesRequestsPost201BodyCatchModel?),
    ) as $Res);
  }
}
