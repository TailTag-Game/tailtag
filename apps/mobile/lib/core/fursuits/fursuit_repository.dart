import "package:tailtag_api/tailtag_api.dart" as api;
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tonik_util/tonik_util.dart";

typedef _ActivationItem =
    api.ApiConventionsConventionIdFursuitActivationsGet200BodyArrayModel;
typedef _ParticipationBody =
    api.ApiConventionsConventionIdFursuitActivationsFursuitIdPutBodyBodyModel;
typedef _SessionBody =
    // The generated name is longer than one line.
    // ignore: lines_longer_than_80_chars
    api.ApiConventionsConventionIdFursuitActivationsFursuitIdCatchSessionPutBodyBodyModel;

/// Reads and writes the signed-in player's suits, their participation, and
/// their catch sessions.
///
/// Wire types stay inside this class: callers get TailTag models or an
/// [ApiFailure]. The server owns every rule, so this class sends values as
/// given and keeps the server's order.
final class FursuitRepository {
  /// Creates a repository over the shared [_transport].
  const new(this._transport);

  final ApiTransport _transport;

  /// The player's suits, in server order.
  Future<List<Fursuit>> listFursuits({ApiCancellation? cancellation}) async {
    final response = await _transport.execute(
      operationId: "fursuitsList",
      cancellation: cancellation,
      call: (token) => _transport.fursuits.fursuitsList(cancellation: token),
    );
    return switch (response) {
      api.FursuitsListResponse200(:final body) => [
        for (final item in body)
          _fursuit(item.id, item.name, item.photoUrl, item.isEnabled),
      ],
      // The transport throws for every non-2xx status before this point.
      api.FursuitsListResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// Registers a suit with [name] and [photo].
  Future<Fursuit> createFursuit({
    required String name,
    required PickedPhoto photo,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "fursuitsCreate",
      cancellation: cancellation,
      multipart: true,
      call: (token) => _transport.fursuits.fursuitsCreate(
        body: api.ApiFursuitsPostBodyBodyModel(
          name: name,
          photo: TonikFileBytes(photo.bytes, fileName: photo.name),
        ),
        cancellation: token,
      ),
    );
    return switch (response) {
      api.FursuitsCreateResponse201(:final body) => _fursuit(
        body.id,
        body.name,
        body.photoUrl,
        body.isEnabled,
      ),
      api.FursuitsCreateResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// Changes the name of suit [id]. It never sends the approval mode.
  Future<Fursuit> renameFursuit(
    int id, {
    required String name,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "fursuitsUpdate",
      cancellation: cancellation,
      call: (token) => _transport.fursuits.fursuitsUpdate(
        id: id,
        body: api.ApiFursuitsIdPatchBodyBodyModel(name: name),
        cancellation: token,
      ),
    );
    return switch (response) {
      api.FursuitsUpdateResponse200(:final body) => _fursuit(
        body.id,
        body.name,
        body.photoUrl,
        body.isEnabled,
      ),
      api.FursuitsUpdateResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// Replaces the photo of suit [id].
  Future<Fursuit> replacePhoto(
    int id, {
    required PickedPhoto photo,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "fursuitsReplacePhoto",
      cancellation: cancellation,
      multipart: true,
      call: (token) => _transport.fursuits.fursuitsReplacePhoto(
        id: id,
        body: api.ApiFursuitsIdPhotoPutBodyBodyModel(
          photo: TonikFileBytes(photo.bytes, fileName: photo.name),
        ),
        cancellation: token,
      ),
    );
    return switch (response) {
      api.FursuitsReplacePhotoResponse200(:final body) => _fursuit(
        body.id,
        body.name,
        body.photoUrl,
        body.isEnabled,
      ),
      api.FursuitsReplacePhotoResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// The participation rows of the player's suits at [conventionId]. A suit
  /// that never participated there has no row.
  Future<List<FursuitActivation>> listActivations(
    int conventionId, {
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "conventionFursuitActivationsList",
      cancellation: cancellation,
      // A null session means "never started", so the key must be present.
      requiredItemKeys: const ["catch_session"],
      call: (token) => _transport.conventions.conventionFursuitActivationsList(
        conventionId: conventionId,
        cancellation: token,
      ),
    );
    return switch (response) {
      api.ConventionFursuitActivationsListResponse200(:final body) => [
        for (final item in body) _activation(item),
      ],
      api.ConventionFursuitActivationsListResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// Sets whether suit [fursuitId] participates at [conventionId].
  ///
  /// The caller reads the list again afterward, because turning
  /// participation off also ends the catch session.
  Future<void> setParticipation(
    int conventionId,
    int fursuitId, {
    required bool active,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "conventionFursuitActivationsSetState",
      cancellation: cancellation,
      call: (token) =>
          _transport.conventions.conventionFursuitActivationsSetState(
            conventionId: conventionId,
            fursuitId: fursuitId,
            body: _ParticipationBody(isActive: active),
            cancellation: token,
          ),
    );
    if (response is! api.ConventionFursuitActivationsSetStateResponse200) {
      throw const ApiUnexpectedFailure();
    }
  }

  /// Starts or stops the catch session of suit [fursuitId] at
  /// [conventionId]. It returns the session, or null when the suit never
  /// had one.
  Future<CatchSession?> setCatchSession(
    int conventionId,
    int fursuitId, {
    required bool active,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "conventionFursuitCatchSessionSetState",
      cancellation: cancellation,
      call: (token) =>
          _transport.conventions.conventionFursuitCatchSessionSetState(
            conventionId: conventionId,
            fursuitId: fursuitId,
            body: _SessionBody(isActive: active),
            cancellation: token,
          ),
    );
    return switch (response) {
      api.ConventionFursuitCatchSessionSetStateResponse200(:final body) =>
        _session(
          isActive: body.isActive,
          startedAt: body.startedAt,
          expiresAt: body.expiresAt,
          endedAt: body.endedAt,
          endReason: _endReason(body.endReason),
        ),
      api.ConventionFursuitCatchSessionSetStateResponse() =>
        throw const ApiUnexpectedFailure(),
    };
  }

  /// The tag of suit [id]. The first read of a suit that never had a tag
  /// makes the server create one.
  Future<FursuitTag> readTag(int id, {ApiCancellation? cancellation}) async {
    final response = await _transport.execute(
      operationId: "fursuitTagRetrieve",
      cancellation: cancellation,
      call: (token) =>
          _transport.fursuits.fursuitTagRetrieve(id: id, cancellation: token),
    );
    return switch (response) {
      api.FursuitTagRetrieveResponse200(:final body) => _tag(
        body.fursuitId,
        body.state.name,
        body.tagVersion,
        body.payload,
      ),
      api.FursuitTagRetrieveResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// Replaces the tag of suit [id] if its version is still
  /// [expectedVersion]. The caller never repeats it on its own.
  Future<FursuitTag> replaceTag(
    int id, {
    required int expectedVersion,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "fursuitTagReplace",
      cancellation: cancellation,
      call: (token) => _transport.fursuits.fursuitTagReplace(
        id: id,
        body: api.ApiFursuitsIdTagReplacePostBodyBodyModel(
          expectedVersion: expectedVersion,
        ),
        cancellation: token,
      ),
    );
    return switch (response) {
      api.FursuitTagReplaceResponse200(:final body) => _tag(
        body.fursuitId,
        body.state.name,
        body.tagVersion,
        body.payload,
      ),
      api.FursuitTagReplaceResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// A current tag must carry a payload, and a revoked one must not.
  static FursuitTag _tag(
    int fursuitId,
    String state,
    int version,
    String? payload,
  ) {
    final tagState = switch (state) {
      "current" => TagState.current,
      "revoked" => TagState.revoked,
      _ => throw const ApiUnexpectedFailure(),
    };
    if ((tagState == TagState.current) != (payload != null)) {
      throw const ApiUnexpectedFailure();
    }
    return FursuitTag(
      fursuitId: fursuitId,
      state: tagState,
      version: version,
      payload: payload,
    );
  }

  /// The generated model makes most fields optional. A response without one
  /// cannot show a real suit, so it fails closed.
  static Fursuit _fursuit(int? id, String name, Uri? photoUrl, bool? enabled) {
    if (id == null || photoUrl == null || enabled == null) {
      throw const ApiUnexpectedFailure();
    }
    return Fursuit(id: id, name: name, photoUrl: photoUrl, isEnabled: enabled);
  }

  static FursuitActivation _activation(_ActivationItem item) {
    final fursuitId = item.fursuitId;
    final isActive = item.isActive;
    final isEligible = item.isEligible;
    if (fursuitId == null || isActive == null || isEligible == null) {
      throw const ApiUnexpectedFailure();
    }
    final wire = item.catchSession;
    final session = wire == null
        ? null
        : _session(
            isActive: wire.isActive,
            startedAt: wire.startedAt,
            expiresAt: wire.expiresAt,
            endedAt: wire.endedAt,
            endReason: _endReason(wire.endReason),
          );
    return FursuitActivation(
      fursuitId: fursuitId,
      isActive: isActive,
      isEligible: isEligible,
      session: session,
    );
  }

  /// The two generated end-reason enums have the same members, so this
  /// maps either one by member name.
  static CatchSessionEndReason? _endReason(Enum? wire) => switch (wire?.name) {
    null => null,
    "owner" => CatchSessionEndReason.owner,
    r"$operator" => CatchSessionEndReason.operator,
    "eligibilityLost" => CatchSessionEndReason.eligibilityLost,
    "expired" => CatchSessionEndReason.expired,
    _ => throw const ApiUnexpectedFailure(),
  };

  /// A session read. A stop for a suit that never had a session has no
  /// times, which means "no session".
  static CatchSession? _session({
    required bool? isActive,
    required DateTime? startedAt,
    required DateTime? expiresAt,
    required DateTime? endedAt,
    required CatchSessionEndReason? endReason,
  }) {
    if (isActive == null) {
      throw const ApiUnexpectedFailure();
    }
    if (startedAt == null || expiresAt == null) {
      if (isActive) {
        throw const ApiUnexpectedFailure();
      }
      return null;
    }
    return CatchSession(
      isActive: isActive,
      startedAt: startedAt,
      expiresAt: expiresAt,
      endedAt: endedAt,
      endReason: endReason,
    );
  }
}
