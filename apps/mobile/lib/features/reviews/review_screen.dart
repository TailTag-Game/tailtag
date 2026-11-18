import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/catches/catch_models.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
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
import "package:tailtag_mobile/features/reviews/review_controller.dart";
import "package:tailtag_mobile/features/reviews/review_strings.dart";

/// The requests on the owner's suits in every open review window, grouped
/// by convention with the selected convention first (#512 AC9 to AC33).
class ReviewScreen extends ConsumerStatefulWidget {
  /// Creates the screen for the selected [convention]. A non-null
  /// [fursuitId] shows only that suit's requests.
  const new({
    required this.convention,
    required this.onReloadHome,
    this.fursuitId,
    super.key,
  });

  /// The selected convention of the home.
  final Convention convention;

  /// The suit filter, or null for every suit.
  final int? fursuitId;

  /// Reads the home state again.
  final VoidCallback onReloadHome;

  @override
  ConsumerState<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends ConsumerState<ReviewScreen> {
  ReviewController get _controller =>
      ref.read(reviewControllerProvider(widget.fursuitId).notifier);

  @override
  void initState() {
    super.initState();
    // A provider cannot change while a widget builds, so the read waits.
    scheduleMicrotask(() {
      if (mounted) {
        unawaited(_controller.read());
      }
    });
  }

  void _snack(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _approve(OwnerCatchRequest request) async {
    if (await _controller.approve(request) && mounted) {
      _snack(ReviewStrings.approved);
    }
  }

  Future<void> _decline(
    OwnerCatchRequest request,
    String conventionName,
  ) async {
    final block = await showModalBottomSheet<bool>(
      context: context,
      showDragHandle: true,
      useSafeArea: true,
      builder: (context) => _DeclineSheet(
        suitName: request.fursuit.name,
        conventionName: conventionName,
      ),
    );
    if (block == null || !mounted) {
      return;
    }
    final controller = _controller;
    final messenger = ScaffoldMessenger.of(context);
    // Undo belongs to this player. After sign-out or an account change it
    // does nothing (#512 AC34).
    final scope = ref.read(playerScopeProvider);
    // The undo time starts when the app sends the decline. The server's
    // `declined_at` is later, so undo never shows after the server's limit,
    // whatever the device clock says (#512 G4).
    final window = block ? null : UndoWindow.start();
    final done = await controller.decline(request, block: block);
    if (!done) {
      window?.cancel();
      return;
    }
    if (window == null) {
      messenger
        ..hideCurrentSnackBar()
        ..showSnackBar(
          const SnackBar(content: Text(ReviewStrings.blockedDone)),
        );
      return;
    }
    window.show(
      messenger,
      onUndo: () {
        if (scope.isActive) {
          unawaited(controller.undo(request.id));
        }
      },
    );
  }

  Future<void> _restore(OwnerCatchRequest request) async {
    if (await _controller.restore(request) && mounted) {
      _snack(ReviewStrings.restored);
    }
  }

  Future<void> _unblock(OwnerCatchRequest request) async {
    if (await _controller.unblock(request) && mounted) {
      _snack(ReviewStrings.unblocked);
    }
  }

  @override
  Widget build(BuildContext context) {
    final provider = reviewControllerProvider(widget.fursuitId);
    ref.listen(provider, (previous, next) {
      if (next.banner == ReviewBanner.ineligible &&
          previous?.banner != ReviewBanner.ineligible) {
        widget.onReloadHome();
      }
    });
    final state = ref.watch(provider);
    final controller = _controller;
    final requests = state.requests;
    final newest = requests == null ? const <int>{} : _newestOfTrio(requests);
    return Scaffold(
      appBar: AppBar(title: const Text(ReviewStrings.title)),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: controller.read,
          child: ListView(
            key: const Key("review-list"),
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.symmetric(vertical: TokenSpacing.lg),
            children: [
              if (_banner(state, controller.read) case final banner?)
                Padding(
                  padding: const EdgeInsets.fromLTRB(
                    TokenSpacing.xl,
                    0,
                    TokenSpacing.xl,
                    TokenSpacing.lg,
                  ),
                  child: banner,
                ),
              if (requests == null && state.reading)
                const DelayedVisibility(
                  child: Padding(
                    padding: EdgeInsets.all(TokenSpacing.xl),
                    child: Center(
                      child: CircularProgressIndicator(
                        semanticsLabel: UiStrings.loading,
                      ),
                    ),
                  ),
                )
              else if (requests != null && requests.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(TokenSpacing.xl),
                  child: EmptyState(
                    key: Key("review-empty"),
                    icon: Icons.inbox_outlined,
                    title: ReviewStrings.empty,
                    body: ReviewStrings.emptyBody,
                  ),
                )
              else if (requests != null)
                for (final group in _groups(requests)) ...[
                  _GroupHeader(
                    conventionId: group.conventionId,
                    convention: state.conventions[group.conventionId],
                    deadlineAt: group.requests.first.reviewDeadlineAt,
                  ),
                  for (final (part, rows) in [
                    (
                      ReviewStrings.toReviewPart,
                      group.requests.where(_isPending).toList(),
                    ),
                    (
                      ReviewStrings.decidedPart,
                      group.requests
                          .where((request) => !_isPending(request))
                          .toList(),
                    ),
                  ])
                    if (rows.isNotEmpty) ...[
                      _PartHeader(label: part),
                      for (final request in rows)
                        _ReviewRow(
                          request: request,
                          conventionName:
                              state.conventions[request.conventionId]?.name ??
                              CatchStrings.otherConvention,
                          newest: newest.contains(request.id),
                          acting: state.acting,
                          onApprove: () => unawaited(_approve(request)),
                          onDecline: (conventionName) =>
                              unawaited(_decline(request, conventionName)),
                          onRestore: () => unawaited(_restore(request)),
                          onUnblock: () => unawaited(_unblock(request)),
                        ),
                    ],
                ],
            ],
          ),
        ),
      ),
    );
  }

  static bool _isPending(OwnerCatchRequest request) =>
      request.state == CatchRequestState.pending;

  /// The IDs of the newest row of each player, suit, and convention. The
  /// server order is newest first, so a trio's first row is its newest.
  static Set<int> _newestOfTrio(List<OwnerCatchRequest> requests) {
    final seen = <({String handle, int fursuitId, int conventionId})>{};
    return {
      for (final request in requests)
        if (seen.add(request.trio)) request.id,
    };
  }

  /// The groups in display order: the selected convention first, then the
  /// others by their newest request (#512 AC9).
  List<({int conventionId, List<OwnerCatchRequest> requests})> _groups(
    List<OwnerCatchRequest> requests,
  ) {
    final byConvention = <int, List<OwnerCatchRequest>>{};
    for (final request in requests) {
      (byConvention[request.conventionId] ??= []).add(request);
    }
    final selected = widget.convention.id;
    final ids = [
      if (byConvention.containsKey(selected)) selected,
      for (final id in byConvention.keys)
        if (id != selected) id,
    ];
    return [
      for (final id in ids) (conventionId: id, requests: byConvention[id]!),
    ];
  }

  Widget? _banner(ReviewState state, Future<void> Function() onTryAgain) {
    final failure = state.readFailure;
    if (failure != null) {
      return StatusBanner(
        key: const Key("review-banner"),
        tone: StatusTone.error,
        message: (genericErrorFor(failure) ?? GenericError.unknown).message,
        actionLabel: UiStrings.tryAgain,
        actionLoading: state.reading,
        onAction: () => unawaited(onTryAgain()),
      );
    }
    final banner = state.banner;
    if (banner == null) {
      return null;
    }
    final (tone, message) = switch (banner) {
      ReviewBanner.serviceOff => (StatusTone.warning, ReviewStrings.serviceOff),
      ReviewBanner.ineligible || ReviewBanner.apiAccess => (
        StatusTone.error,
        GenericError.unknown.message,
      ),
      ReviewBanner.changed => (StatusTone.warning, ReviewStrings.changed),
      ReviewBanner.paused => (StatusTone.warning, ReviewStrings.paused),
      ReviewBanner.alreadyCaught => (
        StatusTone.warning,
        ReviewStrings.alreadyCaught,
      ),
      ReviewBanner.cannotRestore => (
        StatusTone.warning,
        ReviewStrings.cannotRestore,
      ),
      ReviewBanner.tooLateToUndo => (
        StatusTone.warning,
        ReviewStrings.tooLateToUndo,
      ),
      ReviewBanner.gone => (StatusTone.warning, ReviewStrings.gone),
      ReviewBanner.unknown => (StatusTone.warning, ReviewStrings.unknown),
      ReviewBanner.failed => (
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
      key: const Key("review-banner"),
      tone: tone,
      message: message,
      actionLabel: UiStrings.tryAgain,
      actionLoading: state.reading,
      onAction: () => unawaited(onTryAgain()),
    );
  }
}

/// The undo time of one ordinary decline, and its snackbar (#512 AC19).
///
/// It starts when the app sends the decline and ends [undoLimit] later.
/// The snackbar sets `persist: false`, because Flutter keeps a snackbar
/// with an action open by default. At the end of the time, the window
/// closes its own snackbar, unless a newer snackbar already replaced it.
final class UndoWindow {
  /// Starts the time now.
  new start() {
    _timer = Timer(undoLimit, _end);
  }

  late final Timer _timer;
  bool _ended = false;
  ScaffoldFeatureController<SnackBar, SnackBarClosedReason>? _snack;
  bool _snackClosed = false;

  /// Stops the time without a snackbar.
  void cancel() => _timer.cancel();

  /// Shows the decline snackbar on [messenger]. While the time runs, it
  /// has an "Undo" action that calls [onUndo].
  ///
  /// It removes the current snackbar at once, with no exit animation, so
  /// the undo snackbar shows first and never waits in the queue while its
  /// time runs.
  void show(ScaffoldMessengerState messenger, {required VoidCallback onUndo}) {
    messenger.removeCurrentSnackBar();
    if (_ended) {
      messenger.showSnackBar(
        const SnackBar(content: Text(ReviewStrings.declined)),
      );
      return;
    }
    final snack = messenger.showSnackBar(
      SnackBar(
        key: const Key("review-undo-snackbar"),
        content: const Text(ReviewStrings.declined),
        persist: false,
        duration: undoLimit,
        action: SnackBarAction(
          key: const Key("review-undo"),
          label: ReviewStrings.undo,
          onPressed: () {
            if (!_ended) {
              onUndo();
            }
          },
        ),
      ),
    );
    _snack = snack;
    unawaited(snack.closed.then((_) => _snackClosed = true));
  }

  void _end() {
    _ended = true;
    final snack = _snack;
    if (snack != null && !_snackClosed) {
      snack.close();
    }
  }
}

/// The convention name and the review deadline of one group (#512 AC10).
class _GroupHeader extends StatelessWidget {
  const new({
    required this.conventionId,
    required this.convention,
    required this.deadlineAt,
  });

  final int conventionId;
  final Convention? convention;
  final DateTime deadlineAt;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final known = convention;
    final deadline = known?.reviewDeadlineLocalDate == null
        ? ReviewStrings.reviewUntilInstant(
            CatchStrings.instant(context, deadlineAt),
          )
        : ReviewStrings.reviewUntil(
            CatchStrings.reviewEnd(
              context,
              convention: known,
              deadlineAt: deadlineAt,
            ),
          );
    return MergeSemantics(
      child: Padding(
        key: Key("review-group-$conventionId"),
        padding: const EdgeInsets.fromLTRB(
          TokenSpacing.xl,
          TokenSpacing.lg,
          TokenSpacing.xl,
          TokenSpacing.sm,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          spacing: TokenSpacing.xs,
          children: [
            Semantics(
              header: true,
              child: Text(
                known?.name ?? CatchStrings.otherConvention,
                style: textTheme.titleMedium,
              ),
            ),
            Text(deadline, style: textTheme.bodyMedium),
          ],
        ),
      ),
    );
  }
}

/// "To review" or "Decided" inside a group.
class _PartHeader extends StatelessWidget {
  const new({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        TokenSpacing.xl,
        TokenSpacing.sm,
        TokenSpacing.xl,
        TokenSpacing.xs,
      ),
      child: Semantics(
        header: true,
        child: Text(label, style: Theme.of(context).textTheme.titleSmall),
      ),
    );
  }
}

class _ReviewRow extends StatelessWidget {
  const new({
    required this.request,
    required this.conventionName,
    required this.newest,
    required this.acting,
    required this.onApprove,
    required this.onDecline,
    required this.onRestore,
    required this.onUnblock,
  });

  final OwnerCatchRequest request;
  final String conventionName;

  /// Whether this is the newest row of its player, suit, and convention.
  final bool newest;
  final ({int id, ReviewAction action})? acting;
  final VoidCallback onApprove;
  final ValueChanged<String> onDecline;
  final VoidCallback onRestore;
  final VoidCallback onUnblock;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final player = request.player;
    final name = player.displayName;
    final handle = ReviewStrings.handle(player.handle);
    final time = CatchStrings.instant(context, request.requestedAt);
    final stateLabel = ReviewStrings.stateLabel(request.state);
    final pending = request.state == CatchRequestState.pending;
    final declines = request.priorDeclineCount > 0
        ? ReviewStrings.priorDeclines(request.priorDeclineCount)
        : null;
    final paused = pending && request.approvalPaused;
    // Buttons that the server would refuse do not show (#512 AC22, AC23).
    final canRestore = newest && request.state == CatchRequestState.declined;
    final canUnblock = newest && request.playerBlocked;
    final busy = acting != null;
    bool running(ReviewAction action) =>
        acting?.id == request.id && acting?.action == action;

    final buttons = <Widget>[
      if (pending) ...[
        TailTagButton(
          key: Key("review-approve-${request.id}"),
          label: ReviewStrings.approve,
          semanticsLabel: ReviewStrings.approveFor(name),
          loading: running(ReviewAction.approve),
          onPressed: busy || paused ? null : onApprove,
        ),
        TailTagButton(
          key: Key("review-decline-${request.id}"),
          label: ReviewStrings.decline,
          semanticsLabel: ReviewStrings.declineFor(name),
          variant: TailTagButtonVariant.secondary,
          loading: running(ReviewAction.decline),
          onPressed: busy ? null : () => onDecline(conventionName),
        ),
      ],
      if (canRestore)
        TailTagButton(
          key: Key("review-restore-${request.id}"),
          label: ReviewStrings.restore,
          semanticsLabel: ReviewStrings.restoreFor(name),
          variant: TailTagButtonVariant.secondary,
          loading: running(ReviewAction.restore),
          onPressed: busy ? null : onRestore,
        ),
      if (canUnblock)
        TailTagButton(
          key: Key("review-unblock-${request.id}"),
          label: ReviewStrings.removeBlock,
          semanticsLabel: ReviewStrings.removeBlockFor(name),
          variant: TailTagButtonVariant.secondary,
          loading: running(ReviewAction.unblock),
          onPressed: busy ? null : onUnblock,
        ),
    ];

    // One semantics node joins every fact about the request (#512 AC32).
    final summary = [
      name,
      handle,
      request.fursuit.name,
      conventionName,
      time,
      stateLabel,
      ?declines,
      if (request.playerBlocked) ReviewStrings.blocked,
      if (paused) ReviewStrings.paused,
    ].join(", ");

    return Column(
      key: Key("review-row-${request.id}"),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          container: true,
          label: summary,
          excludeSemantics: true,
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(
              horizontal: TokenSpacing.xl,
            ),
            leading: TailTagAvatar(
              name: request.fursuit.name,
              kind: AvatarKind.fursuit,
              imageUrl: request.fursuit.photoUrl.toString(),
            ),
            title: Text(name, maxLines: 2, overflow: TextOverflow.ellipsis),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              spacing: TokenSpacing.xs,
              children: [
                Text("$handle · ${request.fursuit.name}"),
                Text(time),
                if (declines != null) Text(declines),
                Wrap(
                  spacing: TokenSpacing.sm,
                  runSpacing: TokenSpacing.xs,
                  children: [
                    StatusBadge(
                      tone: switch (request.state) {
                        CatchRequestState.approved => StatusTone.success,
                        CatchRequestState.declined => StatusTone.warning,
                        _ => StatusTone.neutral,
                      },
                      label: stateLabel,
                    ),
                    if (request.playerBlocked)
                      StatusBadge(
                        key: Key("review-blocked-${request.id}"),
                        tone: StatusTone.warning,
                        label: ReviewStrings.blocked,
                      ),
                  ],
                ),
                if (paused)
                  Text(
                    ReviewStrings.paused,
                    key: Key("review-paused-${request.id}"),
                    style: textTheme.bodyMedium,
                  ),
              ],
            ),
          ),
        ),
        if (buttons.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(
              TokenSpacing.xl,
              0,
              TokenSpacing.xl,
              TokenSpacing.md,
            ),
            child: Wrap(
              alignment: WrapAlignment.end,
              spacing: TokenSpacing.sm,
              runSpacing: TokenSpacing.sm,
              children: buttons,
            ),
          ),
      ],
    );
  }
}

/// The choice between a plain decline and a decline with a block. It
/// returns false for a plain decline and true for a block (#512 AC15).
class _DeclineSheet extends StatelessWidget {
  const new({required this.suitName, required this.conventionName});

  final String suitName;
  final String conventionName;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(
          TokenSpacing.sm,
          0,
          TokenSpacing.sm,
          TokenSpacing.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ListTile(
              key: const Key("review-decline-plain"),
              leading: const Icon(Icons.close_outlined),
              title: const Text(ReviewStrings.decline),
              onTap: () => Navigator.of(context).pop(false),
            ),
            ListTile(
              key: const Key("review-decline-block"),
              leading: const Icon(Icons.block_outlined),
              title: const Text(ReviewStrings.declineAndBlock),
              subtitle: Text(ReviewStrings.blockHelp(suitName, conventionName)),
              onTap: () => Navigator.of(context).pop(true),
            ),
          ],
        ),
      ),
    );
  }
}
