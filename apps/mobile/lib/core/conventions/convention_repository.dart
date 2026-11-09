import "package:tailtag_api/tailtag_api.dart" as api;
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";

/// Reads conventions and writes the player's participation at
/// `/api/conventions/`.
///
/// Wire types stay inside this class: callers get TailTag models or an
/// [ApiFailure]. The repository keeps the server's order.
final class ConventionRepository {
  /// Creates a repository over the shared [_transport].
  const new(this._transport);

  final ApiTransport _transport;

  /// The conventions that are open now.
  Future<List<Convention>> listConventions({
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "conventionsList",
      cancellation: cancellation,
      call: (token) =>
          _transport.conventions.conventionsList(cancellation: token),
    );
    return switch (response) {
      api.ConventionsListResponse200(:final body) =>
        body.map(_convention).toList(growable: false),
      // The transport throws for every non-2xx status before this point.
      api.ConventionsListResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// The player's enrollments in every convention status.
  Future<List<ConventionEnrollment>> listEnrollments({
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "conventionsEnrollmentsList",
      cancellation: cancellation,
      call: (token) => _transport.conventions.conventionsEnrollmentsList(
        cancellation: token,
      ),
    );
    return switch (response) {
      api.ConventionsEnrollmentsListResponse200(:final body) =>
        body.map(_enrollment).toList(growable: false),
      api.ConventionsEnrollmentsListResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// The selected enrollment, or null when the player has no selection.
  Future<ConventionEnrollment?> readSelection({
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "conventionsActiveRetrieve",
      cancellation: cancellation,
      call: (token) =>
          _transport.conventions.conventionsActiveRetrieve(cancellation: token),
    );
    return switch (response) {
      api.ConventionsActiveRetrieveResponse200(:final body) =>
        switch (body.enrollment) {
          null => null,
          final selected => _enrollment(selected.conventionEnrollment),
        },
      api.ConventionsActiveRetrieveResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// Enrolls the player in [conventionId] and selects it in one request.
  /// A first enrollment returns `201`, and a repeat returns `200`.
  Future<ConventionEnrollment> enrollAndSelect(
    int conventionId, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "conventionsEnrollmentsCreate",
      cancellation: cancellation,
      call: (token) => _transport.conventions.conventionsEnrollmentsCreate(
        body: api.ApiConventionsEnrollmentsPostBodyRequestBodyJson(
          api.ConventionEnrollRequest(
            conventionId: conventionId,
            setActive: true,
          ),
        ),
        cancellation: token,
      ),
    );
    return switch (response) {
      api.ConventionsEnrollmentsCreateResponse200(:final body) ||
      api.ConventionsEnrollmentsCreateResponse201(
        :final body,
      ) => _enrollment(body),
      api.ConventionsEnrollmentsCreateResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// Selects [conventionId], which the player already joined.
  Future<ConventionEnrollment> select(
    int conventionId, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "conventionsActiveUpdate",
      cancellation: cancellation,
      call: (token) => _transport.conventions.conventionsActiveUpdate(
        body: api.ApiConventionsActivePutBodyRequestBodyJson(
          api.SelectActiveConventionRequest(conventionId: conventionId),
        ),
        cancellation: token,
      ),
    );
    return switch (response) {
      api.ConventionsActiveUpdateResponse200(:final body) =>
        switch (body.enrollment) {
          null => throw const ApiUnexpectedFailure(),
          final selected => _enrollment(selected.conventionEnrollment),
        },
      api.ConventionsActiveUpdateResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// The generated model makes every field optional. A response without one
  /// cannot show a real convention, so it fails closed.
  static Convention _convention(api.Convention? wire) {
    final id = wire?.id;
    final name = wire?.name;
    final status = wire?.status?.statusEnum;
    final start = wire?.startDate;
    final end = wire?.endDate;
    if (id == null ||
        name == null ||
        status == null ||
        start == null ||
        end == null) {
      throw const ApiUnexpectedFailure();
    }
    return Convention(
      id: id,
      name: name,
      status: _status(status),
      startDate: start.toDateTime(),
      endDate: end.toDateTime(),
    );
  }

  static ConventionEnrollment _enrollment(api.ConventionEnrollment wire) {
    final id = wire.id;
    final isActive = wire.isActive;
    if (id == null || isActive == null) {
      throw const ApiUnexpectedFailure();
    }
    return ConventionEnrollment(
      id: id,
      convention: _convention(wire.convention?.convention),
      isSelected: isActive,
    );
  }

  static ConventionStatus _status(api.StatusEnum status) => switch (status) {
    api.StatusEnum.draft => ConventionStatus.draft,
    api.StatusEnum.active => ConventionStatus.active,
    api.StatusEnum.paused => ConventionStatus.paused,
    api.StatusEnum.completed => ConventionStatus.completed,
    api.StatusEnum.cancelled => ConventionStatus.cancelled,
  };
}
