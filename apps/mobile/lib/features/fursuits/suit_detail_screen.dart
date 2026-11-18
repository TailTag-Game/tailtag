import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_providers.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_avatar.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";
import "package:tailtag_mobile/features/fursuits/photo_picker.dart";
import "package:tailtag_mobile/features/fursuits/suit_status.dart";
import "package:tailtag_mobile/features/fursuits/suit_widgets.dart";
import "package:tailtag_mobile/features/fursuits/suits_controller.dart";
import "package:tailtag_mobile/features/reviews/pending_summary_controller.dart";
import "package:tailtag_mobile/features/reviews/review_entries.dart";
import "package:tailtag_mobile/features/reviews/review_strings.dart";

/// One suit: its photo and name, then its participation and catch session
/// at the selected convention, then its catch approval parts (#512), then
/// the row that opens its tag.
class SuitDetailScreen extends ConsumerStatefulWidget {
  /// Creates the screen for suit [fursuitId] at [convention].
  const new({
    required this.convention,
    required this.fursuitId,
    required this.onOpenTag,
    required this.onOpenReview,
    super.key,
  });

  /// The selected convention.
  final Convention convention;

  /// The suit's server ID.
  final int fursuitId;

  /// Opens the tag screen of the suit.
  final VoidCallback onOpenTag;

  /// Opens the review screen of the suit (#512 AC5).
  final VoidCallback onOpenReview;

  @override
  ConsumerState<SuitDetailScreen> createState() => _SuitDetailScreenState();
}

class _SuitDetailScreenState extends ConsumerState<SuitDetailScreen> {
  @override
  void initState() {
    super.initState();
    _readSoon();
  }

  @override
  void didUpdateWidget(SuitDetailScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.convention.id != widget.convention.id) {
      _readSoon();
    }
  }

  /// A provider cannot change while a widget builds, so the read waits.
  void _readSoon() {
    scheduleMicrotask(() {
      if (mounted) {
        unawaited(_controller.read());
        // The counts decide whether the approval parts show, so this screen
        // reads them even while they are hidden (#512 AC30).
        unawaited(ref.read(pendingSummaryProvider.notifier).read());
      }
    });
  }

  SuitsController get _controller =>
      ref.read(suitsControllerProvider(widget.convention.id).notifier);

  void _snack(String text) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _toggleParticipation(bool next) async {
    if (!next) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => const _DeactivateDialog(),
      );
      if (confirmed != true || !mounted) {
        return;
      }
    }
    await _controller.setParticipation(widget.fursuitId, active: next);
  }

  Future<void> _toggleSession(bool next) async {
    final done = await _controller.setCatchSession(
      widget.fursuitId,
      active: next,
    );
    if (done && !next && mounted) {
      _snack(FursuitStrings.sessionStopped);
    }
  }

  Future<void> _setApproval(bool automatic) async {
    await _controller.setApprovalMode(
      widget.fursuitId,
      automatic ? CatchApprovalMode.automatic : CatchApprovalMode.manual,
    );
  }

  Future<void> _changePhoto() async {
    final outcome = await pickSuitPhoto(context, ref.read(photoSourceProvider));
    if (!mounted) {
      return;
    }
    switch (outcome) {
      case PhotoPickCancelled():
        return;
      case PhotoPickProblem(:final message):
        _snack(message);
      case PhotoPicked(:final photo):
        final result = await _controller.replacePhoto(widget.fursuitId, photo);
        if (!mounted) {
          return;
        }
        switch (result) {
          case SuitWriteDone():
            _snack(FursuitStrings.photoSaved);
          case SuitWriteFieldError(:final message):
            _snack(message);
          case SuitWriteFailed() || SuitWriteUnknown():
            break;
        }
    }
  }

  Future<void> _changeName(Fursuit fursuit) async {
    final saved = await showModalBottomSheet<bool>(
      context: context,
      showDragHandle: true,
      useSafeArea: true,
      isScrollControlled: true,
      builder: (context) => _RenameSheet(
        initialName: fursuit.name,
        onSave: (name) => _controller.rename(widget.fursuitId, name),
      ),
    );
    if (saved == true && mounted) {
      _snack(FursuitStrings.nameSaved);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(suitsControllerProvider(widget.convention.id));
    final fursuit = state.fursuit(widget.fursuitId);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          fursuit?.name ?? FursuitStrings.mySuits,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: SafeArea(
        child: RefreshIndicator(
          // The counts decide whether the approval parts show, so a pull
          // to refresh reads them too (#512 AC30).
          onRefresh: () => Future.wait([
            _controller.read(),
            ref.read(pendingSummaryProvider.notifier).read(),
          ]),
          child: ListView(
            key: const Key("suit-detail"),
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.symmetric(vertical: TokenSpacing.lg),
            children: [
              if (suitsBanner(state, _controller.read) case final banner?)
                _inset(banner),
              // A suit that is not in the list yet can arrive with the read
              // that runs. The screen says "not found" only after the read.
              if (fursuit == null && state.reading)
                const SuitsLoading()
              else if (fursuit == null && state.fursuits != null)
                _inset(
                  Text(
                    FursuitStrings.suitMissing,
                    key: const Key("suit-missing"),
                    style: Theme.of(context).textTheme.bodyLarge,
                  ),
                )
              else if (fursuit != null)
                ..._content(context, state, fursuit),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _content(
    BuildContext context,
    SuitsState state,
    Fursuit fursuit,
  ) {
    final textTheme = Theme.of(context).textTheme;
    final convention = widget.convention;
    final activation = state.activations[fursuit.id];
    final write = state.writes[fursuit.id];
    final busy = write != null;
    final now = DateTime.now();
    final participationReason = participationBlock(
      fursuit,
      convention,
      activation,
    );
    final sessionReason = sessionBlock(fursuit, convention, activation);
    final participating = activation?.isActive ?? false;
    final catchable = activation?.isCatchable ?? false;
    final session = activation?.session;
    final note = sessionNoteFor(activation);
    return [
      _inset(
        Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          spacing: TokenSpacing.md,
          children: [
            Center(
              child: TailTagAvatar(
                name: fursuit.name,
                kind: AvatarKind.fursuit,
                imageUrl: fursuit.photoUrl.toString(),
                size: AvatarSize.large,
              ),
            ),
            Text(
              fursuit.name,
              key: const Key("suit-name"),
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: textTheme.titleLarge,
            ),
            Align(child: suitBadge(badgeFor(activation))),
            TailTagButton(
              key: const Key("suit-change-name"),
              label: FursuitStrings.changeName,
              variant: TailTagButtonVariant.secondary,
              loading: write == SuitWrite.name,
              onPressed: busy ? null : () => unawaited(_changeName(fursuit)),
            ),
            TailTagButton(
              key: const Key("suit-change-photo"),
              label: FursuitStrings.changePhoto,
              variant: TailTagButtonVariant.secondary,
              loading: write == SuitWrite.photo,
              onPressed: busy ? null : () => unawaited(_changePhoto()),
            ),
          ],
        ),
      ),
      const SizedBox(height: TokenSpacing.xl),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.xl),
        child: Semantics(
          header: true,
          child: Text(
            FursuitStrings.atConvention(convention.name),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: textTheme.titleMedium,
          ),
        ),
      ),
      SwitchListTile(
        key: const Key("suit-participation"),
        value: participating,
        onChanged: busy || participationReason != null
            ? null
            : (next) => unawaited(_toggleParticipation(next)),
        title: Text(FursuitStrings.participatingAt(convention.name)),
        subtitle: switchSubtitle(
          pending: write == SuitWrite.participation,
          text: participationReason == null
              ? FursuitStrings.participationHelp
              : disabledReasonText(participationReason),
        ),
      ),
      SwitchListTile(
        key: const Key("suit-session"),
        value: catchable,
        onChanged: busy || sessionReason != null
            ? null
            : (next) => unawaited(_toggleSession(next)),
        title: const Text(FursuitStrings.outForCatching),
        subtitle: switchSubtitle(
          pending: write == SuitWrite.session,
          text: switch ((sessionReason, catchable, session)) {
            (final DisabledReason reason, _, _) => disabledReasonText(reason),
            (null, true, final CatchSession live) => FursuitStrings.outUntil(
              FursuitStrings.time(context, live.expiresAt, now),
            ),
            _ => FursuitStrings.sessionHelp,
          },
        ),
      ),
      if (note != null)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.xl),
          child: Text(
            switch (note.kind) {
              SessionNoteKind.timedOut => FursuitStrings.sessionTimedOut(
                FursuitStrings.time(context, note.at, now),
              ),
              SessionNoteKind.staffEnded => FursuitStrings.sessionStaffEnded(
                FursuitStrings.time(context, note.at, now),
              ),
            },
            key: const Key("suit-session-note"),
            style: textTheme.bodyMedium,
          ),
        ),
      // The approval parts hide while the server has no catch review
      // (#512 AC27).
      if (reviewAvailable(ref)) ...[
        const SizedBox(height: TokenSpacing.xl),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.xl),
          child: Semantics(
            header: true,
            child: Text(
              ReviewStrings.approvalSection,
              style: textTheme.titleMedium,
            ),
          ),
        ),
        // The server accepts a mode change for a disabled suit too, so the
        // switch stays enabled (#512 AC7).
        SwitchListTile(
          key: const Key("suit-approval"),
          value: fursuit.approvalMode == CatchApprovalMode.automatic,
          onChanged: busy ? null : (next) => unawaited(_setApproval(next)),
          title: const Text(ReviewStrings.automatic),
          subtitle: switchSubtitle(
            pending: write == SuitWrite.approval,
            text: fursuit.approvalMode == CatchApprovalMode.automatic
                ? ReviewStrings.automaticHelp
                : ReviewStrings.manualHelp,
          ),
        ),
        ReviewEntry.suit(fursuitId: fursuit.id, onOpen: widget.onOpenReview),
      ],
      const SizedBox(height: TokenSpacing.xl),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.xl),
        child: Semantics(
          header: true,
          child: Text(FursuitStrings.tagSection, style: textTheme.titleMedium),
        ),
      ),
      // The tag read creates the first tag, so this screen never reads it.
      ListTile(
        key: const Key("suit-show-tag"),
        contentPadding: const EdgeInsets.symmetric(horizontal: TokenSpacing.xl),
        enabled: fursuit.isEnabled,
        title: const Text(FursuitStrings.showTag),
        subtitle: Text(
          fursuit.isEnabled
              ? FursuitStrings.showTagHelp
              : FursuitStrings.suitDisabled,
        ),
        trailing: const Icon(Icons.chevron_right_outlined),
        onTap: widget.onOpenTag,
      ),
    ];
  }

  static Widget _inset(Widget child) => Padding(
    padding: const EdgeInsets.fromLTRB(
      TokenSpacing.xl,
      0,
      TokenSpacing.xl,
      TokenSpacing.lg,
    ),
    child: child,
  );
}

class _DeactivateDialog extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text(FursuitStrings.deactivateTitle),
      content: const Text(FursuitStrings.deactivateBody),
      actions: [
        TailTagButton(
          key: const Key("deactivate-cancel"),
          label: FursuitStrings.cancel,
          variant: TailTagButtonVariant.secondaryText,
          onPressed: () => Navigator.of(context).pop(false),
        ),
        TailTagButton(
          key: const Key("deactivate-confirm"),
          label: FursuitStrings.deactivateConfirm,
          variant: TailTagButtonVariant.destructive,
          onPressed: () => Navigator.of(context).pop(true),
        ),
      ],
    );
  }
}

class _RenameSheet extends StatefulWidget {
  const new({required this.initialName, required this.onSave});

  final String initialName;
  final Future<SuitWriteResult> Function(String name) onSave;

  @override
  State<_RenameSheet> createState() => _RenameSheetState();
}

class _RenameSheetState extends State<_RenameSheet> {
  late final TextEditingController _name = TextEditingController(
    text: widget.initialName,
  );
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    final result = await widget.onSave(_name.text);
    if (!mounted) {
      return;
    }
    switch (result) {
      case SuitWriteDone():
        Navigator.of(context).pop(true);
      case SuitWriteFieldError(:final message):
        setState(() {
          _saving = false;
          _error = message;
        });
      case SuitWriteUnknown():
        // The name was not sent again. The sheet keeps it for a new try
        // after the owner checks the current state.
        setState(() {
          _saving = false;
          _error = FursuitStrings.writeUnknownOutcome;
        });
      case SuitWriteFailed():
        // The screen banner says why.
        Navigator.of(context).pop(false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_saving,
      // The sheet scrolls, so the field and the button stay reachable at a
      // large text scale with the keyboard open.
      child: SingleChildScrollView(
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            TokenSpacing.xl,
            0,
            TokenSpacing.xl,
            TokenSpacing.xl + MediaQuery.viewInsetsOf(context).bottom,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            spacing: TokenSpacing.lg,
            children: [
              ValueListenableBuilder(
                valueListenable: _name,
                builder: (context, value, _) => TextField(
                  key: const Key("rename-field"),
                  controller: _name,
                  enabled: !_saving,
                  autofocus: true,
                  maxLength: 50,
                  textCapitalization: TextCapitalization.words,
                  textInputAction: TextInputAction.done,
                  decoration: InputDecoration(
                    labelText: FursuitStrings.nameLabel,
                    errorText: _error,
                  ),
                  onSubmitted: value.text.trim().isEmpty || _saving
                      ? null
                      : (_) => unawaited(_save()),
                ),
              ),
              ValueListenableBuilder(
                valueListenable: _name,
                builder: (context, value, _) => TailTagButton(
                  key: const Key("rename-save"),
                  label: FursuitStrings.save,
                  loading: _saving,
                  onPressed: value.text.trim().isEmpty || _saving
                      ? null
                      : () => unawaited(_save()),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
