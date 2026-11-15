import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_providers.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// The message at the top of the register form.
enum RegisterBanner {
  /// The app does not know whether the suit was saved.
  unknownOutcome,

  /// The API refused the token while the native session stayed active.
  apiAccess,

  /// The server refused the save because of the player profile.
  notEligible,

  /// The save failed for another reason, in [RegisterState.failure].
  failed,
}

/// What the register form shows. It lives in memory only.
@immutable
final class RegisterState {
  /// Creates a state.
  const new({
    this.photo,
    this.saving = false,
    this.nameError,
    this.photoError,
    this.banner,
    this.failure,
    this.created,
  });

  /// The picked photo, or null.
  final PickedPhoto? photo;

  /// Whether the save runs.
  final bool saving;

  /// The server's message for the name, or null.
  final String? nameError;

  /// The server's message for the photo, or null.
  final String? photoError;

  /// The form message, or null.
  final RegisterBanner? banner;

  /// The failure for [RegisterBanner.failed].
  final ApiFailure? failure;

  /// The saved suit. The screen leaves when it is set.
  final Fursuit? created;
}

/// Owns the register form. A new player scope rebuilds it and clears the
/// form.
final class RegisterController extends Notifier<RegisterState> {
  @override
  RegisterState build() {
    ref.watch(playerScopeProvider);
    return const RegisterState();
  }

  /// Keeps [photo] for the save.
  void setPhoto(PickedPhoto photo) {
    state = RegisterState(photo: photo, banner: state.banner);
  }

  /// Saves a suit with [name] and the picked photo. It sends nothing when
  /// a save runs or the form has no photo.
  Future<void> save(String name) async {
    final photo = state.photo;
    if (state.saving || photo == null) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    state = RegisterState(photo: photo, saving: true);
    try {
      final fursuit = await ref
          .read(fursuitRepositoryProvider)
          .createFursuit(
            name: name,
            photo: photo,
            cancellation: scope.cancellation,
          );
      if (ref.mounted && scope.isActive) {
        state = RegisterState(photo: photo, created: fursuit);
      }
    } on ApiFailure catch (failure) {
      if (ref.mounted && scope.isActive) {
        final next = await _afterFailure(scope, photo, failure);
        // The failure path can wait for a session check, so the scope can
        // close before it ends.
        if (ref.mounted && scope.isActive) {
          state = next;
        }
      }
    }
  }

  Future<RegisterState> _afterFailure(
    PlayerScope scope,
    PickedPhoto photo,
    ApiFailure failure,
  ) async {
    switch (failure) {
      case ApiCancelledFailure():
        return RegisterState(photo: photo);
      case ApiConnectivityFailure() || ApiTimeoutFailure():
        // The suit can exist now. A new save could make a second one.
        return RegisterState(
          photo: photo,
          banner: RegisterBanner.unknownOutcome,
        );
      case ApiValidationFailure(:final fieldErrors):
        final name = _first(fieldErrors["name"]);
        final photoError = _first(fieldErrors["photo"]);
        return RegisterState(
          photo: photo,
          nameError: name,
          photoError: photoError,
          banner: name == null && photoError == null
              ? RegisterBanner.failed
              : null,
          failure: failure,
        );
      case ApiPermissionFailure():
        return RegisterState(photo: photo, banner: RegisterBanner.notEligible);
      case ApiUnauthenticatedFailure():
        final session = ref.read(authSessionProvider);
        await session.recheckSession();
        return RegisterState(
          photo: photo,
          banner: scope.isActive && session.state is AuthSignedIn
              ? RegisterBanner.apiAccess
              : null,
        );
      case ApiFailure():
        return RegisterState(
          photo: photo,
          banner: RegisterBanner.failed,
          failure: failure,
        );
    }
  }

  static String? _first(List<String>? messages) =>
      messages == null || messages.isEmpty ? null : messages.first;
}

/// The register form state. It ends when the register screen leaves.
final NotifierProvider<RegisterController, RegisterState>
registerControllerProvider = NotifierProvider.autoDispose(
  RegisterController.new,
);
