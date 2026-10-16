// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i3;

import 'package:http/http.dart' as _i6;
import 'package:tailtag_api/src/operation/me_retrieve.dart' as _i2;
import 'package:tailtag_api/src/response_wrapper/me_retrieve_response.dart'
    as _i5;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i4;

class MeApi {
  MeApi(_i1.Server server)
    : _meRetrieve = _i2.MeRetrieve(server.baseUrl, () => server.client);

  final _i2.MeRetrieve _meRetrieve;

  /// Return the authenticated TailTag application-user identity.
  ///
  /// Security:
  /// - HTTP Bearer
  _i3.Future<_i4.TonikResult<_i5.MeRetrieveResponse, _i6.Response>> meRetrieve({
    _i4.TonikCancellation? cancellation,
  }) async => _meRetrieve(cancellation: cancellation);
}
