// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i5;

import 'package:http/http.dart' as _i8;
import 'package:tailtag_api/src/model/api_catches_preview_post_body_body_model.dart'
    as _i12;
import 'package:tailtag_api/src/model/catch_confirmation_request_schema.dart'
    as _i10;
import 'package:tailtag_api/src/operation/catch_confirm.dart' as _i3;
import 'package:tailtag_api/src/operation/catch_history_list.dart' as _i2;
import 'package:tailtag_api/src/operation/catch_preview.dart' as _i4;
import 'package:tailtag_api/src/response_wrapper/catch_confirm_response.dart'
    as _i9;
import 'package:tailtag_api/src/response_wrapper/catch_history_list_response.dart'
    as _i7;
import 'package:tailtag_api/src/response_wrapper/catch_preview_response.dart'
    as _i11;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i6;

class CatchesApi {
  CatchesApi(_i1.Server server)
    : _catchHistoryList = _i2.CatchHistoryList(
        server.baseUrl,
        () => server.client,
      ),
      _catchConfirm = _i3.CatchConfirm(server.baseUrl, () => server.client),
      _catchPreview = _i4.CatchPreview(server.baseUrl, () => server.client);

  final _i2.CatchHistoryList _catchHistoryList;

  final _i3.CatchConfirm _catchConfirm;

  final _i4.CatchPreview _catchPreview;

  /// Returns only the authenticated player's Catch history ordered by -caught_at then -id. catch_count is the total number of matching Catch rows before pagination. Each supported query parameter may appear at most once; unknown query parameters are rejected.
  ///
  /// Security:
  /// - HTTP Bearer
  _i5.Future<_i6.TonikResult<_i7.CatchHistoryListResponse, _i8.Response>>
  catchHistoryList({
    _i5.int? conventionId,
    _i5.int page = _i2.CatchHistoryList.pageDefault,
    _i5.int pageSize = _i2.CatchHistoryList.pageSizeDefault,
    _i6.TonikCancellation? cancellation,
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
  @_i5.Deprecated('This operation is deprecated.')
  _i5.Future<_i6.TonikResult<_i9.CatchConfirmResponse, _i8.Response>>
  catchConfirm({
    required _i10.CatchConfirmationRequestSchema body,
    _i6.TonikCancellation? cancellation,
  }) async => _catchConfirm(body: body, cancellation: cancellation);

  /// Resolve a scanned tag against the caller's selected convention. Preview creates nothing. Unknown, revoked, and unavailable targets share one neutral 404.
  ///
  /// Security:
  /// - HTTP Bearer
  _i5.Future<_i6.TonikResult<_i11.CatchPreviewResponse, _i8.Response>>
  catchPreview({
    required _i12.ApiCatchesPreviewPostBodyBodyModel body,
    _i6.TonikCancellation? cancellation,
  }) async => _catchPreview(body: body, cancellation: cancellation);
}
