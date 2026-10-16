// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i5;
import 'dart:core' as _i3;

import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/convention_status_all_of_model.dart'
    as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

/// Serializer exposing safe, read-only convention representation.
@_i2.immutable
class Convention extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const Convention({
    this.id,
    this.name,
    this.status,
    this.startDate,
    this.endDate,
  });

  factory Convention.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: ',',
      expectedKeys: {r'id', r'name', r'status', r'start_date', r'end_date'},
      listKeys: {},
      context: r'Convention',
    );
    return Convention(
      id: _$values[r'id'].decodeSimpleInt(context: r'Convention.id'),
      name: _$values[r'name'].decodeSimpleString(context: r'Convention.name'),
      status: _i4.ConventionStatusAllOfModel.fromSimple(
        _$values[r'status'],
        explode: explode,
      ),
      startDate: _$values[r'start_date'].decodeSimpleDate(
        context: r'Convention.start_date',
      ),
      endDate: _$values[r'end_date'].decodeSimpleDate(
        context: r'Convention.end_date',
      ),
    );
  }

  factory Convention.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'Convention');
    return Convention(
      id: _$map[r'id'].decodeJsonInt(context: r'Convention.id'),
      name: _$map[r'name'].decodeJsonString(context: r'Convention.name'),
      status: _i4.ConventionStatusAllOfModel.fromJson(_$map[r'status']),
      startDate: _$map[r'start_date'].decodeJsonDate(
        context: r'Convention.start_date',
      ),
      endDate: _$map[r'end_date'].decodeJsonDate(
        context: r'Convention.end_date',
      ),
    );
  }

  factory Convention.fromForm(_i3.String? value, {required _i3.bool explode}) {
    final _$values = value.decodeObject(
      explode: explode,
      explodeSeparator: '&',
      expectedKeys: {r'id', r'name', r'status', r'start_date', r'end_date'},
      listKeys: {},
      context: r'Convention',
    );
    return Convention(
      id: _$values[r'id'].decodeFormInt(context: r'Convention.id'),
      name: _$values[r'name'].decodeFormString(context: r'Convention.name'),
      status: _i4.ConventionStatusAllOfModel.fromForm(
        _$values[r'status'],
        explode: explode,
      ),
      startDate: _$values[r'start_date'].decodeFormDate(
        context: r'Convention.start_date',
      ),
      endDate: _$values[r'end_date'].decodeFormDate(
        context: r'Convention.end_date',
      ),
    );
  }

  final _i3.int? id;

  /// The official name of the convention.
  final _i3.String? name;

  /// Operational lifecycle state of the convention.
  ///
  /// * `draft` - Draft
  /// * `active` - Active
  /// * `paused` - Paused
  /// * `completed` - Completed
  /// * `cancelled` - Cancelled
  final _i4.ConventionStatusAllOfModel? status;

  /// Start date of the convention.
  final _i1.Date? startDate;

  /// End date of the convention.
  final _i1.Date? endDate;

  @_i3.override
  _i3.Object? toJson() => <_i3.String, _i3.Object?>{};

  $$ConventionCopyWith<Convention> get copyWith => _ConventionCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    return other is Convention &&
        other.id == this.id &&
        other.name == this.name &&
        other.status == this.status &&
        other.startDate == this.startDate &&
        other.endDate == this.endDate;
  }

  @_i3.override
  _i3.int get hashCode {
    return _i3.Object.hashAll([id, name, status, startDate, endDate]);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) {
    return <_i3.String, _i1.PropertyValue>{};
  }

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i5.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode Convention: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$ConventionCopyWith<$Res> {
  factory $$ConventionCopyWith(Convention value) = _ConventionCopyWith<$Res>;

  $Res call({
    _i3.int? id,
    _i3.String? name,
    _i4.ConventionStatusAllOfModel? status,
    _i1.Date? startDate,
    _i1.Date? endDate,
  });
  _i3.int? get id;
  _i3.String? get name;
  _i4.ConventionStatusAllOfModel? get status;
  _i1.Date? get startDate;
  _i1.Date? get endDate;
}

class _ConventionCopyWith<$Res> implements $$ConventionCopyWith<$Res> {
  _ConventionCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final Convention _value;

  @_i3.override
  _i3.int? get id => _value.id;

  @_i3.override
  _i3.String? get name => _value.name;

  @_i3.override
  _i4.ConventionStatusAllOfModel? get status => _value.status;

  @_i3.override
  _i1.Date? get startDate => _value.startDate;

  @_i3.override
  _i1.Date? get endDate => _value.endDate;

  @_i3.override
  $Res call({
    _i3.Object? id = _sentinel,
    _i3.Object? name = _sentinel,
    _i3.Object? status = _sentinel,
    _i3.Object? startDate = _sentinel,
    _i3.Object? endDate = _sentinel,
  }) {
    return (Convention(
      id: _i3.identical(id, _sentinel) ? this.id : (id as _i3.int?),
      name: _i3.identical(name, _sentinel) ? this.name : (name as _i3.String?),
      status: _i3.identical(status, _sentinel)
          ? this.status
          : (status as _i4.ConventionStatusAllOfModel?),
      startDate: _i3.identical(startDate, _sentinel)
          ? this.startDate
          : (startDate as _i1.Date?),
      endDate: _i3.identical(endDate, _sentinel)
          ? this.endDate
          : (endDate as _i1.Date?),
    ) as $Res);
  }
}
