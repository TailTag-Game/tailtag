// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:convert' as _i6;
import 'dart:core' as _i3;

import 'package:collection/collection.dart' as _i5;
import 'package:meta/meta.dart' as _i2;
import 'package:tailtag_api/src/model/player_request.dart' as _i4;
import 'package:tonik_util/tonik_util.dart' as _i1;

@_i2.immutable
class PlayerRequestList extends _i1.ObjectParameterEncodable
    implements _i1.UriEncodable {
  const PlayerRequestList({required this.results});

  factory PlayerRequestList.fromSimple(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.SimpleDecodingException(
      r'Simple encoding not supported for PlayerRequestList: contains complex types',
    );
  }

  factory PlayerRequestList.fromJson(_i3.Object? json) {
    final _$map = json.decodeMap(context: r'PlayerRequestList');
    return PlayerRequestList(
      results: _$map[r'results']
          .decodeJsonList<_i3.Object?>(context: r'PlayerRequestList.results')
          .map(_i4.PlayerRequest.fromJson)
          .toList(),
    );
  }

  factory PlayerRequestList.fromForm(
    _i3.String? value, {
    required _i3.bool explode,
  }) {
    throw _i1.FormDecodingException(
      r'Form encoding not supported for PlayerRequestList: contains complex types',
    );
  }

  final _i3.List<_i4.PlayerRequest> results;

  @_i3.override
  _i3.Object? toJson() => {r'results': results.map((e) => e.toJson()).toList()};

  $$PlayerRequestListCopyWith<PlayerRequestList> get copyWith =>
      _PlayerRequestListCopyWith(this);

  @_i3.override
  _i3.bool operator ==(_i3.Object other) {
    if (_i3.identical(this, other)) return true;
    const _$deepEquals = _i5.DeepCollectionEquality();
    return other is PlayerRequestList &&
        _$deepEquals.equals(other.results, this.results);
  }

  @_i3.override
  _i3.int get hashCode {
    const deepEquals = _i5.DeepCollectionEquality();
    return deepEquals.hash(results);
  }

  _i1.EncodingShape get currentEncodingShape => _i1.EncodingShape.complex;

  @_i3.override
  _i3.Map<_i3.String, _i1.PropertyValue> parameterProperties({
    _i3.bool allowEmpty = true,
  }) => throw _i1.EncodingException(
    r'parameterProperties not supported for PlayerRequestList: contains complex types',
  );

  @_i3.override
  _i3.String uriEncode({
    required _i3.bool allowEmpty,
    required _i6.Encoding textEncoding,
    _i3.bool useQueryComponent = false,
    _i3.bool allowReserved = false,
  }) {
    throw _i1.EncodingException(
      r'Cannot uriEncode PlayerRequestList: complex types cannot be URI-encoded',
    );
  }
}

abstract class $$PlayerRequestListCopyWith<$Res> {
  factory $$PlayerRequestListCopyWith(PlayerRequestList value) =
      _PlayerRequestListCopyWith<$Res>;

  $Res call({_i3.List<_i4.PlayerRequest>? results});
  _i3.List<_i4.PlayerRequest> get results;
}

class _PlayerRequestListCopyWith<$Res>
    implements $$PlayerRequestListCopyWith<$Res> {
  _PlayerRequestListCopyWith(this._value);

  static const _sentinel = _i3.Object();

  final PlayerRequestList _value;

  @_i3.override
  _i3.List<_i4.PlayerRequest> get results => _value.results;

  @_i3.override
  $Res call({_i3.Object? results = _sentinel}) {
    return (PlayerRequestList(
      results: _i3.identical(results, _sentinel)
          ? this.results
          : (results as _i3.List<_i4.PlayerRequest>),
    ) as $Res);
  }
}
