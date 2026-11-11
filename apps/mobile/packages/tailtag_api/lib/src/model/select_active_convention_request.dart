// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i4;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// Request serializer for selecting an active convention.
@_i2.immutable
class SelectActiveConventionRequest extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const SelectActiveConventionRequest({required this.conventionId});

  factory SelectActiveConventionRequest.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'convention_id'},
      listKeys: {},
      context: r'SelectActiveConventionRequest',
    );
    return SelectActiveConventionRequest(
      conventionId: _$values[r'convention_id'].decodeSimpleInt(
        context: r'SelectActiveConventionRequest.convention_id',
      ),
    );
  }

  factory SelectActiveConventionRequest.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'SelectActiveConventionRequest');
    return SelectActiveConventionRequest(
      conventionId: _$map[r'convention_id'].decodeJsonInt(
        context: r'SelectActiveConventionRequest.convention_id',
      ),
    );
  }

  factory SelectActiveConventionRequest.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'convention_id'},
      listKeys: {},
      context: r'SelectActiveConventionRequest',
    );
    return SelectActiveConventionRequest(
      conventionId: _$values[r'convention_id'].decodeFormInt(
        context: r'SelectActiveConventionRequest.convention_id',
      ),
    );
  }

  final _i3.int conventionId;

  @_i3.override
  _i3.Object? toJson() => {r'convention_id': conventionId};

  $$SelectActiveConventionRequestCopyWith<SelectActiveConventionRequest>
  get copyWith => _SelectActiveConventionRequestCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is SelectActiveConventionRequest &&
        other.conventionId == this.conventionId;
  }

  @_i3.override
  _i3.int get hashCode => conventionId.hashCode;

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    final _$result = <_i3.String, _i1.PropertyValue>{};
    _$result[r'convention_id'] = _i1.PropertyValue.scalar(
      conventionId.toString(),
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
      r'Cannot uriEncode SelectActiveConventionRequest: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$SelectActiveConventionRequestCopyWith<$Res> {
  factory $$SelectActiveConventionRequestCopyWith(
    SelectActiveConventionRequest value,
  ) = _SelectActiveConventionRequestCopyWith<$Res>;

  $Res call({_i3.int? conventionId});
  _i3.int get conventionId;
}

class _SelectActiveConventionRequestCopyWith<$Res>
    implements $$SelectActiveConventionRequestCopyWith<$Res> {
  _SelectActiveConventionRequestCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final SelectActiveConventionRequest _value;

  @_i3.override
  _i3.int get conventionId => _value.conventionId;

  @_i3.override
  $Res call({_i3.Object? conventionId = _sentinel}) {
    return (SelectActiveConventionRequest(
      conventionId: _i3.identical(conventionId, _sentinel)
          ? this.conventionId
          : (conventionId as _i3.int),
    ) as $Res);
  }
}
