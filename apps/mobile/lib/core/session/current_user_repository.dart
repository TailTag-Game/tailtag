import "package:tailtag_api/tailtag_api.dart";
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/session/current_user.dart";

/// Reads the signed-in player's identity from `GET /api/me/`.
///
/// Wire types stay inside this class: callers get a [CurrentUser] or an
/// [ApiFailure].
final class CurrentUserRepository {
  /// Creates a repository over the shared [_transport].
  const new(this._transport);

  final ApiTransport _transport;

  /// Fetches the identity; throws an [ApiFailure] on any failure.
  Future<CurrentUser> fetch({ApiCancellation? cancellation}) async {
    final response = await _transport.execute(
      operationId: "meRetrieve",
      cancellation: cancellation,
      call: (token) => _transport.me.meRetrieve(cancellation: token),
    );
    return switch (response) {
      MeRetrieveResponse200(:final body) => CurrentUser(body.id),
      // The transport throws for every non-2xx status before this point.
      MeRetrieveResponse401() => throw const ApiUnexpectedFailure(
        statusCode: 401,
      ),
    };
  }
}
