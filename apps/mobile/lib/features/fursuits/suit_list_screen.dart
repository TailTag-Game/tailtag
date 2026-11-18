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
import "package:tailtag_mobile/features/reviews/review_entries.dart";

/// The player's suits, each with its badge at the selected convention.
class SuitListScreen extends ConsumerStatefulWidget {
  /// Creates the screen for [convention].
  const new({
    required this.convention,
    required this.onOpenSuit,
    required this.onRegister,
    required this.onOpenReview,
    super.key,
  });

  /// The selected convention.
  final Convention convention;

  /// Opens the suit screen of a suit.
  final ValueChanged<int> onOpenSuit;

  /// Opens the register form.
  final VoidCallback onRegister;

  /// Opens the review screen of every suit (#512 AC4).
  final VoidCallback onOpenReview;

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
    return Scaffold(
      appBar: AppBar(title: const Text(FursuitStrings.mySuits)),
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
              else if (fursuits != null) ...[
                ReviewEntry.suitList(onOpen: widget.onOpenReview),
                for (final fursuit in fursuits)
                  _SuitRow(
                    fursuit: fursuit,
                    badge: badgeFor(state.activations[fursuit.id]),
                    onTap: () => widget.onOpenSuit(fursuit.id),
                  ),
                Padding(
                  padding: const EdgeInsets.all(TokenSpacing.xl),
                  child: TailTagButton(
                    key: const Key("suits-register"),
                    label: FursuitStrings.registerSuit,
                    variant: TailTagButtonVariant.secondary,
                    onPressed: widget.onRegister,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _SuitRow extends StatelessWidget {
  const new({required this.fursuit, required this.badge, required this.onTap});

  final Fursuit fursuit;
  final SuitBadge badge;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final statusBadge = suitBadge(badge);
    // One semantics node joins the name and the badge text.
    return MergeSemantics(
      child: ListTile(
        key: Key("suit-row-${fursuit.id}"),
        contentPadding: const EdgeInsets.symmetric(horizontal: TokenSpacing.xl),
        leading: TailTagAvatar(
          name: fursuit.name,
          kind: AvatarKind.fursuit,
          imageUrl: fursuit.photoUrl.toString(),
        ),
        title: Text(fursuit.name, maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: StatusBadge.rowSubtitle(context, statusBadge),
        trailing: StatusBadge.rowTrailing(context, statusBadge),
        onTap: onTap,
      ),
    );
  }
}
