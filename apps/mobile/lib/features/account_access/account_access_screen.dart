import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";

/// The signed-out entry screen: create an account or sign in.
class AccountAccessScreen extends ConsumerWidget {
  /// Creates the screen. [onChoose] opens email entry after the choice.
  const new({required this.onChoose, super.key});

  /// Opens email entry.
  final VoidCallback onChoose;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    void choose(AccessMode mode) {
      ref.read(accessFlowProvider.notifier).begin(mode);
      onChoose();
    }

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
                const SizedBox(height: TokenSpacing.sm),
                TailTagButton(
                  key: const Key("access-create-account"),
                  label: AccountAccessStrings.createAccount,
                  onPressed: () => choose(AccessMode.createAccount),
                ),
                TailTagButton(
                  key: const Key("access-sign-in"),
                  label: AccountAccessStrings.signIn,
                  variant: TailTagButtonVariant.secondary,
                  onPressed: () => choose(AccessMode.signIn),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
