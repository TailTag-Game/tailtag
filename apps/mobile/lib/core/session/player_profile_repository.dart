import "package:tailtag_api/tailtag_api.dart";
import "package:tailtag_mobile/core/api/api_cancellation.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/api/api_transport.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";

/// Reads and saves the signed-in player's profile at `/api/profile/`.
///
/// Wire types stay inside this class: callers get a [PlayerProfile] or an
/// [ApiFailure].
final class PlayerProfileRepository {
  /// Creates a repository over the shared [_transport].
  const new(this._transport);

  final ApiTransport _transport;

  /// Fetches the profile; throws an [ApiFailure] on any failure.
  Future<PlayerProfile> fetch({ApiCancellation? cancellation}) async {
    final response = await _transport.execute(
      operationId: "profileRetrieve",
      cancellation: cancellation,
      call: (token) => _transport.profile.profileRetrieve(cancellation: token),
    );
    return switch (response) {
      ProfileRetrieveResponse200(:final body) => _profile(
        handle: body.handle,
        displayName: body.displayName,
        avatarUrl: body.avatarUrl,
        onboardingComplete: body.onboardingComplete,
        isEnabled: body.isEnabled,
      ),
      // The transport throws for every non-2xx status before this point.
      ProfileRetrieveResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// Sends both text fields exactly as given; throws an [ApiFailure] on any
  /// failure. The server owns normalization and every rule.
  Future<PlayerProfile> save({
    required String handle,
    required String displayName,
    ApiCancellation? cancellation,
  }) async {
    final response = await _transport.execute(
      operationId: "profileUpdate",
      cancellation: cancellation,
      call: (token) => _transport.profile.profileUpdate(
        body: ApiProfilePutBodyRequestBodyJson(
          ProfilePut(handle: handle, displayName: displayName),
        ),
        cancellation: token,
      ),
    );
    return switch (response) {
      ProfileUpdateResponse200(:final body) => _profile(
        handle: body.handle,
        displayName: body.displayName,
        avatarUrl: body.avatarUrl,
        onboardingComplete: body.onboardingComplete,
        isEnabled: body.isEnabled,
      ),
      // The transport throws for every non-2xx status before this point.
      ProfileUpdateResponse() => throw const ApiUnexpectedFailure(),
    };
  }

  /// The generated model makes the state flags optional. A response without
  /// them cannot select a route, so it fails closed.
  static PlayerProfile _profile({
    required String? handle,
    required String? displayName,
    required Uri? avatarUrl,
    required bool? onboardingComplete,
    required bool? isEnabled,
  }) {
    if (onboardingComplete == null || isEnabled == null) {
      throw const ApiUnexpectedFailure(statusCode: 200);
    }
    return PlayerProfile(
      handle: handle,
      displayName: displayName,
      avatarUrl: avatarUrl,
      onboardingComplete: onboardingComplete,
      isEnabled: isEnabled,
    );
  }
}
