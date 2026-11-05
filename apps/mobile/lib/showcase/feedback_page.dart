import "dart:async";

import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/showcase/showcase_parts.dart";

/// Showcase tab for banners, loading, snackbars, dialogs, and bottom sheets.
class FeedbackPage extends StatelessWidget {
  /// Creates the tab.
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return const ShowcasePage(
      children: [
        _BannerSection(),
        _LoadingSection(),
        _SnackbarSection(),
        _DialogSection(),
        _SheetSection(),
      ],
    );
  }
}

/// A secondary button that starts a live example.
class _StartButton extends StatelessWidget {
  const new({required this.label, required this.onPressed, this.icon});

  final String label;
  final VoidCallback onPressed;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: TailTagButton(
        label: label,
        icon: icon,
        variant: TailTagButtonVariant.secondary,
        onPressed: onPressed,
      ),
    );
  }
}

class _BannerSection extends StatefulWidget {
  const new();

  @override
  State<_BannerSection> createState() => _BannerSectionState();
}

class _BannerSectionState extends State<_BannerSection> {
  bool _retrying = false;

  Future<void> _retry() async {
    setState(() => _retrying = true);
    await fakeServer();
    if (mounted) {
      setState(() => _retrying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    const noConnection = GenericError.noConnection;
    return ShowcaseSection(
      title: "Status banner",
      children: [
        ShowcaseExample(
          label: "Error: no connection. Live: tap Try again to see loading.",
          child: StatusBanner(
            tone: StatusTone.error,
            message: noConnection.message,
            actionLabel: noConnection.actionLabel,
            actionLoading: _retrying,
            onAction: _retry,
          ),
        ),
        for (final error in const [GenericError.timeout, GenericError.unknown])
          ShowcaseExample(
            label: "Error: ${error.name}",
            child: StatusBanner(
              tone: StatusTone.error,
              message: error.message,
              actionLabel: error.actionLabel,
              onAction: noop,
            ),
          ),
        const ShowcaseExample(
          label: "Warning (F8)",
          child: StatusBanner(
            tone: StatusTone.warning,
            message: "This fursuit is not out right now.",
          ),
        ),
        const ShowcaseExample(
          label: "Neutral (F8)",
          child: StatusBanner(
            tone: StatusTone.neutral,
            message: "You already caught this fursuit.",
          ),
        ),
      ],
    );
  }
}

class _LoadingSection extends StatefulWidget {
  const new();

  @override
  State<_LoadingSection> createState() => _LoadingSectionState();
}

class _LoadingSectionState extends State<_LoadingSection> {
  int _refreshes = 0;
  bool _loading = false;

  Future<void> _load() async {
    setState(() => _loading = true);
    await fakeServer();
    if (mounted) {
      setState(() => _loading = false);
    }
  }

  Future<void> _refresh() async {
    await fakeServer();
    if (mounted) {
      setState(() => _refreshes++);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ShowcaseSection(
      title: "Loading indicator",
      children: [
        const ShowcaseExample(
          label: "Screen and small",
          child: Row(
            children: [
              CircularProgressIndicator(semanticsLabel: "Loading fursuits"),
              SizedBox(width: TokenSpacing.xl),
              SizedBox.square(
                dimension: TokenSize.iconSmall,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  semanticsLabel: "Loading",
                ),
              ),
            ],
          ),
        ),
        ShowcaseExample(
          label: "Live: a 1.5 s load. The spinner waits 500 ms.",
          child: SizedBox(
            height: 120,
            child: Card(
              child: Center(
                child: _loading
                    ? const DelayedVisibility(
                        child: CircularProgressIndicator(
                          semanticsLabel: "Loading catches",
                        ),
                      )
                    : TailTagButton(
                        label: "Load catches",
                        variant: TailTagButtonVariant.secondary,
                        onPressed: _load,
                      ),
              ),
            ),
          ),
        ),
        ShowcaseExample(
          label: "Live: pull down to refresh",
          child: SizedBox(
            height: 200,
            child: Card(
              child: RefreshIndicator(
                onRefresh: _refresh,
                child: ListView(
                  children: [
                    for (var i = 1; i <= 4; i++)
                      ListTile(title: Text("Catch $i (refreshed $_refreshes)")),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _SnackbarSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return ShowcaseSection(
      title: "Snackbar",
      children: [
        ShowcaseExample(
          label: "Live: one short sentence, no action",
          child: _StartButton(
            label: "Show snackbar",
            onPressed: () => showSnack(context, "Catch confirmed"),
          ),
        ),
      ],
    );
  }
}

class _DialogSection extends StatefulWidget {
  const new();

  @override
  State<_DialogSection> createState() => _DialogSectionState();
}

class _DialogSectionState extends State<_DialogSection> {
  bool _failed = false;

  Future<void> _rotate({required bool fails}) async {
    setState(() => _failed = false);
    final result = await showDialog<Object>(
      context: context,
      builder: (context) => ShowcaseConfirmDialog(
        title: "Rotate this QR code?",
        body: "Players can no longer catch with the old code.",
        confirmLabel: "Rotate code",
        onConfirm: () async {
          await fakeServer();
          if (fails) {
            throw const FakeServerFailure();
          }
        },
      ),
    );
    if (!mounted) {
      return;
    }
    if (result is FakeServerFailure) {
      setState(() => _failed = true);
    } else if (result == true) {
      showSnack(context, "QR code rotated");
    }
  }

  @override
  Widget build(BuildContext context) {
    return ShowcaseSection(
      title: "Dialog",
      children: [
        ShowcaseExample(
          label:
              "Live: confirm credential rotation (F7). The confirm button "
              "loads, and Cancel is disabled.",
          child: _StartButton(
            label: "Rotate QR code",
            icon: Icons.refresh_outlined,
            onPressed: () => unawaited(_rotate(fails: false)),
          ),
        ),
        ShowcaseExample(
          label: "Live error: the dialog closes and a banner shows",
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_failed) ...[
                StatusBanner(
                  tone: StatusTone.error,
                  message: GenericError.unknown.message,
                ),
                const SizedBox(height: TokenSpacing.sm),
              ],
              _StartButton(
                label: "Rotate offline",
                onPressed: () => unawaited(_rotate(fails: true)),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _SheetSection extends StatefulWidget {
  const new();

  @override
  State<_SheetSection> createState() => _SheetSectionState();
}

class _SheetSectionState extends State<_SheetSection> {
  String _active = "Northwind Fur Meet";

  Future<void> _pickConvention({bool slow = false, bool fails = false}) async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      useSafeArea: true,
      builder: (context) => _ChoiceSheet(
        title: "Active convention",
        selected: _active,
        slow: slow,
        fails: fails,
      ),
    );
    if (picked != null && mounted) {
      setState(() => _active = picked);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ShowcaseSection(
      title: "Bottom sheet",
      children: [
        ShowcaseExample(
          label: "Live: choice sheet (F3). Active: $_active",
          child: _StartButton(
            label: "Pick convention",
            onPressed: () => unawaited(_pickConvention()),
          ),
        ),
        ShowcaseExample(
          label: "Live loading: the list takes 1.5 s",
          child: _StartButton(
            label: "Pick slowly",
            onPressed: () => unawaited(_pickConvention(slow: true)),
          ),
        ),
        ShowcaseExample(
          label: "Live error: a banner shows at the top of the sheet",
          child: _StartButton(
            label: "Pick offline",
            onPressed: () => unawaited(_pickConvention(fails: true)),
          ),
        ),
        ShowcaseExample(
          label: "Live: photo choices (F2, F4)",
          child: _StartButton(
            label: "Change photo",
            icon: Icons.photo_camera_outlined,
            onPressed: () => unawaited(
              showModalBottomSheet<void>(
                context: context,
                useSafeArea: true,
                builder: (context) => const _PhotoSheet(),
              ),
            ),
          ),
        ),
        ShowcaseExample(
          label: "Live: form sheet with the keyboard",
          child: _StartButton(
            label: "Rename fursuit",
            onPressed: () => unawaited(
              showModalBottomSheet<void>(
                context: context,
                useSafeArea: true,
                isScrollControlled: true,
                builder: (context) => const _FormSheet(),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _ChoiceSheet extends StatefulWidget {
  const new({
    required this.title,
    required this.selected,
    required this.slow,
    required this.fails,
  });

  final String title;
  final String selected;
  final bool slow;
  final bool fails;

  @override
  State<_ChoiceSheet> createState() => _ChoiceSheetState();
}

class _ChoiceSheetState extends State<_ChoiceSheet> {
  static const List<String> _choices = [
    "Northwind Fur Meet",
    "Lakeside Pawcon",
    longConventionName,
  ];

  late bool _loading = widget.slow;
  late bool _failed = widget.fails;

  @override
  void initState() {
    super.initState();
    if (_loading) {
      unawaited(_load());
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    await fakeServer();
    if (mounted) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    const noConnection = GenericError.noConnection;
    return ListView(
      shrinkWrap: true,
      children: [
        // The rows sit spacing.sm in from the sheet edge, so the rounded
        // selected fill does not touch it. The title lines up with the row
        // text at spacing.sm plus spacing.lg, which is spacing.xl.
        Padding(
          padding: const EdgeInsets.fromLTRB(
            TokenSpacing.xl,
            0,
            TokenSpacing.xl,
            TokenSpacing.sm,
          ),
          child: Semantics(
            header: true,
            child: Text(
              widget.title,
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
        ),
        if (_failed)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.lg),
            child: StatusBanner(
              tone: StatusTone.error,
              message: noConnection.message,
              actionLabel: noConnection.actionLabel,
              onAction: () => unawaited(_load()),
            ),
          )
        else if (_loading)
          const Padding(
            padding: EdgeInsets.all(TokenSpacing.xl),
            child: Center(
              child: DelayedVisibility(
                replacement: SizedBox.square(dimension: TokenSize.minTarget),
                child: CircularProgressIndicator(
                  semanticsLabel: "Loading conventions",
                ),
              ),
            ),
          )
        else
          for (final choice in _choices)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.sm),
              child: ListTile(
                title: Text(
                  choice,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                selected: choice == widget.selected,
                trailing: choice == widget.selected
                    ? const Icon(Icons.check)
                    : null,
                onTap: () => Navigator.of(context).pop(choice),
              ),
            ),
        const SizedBox(height: TokenSpacing.lg),
      ],
    );
  }
}

class _PhotoSheet extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    void pick(String text) {
      Navigator.of(context).pop();
      showSnack(context, text);
    }

    return ListView(
      shrinkWrap: true,
      padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.sm),
      children: [
        ListTile(
          leading: const Icon(Icons.photo_camera_outlined),
          title: const Text("Take photo"),
          onTap: () => pick("Camera opens here"),
        ),
        ListTile(
          leading: const Icon(Icons.photo_library_outlined),
          title: const Text("Choose photo"),
          onTap: () => pick("Photo library opens here"),
        ),
        ListTile(
          leading: const Icon(Icons.delete_outlined),
          title: const Text("Remove photo"),
          onTap: () => pick("Photo removed"),
        ),
        const SizedBox(height: TokenSpacing.lg),
      ],
    );
  }
}

class _FormSheet extends StatefulWidget {
  const new();

  @override
  State<_FormSheet> createState() => _FormSheetState();
}

class _FormSheetState extends State<_FormSheet> {
  bool _saving = false;

  Future<void> _save() async {
    setState(() => _saving = true);
    await fakeServer();
    if (!mounted) {
      return;
    }
    Navigator.of(context).pop();
    showSnack(context, "Fursuit saved");
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        TokenSpacing.lg,
        0,
        TokenSpacing.lg,
        TokenSpacing.lg + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            header: true,
            child: Text(
              "Rename fursuit",
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
          const SizedBox(height: TokenSpacing.lg),
          TextFormField(
            enabled: !_saving,
            autofocus: true,
            initialValue: "Blaze",
            maxLength: 50,
            textCapitalization: TextCapitalization.words,
            textInputAction: TextInputAction.done,
            onFieldSubmitted: (_) => _save(),
            decoration: const InputDecoration(labelText: "Fursuit name"),
          ),
          const SizedBox(height: TokenSpacing.lg),
          TailTagButton(label: "Save", loading: _saving, onPressed: _save),
        ],
      ),
    );
  }
}
