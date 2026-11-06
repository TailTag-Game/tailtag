import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";
import "package:tailtag_mobile/features/account_access/google_button.dart";

/// The signed-out entry screen: create an account or sign in.
///
/// The two email choices come first. An "or" divider then leads to the
/// provider section, which holds "Continue with Google". Apple (#479) and
/// passkeys (#480) join that section.
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
    final notifier = ref.read(accessFlowProvider.notifier);

    void choose(AccessMode mode) {
      notifier.begin(mode);
      onChoose();
    }

    Future<void> continueWithGoogle() async {
      if (await notifier.continueWithGoogle()) {
        onProviderCode();
      }
    }

    final providerFailure = flow.failedAction == AccessAction.google
        ? flow.failure
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
                    message: AccountAccessStrings.failureMessage(
                      providerFailure,
                    ),
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
                GoogleButton(
                  key: const Key("access-google"),
                  label: AccountAccessStrings.continueWithGoogle,
                  loading: flow.pending == AccessAction.google,
                  onPressed: flow.isPending ? null : continueWithGoogle,
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
