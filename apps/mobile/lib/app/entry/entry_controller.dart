import "dart:async";

import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/app/entry/entry_stage.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_session.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/conventions/convention_providers.dart";
import "package:tailtag_mobile/core/session/current_user_providers.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/session/player_profile_providers.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// The entry coordinator. It selects the [EntryStage] from the auth state,
/// the bootstrap reads, and sign-out.
///
/// It owns the session epoch: it advances [playerScopeProvider] when a
/// session starts, when a session ends, and when sign-out starts. Every read
/// it starts belongs to one scope. A result from a closed scope is dropped.
///
/// The coordinator never retries a read or an auth call on its own.
final class EntryController extends Notifier<EntryStage> {
  late AuthSession _session;

  /// Whether the last auth state was [AuthSignedIn].
  bool _signedIn = false;

  /// Whether sign-out started and the session has not ended yet.
  bool _signingOut = false;

  /// The ID of the running silent reload, or null. A reload whose ID is no
  /// longer here lost its right to change the stage.
  int? _reload;
  int _lastReload = 0;

  @override
  EntryStage build() {
    _session = ref.watch(authSessionProvider);
    final subscription = _session.states.listen(_onAuth);
    ref
      ..onDispose(subscription.cancel)
      ..listen(foregroundSignalProvider, (_, _) => _onForeground());
    final initial = _session.state;
    if (initial is AuthSignedIn) {
      // The restored session uses the first scope. A provider cannot change
      // another provider while it builds, so the read starts afterwards.
      _signedIn = true;
      scheduleMicrotask(() => unawaited(_bootstrap()));
      return const EntryIdentityLoading();
    }
    return _stageWithoutSession(initial);
  }

  /// Loads the native session again from the auth-recovery stage.
  void reloadSession() {
    final current = state;
    // The session state becomes restoring at once, so a second tap in the
    // same frame does not start a second reload.
    if (current is EntryAuthRecovery &&
        current.canRetry &&
        _session.state is AuthFailed) {
      unawaited(_session.reloadSession());
    }
  }

  /// Runs the bootstrap again from the failed stage.
  void retryIdentity() {
    if (state is EntryIdentityFailed) {
      unawaited(_bootstrap());
    }
  }

  /// Runs the bootstrap again from the account-unavailable stage.
  void refreshProfile() {
    if (state is EntryAccountUnavailable) {
      unawaited(_bootstrap());
    }
  }

  /// Selects the stage from a server [profile] that the onboarding form
  /// resolved. A result from a closed [scope] or another stage is dropped.
  void acceptProfile(PlayerScope scope, PlayerProfile profile) {
    if (_isCurrent(scope) && state is EntryOnboarding) {
      unawaited(_guardRead(scope, () => _routeFromProfile(scope, profile)));
    }
  }

  /// Shows the home of [enrollment], which the picker confirmed with the
  /// server. A result from a closed [scope] or another stage is dropped.
  void acceptSelection(PlayerScope scope, ConventionEnrollment enrollment) {
    if (_isCurrent(scope) && state is EntryConventionPicker) {
      state = EntryConventionHome(enrollment);
    }
  }

  /// Leaves the picker when a fresh [profile] is no longer eligible. A
  /// result from a closed [scope] or another stage is dropped.
  void acceptIneligibleProfile(PlayerScope scope, PlayerProfile profile) {
    final stage = _stageForIneligible(profile);
    if (_isCurrent(scope) && state is EntryConventionPicker && stage != null) {
      state = stage;
    }
  }

  /// Opens the picker from the home. The selection stays until the server
  /// accepts another one.
  void openConventionPicker() {
    final current = state;
    if (current is EntryConventionHome && !_signingOut) {
      _dropReload();
      state = EntryConventionPicker(current: current.enrollment);
    }
  }

  /// Returns from the picker to the home.
  ///
  /// With [writesLocked] true, the selection can differ from the one that
  /// the home showed, so a fresh bootstrap derives the stage.
  void closeConventionPicker({required bool writesLocked}) {
    final current = state;
    if (current is! EntryConventionPicker) {
      return;
    }
    final selected = current.current;
    if (selected == null) {
      return;
    }
    if (writesLocked) {
      _advanceScope();
      unawaited(_bootstrap());
      return;
    }
    state = EntryConventionHome(selected);
  }

  /// Reads the profile and the selection again from the home.
  void refreshHome() {
    if (state is EntryConventionHome) {
      unawaited(_reloadSilently());
    }
  }

  /// Opens the passkey screen from a settled signed-in stage.
  ///
  /// Opening closes the current player scope, so a read that started
  /// earlier cannot move the stage while the screen is open.
  void openPasskeys() {
    final current = state;
    if (!_signedIn ||
        _signingOut ||
        (current is! EntryConventionHome &&
            current is! EntryConventionPicker &&
            current is! EntryIdentityFailed &&
            current is! EntryOnboarding &&
            current is! EntryAccountUnavailable)) {
      return;
    }
    _advanceScope();
    state = const EntryPasskeys();
  }

  /// Closes the passkey screen with a fresh bootstrap of the session, so
  /// the coordinator derives the stage again.
  void closePasskeys() {
    if (state is! EntryPasskeys) {
      return;
    }
    _advanceScope();
    unawaited(_bootstrap());
  }

  /// Starts sign-out. Protected content hides at once.
  Future<void> signOut() async {
    if (_signingOut || !_signedIn) {
      return;
    }
    _signingOut = true;
    _advanceScope();
    state = const EntrySigningOut();
    try {
      await _session.signOut();
    } on Object {
      if (!ref.mounted || !_signingOut) {
        return;
      }
      // The native state decides. If the session ended anyway, the state
      // events move the stage to signed out.
      if (_session.state is AuthSignedIn) {
        state = const EntrySignOutFailed();
      }
    }
  }

  /// Tries sign-out again from the sign-out-failed stage.
  Future<void> retrySignOut() async {
    if (state is! EntrySignOutFailed) {
      return;
    }
    _signingOut = false;
    await signOut();
  }

  /// Leaves the sign-out-failed stage with a fresh bootstrap of the session
  /// that is still active.
  void returnAfterFailedSignOut() {
    if (state is! EntrySignOutFailed) {
      return;
    }
    _signingOut = false;
    _advanceScope();
    unawaited(_bootstrap());
  }

  void _onAuth(AuthState next) {
    if (!ref.mounted) {
      return;
    }
    if (next is AuthSignedIn) {
      if (_signedIn) {
        return;
      }
      _signedIn = true;
      _signingOut = false;
      _advanceScope();
      unawaited(_bootstrap());
      return;
    }
    if (_signedIn) {
      _signedIn = false;
      _advanceScope();
    }
    _signingOut = false;
    state = _stageWithoutSession(next);
  }

  /// The coordinator reloads only the stages with no feature controller.
  /// The picker and the onboarding form reload themselves, because they
  /// know when a write runs.
  void _onForeground() {
    if (!ref.mounted) {
      return;
    }
    final current = state;
    if (current is EntryConventionHome || current is EntryAccountUnavailable) {
      unawaited(_reloadSilently());
    }
  }

  Future<void> _bootstrap() async {
    // A bootstrap scheduled earlier must not replace a later stage, such as
    // signing out.
    if (!ref.mounted || !_signedIn || _signingOut) {
      return;
    }
    _dropReload();
    final scope = ref.read(playerScopeProvider);
    state = const EntryIdentityLoading();
    await _guardRead(scope, () async {
      await ref
          .read(currentUserRepositoryProvider)
          .fetch(cancellation: scope.cancellation);
      if (!_isCurrent(scope)) {
        return;
      }
      final profile = await ref
          .read(playerProfileRepositoryProvider)
          .fetch(cancellation: scope.cancellation);
      if (_isCurrent(scope)) {
        await _routeFromProfile(scope, profile);
      }
    });
  }

  /// Selects the stage from [profile]. An eligible profile needs the
  /// selection first, so the loading stage shows during that read.
  Future<void> _routeFromProfile(
    PlayerScope scope,
    PlayerProfile profile,
  ) async {
    final ineligible = _stageForIneligible(profile);
    if (ineligible != null) {
      state = ineligible;
      return;
    }
    state = const EntryIdentityLoading();
    final selection = await ref
        .read(conventionRepositoryProvider)
        .readSelection(cancellation: scope.cancellation);
    if (_isCurrent(scope)) {
      state = _stageForSelection(selection);
    }
  }

  /// Runs a bootstrap read and maps its failure to a stage.
  Future<void> _guardRead(
    PlayerScope scope,
    Future<void> Function() read,
  ) async {
    try {
      await read();
    } on ApiCancelledFailure {
      return;
    } on ApiUnauthenticatedFailure {
      if (!_isCurrent(scope)) {
        return;
      }
      await _session.recheckSession();
      // If the session ended, the state events move the stage.
      if (_isCurrent(scope) && _session.state is AuthSignedIn) {
        state = const EntryIdentityFailed();
      }
    } on ApiFailure catch (failure) {
      if (_isCurrent(scope)) {
        state = EntryIdentityFailed(failure: failure);
      }
    }
  }

  /// Reads the current stage's server state with no loading stage. It sends
  /// no write. One reload runs at a time.
  Future<void> _reloadSilently() async {
    if (_reload != null || !_signedIn || _signingOut) {
      return;
    }
    final id = ++_lastReload;
    _reload = id;
    final scope = ref.read(playerScopeProvider);
    bool live() => _isCurrent(scope) && _reload == id;

    final shown = state;
    if (shown is EntryConventionHome) {
      state = EntryConventionHome(shown.enrollment, refreshing: true);
    }
    try {
      final profile = await ref
          .read(playerProfileRepositoryProvider)
          .fetch(cancellation: scope.cancellation);
      if (!live()) {
        return;
      }
      final ineligible = _stageForIneligible(profile);
      if (ineligible != null) {
        state = ineligible;
        return;
      }
      if (state is EntryAccountUnavailable) {
        _dropReload();
        await _guardRead(scope, () => _routeFromProfile(scope, profile));
        return;
      }
      final selection = await ref
          .read(conventionRepositoryProvider)
          .readSelection(cancellation: scope.cancellation);
      if (live()) {
        state = _stageForSelection(selection);
      }
    } on ApiCancelledFailure {
      return;
    } on ApiUnauthenticatedFailure {
      if (!live()) {
        return;
      }
      await _session.recheckSession();
      // If the session ended, the state events move the stage.
      if (live() && _session.state is AuthSignedIn) {
        _showReloadFailure(null);
      }
    } on ApiFailure catch (failure) {
      if (live()) {
        _showReloadFailure(failure);
      }
    } finally {
      if (_reload == id) {
        _reload = null;
      }
    }
  }

  /// The content stays. A null [failure] means that the API refused the
  /// token of an active session.
  void _showReloadFailure(ApiFailure? failure) {
    final current = state;
    if (current is EntryConventionHome) {
      state = EntryConventionHome(
        current.enrollment,
        refreshFailure: failure,
        apiAccess: failure == null,
      );
    } else if (current is EntryAccountUnavailable && failure == null) {
      state = const EntryAccountUnavailable(apiAccess: true);
    }
  }

  void _dropReload() => _reload = null;

  bool _isCurrent(PlayerScope scope) =>
      ref.mounted && scope.isActive && _signedIn && !_signingOut;

  void _advanceScope() => ref.read(playerScopeProvider.notifier).advance();

  /// The stage of a profile that cannot participate, or null for an
  /// eligible one. A disabled profile comes first, even when it is
  /// incomplete.
  static EntryStage? _stageForIneligible(PlayerProfile profile) {
    if (!profile.isEnabled) {
      return const EntryAccountUnavailable();
    }
    return profile.onboardingComplete ? null : const EntryOnboarding();
  }

  /// The app never selects a convention for the player.
  static EntryStage _stageForSelection(ConventionEnrollment? selection) =>
      selection == null
      ? const EntryConventionPicker()
      : EntryConventionHome(selection);

  static EntryStage _stageWithoutSession(AuthState state) => switch (state) {
    AuthRestoring() => const EntryRestoring(),
    AuthSignedOut() => const EntrySignedOut(),
    AuthFailed(:final failure) => EntryAuthRecovery(failure),
    // Handled by the callers before they get here.
    AuthSignedIn() => const EntryIdentityLoading(),
  };
}

/// The current entry stage.
final entryControllerProvider = NotifierProvider<EntryController, EntryStage>(
  EntryController.new,
);
