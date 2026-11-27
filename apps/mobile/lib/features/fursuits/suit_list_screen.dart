import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/empty_state.dart";
import "package:tailtag_mobile/core/ui/widgets/status_badge.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";
import "package:tailtag_mobile/features/fursuits/suit_status.dart";
import "package:tailtag_mobile/features/fursuits/suit_widgets.dart";
import "package:tailtag_mobile/features/fursuits/suits_controller.dart";

/// The player's suits, each with its badge and direct TailTag shortcut at the
/// selected convention.
class SuitListScreen extends ConsumerStatefulWidget {
  /// Creates the screen for [convention].
  const new({
    required this.convention,
    required this.onOpenSuit,
    required this.onOpenTag,
    required this.onRegister,
    super.key,
  });

  /// The selected convention.
  final Convention convention;

  /// Opens the suit screen of a suit.
  final ValueChanged<int> onOpenSuit;

  /// Opens the TailTag screen of a suit directly.
  final ValueChanged<int> onOpenTag;

  /// Opens the register form.
  final VoidCallback onRegister;

  @override
  ConsumerState<SuitListScreen> createState() => _SuitListScreenState();
}

class _SuitListScreenState extends ConsumerState<SuitListScreen> {
  @override
  void initState() {
    super.initState();
    _readSoon();
  }

  @override
  void didUpdateWidget(SuitListScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.convention.id != widget.convention.id) {
      _readSoon();
    }
  }

  /// A provider cannot change while a widget builds, so the read waits.
  void _readSoon() {
    scheduleMicrotask(() {
      if (mounted) {
        unawaited(
          ref
              .read(suitsControllerProvider(widget.convention.id).notifier)
              .read(),
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = suitsControllerProvider(widget.convention.id);
    final state = ref.watch(provider);
    final controller = ref.read(provider.notifier);
    final fursuits = state.fursuits;
    final hasSuits = fursuits != null && fursuits.isNotEmpty;
    return Scaffold(
      appBar: AppBar(
        title: const Text(FursuitStrings.mySuits),
        actions: [
          if (hasSuits)
            IconButton(
              key: const Key("suits-register"),
              icon: const Icon(Icons.add),
              tooltip: FursuitStrings.registerSuit,
              onPressed: widget.onRegister,
            ),
        ],
      ),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: controller.read,
          child: ListView(
            key: const Key("suit-list"),
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.symmetric(vertical: TokenSpacing.lg),
            children: [
              if (suitsBanner(state, controller.read) case final banner?)
                Padding(
                  padding: const EdgeInsets.fromLTRB(
                    TokenSpacing.xl,
                    0,
                    TokenSpacing.xl,
                    TokenSpacing.lg,
                  ),
                  child: banner,
                ),
              if (fursuits == null && state.reading)
                const SuitsLoading()
              else if (fursuits != null && fursuits.isEmpty)
                Padding(
                  padding: const EdgeInsets.all(TokenSpacing.xl),
                  child: EmptyState(
                    key: const Key("suits-empty"),
                    icon: Icons.pets_outlined,
                    title: FursuitStrings.emptyTitle,
                    body: FursuitStrings.emptyBody,
                    action: TailTagButton(
                      key: const Key("suits-register"),
                      label: FursuitStrings.registerSuit,
                      onPressed: widget.onRegister,
                    ),
                  ),
                )
              else if (fursuits != null)
                for (final fursuit in fursuits)
                  _SuitCard(
                    fursuit: fursuit,
                    badge: badgeFor(state.activations[fursuit.id]),
                    onTap: () => widget.onOpenSuit(fursuit.id),
                    onOpenTag: fursuit.isEnabled
                        ? () => widget.onOpenTag(fursuit.id)
                        : null,
                  ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SuitCard extends StatelessWidget {
  const new({
    required this.fursuit,
    required this.badge,
    required this.onTap,
    required this.onOpenTag,
  });

  final Fursuit fursuit;
  final SuitBadge badge;
  final VoidCallback onTap;
  final VoidCallback? onOpenTag;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final statusBadge = suitBadge(badge);
    final largeText =
        MediaQuery.textScalerOf(context).scale(1) >
        StatusBadge.maxBesideTitleTextScale;
    final qrButton = onOpenTag == null
        ? null
        : IconButton(
            key: Key("suit-qr-${fursuit.id}"),
            icon: const Icon(Icons.qr_code_2),
            tooltip: FursuitStrings.showTag,
            onPressed: onOpenTag,
          );
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: TokenSpacing.xl,
        vertical: TokenSpacing.xs,
      ),
      child: Card(
        margin: EdgeInsets.zero,
        child: InkWell(
          key: Key("suit-row-${fursuit.id}"),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(TokenSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              spacing: TokenSpacing.sm,
              children: [
                Row(
                  children: [
                    TailTagAvatar(
                      name: fursuit.name,
                      kind: AvatarKind.fursuit,
                      imageUrl: fursuit.photoUrl.toString(),
                    ),
                    const SizedBox(width: TokenSpacing.md),
                    Expanded(
                      child: MergeSemantics(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          spacing: TokenSpacing.xs,
                          children: [
                            Text(
                              fursuit.name,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: textTheme.titleMedium,
                            ),
                            statusBadge,
                          ],
                        ),
                      ),
                    ),
                    if (!largeText && qrButton != null) qrButton,
                  ],
                ),
                if (largeText && qrButton != null)
                  Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: qrButton,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
