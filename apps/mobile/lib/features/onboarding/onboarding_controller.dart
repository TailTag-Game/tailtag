import "dart:async";

import "package:flutter/foundation.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/session/player_profile_providers.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// The server call that the form waits for.
enum OnboardingPending {
  /// The `PUT` of both fields.
  save,

  /// The `GET` that follows a refusal or an unknown outcome.
  read,
}

/// The message at the top of the form.
enum OnboardingBanner {
  /// The server refused the save for a reason with no field.
  unknownError,

  /// The app does not know whether the save reached the server.
  unknownOutcome,

  /// The API refused the token while the native session stayed active.
  apiAccess,
}

/// A field of the form.
enum OnboardingField {
  /// The handle.
  handle,

  /// The display name.
  displayName,
}

/// A server profile that decides the next stage, and the scope it belongs
/// to.
@immutable
final class OnboardingResolution {
  /// Creates a resolution.
  const new(this.scope, this.profile);

  /// The player scope that read the profile.
  final PlayerScope scope;

  /// The server profile.
  final PlayerProfile profile;
}

/// What the form shows. It lives in memory only.
@immutable
final class OnboardingState {
  /// Creates a state.
  const new({
    this.pending,
    this.banner,
    this.writesLocked = false,
    this.handleError,
    this.displayNameError,
    this.resolution,
  });

  /// The running server call, or null.
  final OnboardingPending? pending;

  /// The banner, or null.
  final OnboardingBanner? banner;

  /// Whether a save must wait for a successful read.
  final bool writesLocked;

  /// The server message for the handle, or null.
  final String? handleError;

  /// The server message for the display name, or null.
  final String? displayNameError;

  /// The profile that decides the next stage, or null.
  final OnboardingResolution? resolution;

  /// Whether Continue can start a save.
  bool get canContinue => pending == null && !writesLocked;

  /// Whether the player can leave for another signed-in screen.
  bool get canLeave => pending == null;
}

/// Runs the onboarding form over the profile repository.
///
/// It sends one save at a time and only on an explicit action. It never
/// repeats a save. After a result with no definite answer, it locks saves
/// until a read succeeds. Every async step captures its [PlayerScope], so a
/// late result from a closed scope changes nothing.
final class OnboardingController extends Notifier<OnboardingState> {
  /// The ID of the latest foreground read. A save or a recovery read makes
  /// an earlier ID stale.
  int _foregroundRead = 0;
  bool _foregroundRunning = false;

  @override
  OnboardingState build() {
    // A new player scope rebuilds this provider and clears the form state.
    ref
      ..watch(playerScopeProvider)
      ..listen(
        foregroundSignalProvider,
        (_, _) => unawaited(_readOnForeground()),
      );
    return const OnboardingState();
  }

  /// Saves both fields exactly as typed.
  Future<void> submit({
    required String handle,
    required String displayName,
  }) async {
    if (!state.canContinue) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    _foregroundRead++;
    state = const OnboardingState(pending: OnboardingPending.save);
    final PlayerProfile profile;
    try {
      profile = await ref
          .read(playerProfileRepositoryProvider)
          .save(
            handle: handle,
            displayName: displayName,
            cancellation: scope.cancellation,
          );
    } on ApiFailure catch (failure) {
      if (scope.isActive) {
        await _afterFailedSave(scope, failure);
      }
      return;
    }
    if (!scope.isActive) {
      return;
    }
    if (profile.onboardingComplete) {
      _resolve(scope, profile);
    } else {
      state = _unknownOutcome();
    }
  }

  /// Reads the profile after a save with no definite answer.
  Future<void> retry() async {
    if (state.pending != null || !state.writesLocked) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    _foregroundRead++;
    state = OnboardingState(
      pending: OnboardingPending.read,
      banner: state.banner,
      writesLocked: true,
    );
    await _read(scope);
  }

  /// Clears the server message of [field] after the player edits it.
  void clearFieldError(OnboardingField field) {
    final current = state;
    final error = switch (field) {
      OnboardingField.handle => current.handleError,
      OnboardingField.displayName => current.displayNameError,
    };
    if (error == null) {
      return;
    }
    state = OnboardingState(
      pending: current.pending,
      banner: current.banner,
      writesLocked: current.writesLocked,
      handleError: field == OnboardingField.handle ? null : current.handleError,
      displayNameError: field == OnboardingField.displayName
          ? null
          : current.displayNameError,
    );
  }

  /// Reads the profile after the app returns to the foreground.
  ///
  /// It sends no save and leaves the form state alone. The route changes
  /// only if the profile is no longer enabled and incomplete.
  Future<void> _readOnForeground() async {
    if (_foregroundRunning || state.pending != null) {
      return;
    }
    final id = ++_foregroundRead;
    final scope = ref.read(playerScopeProvider);
    bool live() => ref.mounted && scope.isActive && id == _foregroundRead;
    _foregroundRunning = true;
    try {
      final profile = await ref
          .read(playerProfileRepositoryProvider)
          .fetch(cancellation: scope.cancellation);
      if (live() && (profile.onboardingComplete || !profile.isEnabled)) {
        _resolve(scope, profile);
      }
    } on ApiUnauthenticatedFailure {
      if (live()) {
        await _sessionStaysActive(scope);
      }
    } on ApiFailure {
      return;
    } finally {
      _foregroundRunning = false;
    }
  }

  Future<void> _afterFailedSave(PlayerScope scope, ApiFailure failure) async {
    switch (failure) {
      case ApiCancelledFailure():
        return;
      case ApiValidationFailure(:final fieldErrors):
        final handle = _first(fieldErrors["handle"]);
        final displayName = _first(fieldErrors["display_name"]);
        state = OnboardingState(
          handleError: handle,
          displayNameError: displayName,
          banner: handle == null && displayName == null
              ? OnboardingBanner.unknownError
              : null,
        );
      case ApiUnauthenticatedFailure():
        if (await _sessionStaysActive(scope)) {
          state = const OnboardingState(
            banner: OnboardingBanner.apiAccess,
            writesLocked: true,
          );
        }
      case ApiPermissionFailure():
        await _read(scope, bannerIfIncomplete: OnboardingBanner.unknownError);
      case ApiFailure():
        state = _unknownOutcome();
    }
  }

  /// Reads the server profile and routes from it. It sends no save.
  Future<void> _read(
    PlayerScope scope, {
    OnboardingBanner? bannerIfIncomplete,
  }) async {
    final PlayerProfile profile;
    try {
      profile = await ref
          .read(playerProfileRepositoryProvider)
          .fetch(cancellation: scope.cancellation);
    } on ApiCancelledFailure {
      return;
    } on ApiUnauthenticatedFailure {
      if (scope.isActive && await _sessionStaysActive(scope)) {
        state = _unknownOutcome();
      }
      return;
    } on ApiFailure {
      if (scope.isActive) {
        state = _unknownOutcome();
      }
      return;
    }
    if (!scope.isActive) {
      return;
    }
    if (profile.onboardingComplete || !profile.isEnabled) {
      _resolve(scope, profile);
    } else {
      state = OnboardingState(banner: bannerIfIncomplete);
    }
  }

  /// Checks the native session once. If it ended, the state events move the
  /// stage and close [scope].
  Future<bool> _sessionStaysActive(PlayerScope scope) async {
    final session = ref.read(authSessionProvider);
    await session.recheckSession();
    return scope.isActive && session.state is AuthSignedIn;
  }

  /// The form stays busy, so no tap lands before the route changes.
  void _resolve(PlayerScope scope, PlayerProfile profile) {
    state = OnboardingState(
      pending: state.pending,
      banner: state.banner,
      writesLocked: state.writesLocked,
      resolution: OnboardingResolution(scope, profile),
    );
  }

  /// A failed read keeps the banner that the player already sees.
  OnboardingState _unknownOutcome() => OnboardingState(
    banner: state.banner ?? OnboardingBanner.unknownOutcome,
    writesLocked: true,
  );

  static String? _first(List<String>? messages) =>
      messages == null || messages.isEmpty ? null : messages.first;
}

/// The form state. It ends when the screen leaves or the player scope
/// changes.
final NotifierProvider<OnboardingController, OnboardingState>
onboardingControllerProvider =
    NotifierProvider.autoDispose<OnboardingController, OnboardingState>(
      OnboardingController.new,
    );
