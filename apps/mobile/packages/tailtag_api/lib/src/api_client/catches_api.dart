// Generated code - do not modify by hand

// ignore_for_file: no_leading_underscores_for_library_prefixes

import 'dart:core' as _i15;

import 'package:http/http.dart' as _i18;
import 'package:tailtag_api/src/model/api_catches_preview_post_body_body_model.dart'
    as _i30;
import 'package:tailtag_api/src/model/catch_confirmation_request_schema.dart'
    as _i20;
import 'package:tailtag_api/src/model/catch_request_decline.dart' as _i25;
import 'package:tailtag_api/src/model/catch_request_payload.dart' as _i33;
import 'package:tailtag_api/src/operation/catch_confirm.dart' as _i3;
import 'package:tailtag_api/src/operation/catch_history_list.dart' as _i2;
import 'package:tailtag_api/src/operation/catch_incoming_requests_approve.dart'
    as _i5;
import 'package:tailtag_api/src/operation/catch_incoming_requests_decline.dart'
    as _i7;
import 'package:tailtag_api/src/operation/catch_incoming_requests_list.dart'
    as _i4;
import 'package:tailtag_api/src/operation/catch_incoming_requests_restore.dart'
    as _i8;
import 'package:tailtag_api/src/operation/catch_incoming_requests_summary.dart'
    as _i10;
import 'package:tailtag_api/src/operation/catch_incoming_requests_unblock.dart'
    as _i6;
import 'package:tailtag_api/src/operation/catch_incoming_requests_undo_decline.dart'
    as _i9;
import 'package:tailtag_api/src/operation/catch_preview.dart' as _i11;
import 'package:tailtag_api/src/operation/catch_requests_create.dart' as _i13;
import 'package:tailtag_api/src/operation/catch_requests_list.dart' as _i12;
import 'package:tailtag_api/src/operation/catch_requests_withdraw.dart' as _i14;
import 'package:tailtag_api/src/response_wrapper/catch_confirm_response.dart'
    as _i19;
import 'package:tailtag_api/src/response_wrapper/catch_history_list_response.dart'
    as _i17;
import 'package:tailtag_api/src/response_wrapper/catch_incoming_requests_approve_response.dart'
    as _i22;
import 'package:tailtag_api/src/response_wrapper/catch_incoming_requests_decline_response.dart'
    as _i24;
import 'package:tailtag_api/src/response_wrapper/catch_incoming_requests_list_response.dart'
    as _i21;
import 'package:tailtag_api/src/response_wrapper/catch_incoming_requests_restore_response.dart'
    as _i26;
import 'package:tailtag_api/src/response_wrapper/catch_incoming_requests_summary_response.dart'
    as _i28;
import 'package:tailtag_api/src/response_wrapper/catch_incoming_requests_unblock_response.dart'
    as _i23;
import 'package:tailtag_api/src/response_wrapper/catch_incoming_requests_undo_decline_response.dart'
    as _i27;
import 'package:tailtag_api/src/response_wrapper/catch_preview_response.dart'
    as _i29;
import 'package:tailtag_api/src/response_wrapper/catch_requests_create_response.dart'
    as _i32;
import 'package:tailtag_api/src/response_wrapper/catch_requests_list_response.dart'
    as _i31;
import 'package:tailtag_api/src/response_wrapper/catch_requests_withdraw_response.dart'
    as _i34;
import 'package:tailtag_api/src/server/server.dart' as _i1;
import 'package:tonik_util/tonik_util.dart' as _i16;

class CatchesApi {
  CatchesApi(_i1.Server server)
    : _catchHistoryList = _i2.CatchHistoryList(
        server.baseUrl,
        () => server.client,
      ),
      _catchConfirm = _i3.CatchConfirm(server.baseUrl, () => server.client),
      _catchIncomingRequestsList = _i4.CatchIncomingRequestsList(
        server.baseUrl,
        () => server.client,
      ),
      _catchIncomingRequestsApprove = _i5.CatchIncomingRequestsApprove(
        server.baseUrl,
        () => server.client,
      ),
      _catchIncomingRequestsUnblock = _i6.CatchIncomingRequestsUnblock(
        server.baseUrl,
        () => server.client,
      ),
      _catchIncomingRequestsDecline = _i7.CatchIncomingRequestsDecline(
        server.baseUrl,
        () => server.client,
      ),
      _catchIncomingRequestsRestore = _i8.CatchIncomingRequestsRestore(
        server.baseUrl,
        () => server.client,
      ),
      _catchIncomingRequestsUndoDecline = _i9.CatchIncomingRequestsUndoDecline(
        server.baseUrl,
        () => server.client,
      ),
      _catchIncomingRequestsSummary = _i10.CatchIncomingRequestsSummary(
        server.baseUrl,
        () => server.client,
      ),
      _catchPreview = _i11.CatchPreview(server.baseUrl, () => server.client),
      _catchRequestsList = _i12.CatchRequestsList(
        server.baseUrl,
        () => server.client,
      ),
      _catchRequestsCreate = _i13.CatchRequestsCreate(
        server.baseUrl,
        () => server.client,
      ),
      _catchRequestsWithdraw = _i14.CatchRequestsWithdraw(
        server.baseUrl,
        () => server.client,
      );

  final _i2.CatchHistoryList _catchHistoryList;

  final _i3.CatchConfirm _catchConfirm;

  final _i4.CatchIncomingRequestsList _catchIncomingRequestsList;

  final _i5.CatchIncomingRequestsApprove _catchIncomingRequestsApprove;

  final _i6.CatchIncomingRequestsUnblock _catchIncomingRequestsUnblock;

  final _i7.CatchIncomingRequestsDecline _catchIncomingRequestsDecline;

  final _i8.CatchIncomingRequestsRestore _catchIncomingRequestsRestore;

  final _i9.CatchIncomingRequestsUndoDecline _catchIncomingRequestsUndoDecline;

  final _i10.CatchIncomingRequestsSummary _catchIncomingRequestsSummary;

  final _i11.CatchPreview _catchPreview;

  final _i12.CatchRequestsList _catchRequestsList;

  final _i13.CatchRequestsCreate _catchRequestsCreate;

  final _i14.CatchRequestsWithdraw _catchRequestsWithdraw;

  /// Returns only the authenticated player's Catch history ordered by -caught_at then -id. catch_count is the total number of matching Catch rows before pagination. Each supported query parameter may appear at most once; unknown query parameters are rejected.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<_i16.TonikResult<_i17.CatchHistoryListResponse, _i18.Response>>
  catchHistoryList({
    _i15.int? conventionId,
    _i15.int page = _i2.CatchHistoryList.pageDefault,
    _i15.int pageSize = _i2.CatchHistoryList.pageSizeDefault,
    _i16.TonikCancellation? cancellation,
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
  @_i15.Deprecated('This operation is deprecated.')
  _i15.Future<_i16.TonikResult<_i19.CatchConfirmResponse, _i18.Response>>
  catchConfirm({
    required _i20.CatchConfirmationRequestSchema body,
    _i16.TonikCancellation? cancellation,
  }) async => _catchConfirm(body: body, cancellation: cancellation);

  /// List requests on the caller's suits, newest first, for conventions whose review window is open.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i21.CatchIncomingRequestsListResponse, _i18.Response>
  >
  catchIncomingRequestsList({
    _i15.int? conventionId,
    _i15.int? fursuitId,
    _i16.TonikCancellation? cancellation,
  }) async => _catchIncomingRequestsList(
    conventionId: conventionId,
    fursuitId: fursuitId,
    cancellation: cancellation,
  );

  /// Approve a pending request. The catch time is the request time. A repeat returns the same catch.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i22.CatchIncomingRequestsApproveResponse, _i18.Response>
  >
  catchIncomingRequestsApprove({
    required _i15.int id,
    _i16.TonikCancellation? cancellation,
  }) async => _catchIncomingRequestsApprove(id: id, cancellation: cancellation);

  /// Remove the block for this request's player, suit, and convention. The cooldown stays. No block in place also returns 204.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i23.CatchIncomingRequestsUnblockResponse, _i18.Response>
  >
  catchIncomingRequestsUnblock({
    required _i15.int id,
    _i16.TonikCancellation? cancellation,
  }) async => _catchIncomingRequestsUnblock(id: id, cancellation: cancellation);

  /// Decline a pending request. No reason is needed. With block true, the player is also blocked for this suit at this convention.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i24.CatchIncomingRequestsDeclineResponse, _i18.Response>
  >
  catchIncomingRequestsDecline({
    required _i25.CatchRequestDecline body,
    required _i15.int id,
    _i16.TonikCancellation? cancellation,
  }) async => _catchIncomingRequestsDecline(
    body: body,
    id: id,
    cancellation: cancellation,
  );

  /// Restore a declined request to pending before the review deadline. An active block stays.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i26.CatchIncomingRequestsRestoreResponse, _i18.Response>
  >
  catchIncomingRequestsRestore({
    required _i15.int id,
    _i16.TonikCancellation? cancellation,
  }) async => _catchIncomingRequestsRestore(id: id, cancellation: cancellation);

  /// Undo an ordinary decline within 10 seconds. The request returns to pending, and the decline no longer counts.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<
      _i27.CatchIncomingRequestsUndoDeclineResponse,
      _i18.Response
    >
  >
  catchIncomingRequestsUndoDecline({
    required _i15.int id,
    _i16.TonikCancellation? cancellation,
  }) async =>
      _catchIncomingRequestsUndoDecline(id: id, cancellation: cancellation);

  /// Count pending requests on the caller's suits in open windows.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i28.CatchIncomingRequestsSummaryResponse, _i18.Response>
  >
  catchIncomingRequestsSummary({
    _i15.int? conventionId,
    _i16.TonikCancellation? cancellation,
  }) async => _catchIncomingRequestsSummary(
    conventionId: conventionId,
    cancellation: cancellation,
  );

  /// Resolve a scanned tag against the caller's selected convention. Preview creates nothing. Unknown, revoked, and unavailable targets share one neutral 404.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<_i16.TonikResult<_i29.CatchPreviewResponse, _i18.Response>>
  catchPreview({
    required _i30.ApiCatchesPreviewPostBodyBodyModel body,
    _i16.TonikCancellation? cancellation,
  }) async => _catchPreview(body: body, cancellation: cancellation);

  /// List the caller's catch requests, newest first, for conventions whose review window is open. A closed window hides its requests.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<_i16.TonikResult<_i31.CatchRequestsListResponse, _i18.Response>>
  catchRequestsList({
    _i15.int? conventionId,
    _i16.TonikCancellation? cancellation,
  }) async => _catchRequestsList(
    conventionId: conventionId,
    cancellation: cancellation,
  );

  /// Submit a scanned tag at the caller's selected convention. Approval is manual by default. A retry returns the existing pending request or catch.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<_i16.TonikResult<_i32.CatchRequestsCreateResponse, _i18.Response>>
  catchRequestsCreate({
    required _i33.CatchRequestPayload body,
    _i16.TonikCancellation? cancellation,
  }) async => _catchRequestsCreate(body: body, cancellation: cancellation);

  /// Withdraw the caller's pending request. A withdrawal does not count as a decline and does not reset a cooldown.
  ///
  /// Security:
  /// - HTTP Bearer
  _i15.Future<
    _i16.TonikResult<_i34.CatchRequestsWithdrawResponse, _i18.Response>
  >
  catchRequestsWithdraw({
    required _i15.int id,
    _i16.TonikCancellation? cancellation,
  }) async => _catchRequestsWithdraw(id: id, cancellation: cancellation);
}
