import "dart:async";

import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/app/entry/entry_stage.dart";
import "package:tailtag_mobile/core/api/api_failure.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/auth_session.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/session/current_user_providers.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/session/player_profile_providers.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";

/// The entry coordinator. It selects the [EntryStage] from the auth state,
/// the identity and profile bootstrap, and sign-out.
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

  @override
  EntryStage build() {
    _session = ref.watch(authSessionProvider);
    final subscription = _session.states.listen(_onAuth);
    ref.onDispose(subscription.cancel);
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

  /// Reads the identity and the profile again from the identity-failed
  /// stage.
  void retryIdentity() {
    if (state is EntryIdentityFailed) {
      unawaited(_bootstrap());
    }
  }

  /// Reads the identity and the profile again from the account-unavailable
  /// stage.
  void refreshProfile() {
    if (state is EntryAccountUnavailable) {
      unawaited(_bootstrap());
    }
  }

  /// Selects the stage from a server [profile] that the onboarding form
  /// resolved. A result from a closed [scope] or another stage is dropped.
  void acceptProfile(PlayerScope scope, PlayerProfile profile) {
    if (_isCurrent(scope) && state is EntryOnboarding) {
      state = _stageForProfile(profile);
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
        (current is! EntryReady &&
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

  Future<void> _bootstrap() async {
    // A bootstrap scheduled earlier must not replace a later stage, such as
    // signing out.
    if (!ref.mounted || !_signedIn || _signingOut) {
      return;
    }
    final scope = ref.read(playerScopeProvider);
    state = const EntryIdentityLoading();
    try {
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
        state = _stageForProfile(profile);
      }
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

  bool _isCurrent(PlayerScope scope) =>
      ref.mounted && scope.isActive && _signedIn && !_signingOut;

  void _advanceScope() => ref.read(playerScopeProvider.notifier).advance();

  /// A disabled profile comes first, even when it is incomplete.
  static EntryStage _stageForProfile(PlayerProfile profile) {
    if (!profile.isEnabled) {
      return const EntryAccountUnavailable();
    }
    return profile.onboardingComplete
        ? const EntryReady()
        : const EntryOnboarding();
  }

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
