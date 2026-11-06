import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";
import "package:tailtag_mobile/features/account_access/email_address.dart";

/// Email entry for sign-in or account creation.
class EmailEntryScreen extends ConsumerStatefulWidget {
  /// Creates the screen. [onCodeSent] opens code entry.
  const new({required this.onCodeSent, super.key});

  /// Opens code entry after Clerk sent a code.
  final VoidCallback onCodeSent;

  @override
  ConsumerState<EmailEntryScreen> createState() => _EmailEntryScreenState();
}

class _EmailEntryScreenState extends ConsumerState<EmailEntryScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _email = TextEditingController(
    text: ref.read(accessFlowProvider).email,
  );

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    final sent = await ref
        .read(accessFlowProvider.notifier)
        .sendCode(_email.text);
    if (sent && mounted) {
      widget.onCodeSent();
    }
  }

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(accessFlowProvider);
    final notifier = ref.read(accessFlowProvider.notifier);
    final failure = flow.failure;
    final title = switch (flow.mode) {
      AccessMode.signIn => AccountAccessStrings.signIn,
      AccessMode.createAccount => AccountAccessStrings.createAccount,
    };
    return PopScope(
      canPop: !flow.isPending,
      onPopInvokedWithResult: (didPop, _) {
        // A route change can pop this page while the tree builds, so the
        // flow changes after the frame.
        if (didPop) {
          scheduleMicrotask(notifier.reset);
        }
      },
      child: Scaffold(
        appBar: AppBar(title: Text(title)),
        body: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(TokenSpacing.xl),
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                spacing: TokenSpacing.lg,
                children: [
                  if (failure != null)
                    StatusBanner(
                      key: const Key("access-failure"),
                      tone: StatusTone.error,
                      message: AccountAccessStrings.failureMessage(failure),
                      actionLabel: switch (failure) {
                        AuthAccountExistsFailure() =>
                          AccountAccessStrings.signInInstead,
                        AuthAccountNotFoundFailure() =>
                          AccountAccessStrings.createInstead,
                        _ => null,
                      },
                      onAction: notifier.switchMode,
                    ),
                  TextFormField(
                    key: const Key("access-email"),
                    controller: _email,
                    enabled: !flow.isPending,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.done,
                    autocorrect: false,
                    enableSuggestions: false,
                    autofillHints: const [AutofillHints.email],
                    decoration: const InputDecoration(
                      labelText: AccountAccessStrings.emailLabel,
                      helperText: AccountAccessStrings.emailHelper,
                      helperMaxLines: 3,
                      errorMaxLines: 3,
                    ),
                    validator: (value) =>
                        isPlausibleEmailAddress((value ?? "").trim())
                        ? null
                        : AccountAccessStrings.emailInvalid,
                    onFieldSubmitted: (_) => _send(),
                  ),
                  TailTagButton(
                    key: const Key("access-send-code"),
                    label: AccountAccessStrings.sendCode,
                    loading: flow.pending == AccessAction.send,
                    onPressed: flow.isPending ? null : _send,
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
