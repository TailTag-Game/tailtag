import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/features/reviews/pending_summary_controller.dart";
import "package:tailtag_mobile/features/reviews/review_strings.dart";

/// The ways into the review screen, with their pending counts (#512 AC3 to
/// AC5). Each reads the counts when it first shows. None shows while the
/// server has no catch review (AC27).
///
/// [ReviewEntry.home] shows only while something waits for review, and
/// then adds its own top space.
/// [ReviewEntry.suitList] and [ReviewEntry.suit] always show.
class ReviewEntry extends ConsumerStatefulWidget {
  /// The convention home row.
  const new home({required this.onOpen, required this.onIneligible, super.key})
    : fursuitId = null,
      _kind = _EntryKind.home;

  /// The row at the top of the suit list.
  const new suitList({required this.onOpen, super.key})
    : fursuitId = null,
      onIneligible = null,
      _kind = _EntryKind.suitList;

  /// The row on the suit detail screen of suit [fursuitId].
  const new suit({required this.fursuitId, required this.onOpen, super.key})
    : onIneligible = null,
      _kind = _EntryKind.suit;

  /// The suit whose count shows, or null for every suit.
  final int? fursuitId;

  /// Opens the review screen.
  final VoidCallback onOpen;

  /// Reads the home state again after a 403 (#512 AC26).
  final VoidCallback? onIneligible;

  final _EntryKind _kind;

  @override
  ConsumerState<ReviewEntry> createState() => _ReviewEntryState();
}

enum _EntryKind { home, suitList, suit }

class _ReviewEntryState extends ConsumerState<ReviewEntry> {
  @override
  void initState() {
    super.initState();
    // The suit detail screen reads the counts itself, because it hides its
    // row while the counts are unavailable (#512 AC30).
    if (widget._kind == _EntryKind.suit) {
      return;
    }
    // A provider cannot change while a widget builds, so the read waits.
    scheduleMicrotask(() {
      if (mounted) {
        unawaited(ref.read(pendingSummaryProvider.notifier).read());
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final onIneligible = widget.onIneligible;
    if (onIneligible != null) {
      ref.listen(pendingSummaryProvider, (previous, next) {
        if (next.ineligible && !(previous?.ineligible ?? false)) {
          onIneligible();
        }
      });
    }
    final state = ref.watch(pendingSummaryProvider);
    final summary = state.summary;
    if (!state.available) {
      return const SizedBox.shrink();
    }
    switch (widget._kind) {
      case _EntryKind.home:
        final count = summary?.pendingCount ?? 0;
        if (count == 0) {
          return const SizedBox.shrink();
        }
        final scheme = Theme.of(context).colorScheme;
        return Padding(
          padding: const EdgeInsets.only(top: TokenSpacing.lg),
          child: Card(
            margin: EdgeInsets.zero,
            child: ListTile(
              key: const Key("home-review"),
              leading: CircleAvatar(
                backgroundColor: scheme.primaryContainer,
                foregroundColor: scheme.onPrimaryContainer,
                child: const Icon(Icons.inbox_outlined),
              ),
              title: Text(ReviewStrings.toReview(count)),
              trailing: const Icon(Icons.chevron_right_outlined),
              onTap: widget.onOpen,
            ),
          ),
        );
      case _EntryKind.suitList:
        return ListTile(
          key: const Key("suits-review"),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: TokenSpacing.xl,
          ),
          leading: const Icon(Icons.inbox_outlined),
          title: const Text(ReviewStrings.title),
          subtitle: Text(ReviewStrings.waiting(summary?.pendingCount ?? 0)),
          trailing: const Icon(Icons.chevron_right_outlined),
          onTap: widget.onOpen,
        );
      case _EntryKind.suit:
        final id = widget.fursuitId!;
        return ListTile(
          key: const Key("suit-review"),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: TokenSpacing.lg,
          ),
          title: const Text(ReviewStrings.suitRequests),
          subtitle: Text(ReviewStrings.waiting(summary?.forFursuit(id) ?? 0)),
          trailing: const Icon(Icons.chevron_right_outlined),
          onTap: widget.onOpen,
        );
    }
  }
}

/// Whether the server has catch review, so the approval switch can show
/// (#512 AC27). It is true until a read proves otherwise.
bool reviewAvailable(WidgetRef ref) =>
    ref.watch(pendingSummaryProvider).available;
