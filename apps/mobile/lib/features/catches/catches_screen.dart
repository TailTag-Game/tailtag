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
import "package:tailtag_mobile/core/ui/widgets/status_badge.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/catches/catch_strings.dart";
import "package:tailtag_mobile/features/catches/catches_controller.dart";

/// The narrowest viewport that keeps two collection columns side by side.
const double _minTwoColumnWidth = 340;

/// The private collection (F9): completed catches with convention filter
/// chips. The next page loads at the end of the list (#511 AC28, AC29).
class CatchesScreen extends ConsumerStatefulWidget {
  /// Creates the collection for the selected [convention].
  const new({required this.convention, required this.onScan, super.key});

  /// The selected convention of the home, the default filter.
  final Convention convention;

  /// Opens the full-screen scanner from the empty state.
  final VoidCallback onScan;

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
        child: LayoutBuilder(
          builder: (context, constraints) {
            final textScale = MediaQuery.textScalerOf(context).scale(1);
            final twoColumns =
                constraints.maxWidth >= _minTwoColumnWidth &&
                textScale <= StatusBadge.maxBesideTitleTextScale;
            VoidCallback? onShownFor(int index, int count) =>
                // The last card asks for the next page once it builds near the
                // viewport. After a failure only "Try again" reads again, so a
                // broken connection never starts a request loop.
                index == count - 1 && state.hasNext && failure == null
                ? () => unawaited(controller.loadMore())
                : null;
            return RefreshIndicator(
              onRefresh: controller.read,
              child: CustomScrollView(
                key: const Key("catches-list"),
                physics: const AlwaysScrollableScrollPhysics(),
                slivers: [
                  SliverPadding(
                    padding: const EdgeInsets.only(top: TokenSpacing.lg),
                    sliver: SliverToBoxAdapter(
                      child: _Chips(
                        conventions: state.conventions,
                        filter: state.filter,
                        onSelect: (filter) =>
                            unawaited(controller.select(filter)),
                      ),
                    ),
                  ),
                  if (failure != null)
                    SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.all(TokenSpacing.xl),
                        child: StatusBanner(
                          key: const Key("catches-banner"),
                          tone: StatusTone.error,
                          message:
                              (genericErrorFor(failure) ?? GenericError.unknown)
                                  .message,
                          actionLabel: UiStrings.tryAgain,
                          actionLoading: state.reading,
                          onAction: () => unawaited(controller.read()),
                        ),
                      ),
                    ),
                  if (catches == null && state.reading)
                    const SliverToBoxAdapter(child: _Loading())
                  else if (catches != null && catches.isEmpty)
                    SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.all(TokenSpacing.xl),
                        child: EmptyState(
                          key: const Key("catches-empty"),
                          icon: Icons.catching_pokemon_outlined,
                          title: CatchStrings.catchesEmpty,
                          body: CatchStrings.catchesEmptyBody,
                          action: widget.convention.catchingOpen
                              ? TailTagButton(
                                  key: const Key("catches-empty-scan"),
                                  label: CatchStrings.scanTag,
                                  icon: Icons.qr_code_scanner,
                                  onPressed: widget.onScan,
                                )
                              : null,
                        ),
                      ),
                    )
                  else if (catches != null) ...[
                    if (!twoColumns)
                      SliverPadding(
                        key: const Key("catches-single-column"),
                        padding: const EdgeInsets.symmetric(
                          horizontal: TokenSpacing.lg,
                        ),
                        sliver: SliverList.separated(
                          itemCount: catches.length,
                          separatorBuilder: (context, index) =>
                              const SizedBox(height: TokenSpacing.md),
                          itemBuilder: (context, index) => _CatchCard(
                            caught: catches[index],
                            showConvention: state.filter == null,
                            onShown: onShownFor(index, catches.length),
                          ),
                        ),
                      )
                    else
                      SliverPadding(
                        key: const Key("catches-grid"),
                        padding: const EdgeInsets.symmetric(
                          horizontal: TokenSpacing.lg,
                        ),
                        sliver: SliverList.separated(
                          itemCount: (catches.length + 1) ~/ 2,
                          separatorBuilder: (context, index) =>
                              const SizedBox(height: TokenSpacing.md),
                          itemBuilder: (context, rowIndex) {
                            final first = rowIndex * 2;
                            final second = first + 1;
                            return Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              spacing: TokenSpacing.md,
                              children: [
                                Expanded(
                                  child: _CatchCard(
                                    caught: catches[first],
                                    showConvention: state.filter == null,
                                    onShown: onShownFor(first, catches.length),
                                  ),
                                ),
                                Expanded(
                                  child: second < catches.length
                                      ? _CatchCard(
                                          caught: catches[second],
                                          showConvention: state.filter == null,
                                          onShown: onShownFor(
                                            second,
                                            catches.length,
                                          ),
                                        )
                                      : const SizedBox.shrink(),
                                ),
                              ],
                            );
                          },
                        ),
                      ),
                    if (state.loadingMore)
                      const SliverToBoxAdapter(child: _Loading()),
                  ],
                  const SliverToBoxAdapter(
                    child: SizedBox(height: TokenSpacing.lg),
                  ),
                ],
              ),
            );
          },
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
    final chips = [
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
    ];
    final wrapChips =
        MediaQuery.textScalerOf(context).scale(1) >
        StatusBadge.maxBesideTitleTextScale;
    const padding = EdgeInsets.fromLTRB(
      TokenSpacing.lg,
      0,
      TokenSpacing.lg,
      TokenSpacing.md,
    );
    if (wrapChips) {
      return Padding(
        padding: padding,
        child: Wrap(
          spacing: TokenSpacing.sm,
          runSpacing: TokenSpacing.sm,
          children: chips,
        ),
      );
    }
    return SingleChildScrollView(
      key: const Key("catches-chips-scroll"),
      scrollDirection: Axis.horizontal,
      padding: padding,
      child: Row(spacing: TokenSpacing.sm, children: chips),
    );
  }
}

class _CatchCard extends StatefulWidget {
  const new({
    required this.caught,
    required this.showConvention,
    required this.onShown,
  });

  final CaughtFursuit caught;
  final bool showConvention;
  final VoidCallback? onShown;

  @override
  State<_CatchCard> createState() => _CatchCardState();
}

class _CatchCardState extends State<_CatchCard> {
  @override
  void initState() {
    super.initState();
    _notifyShown();
  }

  @override
  void didUpdateWidget(_CatchCard oldWidget) {
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
    final theme = Theme.of(context);
    return Card(
      key: Key("catch-row-${caught.id}"),
      margin: EdgeInsets.zero,
      child: MergeSemantics(
        child: Padding(
          padding: const EdgeInsets.all(TokenSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: TokenSpacing.sm,
            children: [
              TailTagAvatar(
                name: caught.fursuit.name,
                kind: AvatarKind.fursuit,
                imageUrl: caught.fursuit.photoUrl.toString(),
                size: AvatarSize.photo,
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  TokenSpacing.xs,
                  0,
                  TokenSpacing.xs,
                  TokenSpacing.xs,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: TokenSpacing.xs,
                  children: [
                    Text(
                      caught.fursuit.name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleMedium,
                    ),
                    Text(
                      widget.showConvention
                          ? "${caught.conventionName}\n$time"
                          : time,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
