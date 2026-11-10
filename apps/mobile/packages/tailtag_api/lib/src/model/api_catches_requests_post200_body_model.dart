// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/api_catches_requests_post200_body_catch_model.dart'
    as _i6;
import 'package:tailtag_api/src/model/api_catches_requests_post200_body_outcome_model.dart'
    as _i4;
import 'package:tailtag_api/src/model/api_catches_requests_post200_body_request_model.dart'
    as _i5;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class ApiCatchesRequestsPost200BodyModel extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const ApiCatchesRequestsPost200BodyModel({
    required this.outcome,
    required this.request,
    required this.$catch,
  });

  factory ApiCatchesRequestsPost200BodyModel.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for ApiCatchesRequestsPost200BodyModel: contains complex types',
    );
  }

  factory ApiCatchesRequestsPost200BodyModel.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(
      context: r'ApiCatchesRequestsPost200BodyModel',
    );
    return ApiCatchesRequestsPost200BodyModel(
      outcome: _i4.ApiCatchesRequestsPost200BodyOutcomeModel.fromJson(
        _$map[r'outcome'],
      ),
      request: _$map[r'request'] == null
          ? null
          : _i5.ApiCatchesRequestsPost200BodyRequestModel.fromJson(
              _$map[r'request'],
            ),
      $catch: _$map[r'catch'] == null
          ? null
          : _i6.ApiCatchesRequestsPost200BodyCatchModel.fromJson(
              _$map[r'catch'],
            ),
    );
  }

  factory ApiCatchesRequestsPost200BodyModel.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for ApiCatchesRequestsPost200BodyModel: contains complex types',
    );
  }

  final _i4.ApiCatchesRequestsPost200BodyOutcomeModel outcome;

  final _i5.ApiCatchesRequestsPost200BodyRequestModel? request;

  final _i6.ApiCatchesRequestsPost200BodyCatchModel? $catch;

  @_i3.override
  _i3.Object? toJson() => {
    r'outcome': outcome.toJson(),
    r'request': request?.toJson(),
    r'catch': $catch?.toJson(),
  };

  $$ApiCatchesRequestsPost200BodyModelCopyWith<
    ApiCatchesRequestsPost200BodyModel
  >
  get copyWith => _ApiCatchesRequestsPost200BodyModelCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is ApiCatchesRequestsPost200BodyModel &&
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
    r'parameterProperties not supported for ApiCatchesRequestsPost200BodyModel: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i7.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode ApiCatchesRequestsPost200BodyModel: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ApiCatchesRequestsPost200BodyModelCopyWith<$Res> {
  factory $$ApiCatchesRequestsPost200BodyModelCopyWith(
    ApiCatchesRequestsPost200BodyModel value,
  ) = _ApiCatchesRequestsPost200BodyModelCopyWith<$Res>;

  $Res call({
    _i4.ApiCatchesRequestsPost200BodyOutcomeModel? outcome,
    _i5.ApiCatchesRequestsPost200BodyRequestModel? request,
    _i6.ApiCatchesRequestsPost200BodyCatchModel? $catch,
  });
  _i4.ApiCatchesRequestsPost200BodyOutcomeModel get outcome;
  _i5.ApiCatchesRequestsPost200BodyRequestModel? get request;
  _i6.ApiCatchesRequestsPost200BodyCatchModel? get $catch;
}

class _ApiCatchesRequestsPost200BodyModelCopyWith<$Res>
    implements $$ApiCatchesRequestsPost200BodyModelCopyWith<$Res> {
  _ApiCatchesRequestsPost200BodyModelCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final ApiCatchesRequestsPost200BodyModel _value;

  @_i3.override
  _i4.ApiCatchesRequestsPost200BodyOutcomeModel get outcome => _value.outcome;

  @_i3.override
  _i5.ApiCatchesRequestsPost200BodyRequestModel? get request => _value.request;

  @_i3.override
  _i6.ApiCatchesRequestsPost200BodyCatchModel? get $catch => _value.$catch;

  @_i3.override
  $Res call({
    _i3.Object? outcome = _sentinel,
    _i3.Object? request = _sentinel,
    _i3.Object? $catch = _sentinel,
  }) {
    return (ApiCatchesRequestsPost200BodyModel(
      outcome: _i3.identical(outcome, _sentinel)
          ? this.outcome
          : (outcome as _i4.ApiCatchesRequestsPost200BodyOutcomeModel),
      request: _i3.identical(request, _sentinel)
          ? this.request
          : (request as _i5.ApiCatchesRequestsPost200BodyRequestModel?),
      $catch: _i3.identical($catch, _sentinel)
          ? this.$catch
          : ($catch as _i6.ApiCatchesRequestsPost200BodyCatchModel?),
    ) as $Res);
  }
}
