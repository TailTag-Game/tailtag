import "package:flutter/foundation.dart";
import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/app/entry/entry_controller.dart";
import "package:tailtag_mobile/app/entry/entry_stage.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";

/// The English text of the entry screens.
abstract final class EntryStrings {
  /// The app name.
  static const appName = "TailTag";

  /// The restoring label.
  static const restoring = "Loading your session";

  /// The identity loading label.
  static const loadingAccount = "Loading your account";

  /// The signing-out label.
  static const signingOut = "Signing out";

  /// The auth-recovery text.
  static const recovery =
      "TailTag could not load your session. Check your connection, then try "
      "again.";

  /// The unsupported-platform text.
  static const unsupported = "Account access is not available on this device.";

  /// The sign-out failure text.
  static const signOutFailed =
      "TailTag could not sign you out. Check your connection, then try again.";

  /// The action that leaves a failed sign-out.
  static const returnToTailTag = "Return to TailTag";

  /// The API-access failure text.
  static const apiAccess =
      "TailTag could not confirm your account. Try again, or sign out.";

  /// The sign-out action.
  static const signOut = "Sign out";

  /// The action that opens the passkey screen. Every signed-in entry screen
  /// that #482 adds uses it too.
  static const managePasskeys = "Manage passkeys";

  /// The disabled-profile text.
  static const accountUnavailable =
      "Your TailTag account is not available right now.";

  /// The action that reads the account status again.
  static const refresh = "Refresh";

  /// The neutral landing text. It is not a finished home.
  static const landing = "You are signed in.";

  /// The debug proof action.
  static const authProof = "Auth proof (debug)";
}

/// A full-screen wait with a visible label.
class EntryLoadingScreen extends StatelessWidget {
  /// Creates the screen with [label].
  const new({required this.label, this.onSignOut, super.key});

  /// What the app is waiting for.
  final String label;

  /// Signs out during the wait, or null when the wait has no exit.
  final VoidCallback? onSignOut;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: DelayedVisibility(
            child: Padding(
              padding: const EdgeInsets.all(TokenSpacing.xl),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                spacing: TokenSpacing.lg,
                children: [
                  const ExcludeSemantics(child: CircularProgressIndicator()),
                  Text(label, textAlign: TextAlign.center),
                  if (onSignOut != null)
                    TailTagButton(
                      key: const Key("entry-sign-out"),
                      label: EntryStrings.signOut,
                      variant: TailTagButtonVariant.secondary,
                      onPressed: onSignOut,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A full-screen message with up to two actions.
class _EntryMessageScreen extends StatelessWidget {
  const new({
    required this.message,
    this.tone = StatusTone.error,
    this.actions = const [],
  });

  final String message;
  final StatusTone tone;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text(EntryStrings.appName)),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(TokenSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: TokenSpacing.lg,
            children: [
              StatusBanner(tone: tone, message: message),
              ...actions,
            ],
          ),
        ),
      ),
    );
  }
}

/// The native SDK failed to start or lost its state stream.
class AuthRecoveryScreen extends ConsumerWidget {
  /// Creates the screen.
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stage = ref.watch(entryControllerProvider);
    if (stage is! EntryAuthRecovery) {
      return const EntryLoadingScreen(label: EntryStrings.restoring);
    }
    if (!stage.canRetry) {
      return const _EntryMessageScreen(
        message: EntryStrings.unsupported,
        tone: StatusTone.neutral,
      );
    }
    return _EntryMessageScreen(
      message: EntryStrings.recovery,
      actions: [
        TailTagButton(
          key: const Key("entry-reload"),
          label: UiStrings.tryAgain,
          onPressed: ref.read(entryControllerProvider.notifier).reloadSession,
        ),
      ],
    );
  }
}

/// Sign-out failed while the native session stayed active.
class SignOutFailedScreen extends ConsumerWidget {
  /// Creates the screen.
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(entryControllerProvider.notifier);
    return _EntryMessageScreen(
      message: EntryStrings.signOutFailed,
      actions: [
        TailTagButton(
          key: const Key("entry-retry-sign-out"),
          label: UiStrings.tryAgain,
          onPressed: controller.retrySignOut,
        ),
        TailTagButton(
          key: const Key("entry-return"),
          label: EntryStrings.returnToTailTag,
          variant: TailTagButtonVariant.secondary,
          onPressed: controller.returnAfterFailedSignOut,
        ),
      ],
    );
  }
}

/// The identity read failed.
class IdentityFailedScreen extends ConsumerWidget {
  /// Creates the screen.
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stage = ref.watch(entryControllerProvider);
    if (stage is! EntryIdentityFailed) {
      return const EntryLoadingScreen(label: EntryStrings.loadingAccount);
    }
    final controller = ref.read(entryControllerProvider.notifier);
    final failure = stage.failure;
    final message = failure == null
        ? EntryStrings.apiAccess
        : (genericErrorFor(failure) ?? GenericError.unknown).message;
    return _EntryMessageScreen(
      message: message,
      actions: [
        TailTagButton(
          key: const Key("entry-retry-identity"),
          label: UiStrings.tryAgain,
          onPressed: controller.retryIdentity,
        ),
        TailTagButton(
          key: const Key("entry-manage-passkeys"),
          label: EntryStrings.managePasskeys,
          variant: TailTagButtonVariant.secondary,
          onPressed: controller.openPasskeys,
        ),
        TailTagButton(
          key: const Key("entry-sign-out"),
          label: EntryStrings.signOut,
          variant: TailTagButtonVariant.secondary,
          onPressed: controller.signOut,
        ),
      ],
    );
  }
}

/// The server reports that the profile is disabled.
class AccountUnavailableScreen extends ConsumerWidget {
  /// Creates the screen.
  const new({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controller = ref.read(entryControllerProvider.notifier);
    return _EntryMessageScreen(
      message: EntryStrings.accountUnavailable,
      tone: StatusTone.warning,
      actions: [
        TailTagButton(
          key: const Key("entry-refresh"),
          label: EntryStrings.refresh,
          onPressed: controller.refreshProfile,
        ),
        TailTagButton(
          key: const Key("entry-manage-passkeys"),
          label: EntryStrings.managePasskeys,
          variant: TailTagButtonVariant.secondary,
          onPressed: controller.openPasskeys,
        ),
        TailTagButton(
          key: const Key("entry-sign-out"),
          label: EntryStrings.signOut,
          variant: TailTagButtonVariant.secondary,
          onPressed: controller.signOut,
        ),
      ],
    );
  }
}

/// The neutral landing after a completed profile loads.
///
/// It is not the milestone home. Conventions (#482) replace it.
class NeutralLandingScreen extends ConsumerWidget {
  /// Creates the screen. [onOpenAuthProof] opens the debug proof screen in
  /// debug builds.
  const new({required this.onOpenAuthProof, super.key});

  /// Opens the debug proof screen.
  final VoidCallback onOpenAuthProof;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text(EntryStrings.appName)),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(TokenSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: TokenSpacing.lg,
            children: [
              const Text(EntryStrings.landing, textAlign: TextAlign.center),
              TailTagButton(
                key: const Key("entry-manage-passkeys"),
                label: EntryStrings.managePasskeys,
                variant: TailTagButtonVariant.secondary,
                onPressed: ref
                    .read(entryControllerProvider.notifier)
                    .openPasskeys,
              ),
              TailTagButton(
                key: const Key("entry-sign-out"),
                label: EntryStrings.signOut,
                variant: TailTagButtonVariant.secondary,
                onPressed: ref.read(entryControllerProvider.notifier).signOut,
              ),
              if (kDebugMode)
                TailTagButton(
                  key: const Key("entry-auth-proof"),
                  label: EntryStrings.authProof,
                  variant: TailTagButtonVariant.secondary,
                  onPressed: onOpenAuthProof,
                ),
            ],
          ),
        ),
      ),
    );
  }
}
