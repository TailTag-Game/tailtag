import "dart:async";
import "dart:math" as math;

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";
import "package:tailtag_mobile/features/fursuits/suit_widgets.dart";
import "package:tailtag_mobile/features/fursuits/suits_controller.dart";
import "package:tailtag_mobile/features/fursuits/tag_badge.dart";
import "package:tailtag_mobile/features/fursuits/tag_controller.dart";

/// The tag of one suit: a large QR code to show a catcher, the tag image to
/// print, and replacement.
///
/// The tag read runs only here, because the first read creates the tag.
/// The suit name and the catch session state come from the suit list.
class TagScreen extends ConsumerStatefulWidget {
  /// Creates the screen for suit [fursuitId] at [convention].
  const new({required this.convention, required this.fursuitId, super.key});

  /// The selected convention.
  final Convention convention;

  /// The suit's server ID.
  final int fursuitId;

  @override
  ConsumerState<TagScreen> createState() => _TagScreenState();
}

class _TagScreenState extends ConsumerState<TagScreen> {
  final GlobalKey _badgeKey = GlobalKey();
  final GlobalKey _shareKey = GlobalKey();

  @override
  void initState() {
    super.initState();
    // A provider cannot change while a widget builds, so the read waits.
    scheduleMicrotask(() {
      if (mounted) {
        unawaited(_controller.read());
        if (ref.read(_suits).fursuits == null) {
          unawaited(ref.read(_suits.notifier).read());
        }
      }
    });
  }

  TagController get _controller =>
      ref.read(tagControllerProvider(widget.fursuitId).notifier);

  NotifierProvider<SuitsController, SuitsState> get _suits =>
      suitsControllerProvider(widget.convention.id);

  /// Pull to refresh reads the tag, and the suit list too when it is
  /// missing.
  Future<void> _refresh() async {
    await Future.wait([
      _controller.read(),
      if (ref.read(_suits).fursuits == null) ref.read(_suits.notifier).read(),
    ]);
  }

  void _snack(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _replace() async {
    final result = await showDialog<TagReplaceResult>(
      context: context,
      builder: (context) => _ReplaceDialog(onConfirm: _controller.replace),
    );
    if (result == TagReplaceResult.done && mounted) {
      _snack(FursuitStrings.tagReplaced);
    }
  }

  Future<void> _getNewTag() async {
    final result = await _controller.replace();
    if (result == TagReplaceResult.done && mounted) {
      _snack(FursuitStrings.newTagReady);
    }
  }

  Future<void> _share() async {
    final box = _shareKey.currentContext?.findRenderObject() as RenderBox?;
    final origin = box == null || !box.hasSize
        ? null
        : box.localToGlobal(Offset.zero) & box.size;
    await _controller.share(() => captureTagBadge(_badgeKey), origin: origin);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(tagControllerProvider(widget.fursuitId));
    final suits = ref.watch(_suits);
    final fursuit = suits.fursuit(widget.fursuitId);
    final tag = state.tag;
    final payload = tag?.payload;
    return Scaffold(
      appBar: AppBar(
        title: Text(
          fursuit?.name ?? FursuitStrings.tagSection,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: RefreshIndicator(
                onRefresh: _refresh,
                child: ListView(
                  key: const Key("tag-screen"),
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.symmetric(
                    horizontal: TokenSpacing.xl,
                    vertical: TokenSpacing.lg,
                  ),
                  children: [
                    if (_banner(state) case final banner?) ...[
                      banner,
                      const SizedBox(height: TokenSpacing.lg),
                    ],
                    ..._content(context, state, suits, fursuit),
                  ],
                ),
              ),
            ),
            // The badge paints off screen, ready for the tag image. It is
            // outside the scrollable, which would not paint it.
            if (fursuit != null && tag != null && payload != null)
              TagBadgeCapture(
                boundaryKey: _badgeKey,
                badge: TagBadge(
                  payload: payload,
                  name: fursuit.name,
                  version: tag.version,
                ),
              ),
          ],
        ),
      ),
    );
  }

  List<Widget> _content(
    BuildContext context,
    TagScreenState state,
    SuitsState suits,
    Fursuit? fursuit,
  ) {
    final tag = state.tag;
    if (fursuit == null) {
      if (suits.reading) {
        return const [SuitsLoading()];
      }
      if (suits.fursuits == null) {
        // The suit list read failed, so its banner offers the retry.
        final banner = suitsBanner(suits, ref.read(_suits.notifier).read);
        return [if (banner != null) banner else const SuitsLoading()];
      }
      return [
        Text(
          FursuitStrings.suitMissing,
          key: const Key("tag-suit-missing"),
          style: Theme.of(context).textTheme.bodyLarge,
        ),
      ];
    }
    return switch (tag) {
      null when state.reading => const [SuitsLoading()],
      null => const [],
      FursuitTag(state: TagState.revoked) => _revoked(context, state, fursuit),
      FursuitTag() => _current(context, state, fursuit, tag),
    };
  }

  List<Widget> _current(
    BuildContext context,
    TagScreenState state,
    Fursuit fursuit,
    FursuitTag tag,
  ) {
    final textTheme = Theme.of(context).textTheme;
    final catchable =
        ref.watch(_suits).activations[fursuit.id]?.isCatchable ?? false;
    final convention = widget.convention.name;
    final busy = state.replacing || state.sharing;
    return [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(TokenSpacing.lg),
          child: LayoutBuilder(
            builder: (context, box) => Semantics(
              key: const Key("tag-qr"),
              label: FursuitStrings.qrLabel(fursuit.name),
              image: true,
              // In landscape the whole code must still fit on screen.
              child: Center(
                child: TagQr(
                  payload: tag.payload!,
                  size: math.min(
                    box.maxWidth,
                    MediaQuery.sizeOf(context).height * 0.6,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
      const SizedBox(height: TokenSpacing.lg),
      Text(
        fursuit.name,
        key: const Key("tag-name"),
        textAlign: TextAlign.center,
        style: textTheme.titleLarge,
      ),
      Text(
        FursuitStrings.tagVersion(tag.version),
        key: const Key("tag-version"),
        textAlign: TextAlign.center,
        style: textTheme.bodyMedium,
      ),
      const SizedBox(height: TokenSpacing.lg),
      Text(
        FursuitStrings.tagExplain(fursuit.name),
        key: const Key("tag-explain"),
        style: textTheme.bodyLarge,
      ),
      const SizedBox(height: TokenSpacing.sm),
      Text(
        catchable
            ? FursuitStrings.outForCatchingAt(convention)
            : FursuitStrings.notOutForCatchingAt(convention),
        key: const Key("tag-status"),
        style: textTheme.bodyLarge,
      ),
      const SizedBox(height: TokenSpacing.xl),
      TailTagButton(
        key: _shareKey,
        label: FursuitStrings.shareTagImage,
        loading: state.sharing,
        onPressed: busy ? null : () => unawaited(_share()),
      ),
      const SizedBox(height: TokenSpacing.sm),
      Text(
        FursuitStrings.printActualSize,
        key: const Key("tag-print-size"),
        textAlign: TextAlign.center,
        style: textTheme.bodyMedium,
      ),
      const SizedBox(height: TokenSpacing.lg),
      TailTagButton(
        key: const Key("tag-replace"),
        label: FursuitStrings.replaceTag,
        variant: TailTagButtonVariant.secondary,
        onPressed: busy ? null : () => unawaited(_replace()),
      ),
    ];
  }

  List<Widget> _revoked(
    BuildContext context,
    TagScreenState state,
    Fursuit fursuit,
  ) {
    return [
      Text(
        FursuitStrings.tagRevoked(fursuit.name),
        key: const Key("tag-revoked"),
        style: Theme.of(context).textTheme.bodyLarge,
      ),
      const SizedBox(height: TokenSpacing.xl),
      TailTagButton(
        key: const Key("tag-get-new"),
        label: FursuitStrings.getNewTag,
        loading: state.replacing,
        onPressed: state.replacing ? null : () => unawaited(_getNewTag()),
      ),
    ];
  }

  Widget? _banner(TagScreenState state) {
    final banner = state.banner;
    if (banner == null) {
      return null;
    }
    String generic() =>
        (switch (state.failure) {
                  null => null,
                  final failure => genericErrorFor(failure),
                } ??
                GenericError.unknown)
            .message;
    final (tone, message, retry) = switch (banner) {
      TagBanner.unavailable => (
        StatusTone.warning,
        FursuitStrings.tagsUnavailable,
        true,
      ),
      TagBanner.suitDisabled => (
        StatusTone.error,
        FursuitStrings.suitDisabled,
        false,
      ),
      TagBanner.apiAccess => (StatusTone.error, FursuitStrings.apiAccess, true),
      TagBanner.readFailed => (StatusTone.error, generic(), true),
      TagBanner.changed => (
        StatusTone.warning,
        FursuitStrings.tagChanged,
        false,
      ),
      TagBanner.notReplaced => (
        StatusTone.warning,
        FursuitStrings.tagNotReplaced,
        false,
      ),
      TagBanner.conflict => (
        StatusTone.warning,
        FursuitStrings.tagConflict,
        false,
      ),
      TagBanner.checkFailed => (
        StatusTone.error,
        FursuitStrings.tagCheckFailed,
        true,
      ),
      TagBanner.replaceFailed => (StatusTone.error, generic(), false),
      TagBanner.shareFailed => (
        StatusTone.error,
        FursuitStrings.shareFailed,
        false,
      ),
    };
    return StatusBanner(
      key: const Key("tag-banner"),
      tone: tone,
      message: message,
      actionLabel: retry ? UiStrings.tryAgain : null,
      actionLoading: state.reading,
      onAction: retry ? () => unawaited(_controller.read()) : null,
    );
  }
}

/// The confirmation before a replacement. It stays open with a loading
/// confirm button until the server answers, then closes with the result.
class _ReplaceDialog extends StatefulWidget {
  const new({required this.onConfirm});

  final Future<TagReplaceResult> Function() onConfirm;

  @override
  State<_ReplaceDialog> createState() => _ReplaceDialogState();
}

class _ReplaceDialogState extends State<_ReplaceDialog> {
  bool _sending = false;

  Future<void> _confirm() async {
    setState(() => _sending = true);
    final result = await widget.onConfirm();
    if (mounted) {
      Navigator.of(context).pop(result);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_sending,
      child: AlertDialog(
        // At 200% text in landscape the warning must still scroll.
        scrollable: true,
        title: const Text(FursuitStrings.replaceTitle),
        content: const Text(FursuitStrings.replaceBody),
        actions: [
          TailTagButton(
            key: const Key("replace-cancel"),
            label: FursuitStrings.cancel,
            variant: TailTagButtonVariant.secondaryText,
            onPressed: _sending ? null : () => Navigator.of(context).pop(),
          ),
          TailTagButton(
            key: const Key("replace-confirm"),
            label: FursuitStrings.replaceTag,
            variant: TailTagButtonVariant.destructive,
            loading: _sending,
            onPressed: _sending ? null : () => unawaited(_confirm()),
          ),
        ],
      ),
    );
  }
}
