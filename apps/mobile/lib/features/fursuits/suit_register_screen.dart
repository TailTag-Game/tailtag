import "dart:async";
import "dart:typed_data";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_providers.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";
import "package:tailtag_mobile/features/fursuits/photo_picker.dart";
import "package:tailtag_mobile/features/fursuits/register_controller.dart";

/// The form that registers a suit with a name and a required photo.
class SuitRegisterScreen extends ConsumerStatefulWidget {
  /// Creates the form.
  const new({
    required this.onCreated,
    required this.onOutcomeUnknown,
    super.key,
  });

  /// Called once with the saved suit.
  final ValueChanged<Fursuit> onCreated;

  /// Called when the app does not know whether the suit was saved, so the
  /// list reads again.
  final VoidCallback onOutcomeUnknown;

  @override
  ConsumerState<SuitRegisterScreen> createState() => _SuitRegisterScreenState();
}

class _SuitRegisterScreenState extends ConsumerState<SuitRegisterScreen> {
  final TextEditingController _name = TextEditingController();

  /// The picker message, such as a refused camera, or null.
  String? _pickMessage;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _pickPhoto() async {
    final outcome = await pickSuitPhoto(context, ref.read(photoSourceProvider));
    if (!mounted) {
      return;
    }
    switch (outcome) {
      case PhotoPickCancelled():
        return;
      case PhotoPickProblem(:final message):
        setState(() => _pickMessage = message);
      case PhotoPicked(:final photo):
        setState(() => _pickMessage = null);
        ref.read(registerControllerProvider.notifier).setPhoto(photo);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(registerControllerProvider);
    ref.listen(registerControllerProvider, (previous, next) {
      final created = next.created;
      if (created != null && previous?.created == null) {
        widget.onCreated(created);
      }
      if (next.banner == RegisterBanner.unknownOutcome &&
          previous?.banner != RegisterBanner.unknownOutcome) {
        widget.onOutcomeUnknown();
      }
    });
    final photo = state.photo;
    final photoMessage = state.photoError ?? _pickMessage;
    final textTheme = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text(FursuitStrings.registerSuit)),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(TokenSpacing.xl),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: TokenSpacing.lg,
            children: [
              ?_banner(state),
              TextField(
                key: const Key("register-name"),
                controller: _name,
                enabled: !state.saving,
                maxLength: 50,
                textInputAction: TextInputAction.done,
                decoration: InputDecoration(
                  labelText: FursuitStrings.nameLabel,
                  errorText: state.nameError,
                ),
              ),
              Text(FursuitStrings.photoLabel, style: textTheme.titleSmall),
              if (photo != null)
                Center(
                  child: ClipOval(
                    child: Image.memory(
                      Uint8List.fromList(photo.bytes),
                      key: const Key("register-photo-preview"),
                      width: TokenSize.avatarLarge,
                      height: TokenSize.avatarLarge,
                      fit: BoxFit.cover,
                      excludeFromSemantics: true,
                      errorBuilder: (context, error, stackTrace) =>
                          TailTagAvatar(
                            name: _name.text,
                            kind: AvatarKind.fursuit,
                            size: AvatarSize.large,
                          ),
                    ),
                  ),
                ),
              TailTagButton(
                key: const Key("register-photo"),
                label: photo == null
                    ? FursuitStrings.addPhoto
                    : FursuitStrings.changePhoto,
                variant: TailTagButtonVariant.secondary,
                onPressed: state.saving ? null : () => unawaited(_pickPhoto()),
              ),
              if (photoMessage != null)
                Text(
                  photoMessage,
                  key: const Key("register-photo-message"),
                  style: textTheme.bodySmall?.copyWith(color: scheme.error),
                ),
              ValueListenableBuilder(
                valueListenable: _name,
                builder: (context, value, _) => TailTagButton(
                  key: const Key("register-save"),
                  label: FursuitStrings.save,
                  loading: state.saving,
                  onPressed:
                      value.text.trim().isEmpty ||
                          photo == null ||
                          state.saving ||
                          state.created != null
                      ? null
                      : () => unawaited(
                          ref
                              .read(registerControllerProvider.notifier)
                              .save(_name.text),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static Widget? _banner(RegisterState state) {
    final banner = state.banner;
    if (banner == null) {
      return null;
    }
    final (tone, message) = switch (banner) {
      RegisterBanner.unknownOutcome => (
        StatusTone.warning,
        FursuitStrings.createUnknownOutcome,
      ),
      RegisterBanner.apiAccess => (StatusTone.error, FursuitStrings.apiAccess),
      RegisterBanner.notEligible => (
        StatusTone.error,
        FursuitStrings.notEligible,
      ),
      RegisterBanner.failed => (
        StatusTone.error,
        (switch (state.failure) {
                  null => null,
                  final failure => genericErrorFor(failure),
                } ??
                GenericError.unknown)
            .message,
      ),
    };
    return StatusBanner(
      key: const Key("register-banner"),
      tone: tone,
      message: message,
    );
  }
}
