import "dart:async";

import "package:flutter/material.dart";
import "package:flutter/services.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";

/// The length of a Clerk email code.
const int emailCodeLength = 6;

/// Code entry for the current attempt.
///
/// An email attempt shows the address and a "Change email" action. A
/// provider attempt, such as Google, shows no address, and its "Back" action
/// ends the attempt and returns to the account choices. The code stays in
/// this screen's memory only and clears when the screen closes.
class CodeEntryScreen extends ConsumerStatefulWidget {
  /// Creates the screen. [onLeave] opens the previous screen.
  const new({required this.onLeave, super.key});

  /// Opens email entry after an email attempt, or the account choices after
  /// a provider attempt.
  final VoidCallback onLeave;

  @override
  ConsumerState<CodeEntryScreen> createState() => _CodeEntryScreenState();
}

class _CodeEntryScreenState extends ConsumerState<CodeEntryScreen> {
  final _code = TextEditingController();

  @override
  void initState() {
    super.initState();
    _code.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  void _leave() {
    _endFor(
      ref.read(accessFlowProvider),
      ref.read(accessFlowProvider.notifier),
    )();
    widget.onLeave();
  }

  /// The action that ends a provider attempt, or that keeps the email of an
  /// email attempt.
  static VoidCallback _endFor(
    AccessFlowState flow,
    AccessFlowController notifier,
  ) => flow.viaProvider ? notifier.reset : notifier.changeEmail;

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(accessFlowProvider);
    final notifier = ref.read(accessFlowProvider.notifier);
    final failure = flow.failure;
    final complete = _code.text.length == emailCodeLength;
    final leaveLabel = flow.viaProvider
        ? AccountAccessStrings.back
        : AccountAccessStrings.changeEmail;
    return PopScope(
      canPop: !flow.isPending,
      onPopInvokedWithResult: (didPop, _) {
        // A route change can pop this page while the tree builds, so the
        // flow changes after the frame.
        if (didPop) {
          scheduleMicrotask(_endFor(flow, notifier));
        }
      },
      child: Scaffold(
        appBar: AppBar(title: const Text(AccountAccessStrings.codeTitle)),
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(TokenSpacing.xl),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: TokenSpacing.lg,
              children: [
                Text(
                  flow.viaProvider
                      ? AccountAccessStrings.codeBodyProvider
                      : AccountAccessStrings.codeBody(flow.email),
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                if (failure != null)
                  StatusBanner(
                    key: const Key("access-failure"),
                    tone: StatusTone.error,
                    message: AccountAccessStrings.failureMessage(failure),
                    actionLabel: failure is AuthSessionEndedFailure
                        ? leaveLabel
                        : null,
                    onAction: _leave,
                  )
                else if (flow.codeResent)
                  const StatusBanner(
                    key: Key("access-code-resent"),
                    tone: StatusTone.neutral,
                    message: AccountAccessStrings.codeResent,
                  ),
                TextField(
                  key: const Key("access-code"),
                  controller: _code,
                  enabled: !flow.isPending,
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.done,
                  autocorrect: false,
                  enableSuggestions: false,
                  autofillHints: const [AutofillHints.oneTimeCode],
                  inputFormatters: [
                    FilteringTextInputFormatter.digitsOnly,
                    LengthLimitingTextInputFormatter(emailCodeLength),
                  ],
                  decoration: const InputDecoration(
                    labelText: AccountAccessStrings.codeLabel,
                  ),
                ),
                TailTagButton(
                  key: const Key("access-verify"),
                  label: AccountAccessStrings.verify,
                  loading: flow.pending == AccessAction.verify,
                  onPressed: flow.isPending || !complete
                      ? null
                      : () => notifier.verify(_code.text),
                ),
                TailTagButton(
                  key: const Key("access-resend"),
                  label: AccountAccessStrings.resend,
                  variant: TailTagButtonVariant.secondary,
                  loading: flow.pending == AccessAction.resend,
                  onPressed: flow.isPending ? null : notifier.resend,
                ),
                TailTagButton(
                  key: const Key("access-change-email"),
                  label: leaveLabel,
                  variant: TailTagButtonVariant.secondary,
                  onPressed: flow.isPending ? null : _leave,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
