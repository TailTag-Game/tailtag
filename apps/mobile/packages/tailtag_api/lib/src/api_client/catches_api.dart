// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i7;

import 'package:http/http.dart' as _i10;
import 'package:tailtag_api/src/model/api_catches_preview_post_body_body_model.dart'
    as _i14;
import 'package:tailtag_api/src/model/catch_confirmation_request_schema.dart'
    as _i12;
import 'package:tailtag_api/src/model/catch_request_payload.dart' as _i17;
import 'package:tailtag_api/src/operation/catch_confirm.dart' as _i3;
import 'package:tailtag_api/src/operation/catch_history_list.dart' as _i2;
import 'package:tailtag_api/src/operation/catch_preview.dart' as _i4;
import 'package:tailtag_api/src/operation/catch_requests_create.dart' as _i6;
import 'package:tailtag_api/src/operation/catch_requests_list.dart' as _i5;
import 'package:tailtag_api/src/response_wrapper/catch_confirm_response.dart'
    as _i11;
import 'package:tailtag_api/src/response_wrapper/catch_history_list_response.dart'
    as _i9;
import 'package:tailtag_api/src/response_wrapper/catch_preview_response.dart'
    as _i13;
import 'package:tailtag_api/src/response_wrapper/catch_requests_create_response.dart'
    as _i16;
import 'package:tailtag_api/src/response_wrapper/catch_requests_list_response.dart'
    as _i15;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i8;

class CatchesApi {
  CatchesApi(_i1.Server server)
    : _catchHistoryList = _i2.CatchHistoryList(
        server.baseUrl,
        () => server.client,
      ),
      _catchConfirm = _i3.CatchConfirm(server.baseUrl, () => server.client),
      _catchPreview = _i4.CatchPreview(server.baseUrl, () => server.client),
      _catchRequestsList = _i5.CatchRequestsList(
        server.baseUrl,
        () => server.client,
      ),
      _catchRequestsCreate = _i6.CatchRequestsCreate(
        server.baseUrl,
        () => server.client,
      );

  final _i2.CatchHistoryList _catchHistoryList;

  final _i3.CatchConfirm _catchConfirm;

  final _i4.CatchPreview _catchPreview;

  final _i5.CatchRequestsList _catchRequestsList;

  final _i6.CatchRequestsCreate _catchRequestsCreate;

  /// Returns only the authenticated player's Catch history ordered by -caught_at then -id. catch_count is the total number of matching Catch rows before pagination. Each supported query parameter may appear at most once; unknown query parameters are rejected.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i9.CatchHistoryListResponse, _i10.Response>>
  catchHistoryList({
    _i7.int? conventionId,
    _i7.int page = _i2.CatchHistoryList.pageDefault,
    _i7.int pageSize = _i2.CatchHistoryList.pageSizeDefault,
    _i8.TonikCancellation? cancellation,
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
  @_i7.Deprecated('This operation is deprecated.')
  _i7.Future<_i8.TonikResult<_i11.CatchConfirmResponse, _i10.Response>>
  catchConfirm({
    required _i12.CatchConfirmationRequestSchema body,
    _i8.TonikCancellation? cancellation,
  }) async => _catchConfirm(body: body, cancellation: cancellation);

  /// Resolve a scanned tag against the caller's selected convention. Preview creates nothing. Unknown, revoked, and unavailable targets share one neutral 404.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i13.CatchPreviewResponse, _i10.Response>>
  catchPreview({
    required _i14.ApiCatchesPreviewPostBodyBodyModel body,
    _i8.TonikCancellation? cancellation,
  }) async => _catchPreview(body: body, cancellation: cancellation);

  /// List the caller's catch requests, newest first, for conventions whose review window is open. A closed window hides its requests.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i15.CatchRequestsListResponse, _i10.Response>>
  catchRequestsList({
    _i7.int? conventionId,
    _i8.TonikCancellation? cancellation,
  }) async => _catchRequestsList(
    conventionId: conventionId,
    cancellation: cancellation,
  );

  /// Submit a scanned tag at the caller's selected convention. Approval is manual by default. A retry returns the existing pending request or catch.
  ///
  /// Security:
  /// - HTTP Bearer
  _i7.Future<_i8.TonikResult<_i16.CatchRequestsCreateResponse, _i10.Response>>
  catchRequestsCreate({
    required _i17.CatchRequestPayload body,
    _i8.TonikCancellation? cancellation,
  }) async => _catchRequestsCreate(body: body, cancellation: cancellation);
}
