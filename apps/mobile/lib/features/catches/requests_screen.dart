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
import "package:tailtag_mobile/features/catches/requests_controller.dart";

/// The player's own catch requests in every open review window, grouped by
/// convention with the selected convention first (#511 AC22 to AC27).
class RequestsScreen extends ConsumerStatefulWidget {
  /// Creates the list for the selected [convention].
  const new({required this.convention, required this.onReloadHome, super.key});

  /// The selected convention of the home.
  final Convention convention;

  /// Reads the home state again.
  final VoidCallback onReloadHome;

  @override
  ConsumerState<RequestsScreen> createState() => _RequestsScreenState();
}

class _RequestsScreenState extends ConsumerState<RequestsScreen> {
  @override
  void initState() {
    super.initState();
    // A provider cannot change while a widget builds, so the read waits.
    scheduleMicrotask(() {
      if (mounted) {
        unawaited(ref.read(requestsControllerProvider.notifier).read());
      }
    });
  }

  Future<void> _withdraw(PlayerCatchRequest request) async {
    final controller = ref.read(requestsControllerProvider.notifier);
    final done = await showDialog<bool>(
      context: context,
      builder: (context) =>
          _WithdrawDialog(onConfirm: () => controller.withdraw(request)),
    );
    if ((done ?? false) && mounted) {
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(const SnackBar(content: Text(CatchStrings.withdrawn)));
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(requestsControllerProvider, (previous, next) {
      if (next.banner == RequestsBanner.ineligible &&
          previous?.banner != RequestsBanner.ineligible) {
        widget.onReloadHome();
      }
    });
    final state = ref.watch(requestsControllerProvider);
    final controller = ref.read(requestsControllerProvider.notifier);
    final requests = state.requests;
    return Scaffold(
      appBar: AppBar(title: const Text(CatchStrings.navRequests)),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: controller.read,
          child: ListView(
            key: const Key("requests-list"),
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
                    key: Key("requests-empty"),
                    icon: Icons.outbox_outlined,
                    title: CatchStrings.requestsEmpty,
                    body: CatchStrings.requestsEmptyBody,
                  ),
                )
              else if (requests != null)
                for (final group in _groups(requests)) ...[
                  _GroupHeader(
                    conventionId: group.conventionId,
                    convention: state.conventions[group.conventionId],
                    deadlineAt: group.requests.first.reviewDeadlineAt,
                  ),
                  for (final request in group.requests)
                    _RequestRow(
                      request: request,
                      withdrawing: state.withdrawing == request.id,
                      onWithdraw: state.withdrawing == null
                          ? () => unawaited(_withdraw(request))
                          : null,
                    ),
                ],
            ],
          ),
        ),
      ),
    );
  }

  /// The groups in display order: the selected convention first, then the
  /// others by their newest request. The server order is newest first, so
  /// a group's first appearance is its newest request.
  List<({int conventionId, List<PlayerCatchRequest> requests})> _groups(
    List<PlayerCatchRequest> requests,
  ) {
    final byConvention = <int, List<PlayerCatchRequest>>{};
    for (final request in requests) {
      (byConvention[request.conventionId] ??= []).add(request);
    }
    // The map keeps first-appearance order. The selected convention moves
    // to the front.
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

  Widget? _banner(RequestsState state, Future<void> Function() onTryAgain) {
    final failure = state.readFailure;
    if (failure != null) {
      return StatusBanner(
        key: const Key("requests-banner"),
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
      RequestsBanner.serviceOff => (
        StatusTone.warning,
        CatchStrings.requestsOff,
      ),
      RequestsBanner.ineligible => (StatusTone.error, CatchStrings.ineligible),
      RequestsBanner.apiAccess => (
        StatusTone.error,
        GenericError.unknown.message,
      ),
      RequestsBanner.changed => (
        StatusTone.warning,
        CatchStrings.requestChanged,
      ),
      RequestsBanner.gone => (StatusTone.warning, CatchStrings.requestGone),
      RequestsBanner.withdrawUnknown => (
        StatusTone.warning,
        CatchStrings.withdrawUnknown,
      ),
      RequestsBanner.withdrawFailed => (
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
      key: const Key("requests-banner"),
      tone: tone,
      message: message,
      actionLabel: UiStrings.tryAgain,
      actionLoading: state.reading,
      onAction: () => unawaited(onTryAgain()),
    );
  }
}

/// The convention name and the review deadline of one group.
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
        ? CatchStrings.reviewUntilInstant(
            CatchStrings.instant(context, deadlineAt),
          )
        : CatchStrings.reviewUntil(
            CatchStrings.reviewEnd(
              context,
              convention: known,
              deadlineAt: deadlineAt,
            ),
          );
    return MergeSemantics(
      child: Padding(
        key: Key("requests-group-$conventionId"),
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

class _RequestRow extends StatelessWidget {
  const new({
    required this.request,
    required this.withdrawing,
    required this.onWithdraw,
  });

  final PlayerCatchRequest request;
  final bool withdrawing;
  final VoidCallback? onWithdraw;

  @override
  Widget build(BuildContext context) {
    final badge = StatusBadge(
      tone: switch (request.state) {
        CatchRequestState.approved => StatusTone.success,
        CatchRequestState.declined => StatusTone.warning,
        _ => StatusTone.neutral,
      },
      label: CatchStrings.stateLabel(request.state),
    );
    final name = request.fursuit.name;
    return Column(
      key: Key("request-row-${request.id}"),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // One semantics node joins the name, the time, and the state.
        MergeSemantics(
          child: ListTile(
            contentPadding: const EdgeInsets.symmetric(
              horizontal: TokenSpacing.xl,
            ),
            leading: TailTagAvatar(
              name: name,
              kind: AvatarKind.fursuit,
              imageUrl: request.fursuit.photoUrl.toString(),
            ),
            title: Text(name, maxLines: 2, overflow: TextOverflow.ellipsis),
            subtitle: StatusBadge.rowSubtitle(
              context,
              badge,
              subtitle: Text(
                CatchStrings.instant(context, request.requestedAt),
              ),
            ),
            trailing: StatusBadge.rowTrailing(context, badge),
          ),
        ),
        if (request.state == CatchRequestState.pending)
          Padding(
            padding: const EdgeInsets.fromLTRB(
              TokenSpacing.xl,
              0,
              TokenSpacing.xl,
              TokenSpacing.md,
            ),
            child: Align(
              alignment: AlignmentDirectional.centerEnd,
              child: TailTagButton(
                key: Key("request-withdraw-${request.id}"),
                label: CatchStrings.withdraw,
                variant: TailTagButtonVariant.secondary,
                loading: withdrawing,
                onPressed: onWithdraw,
              ),
            ),
          ),
      ],
    );
  }
}

class _WithdrawDialog extends StatefulWidget {
  const new({required this.onConfirm});

  final Future<bool> Function() onConfirm;

  @override
  State<_WithdrawDialog> createState() => _WithdrawDialogState();
}

class _WithdrawDialogState extends State<_WithdrawDialog> {
  bool _sending = false;

  Future<void> _confirm() async {
    setState(() => _sending = true);
    final done = await widget.onConfirm();
    if (mounted) {
      Navigator.of(context).pop(done);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_sending,
      child: AlertDialog(
        scrollable: true,
        title: const Text(CatchStrings.withdrawTitle),
        content: const Text(CatchStrings.withdrawBody),
        actions: [
          TailTagButton(
            key: const Key("withdraw-cancel"),
            label: CatchStrings.cancel,
            variant: TailTagButtonVariant.secondaryText,
            onPressed: _sending ? null : () => Navigator.of(context).pop(),
          ),
          TailTagButton(
            key: const Key("withdraw-confirm"),
            label: CatchStrings.withdraw,
            variant: TailTagButtonVariant.destructive,
            loading: _sending,
            onPressed: _sending ? null : () => unawaited(_confirm()),
          ),
        ],
      ),
    );
  }
}
