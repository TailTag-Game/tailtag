import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/empty_state.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/features/catches/catch_strings.dart";
import "package:tailtag_mobile/features/catches/catches_controller.dart";

/// The private collection (F9): completed catches with convention filter
/// chips. The next page loads at the end of the list (#511 AC28, AC29).
class CatchesScreen extends ConsumerStatefulWidget {
  /// Creates the collection for the selected [convention].
  const new({required this.convention, super.key});

  /// The selected convention of the home, the default filter.
  final Convention convention;

  @override
  ConsumerState<CatchesScreen> createState() => _CatchesScreenState();
}

class _CatchesScreenState extends ConsumerState<CatchesScreen> {
  @override
  void initState() {
    super.initState();
    _readSoon();
  }

  @override
  void didUpdateWidget(CatchesScreen oldWidget) {
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
              .read(catchesControllerProvider(widget.convention.id).notifier)
              .read(),
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final provider = catchesControllerProvider(widget.convention.id);
    final state = ref.watch(provider);
    final controller = ref.read(provider.notifier);
    final catches = state.catches;
    final failure = state.readFailure;
    return Scaffold(
      appBar: AppBar(title: const Text(CatchStrings.navCatches)),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: controller.read,
          child: ListView(
            key: const Key("catches-list"),
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.symmetric(vertical: TokenSpacing.lg),
            children: [
              _Chips(
                conventions: state.conventions,
                filter: state.filter,
                onSelect: (filter) => unawaited(controller.select(filter)),
              ),
              if (failure != null)
                Padding(
                  padding: const EdgeInsets.all(TokenSpacing.xl),
                  child: StatusBanner(
                    key: const Key("catches-banner"),
                    tone: StatusTone.error,
                    message: (genericErrorFor(failure) ?? GenericError.unknown)
                        .message,
                    actionLabel: UiStrings.tryAgain,
                    actionLoading: state.reading,
                    onAction: () => unawaited(controller.read()),
                  ),
                ),
              if (catches == null && state.reading)
                const _Loading()
              else if (catches != null && catches.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(TokenSpacing.xl),
                  child: EmptyState(
                    key: Key("catches-empty"),
                    icon: Icons.catching_pokemon_outlined,
                    title: CatchStrings.catchesEmpty,
                    body: CatchStrings.catchesEmptyBody,
                  ),
                )
              else if (catches != null) ...[
                for (final (index, caught) in catches.indexed)
                  _CatchRow(
                    caught: caught,
                    showConvention: state.filter == null,
                    // The last row asks for the next page once it builds.
                    // After a failure only "Try again" reads again, so a
                    // broken connection never starts a request loop.
                    onShown:
                        index == catches.length - 1 &&
                            state.hasNext &&
                            failure == null
                        ? () => unawaited(controller.loadMore())
                        : null,
                  ),
                if (state.loadingMore) const _Loading(),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return const DelayedVisibility(
      child: Padding(
        padding: EdgeInsets.all(TokenSpacing.xl),
        child: Center(
          child: CircularProgressIndicator(semanticsLabel: UiStrings.loading),
        ),
      ),
    );
  }
}

class _Chips extends StatelessWidget {
  const new({
    required this.conventions,
    required this.filter,
    required this.onSelect,
  });

  final List<Convention> conventions;
  final int? filter;
  final ValueChanged<int?> onSelect;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        TokenSpacing.xl,
        0,
        TokenSpacing.xl,
        TokenSpacing.md,
      ),
      child: Wrap(
        spacing: TokenSpacing.sm,
        runSpacing: TokenSpacing.sm,
        children: [
          FilterChip(
            key: const Key("catches-chip-all"),
            label: const Text(CatchStrings.allConventions),
            selected: filter == null,
            onSelected: (_) => onSelect(null),
          ),
          for (final convention in conventions)
            FilterChip(
              key: Key("catches-chip-${convention.id}"),
              label: Text(convention.name),
              selected: filter == convention.id,
              onSelected: (_) => onSelect(convention.id),
            ),
        ],
      ),
    );
  }
}

class _CatchRow extends StatefulWidget {
  const new({
    required this.caught,
    required this.showConvention,
    required this.onShown,
  });

  final CaughtFursuit caught;
  final bool showConvention;
  final VoidCallback? onShown;

  @override
  State<_CatchRow> createState() => _CatchRowState();
}

class _CatchRowState extends State<_CatchRow> {
  @override
  void initState() {
    super.initState();
    _notifyShown();
  }

  @override
  void didUpdateWidget(_CatchRow oldWidget) {
    super.didUpdateWidget(oldWidget);
    _notifyShown();
  }

  void _notifyShown() {
    final onShown = widget.onShown;
    if (onShown != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          onShown();
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final caught = widget.caught;
    final time = CatchStrings.instant(context, caught.caughtAt);
    return MergeSemantics(
      child: ListTile(
        key: Key("catch-row-${caught.id}"),
        contentPadding: const EdgeInsets.symmetric(horizontal: TokenSpacing.xl),
        leading: TailTagAvatar(
          name: caught.fursuit.name,
          kind: AvatarKind.fursuit,
          imageUrl: caught.fursuit.photoUrl.toString(),
        ),
        title: Text(
          caught.fursuit.name,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Text(
          widget.showConvention ? "${caught.conventionName}\n$time" : time,
        ),
      ),
    );
  }
}
