import "package:tailtag_api/tailtag_api.dart" as api;
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";

/// Previews and submits catch attempts, reads the player's own requests,
/// withdraws a request, reads the private collection, and reads and acts
/// on the requests on the owner's suits.
///
/// Wire types stay inside this class: callers get TailTag models or an
/// [ApiFailure]. The server owns every rule and keeps its own order. The
/// payload goes only into request bodies, never into a path, a query, or a
/// diagnostic.
final class CatchRepository {
  /// Creates a repository over the shared [_transport].
  const new(this._transport);

  final ApiTransport _transport;

  /// Resolves [payload] at the player's selected convention. It creates
  /// nothing.
  Future<CatchPreview> preview(
    TagPayload payload, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchPreview",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchPreview(
        body: api.ApiCatchesPreviewPostBodyBodyModel(payload: payload.value),
        cancellation: token,
      ),
    );
    return switch (response) {
      api.CatchPreviewResponse200(:final body) => CatchPreview(
        fursuit: CatchFursuit(
          id: body.fursuit.id,
          name: body.fursuit.name,
          photoUrl: body.fursuit.photoUrl,
        ),
        conventionId: body.conventionId,
      ),
      // The transport throws for every non-2xx status before this point.
      api.CatchPreviewResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// Submits a catch attempt for [payload]. A repeat after a lost response
  /// returns the existing request or catch.
  Future<CatchSubmission> submit(
    TagPayload payload, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchRequestsCreate",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchRequestsCreate(
        body: api.CatchRequestPayload(payload: payload.value),
        cancellation: token,
      ),
    );
    final body = switch (response) {
      api.CatchRequestsCreateResponse200(:final body) ||
      api.CatchRequestsCreateResponse201(:final body) => body,
      api.CatchRequestsCreateResponse() => throw const ApiUnexpectedFailure(),
    };
    return CatchSubmission(
      outcome: switch (body.outcome) {
        api.CatchRequestOutcome.pending => CatchSubmitOutcome.pending,
        api.CatchRequestOutcome.approved => CatchSubmitOutcome.approved,
        api.CatchRequestOutcome.alreadyPending =>
          CatchSubmitOutcome.alreadyPending,
        api.CatchRequestOutcome.alreadyCaught =>
          CatchSubmitOutcome.alreadyCaught,
      },
      request: switch (body.request) {
        null => null,
        final request => _request(request),
      },
      catchConventionId: body.$catch?.conventionId,
    );
  }

  /// The player's requests in every convention whose review window is
  /// open, in server order.
  Future<List<PlayerCatchRequest>> listRequests({
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchRequestsList",
      cancellation: cancellation,
      call: (token) =>
          _transport.catches.catchRequestsList(cancellation: token),
    );
    return switch (response) {
      api.CatchRequestsListResponse200(:final body) => [
        for (final item in body.results) _request(item),
      ],
      api.CatchRequestsListResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// Withdraws request [id]. A repeat of a withdrawal returns 200.
  Future<PlayerCatchRequest> withdraw(
    int id, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchRequestsWithdraw",
      cancellation: cancellation,
      call: (token) =>
          _transport.catches.catchRequestsWithdraw(id: id, cancellation: token),
    );
    return switch (response) {
      api.CatchRequestsWithdrawResponse200(:final body) => _request(body),
      api.CatchRequestsWithdrawResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// Page [page] of the collection, with the server page size of 20.
  /// It is filtered to [conventionId] when that is not null.
  Future<CatchHistoryPage> listCatches({
    int? conventionId,
    int page = 1,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchHistoryList",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchHistoryList(
        conventionId: conventionId,
        page: page,
        cancellation: token,
      ),
    );
    final body = switch (response) {
      api.CatchHistoryListResponse200(:final body) => body,
      api.CatchHistoryListResponse() => throw const ApiUnexpectedFailure(),
    };
    return CatchHistoryPage(
      items: [for (final item in body.results) _caught(item)],
      hasNext: body.next != null,
    );
  }

  /// The requests on the owner's suits in every open review window, in
  /// server order. It is filtered to [fursuitId] when that is not null.
  Future<List<OwnerCatchRequest>> listIncoming({
    int? fursuitId,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchIncomingRequestsList",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchIncomingRequestsList(
        fursuitId: fursuitId,
        cancellation: token,
      ),
    );
    return switch (response) {
      api.CatchIncomingRequestsListResponse200(:final body) => [
        for (final item in body.results) _ownerRequest(item),
      ],
      api.CatchIncomingRequestsListResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// The pending counts on the owner's suits in every open review window.
  Future<PendingSummary> pendingSummary({ApiCancellation? cancellation}) async {
    final response = await _transport.execute(
      operationId: "catchIncomingRequestsSummary",
      cancellation: cancellation,
      call: (token) =>
          _transport.catches.catchIncomingRequestsSummary(cancellation: token),
    );
    return switch (response) {
      api.CatchIncomingRequestsSummaryResponse200(:final body) =>
        PendingSummary(
          pendingCount: body.pendingCount,
          byFursuit: {
            for (final item in body.fursuits) item.fursuitId: item.pendingCount,
          },
        ),
      api.CatchIncomingRequestsSummaryResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// Approves request [id]. A repeat returns the same result.
  Future<OwnerCatchRequest> approve(
    int id, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchIncomingRequestsApprove",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchIncomingRequestsApprove(
        id: id,
        cancellation: token,
      ),
    );
    return switch (response) {
      api.CatchIncomingRequestsApproveResponse200(:final body) => _ownerRequest(
        body.request,
      ),
      api.CatchIncomingRequestsApproveResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// Declines request [id], and blocks the player for the suit and
  /// convention when [block] is true.
  Future<OwnerCatchRequest> decline(
    int id, {
    required bool block,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchIncomingRequestsDecline",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchIncomingRequestsDecline(
        id: id,
        body: api.CatchRequestDecline(block: block),
        cancellation: token,
      ),
    );
    return switch (response) {
      api.CatchIncomingRequestsDeclineResponse200(:final body) => _ownerRequest(
        body,
      ),
      api.CatchIncomingRequestsDeclineResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// Undoes the ordinary decline of request [id].
  Future<OwnerCatchRequest> undoDecline(
    int id, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchIncomingRequestsUndoDecline",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchIncomingRequestsUndoDecline(
        id: id,
        cancellation: token,
      ),
    );
    return switch (response) {
      api.CatchIncomingRequestsUndoDeclineResponse200(:final body) =>
        _ownerRequest(body),
      api.CatchIncomingRequestsUndoDeclineResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// Returns declined request [id] to pending.
  Future<OwnerCatchRequest> restore(
    int id, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "catchIncomingRequestsRestore",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchIncomingRequestsRestore(
        id: id,
        cancellation: token,
      ),
    );
    return switch (response) {
      api.CatchIncomingRequestsRestoreResponse200(:final body) => _ownerRequest(
        body,
      ),
      api.CatchIncomingRequestsRestoreResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// Removes the block of request [id]'s player, suit, and convention. No
  /// block in place also succeeds.
  Future<void> unblock(int id, {ApiCancellation? cancellation}) async {
    await _transport.execute(
      operationId: "catchIncomingRequestsUnblock",
      cancellation: cancellation,
      call: (token) => _transport.catches.catchIncomingRequestsUnblock(
        id: id,
        cancellation: token,
      ),
    );
  }

  static CatchRequestState _state(api.CatchRequestState wire) => switch (wire) {
    api.CatchRequestState.pending => CatchRequestState.pending,
    api.CatchRequestState.approved => CatchRequestState.approved,
    api.CatchRequestState.declined => CatchRequestState.declined,
    api.CatchRequestState.withdrawn => CatchRequestState.withdrawn,
    api.CatchRequestState.unavailable => CatchRequestState.unavailable,
  };

  static OwnerCatchRequest _ownerRequest(api.OwnerRequest wire) =>
      OwnerCatchRequest(
        id: wire.id,
        fursuit: CatchFursuit(
          id: wire.fursuit.id,
          name: wire.fursuit.name,
          photoUrl: wire.fursuit.photoUrl,
        ),
        conventionId: wire.conventionId,
        player: RequestPlayer(
          displayName: wire.player.displayName,
          handle: wire.player.handle,
        ),
        state: _state(wire.state),
        requestedAt: wire.requestedAt,
        undoAvailableUntil: wire.undoAvailableUntil,
        priorDeclineCount: wire.priorDeclineCount,
        playerBlocked: wire.playerBlocked,
        approvalPaused: wire.approvalPaused,
        reviewDeadlineAt: wire.reviewDeadlineAt,
      );

  static PlayerCatchRequest _request(api.PlayerRequest wire) =>
      PlayerCatchRequest(
        id: wire.id,
        fursuit: CatchFursuit(
          id: wire.fursuit.id,
          name: wire.fursuit.name,
          photoUrl: wire.fursuit.photoUrl,
        ),
        conventionId: wire.conventionId,
        state: _state(wire.state),
        requestedAt: wire.requestedAt,
        reviewDeadlineAt: wire.reviewDeadlineAt,
      );

  /// The generated model makes every history field optional. A row without
  /// one cannot show a real catch, so it fails closed.
  static CaughtFursuit _caught(
    api.CatchHistoryResponseSchemaResultsArrayModel wire,
  ) {
    final id = wire.id;
    final fursuitId = wire.fursuit.id;
    final name = wire.fursuit.name;
    final photo = wire.fursuit.photoUrl;
    final conventionId = wire.convention.id;
    final conventionName = wire.convention.name;
    final caughtAt = wire.caughtAt;
    if (id == null ||
        fursuitId == null ||
        name == null ||
        photo == null ||
        conventionId == null ||
        conventionName == null ||
        caughtAt == null) {
      throw const ApiUnexpectedFailure();
    }
    return CaughtFursuit(
      id: id,
      fursuit: CatchFursuit(id: fursuitId, name: name, photoUrl: photo),
      conventionId: conventionId,
      conventionName: conventionName,
      caughtAt: caughtAt,
    );
  }
}
