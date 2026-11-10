// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i7;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/catch_request_outcome.dart' as _i4;
import 'package:tailtag_api/src/model/player_request.dart' as _i5;
import 'package:tailtag_api/src/model/request_catch.dart' as _i6;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class CatchRequestSubmission extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const CatchRequestSubmission({
    required this.outcome,
    required this.request,
    required this.$catch,
  });

  factory CatchRequestSubmission.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for CatchRequestSubmission: contains complex types',
    );
  }

  factory CatchRequestSubmission.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'CatchRequestSubmission');
    return CatchRequestSubmission(
      outcome: _i4.CatchRequestOutcome.fromJson(_$map[r'outcome']),
      request: _$map[r'request'] == null
          ? null
          : _i5.PlayerRequest.fromJson(_$map[r'request']),
      $catch: _$map[r'catch'] == null
          ? null
          : _i6.RequestCatch.fromJson(_$map[r'catch']),
    );
  }

  factory CatchRequestSubmission.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for CatchRequestSubmission: contains complex types',
    );
  }

  final _i4.CatchRequestOutcome outcome;

  final _i5.PlayerRequest? request;

  final _i6.RequestCatch? $catch;

  @_i3.override
  _i3.Object? toJson() => {
    r'outcome': outcome.toJson(),
    r'request': request?.toJson(),
    r'catch': $catch?.toJson(),
  };

  $$CatchRequestSubmissionCopyWith<CatchRequestSubmission> get copyWith =>
      _CatchRequestSubmissionCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is CatchRequestSubmission &&
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
    r'parameterProperties not supported for CatchRequestSubmission: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i7.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode CatchRequestSubmission: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$CatchRequestSubmissionCopyWith<$Res> {
  factory $$CatchRequestSubmissionCopyWith(CatchRequestSubmission value) =
      _CatchRequestSubmissionCopyWith<$Res>;

  $Res call({
    _i4.CatchRequestOutcome? outcome,
    _i5.PlayerRequest? request,
    _i6.RequestCatch? $catch,
  });
  _i4.CatchRequestOutcome get outcome;
  _i5.PlayerRequest? get request;
  _i6.RequestCatch? get $catch;
}

class _CatchRequestSubmissionCopyWith<$Res>
    implements $$CatchRequestSubmissionCopyWith<$Res> {
  _CatchRequestSubmissionCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final CatchRequestSubmission _value;

  @_i3.override
  _i4.CatchRequestOutcome get outcome => _value.outcome;

  @_i3.override
  _i5.PlayerRequest? get request => _value.request;

  @_i3.override
  _i6.RequestCatch? get $catch => _value.$catch;

  @_i3.override
  $Res call({
    _i3.Object? outcome = _sentinel,
    _i3.Object? request = _sentinel,
    _i3.Object? $catch = _sentinel,
  }) {
    return (CatchRequestSubmission(
      outcome: _i3.identical(outcome, _sentinel)
          ? this.outcome
          : (outcome as _i4.CatchRequestOutcome),
      request: _i3.identical(request, _sentinel)
          ? this.request
          : (request as _i5.PlayerRequest?),
      $catch: _i3.identical($catch, _sentinel)
          ? this.$catch
          : ($catch as _i6.RequestCatch?),
    ) as $Res);
  }
}
