import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/onboarding/onboarding_controller.dart";
import "package:tailtag_mobile/features/onboarding/onboarding_strings.dart";

/// The form that sets the handle and the display name.
class OnboardingScreen extends ConsumerStatefulWidget {
  /// Creates the screen.
  const new({
    required this.onResolved,
    required this.onManagePasskeys,
    required this.onSignOut,
    super.key,
  });

  /// Reports a server profile that decides the next stage.
  final void Function(PlayerScope scope, PlayerProfile profile) onResolved;

  /// Opens the passkey screen.
  final VoidCallback onManagePasskeys;

  /// Signs out.
  final VoidCallback onSignOut;

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _formKey = GlobalKey<FormState>();
  final _handle = TextEditingController();
  final _displayName = TextEditingController();
  AutovalidateMode _autovalidate = AutovalidateMode.disabled;

  @override
  void dispose() {
    _handle.dispose();
    _displayName.dispose();
    super.dispose();
  }

  void _submit() {
    setState(() => _autovalidate = AutovalidateMode.onUserInteraction);
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    unawaited(
      ref
          .read(onboardingControllerProvider.notifier)
          .submit(handle: _handle.text, displayName: _displayName.text),
    );
  }

  static String? _required(String? value, String message) =>
      (value ?? "").trim().isEmpty ? message : null;

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(onboardingControllerProvider);
    final controller = ref.read(onboardingControllerProvider.notifier);
    ref.listen(
      onboardingControllerProvider.select((state) => state.resolution),
      (previous, resolution) {
        if (resolution != null) {
          widget.onResolved(resolution.scope, resolution.profile);
        }
      },
    );
    final banner = state.banner;
    final idle = state.pending == null;
    return Scaffold(
      appBar: AppBar(title: const Text(OnboardingStrings.title)),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(TokenSpacing.xl),
          child: Form(
            key: _formKey,
            autovalidateMode: _autovalidate,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: TokenSpacing.lg,
              children: [
                if (banner != null)
                  StatusBanner(
                    key: const Key("onboarding-banner"),
                    tone: StatusTone.error,
                    message: OnboardingStrings.bannerText(banner),
                    actionLabel: state.writesLocked ? UiStrings.tryAgain : null,
                    actionLoading: state.pending == OnboardingPending.read,
                    onAction: state.writesLocked ? controller.retry : null,
                  ),
                TextFormField(
                  key: const Key("onboarding-handle"),
                  controller: _handle,
                  enabled: idle,
                  maxLength: 32,
                  autocorrect: false,
                  enableSuggestions: false,
                  autofillHints: const [AutofillHints.username],
                  textInputAction: TextInputAction.next,
                  forceErrorText: state.handleError,
                  decoration: const InputDecoration(
                    labelText: OnboardingStrings.handleLabel,
                    helperText: OnboardingStrings.handleHelper,
                    helperMaxLines: 3,
                    errorMaxLines: 3,
                  ),
                  validator: (value) =>
                      _required(value, OnboardingStrings.handleEmpty),
                  onChanged: (_) =>
                      controller.clearFieldError(OnboardingField.handle),
                ),
                TextFormField(
                  key: const Key("onboarding-display-name"),
                  controller: _displayName,
                  enabled: idle,
                  maxLength: 50,
                  textCapitalization: TextCapitalization.words,
                  textInputAction: TextInputAction.done,
                  forceErrorText: state.displayNameError,
                  decoration: const InputDecoration(
                    labelText: OnboardingStrings.displayNameLabel,
                    errorMaxLines: 3,
                  ),
                  validator: (value) =>
                      _required(value, OnboardingStrings.displayNameEmpty),
                  onChanged: (_) =>
                      controller.clearFieldError(OnboardingField.displayName),
                  onFieldSubmitted: (_) => _submit(),
                ),
                TailTagButton(
                  key: const Key("onboarding-continue"),
                  label: OnboardingStrings.submit,
                  loading: state.pending == OnboardingPending.save,
                  onPressed: state.canContinue ? _submit : null,
                ),
                TailTagButton(
                  key: const Key("entry-manage-passkeys"),
                  label: OnboardingStrings.managePasskeys,
                  variant: TailTagButtonVariant.secondary,
                  onPressed: state.canLeave ? widget.onManagePasskeys : null,
                ),
                TailTagButton(
                  key: const Key("entry-sign-out"),
                  label: OnboardingStrings.signOut,
                  variant: TailTagButtonVariant.secondary,
                  onPressed: widget.onSignOut,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
