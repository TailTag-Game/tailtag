import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/passkey.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/passkeys/passkey_controller.dart";
import "package:tailtag_mobile/features/passkeys/passkey_strings.dart";

/// The signed-in passkey screen: list, add, and remove passkeys.
///
/// It needs no profile and no convention, and it shows no product content.
/// Close and system Back call [onClose], except while a change and the read
/// after it run.
class PasskeyScreen extends ConsumerWidget {
  /// Creates the screen.
  const new({required this.onClose, required this.onSignOut, super.key});

  /// Leaves the screen. The app then derives the entry stage again.
  final VoidCallback onClose;

  /// Signs out, for the fresh sign-in that reverification needs.
  final VoidCallback onSignOut;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(passkeyControllerProvider);
    final controller = ref.read(passkeyControllerProvider.notifier);
    final textTheme = Theme.of(context).textTheme;
    final passkeys = state.passkeys;
    final changeFailure = state.changeFailure;
    final readFailure = state.readFailure;
    // A confirmed change shows a snackbar. Only an unknown outcome stays
    // on screen as a banner.
    ref.listen(passkeyControllerProvider.select((state) => state.notice), (
      previous,
      notice,
    ) {
      final text = switch (notice) {
        PasskeyNotice.added => PasskeyStrings.added,
        PasskeyNotice.removed => PasskeyStrings.removed,
        PasskeyNotice.unconfirmed || null => null,
      };
      if (text != null) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(text)));
      }
    });

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop && state.canClose) {
          onClose();
        }
      },
      child: Scaffold(
        appBar: AppBar(
          leading: IconButton(
            key: const Key("passkeys-close"),
            icon: const Icon(Icons.close),
            tooltip: PasskeyStrings.close,
            onPressed: state.canClose ? onClose : null,
          ),
          title: const Text(PasskeyStrings.title),
        ),
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(TokenSpacing.xl),
            children: [
              Text(PasskeyStrings.intro, style: textTheme.bodyLarge),
              const SizedBox(height: TokenSpacing.lg),
              if (state.availability == PasskeyAvailability.unavailable) ...[
                const StatusBanner(
                  key: Key("passkeys-unavailable"),
                  tone: StatusTone.neutral,
                  message: PasskeyStrings.unavailable,
                ),
                const SizedBox(height: TokenSpacing.lg),
              ],
              if (state.notice == PasskeyNotice.unconfirmed) ...[
                const StatusBanner(
                  key: Key("passkeys-notice"),
                  tone: StatusTone.warning,
                  message: PasskeyStrings.unconfirmed,
                ),
                const SizedBox(height: TokenSpacing.lg),
              ],
              if (changeFailure != null) ...[
                StatusBanner(
                  key: const Key("passkeys-change-failure"),
                  tone: StatusTone.error,
                  message: PasskeyStrings.changeFailure(changeFailure),
                ),
                if (changeFailure is AuthReverificationRequiredFailure) ...[
                  const SizedBox(height: TokenSpacing.md),
                  TailTagButton(
                    key: const Key("passkeys-sign-out"),
                    label: PasskeyStrings.signOutAndIn,
                    variant: TailTagButtonVariant.secondary,
                    onPressed: onSignOut,
                  ),
                ],
                const SizedBox(height: TokenSpacing.lg),
              ],
              if (readFailure != null) ...[
                StatusBanner(
                  key: const Key("passkeys-read-failure"),
                  tone: StatusTone.error,
                  message: readFailure is AuthConnectivityFailure
                      ? UiStrings.noConnection
                      : PasskeyStrings.readFailed,
                ),
                const SizedBox(height: TokenSpacing.md),
                TailTagButton(
                  key: const Key("passkeys-retry"),
                  label: UiStrings.tryAgain,
                  variant: TailTagButtonVariant.secondary,
                  loading: state.reading,
                  onPressed: state.reading ? null : controller.retryRead,
                ),
                const SizedBox(height: TokenSpacing.lg),
              ],
              if (state.canAdd) ...[
                TailTagButton(
                  key: const Key("passkeys-add"),
                  label: PasskeyStrings.add,
                  icon: Icons.add,
                  loading: state.change == PasskeyChange.add,
                  onPressed: state.canChange ? controller.add : null,
                ),
                const SizedBox(height: TokenSpacing.lg),
              ],
              if (passkeys == null && state.reading)
                const Center(
                  child: Padding(
                    padding: EdgeInsets.all(TokenSpacing.lg),
                    child: CircularProgressIndicator(
                      semanticsLabel: UiStrings.loading,
                    ),
                  ),
                )
              else if (passkeys != null && passkeys.isEmpty)
                Text(
                  PasskeyStrings.empty,
                  key: const Key("passkeys-empty"),
                  style: textTheme.bodyMedium,
                )
              else if (passkeys != null) ...[
                Semantics(
                  header: true,
                  child: Text(
                    PasskeyStrings.listHeading,
                    style: textTheme.titleMedium,
                  ),
                ),
                for (final passkey in passkeys)
                  _PasskeyRow(
                    passkey: passkey,
                    onRemove: state.canChange
                        ? () => unawaited(_confirmRemove(context, ref, passkey))
                        : null,
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  /// Asks before a removal. Cancelling sends nothing.
  Future<void> _confirmRemove(
    BuildContext context,
    WidgetRef ref,
    PasskeyInfo passkey,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(PasskeyStrings.removeTitle(passkey.name)),
        content: const Text(PasskeyStrings.removeBody),
        actions: [
          TextButton(
            key: const Key("passkeys-remove-cancel"),
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text(PasskeyStrings.cancel),
          ),
          TextButton(
            key: const Key("passkeys-remove-confirm"),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text(PasskeyStrings.removeConfirm),
          ),
        ],
      ),
    );
    if ((confirmed ?? false) && context.mounted) {
      await ref.read(passkeyControllerProvider.notifier).remove(passkey);
    }
  }
}

/// One passkey: its Clerk name, when it was added, and when it was last
/// used. Dates use the device locale.
class _PasskeyRow extends StatelessWidget {
  const new({required this.passkey, required this.onRemove});

  final PasskeyInfo passkey;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final localizations = MaterialLocalizations.of(context);
    final lastUsedAt = passkey.lastUsedAt;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const Icon(Icons.key),
      title: Text(passkey.name),
      subtitle: Text(
        PasskeyStrings.rowDetail(
          localizations.formatShortDate(passkey.createdAt),
          lastUsedAt == null ? null : localizations.formatShortDate(lastUsedAt),
        ),
      ),
      trailing: IconButton(
        icon: const Icon(Icons.delete_outline),
        tooltip: PasskeyStrings.removeLabel(passkey.name),
        onPressed: onRemove,
      ),
    );
  }
}
