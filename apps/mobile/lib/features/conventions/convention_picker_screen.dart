import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/empty_state.dart";
import "package:tailtag_mobile/core/ui/widgets/status_badge.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/conventions/convention_picker_controller.dart";
import "package:tailtag_mobile/features/conventions/convention_strings.dart";

/// The screen where the player joins or selects a convention.
class ConventionPickerScreen extends ConsumerStatefulWidget {
  /// Creates the screen.
  const new({
    required this.onEntered,
    required this.onIneligible,
    required this.onClose,
    required this.onManagePasskeys,
    required this.onSignOut,
    required this.onOpenAuthProof,
    super.key,
  });

  /// Reports the enrollment that the server selected.
  final void Function(PlayerScope scope, ConventionEnrollment enrollment)
  onEntered;

  /// Reports a fresh profile that is no longer eligible.
  final void Function(PlayerScope scope, PlayerProfile profile) onIneligible;

  /// Returns to the home, or null when the player has no selection.
  final void Function({required bool writesLocked})? onClose;

  /// Opens the passkey screen.
  final VoidCallback onManagePasskeys;

  /// Signs out.
  final VoidCallback onSignOut;

  /// Opens the debug proof screen, or null outside debug builds.
  final VoidCallback? onOpenAuthProof;

  @override
  ConsumerState<ConventionPickerScreen> createState() =>
      _ConventionPickerScreenState();
}

class _ConventionPickerScreenState
    extends ConsumerState<ConventionPickerScreen> {
  @override
  void initState() {
    super.initState();
    // A provider cannot change while a widget builds, so the read waits.
    scheduleMicrotask(() {
      if (mounted) {
        unawaited(ref.read(conventionPickerControllerProvider.notifier).open());
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(conventionPickerControllerProvider);
    final controller = ref.read(conventionPickerControllerProvider.notifier);
    ref.listen(
      conventionPickerControllerProvider.select((state) => state.resolution),
      (previous, resolution) {
        switch (resolution) {
          case PickerEntered(:final scope, :final enrollment):
            widget.onEntered(scope, enrollment);
          case PickerIneligible(:final scope, :final profile):
            widget.onIneligible(scope, profile);
          case null:
            break;
        }
      },
    );
    final close = widget.onClose;
    void leave() => close?.call(writesLocked: state.writesLocked);
    final rows = state.rows;
    return PopScope(
      canPop: close == null && state.canLeave,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop && state.canLeave) {
          leave();
        }
      },
      child: Scaffold(
        appBar: AppBar(
          leading: close == null
              ? null
              : IconButton(
                  key: const Key("conventions-close"),
                  icon: const Icon(Icons.close),
                  tooltip: ConventionStrings.close,
                  onPressed: state.canLeave ? leave : null,
                ),
          automaticallyImplyLeading: false,
          title: const Text(ConventionStrings.pickerTitle),
        ),
        body: SafeArea(
          child: RefreshIndicator(
            onRefresh: controller.pullToRefresh,
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(TokenSpacing.xl),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                spacing: TokenSpacing.lg,
                children: [
                  ?_banner(state, controller),
                  if (rows == null && state.reading)
                    const _PickerLoading()
                  else if (rows != null && rows.isEmpty)
                    EmptyState(
                      key: const Key("conventions-empty"),
                      icon: Icons.event_busy_outlined,
                      title: ConventionStrings.emptyTitle,
                      body: ConventionStrings.emptyBody,
                      action: TailTagButton(
                        key: const Key("conventions-refresh"),
                        label: ConventionStrings.refresh,
                        variant: TailTagButtonVariant.secondary,
                        loading: state.reading,
                        onPressed: controller.tryAgain,
                      ),
                    )
                  else if (rows != null)
                    for (final row in rows)
                      _ConventionCard(
                        key: Key("convention-card-${row.convention.id}"),
                        row: row,
                        writing: state.writingId == row.convention.id,
                        onEnter: state.canWrite
                            ? () => unawaited(controller.enter(row))
                            : null,
                      ),
                  TailTagButton(
                    key: const Key("entry-manage-passkeys"),
                    label: ConventionStrings.managePasskeys,
                    variant: TailTagButtonVariant.secondary,
                    onPressed: state.canLeave ? widget.onManagePasskeys : null,
                  ),
                  TailTagButton(
                    key: const Key("entry-sign-out"),
                    label: ConventionStrings.signOut,
                    variant: TailTagButtonVariant.secondary,
                    onPressed: widget.onSignOut,
                  ),
                  if (widget.onOpenAuthProof != null)
                    TailTagButton(
                      key: const Key("entry-auth-proof"),
                      label: ConventionStrings.authProof,
                      variant: TailTagButtonVariant.secondary,
                      onPressed: widget.onOpenAuthProof,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// One banner at a time. A read failure replaces any other banner.
  static Widget? _banner(
    ConventionPickerState state,
    ConventionPickerController controller,
  ) {
    final failure = state.readFailure;
    if (failure != null) {
      return StatusBanner(
        key: const Key("conventions-banner"),
        tone: StatusTone.error,
        message: (genericErrorFor(failure) ?? GenericError.unknown).message,
        actionLabel: UiStrings.tryAgain,
        actionLoading: state.reading,
        onAction: controller.tryAgain,
      );
    }
    final banner = state.banner;
    if (banner == null) {
      return null;
    }
    return StatusBanner(
      key: const Key("conventions-banner"),
      tone: ConventionStrings.bannerTone(banner),
      message: ConventionStrings.bannerText(banner),
      actionLabel: state.writesLocked ? UiStrings.tryAgain : null,
      actionLoading: state.recovering || state.reading,
      onAction: state.writesLocked ? controller.tryAgain : null,
    );
  }
}

class _PickerLoading extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return const DelayedVisibility(
      child: Column(
        spacing: TokenSpacing.lg,
        children: [
          ExcludeSemantics(child: CircularProgressIndicator()),
          Text(ConventionStrings.loading, textAlign: TextAlign.center),
        ],
      ),
    );
  }
}

class _ConventionCard extends StatelessWidget {
  const new({
    required this.row,
    required this.writing,
    required this.onEnter,
    super.key,
  });

  final ConventionRow row;
  final bool writing;
  final VoidCallback? onEnter;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final convention = row.convention;
    final id = convention.id;
    final badge = switch (row.kind) {
      ConventionRowKind.fresh => null,
      ConventionRowKind.joined => const StatusBadge(
        tone: StatusTone.neutral,
        label: ConventionStrings.joined,
      ),
      ConventionRowKind.selected => const StatusBadge(
        tone: StatusTone.success,
        label: ConventionStrings.selected,
      ),
    };
    final action = switch (row.kind) {
      ConventionRowKind.fresh => ConventionStrings.joinAndEnter,
      ConventionRowKind.joined => ConventionStrings.enterConvention,
      ConventionRowKind.selected => null,
    };
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(TokenSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: TokenSpacing.md,
          children: [
            Text(
              convention.name,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: textTheme.titleLarge,
            ),
            Text(
              ConventionStrings.dates(context, convention),
              style: textTheme.bodyMedium,
            ),
            if (badge != null)
              Align(alignment: AlignmentDirectional.centerStart, child: badge),
            if (action != null)
              TailTagButton(
                key: Key("convention-action-$id"),
                label: action,
                loading: writing,
                onPressed: onEnter,
              ),
          ],
        ),
      ),
    );
  }
}
