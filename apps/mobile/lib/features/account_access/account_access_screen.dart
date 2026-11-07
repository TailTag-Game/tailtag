import "package:flutter/foundation.dart";
import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/auth/passkey.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";
import "package:tailtag_mobile/features/account_access/apple_button.dart";
import "package:tailtag_mobile/features/account_access/google_button.dart";

/// The signed-out entry screen: create an account or sign in.
///
/// The two email choices come first. An "or" divider then leads to the
/// provider section. On iOS, it holds "Continue with Apple" and then
/// "Continue with Google". Android has no Apple flow, so it shows only
/// Google. "Sign in with a passkey" ends the section when passkeys work on
/// this device. Otherwise a note says that they do not.
class AccountAccessScreen extends ConsumerWidget {
  /// Creates the screen. [onChoose] opens email entry after the choice.
  /// [onProviderCode] opens code entry when a provider attempt needs an
  /// email code.
  const new({required this.onChoose, required this.onProviderCode, super.key});

  /// Opens email entry.
  final VoidCallback onChoose;

  /// Opens code entry for a provider attempt.
  final VoidCallback onProviderCode;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(accessFlowProvider);
    // Unknown while it loads: the section then shows neither the button nor
    // the note.
    final passkeys = ref.watch(passkeyAvailabilityProvider).value;
    final notifier = ref.read(accessFlowProvider.notifier);

    void choose(AccessMode mode) {
      notifier.begin(mode);
      onChoose();
    }

    Future<void> continueWith(Future<bool> Function() call) async {
      if (await call()) {
        onProviderCode();
      }
    }

    final failedAction = flow.failedAction;
    final failure = flow.failure;
    final providerFailure =
        failedAction != null && failedAction.isProvider && failure != null
        ? AccountAccessStrings.providerFailureMessage(failedAction, failure)
        : null;

    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(TokenSpacing.xl),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: TokenSpacing.lg,
              children: [
                Semantics(
                  header: true,
                  child: Text(
                    AccountAccessStrings.welcomeTitle,
                    style: textTheme.headlineMedium,
                    textAlign: TextAlign.center,
                  ),
                ),
                Text(
                  AccountAccessStrings.welcomeBody,
                  style: textTheme.bodyLarge,
                  textAlign: TextAlign.center,
                ),
                if (providerFailure != null)
                  StatusBanner(
                    key: const Key("access-provider-failure"),
                    tone: StatusTone.error,
                    message: providerFailure,
                  ),
                const SizedBox(height: TokenSpacing.sm),
                TailTagButton(
                  key: const Key("access-create-account"),
                  label: AccountAccessStrings.createAccount,
                  onPressed: flow.isPending
                      ? null
                      : () => choose(AccessMode.createAccount),
                ),
                TailTagButton(
                  key: const Key("access-sign-in"),
                  label: AccountAccessStrings.signIn,
                  variant: TailTagButtonVariant.secondary,
                  onPressed: flow.isPending
                      ? null
                      : () => choose(AccessMode.signIn),
                ),
                const _OrDivider(),
                if (defaultTargetPlatform == TargetPlatform.iOS)
                  AppleButton(
                    key: const Key("access-apple"),
                    loading: flow.pending == AccessAction.apple,
                    onPressed: flow.isPending
                        ? null
                        : () => continueWith(notifier.continueWithApple),
                  ),
                GoogleButton(
                  key: const Key("access-google"),
                  label: AccountAccessStrings.continueWithGoogle,
                  loading: flow.pending == AccessAction.google,
                  onPressed: flow.isPending
                      ? null
                      : () => continueWith(notifier.continueWithGoogle),
                ),
                if (passkeys == PasskeyAvailability.available)
                  TailTagButton(
                    key: const Key("access-passkey"),
                    label: AccountAccessStrings.signInWithPasskey,
                    icon: Icons.key,
                    variant: TailTagButtonVariant.secondary,
                    loading: flow.pending == AccessAction.passkey,
                    onPressed: flow.isPending
                        ? null
                        : () => continueWith(notifier.continueWithPasskey),
                  )
                else if (passkeys == PasskeyAvailability.unavailable)
                  Text(
                    AccountAccessStrings.passkeysUnavailable,
                    key: const Key("access-passkeys-unavailable"),
                    style: textTheme.bodyMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                    textAlign: TextAlign.center,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A thin line with "or" between the email choices and the providers.
class _OrDivider extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      spacing: TokenSpacing.md,
      children: [
        const Expanded(child: Divider()),
        Text(
          AccountAccessStrings.or,
          style: theme.textTheme.bodyMedium?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        const Expanded(child: Divider()),
      ],
    );
  }
}
