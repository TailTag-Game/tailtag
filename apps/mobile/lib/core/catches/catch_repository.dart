import "package:tailtag_api/tailtag_api.dart" as api;
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";

/// Previews and submits catch attempts, reads the player's own requests,
/// withdraws a request, and reads the private collection.
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

  static PlayerCatchRequest _request(api.PlayerRequest wire) =>
      PlayerCatchRequest(
        id: wire.id,
        fursuit: CatchFursuit(
          id: wire.fursuit.id,
          name: wire.fursuit.name,
          photoUrl: wire.fursuit.photoUrl,
        ),
        conventionId: wire.conventionId,
        state: switch (wire.state) {
          api.CatchRequestState.pending => CatchRequestState.pending,
          api.CatchRequestState.approved => CatchRequestState.approved,
          api.CatchRequestState.declined => CatchRequestState.declined,
          api.CatchRequestState.withdrawn => CatchRequestState.withdrawn,
          api.CatchRequestState.unavailable => CatchRequestState.unavailable,
        },
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
