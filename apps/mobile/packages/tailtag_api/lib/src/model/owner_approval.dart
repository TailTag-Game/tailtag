// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/owner_request.dart' as _i4;
import 'package:tailtag_api/src/model/request_catch.dart' as _i5;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class OwnerApproval extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const OwnerApproval({required this.request, required this.$catch});

  factory OwnerApproval.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for OwnerApproval: contains complex types',
    );
  }

  factory OwnerApproval.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'OwnerApproval');
    return OwnerApproval(
      request: _i4.OwnerRequest.fromJson(_$map[r'request']),
      $catch: _i5.RequestCatch.fromJson(_$map[r'catch']),
    );
  }

  factory OwnerApproval.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for OwnerApproval: contains complex types',
    );
  }

  final _i4.OwnerRequest request;

  final _i5.RequestCatch $catch;

  @_i3.override
  _i3.Object? toJson() => {
    r'request': request.toJson(),
    r'catch': $catch.toJson(),
  };

  $$OwnerApprovalCopyWith<OwnerApproval> get copyWith =>
      _OwnerApprovalCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is OwnerApproval &&
        other.request == this.request &&
        other.$catch == this.$catch;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([request, $catch]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for OwnerApproval: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode OwnerApproval: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$OwnerApprovalCopyWith<$Res> {
  factory $$OwnerApprovalCopyWith(OwnerApproval value) =
      _OwnerApprovalCopyWith<$Res>;

  $Res call({_i4.OwnerRequest? request, _i5.RequestCatch? $catch});
  _i4.OwnerRequest get request;
  _i5.RequestCatch get $catch;
}

class _OwnerApprovalCopyWith<$Res> implements $$OwnerApprovalCopyWith<$Res> {
  _OwnerApprovalCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final OwnerApproval _value;

  @_i3.override
  _i4.OwnerRequest get request => _value.request;

  @_i3.override
  _i5.RequestCatch get $catch => _value.$catch;

  @_i3.override
  $Res call({_i3.Object? request = _sentinel, _i3.Object? $catch = _sentinel}) {
    return (OwnerApproval(
      request: _i3.identical(request, _sentinel)
          ? this.request
          : (request as _i4.OwnerRequest),
      $catch: _i3.identical($catch, _sentinel)
          ? this.$catch
          : ($catch as _i5.RequestCatch),
    ) as $Res);
  }
}
