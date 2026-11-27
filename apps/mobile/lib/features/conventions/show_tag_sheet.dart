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
import "package:tailtag_mobile/features/conventions/convention_strings.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";
import "package:tailtag_mobile/features/fursuits/suit_status.dart";
import "package:tailtag_mobile/features/fursuits/suit_widgets.dart";
import "package:tailtag_mobile/features/fursuits/suits_controller.dart";

/// Opens the modal bottom sheet that lets the player pick a suit and view
/// its TailTag from Home.
///
/// The sheet reads only the suit list and activations on demand. It never
/// reads a tag endpoint, so it never triggers lazy tag creation.
Future<void> showMyTailTagSheet(
  BuildContext context, {
  required Convention convention,
  required ValueChanged<int> onOpenTag,
  required VoidCallback onRegister,
}) {
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    useSafeArea: true,
    isScrollControlled: true,
    builder: (sheetContext) => _ShowTagSheet(
      convention: convention,
      onOpenTag: (id) {
        Navigator.of(sheetContext).pop();
        onOpenTag(id);
      },
      onRegister: () {
        Navigator.of(sheetContext).pop();
        onRegister();
      },
    ),
  );
}

class _ShowTagSheet extends ConsumerStatefulWidget {
  const new({
    required this.convention,
    required this.onOpenTag,
    required this.onRegister,
  });

  final Convention convention;
  final ValueChanged<int> onOpenTag;
  final VoidCallback onRegister;

  @override
  ConsumerState<_ShowTagSheet> createState() => _ShowTagSheetState();
}

class _ShowTagSheetState extends ConsumerState<_ShowTagSheet> {
  @override
  void initState() {
    super.initState();
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
    final textTheme = Theme.of(context).textTheme;
    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * 0.75,
        ),
        child: SingleChildScrollView(
          key: const Key("show-tag-sheet"),
          padding: const EdgeInsets.fromLTRB(
            TokenSpacing.lg,
            0,
            TokenSpacing.lg,
            TokenSpacing.xl,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: TokenSpacing.md,
            children: [
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: TokenSpacing.sm,
                ),
                child: Semantics(
                  header: true,
                  child: Text(
                    ConventionStrings.showMyTag,
                    style: textTheme.titleLarge,
                  ),
                ),
              ),
              ?suitsBanner(state, controller.read),
              if (fursuits == null && state.reading)
                const SuitsLoading()
              else if (fursuits != null && fursuits.isEmpty)
                EmptyState(
                  key: const Key("show-tag-empty"),
                  icon: Icons.pets_outlined,
                  title: FursuitStrings.emptyTitle,
                  body: FursuitStrings.emptyBody,
                  action: TailTagButton(
                    key: const Key("show-tag-register"),
                    label: FursuitStrings.registerSuit,
                    onPressed: widget.onRegister,
                  ),
                )
              else if (fursuits != null)
                for (final fursuit in fursuits)
                  _ShowTagSuitRow(
                    fursuit: fursuit,
                    badge: badgeFor(state.activations[fursuit.id]),
                    onTap: fursuit.isEnabled
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

class _ShowTagSuitRow extends StatelessWidget {
  const new({required this.fursuit, required this.badge, required this.onTap});

  final Fursuit fursuit;
  final SuitBadge badge;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final statusBadge = suitBadge(badge);
    final disabledNote = fursuit.isEnabled
        ? null
        : const Text(FursuitStrings.suitDisabled);
    return MergeSemantics(
      child: ListTile(
        key: Key("show-tag-suit-${fursuit.id}"),
        enabled: fursuit.isEnabled,
        leading: TailTagAvatar(
          name: fursuit.name,
          kind: AvatarKind.fursuit,
          imageUrl: fursuit.photoUrl.toString(),
        ),
        title: Text(fursuit.name, maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: StatusBadge.rowSubtitle(
          context,
          statusBadge,
          subtitle: disabledNote,
        ),
        trailing: StatusBadge.rowTrailing(context, statusBadge),
        onTap: onTap,
      ),
    );
  }
}
