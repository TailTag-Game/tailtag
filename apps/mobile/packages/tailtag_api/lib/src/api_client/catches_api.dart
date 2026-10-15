// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i4;

import 'package:http/http.dart' as _i7;
import 'package:tailtag_api/src/model/catch_confirmation_request_schema.dart'
    as _i9;
import 'package:tailtag_api/src/operation/catch_confirm.dart' as _i3;
import 'package:tailtag_api/src/operation/catch_history_list.dart' as _i2;
import 'package:tailtag_api/src/response_wrapper/catch_confirm_response.dart'
    as _i8;
import 'package:tailtag_api/src/response_wrapper/catch_history_list_response.dart'
    as _i6;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i5;

class CatchesApi {
  CatchesApi(_i1.Server server)
    : _catchHistoryList = _i2.CatchHistoryList(
        server.baseUrl,
        () => server.client,
      ),
      _catchConfirm = _i3.CatchConfirm(server.baseUrl, () => server.client);

  final _i2.CatchHistoryList _catchHistoryList;

  final _i3.CatchConfirm _catchConfirm;

  /// Returns only the authenticated player's Catch history ordered by -caught_at then -id. catch_count is the total number of matching Catch rows before pagination. Each supported query parameter may appear at most once; unknown query parameters are rejected.
  ///
  /// Security:
  /// - HTTP Bearer
  _i4.Future<_i5.TonikResult<_i6.CatchHistoryListResponse, _i7.Response>>
  catchHistoryList({
    _i4.int? conventionId,
    _i4.int page = _i2.CatchHistoryList.pageDefault,
    _i4.int pageSize = _i2.CatchHistoryList.pageSizeDefault,
    _i5.TonikCancellation? cancellation,
  }) async => _catchHistoryList(
    conventionId: conventionId,
    page: page,
    pageSize: pageSize,
    cancellation: cancellation,
  );

  /// Delegate one opaque credential to the sole catch-write authority.
  ///
  /// Security:
  /// - HTTP Bearer
  _i4.Future<_i5.TonikResult<_i8.CatchConfirmResponse, _i7.Response>>
  catchConfirm({
    required _i9.CatchConfirmationRequestSchema body,
    _i5.TonikCancellation? cancellation,
  }) async => _catchConfirm(body: body, cancellation: cancellation);
}
