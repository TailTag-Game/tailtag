import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/showcase/showcase_parts.dart";

/// Showcase tab for buttons, icon buttons, text fields, switches, and chips.
class ControlsPage extends StatelessWidget {
  /// Creates the tab.
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return const ShowcasePage(
      children: [
        _ButtonSection(),
        _IconButtonSection(),
        _TextFieldSection(),
        _SwitchSection(),
        _ChipSection(),
      ],
    );
  }
}

/// The fixed states that a pressable control shows, with no tap.
const List<(String, Set<WidgetState>?)> _fixedStates = [
  ("Normal", {}),
  ("Pressed", {WidgetState.pressed}),
  ("Focused", {WidgetState.focused}),
  ("Disabled", null),
];

class _ButtonSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final variants = <(String, TailTagButtonVariant, String, Color)>[
      ("Primary", TailTagButtonVariant.primary, "Save", scheme.onPrimary),
      ("Secondary", TailTagButtonVariant.secondary, "Edit", scheme.primary),
      (
        "Secondary text, in a dialog or banner",
        TailTagButtonVariant.secondaryText,
        "Cancel",
        scheme.primary,
      ),
      (
        "Destructive, for a dialog confirm only",
        TailTagButtonVariant.destructive,
        "Rotate code",
        scheme.onError,
      ),
    ];
    return ShowcaseSection(
      title: "Button",
      children: [
        for (final (name, variant, label, content) in variants)
          ShowcaseExample(
            label: name,
            child: Wrap(
              spacing: TokenSpacing.sm,
              runSpacing: TokenSpacing.sm,
              children: [
                for (final (state, states) in _fixedStates)
                  StateCaption(
                    state,
                    child: ForcedStates(
                      states: states ?? const {},
                      pressedContent: content,
                      child: TailTagButton(
                        label: label,
                        variant: variant,
                        onPressed: states == null ? null : noop,
                      ),
                    ),
                  ),
                StateCaption(
                  "Loading",
                  child: TailTagButton(
                    label: label,
                    variant: variant,
                    loading: true,
                    onPressed: noop,
                  ),
                ),
              ],
            ),
          ),
        const ShowcaseExample(
          label: "With a leading icon",
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: TailTagButton(
              label: "Confirm catch",
              icon: Icons.check_circle_outlined,
              onPressed: noop,
            ),
          ),
        ),
        const ShowcaseExample(
          label: "Live: tap to run a 1.5 s action. The spinner waits 500 ms.",
          child: _LiveLoadingButton(),
        ),
      ],
    );
  }
}

class _LiveLoadingButton extends StatefulWidget {
  const new();

  @override
  State<_LiveLoadingButton> createState() => _LiveLoadingButtonState();
}

class _LiveLoadingButtonState extends State<_LiveLoadingButton> {
  bool _loading = false;

  Future<void> _run() async {
    setState(() => _loading = true);
    await fakeServer();
    if (mounted) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: TailTagButton(label: "Enroll", loading: _loading, onPressed: _run),
    );
  }
}

class _IconButtonSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    final content = Theme.of(context).colorScheme.onSurfaceVariant;
    return ShowcaseSection(
      title: "Icon button",
      children: [
        ShowcaseExample(
          label: "Standard, with a required tooltip",
          child: Wrap(
            spacing: TokenSpacing.lg,
            children: [
              for (final (state, states) in _fixedStates)
                StateCaption(
                  state,
                  child: ForcedStates(
                    states: states ?? const {},
                    pressedContent: content,
                    child: IconButton(
                      tooltip: "Share QR code",
                      icon: Icon(Icons.adaptive.share),
                      onPressed: states == null ? null : noop,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _TextFieldSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return ShowcaseSection(
      title: "Text field",
      children: [
        const ShowcaseExample(
          label: "Normal, with helper text and a counter",
          child: TextField(
            maxLength: 50,
            decoration: InputDecoration(
              labelText: "Display name",
              helperText: "Other players see this name.",
            ),
          ),
        ),
        const ShowcaseExample(
          label: "Optional field",
          child: TextField(
            decoration: InputDecoration(labelText: "Species (optional)"),
          ),
        ),
        // InputDecorator draws the real themed field in its focused look.
        const ShowcaseExample(
          label: "Focused (fixed; tap any field to focus it for real)",
          child: InputDecorator(
            isFocused: true,
            decoration: InputDecoration(labelText: "Fursuit name"),
            child: Text("Blaze"),
          ),
        ),
        ShowcaseExample(
          label: "Error",
          child: TextField(
            controller: TextEditingController(),
            maxLength: 50,
            decoration: const InputDecoration(
              labelText: "Fursuit name",
              errorText: "Enter a name.",
            ),
          ),
        ),
        ShowcaseExample(
          label: "Long helper text: wraps to three lines",
          child: TextField(
            controller: TextEditingController(text: "ember_sky"),
            maxLength: 32,
            decoration: const InputDecoration(
              labelText: "Handle",
              helperText:
                  "Other players find you by this handle. Use lowercase "
                  "letters, numbers, and underscores. You can change it "
                  "later from your profile, but old links stop working.",
            ),
          ),
        ),
        ShowcaseExample(
          label: "Disabled, only while the form saves",
          child: TextField(
            enabled: false,
            controller: TextEditingController(text: "blaze_the_fox"),
            maxLength: 32,
            decoration: const InputDecoration(labelText: "Handle"),
          ),
        ),
        const ShowcaseExample(
          label: "Live: errors show on first submit, then as you type",
          child: _FormDemo(),
        ),
      ],
    );
  }
}

class _FormDemo extends StatefulWidget {
  const new();

  @override
  State<_FormDemo> createState() => _FormDemoState();
}

class _FormDemoState extends State<_FormDemo> {
  final _formKey = GlobalKey<FormState>();
  AutovalidateMode _autovalidate = AutovalidateMode.disabled;
  bool _saving = false;
  bool _failed = false;

  String? _required(String? value) {
    if (value == null || value.trim().isEmpty) {
      return "Enter a name.";
    }
    return null;
  }

  String? _handle(String? value) {
    if (value == null || value.trim().isEmpty) {
      return "Enter a handle.";
    }
    if (!RegExp(r"^[a-z0-9_]+$").hasMatch(value)) {
      return "Use lowercase letters, numbers, and underscores only.";
    }
    return null;
  }

  Future<void> _submit() async {
    setState(() {
      _autovalidate = AutovalidateMode.onUserInteraction;
      _failed = false;
    });
    if (!(_formKey.currentState?.validate() ?? false)) {
      return;
    }
    setState(() => _saving = true);
    await fakeServer();
    if (!mounted) {
      return;
    }
    setState(() => _saving = false);
    showSnack(context, "Profile saved");
  }

  Future<void> _submitAndFail() async {
    setState(() => _saving = true);
    await fakeServer();
    if (mounted) {
      setState(() {
        _saving = false;
        _failed = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      autovalidateMode: _autovalidate,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (_failed) ...[
            StatusBanner(
              tone: StatusTone.error,
              message: GenericError.noConnection.message,
              actionLabel: GenericError.noConnection.actionLabel,
              actionLoading: _saving,
              onAction: _submit,
            ),
            const SizedBox(height: TokenSpacing.lg),
          ],
          TextFormField(
            enabled: !_saving,
            maxLength: 50,
            textCapitalization: TextCapitalization.words,
            textInputAction: TextInputAction.next,
            validator: _required,
            decoration: const InputDecoration(labelText: "Display name"),
          ),
          const SizedBox(height: TokenSpacing.sm),
          TextFormField(
            enabled: !_saving,
            maxLength: 32,
            autocorrect: false,
            autofillHints: const [AutofillHints.username],
            textInputAction: TextInputAction.done,
            onFieldSubmitted: (_) => _submit(),
            validator: _handle,
            decoration: const InputDecoration(
              labelText: "Handle",
              helperText: "Lowercase letters, numbers, and underscores.",
            ),
          ),
          const SizedBox(height: TokenSpacing.lg),
          Wrap(
            spacing: TokenSpacing.sm,
            runSpacing: TokenSpacing.sm,
            children: [
              TailTagButton(
                label: "Save",
                loading: _saving,
                onPressed: _submit,
              ),
              TailTagButton(
                label: "Save offline",
                variant: TailTagButtonVariant.secondary,
                onPressed: _saving ? null : _submitAndFail,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SwitchSection extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    return const ShowcaseSection(
      title: "Switch",
      children: [
        ShowcaseExample(
          label: "Live: waits for the server before it moves",
          bleed: true,
          child: _ServerSwitch(
            title: "Out for catching",
            subtitle: "Other players can catch this fursuit now.",
          ),
        ),
        ShowcaseExample(
          label: "Live: turning off asks for confirmation",
          bleed: true,
          child: _ServerSwitch(
            title: "Active at Northwind Fur Meet",
            subtitle: "Shows this fursuit at the convention.",
            confirmOff: true,
          ),
        ),
        ShowcaseExample(
          label: "Live error: the server fails, so the switch stays",
          bleed: true,
          child: _ServerSwitch(
            title: "Out for catching",
            subtitle: "This example always fails.",
            fails: true,
          ),
        ),
        ShowcaseExample(
          label: "Disabled",
          bleed: true,
          child: SwitchListTile(
            value: false,
            onChanged: null,
            title: Text("Out for catching"),
            subtitle: Text("Activate this fursuit first."),
          ),
        ),
      ],
    );
  }
}

class _ServerSwitch extends StatefulWidget {
  const new({
    required this.title,
    required this.subtitle,
    this.confirmOff = false,
    this.fails = false,
  });

  final String title;
  final String subtitle;
  final bool confirmOff;
  final bool fails;

  @override
  State<_ServerSwitch> createState() => _ServerSwitchState();
}

class _ServerSwitchState extends State<_ServerSwitch> {
  bool _value = true;
  bool _pending = false;
  bool _failed = false;

  Future<void> _toggle(bool next) async {
    if (widget.confirmOff && !next) {
      final confirmed = await showDialog<Object>(
        context: context,
        builder: (context) => const ShowcaseConfirmDialog(
          title: "Turn off this fursuit?",
          body:
              "Its QR code stops working for good. "
              "Turning it on again makes a new code.",
          confirmLabel: "Turn off",
        ),
      );
      if (confirmed != true || !mounted) {
        return;
      }
    }
    setState(() {
      _pending = true;
      _failed = false;
    });
    await fakeServer();
    if (!mounted) {
      return;
    }
    setState(() {
      _pending = false;
      _failed = widget.fails;
      if (!widget.fails) {
        _value = next;
      }
    });
    if (!next && !widget.fails) {
      showSnack(context, "${widget.title}: off");
    }
  }

  @override
  Widget build(BuildContext context) {
    final subtitle = Text(widget.subtitle);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (_failed)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.lg),
            child: StatusBanner(
              tone: StatusTone.error,
              message: GenericError.noConnection.message,
            ),
          ),
        SwitchListTile(
          value: _value,
          onChanged: _pending ? null : _toggle,
          title: Text(widget.title),
          subtitle: _pending
              ? DelayedVisibility(
                  replacement: subtitle,
                  child: const Row(
                    children: [
                      SizedBox.square(
                        dimension: TokenSize.iconSmall,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                      SizedBox(width: TokenSpacing.sm),
                      Flexible(child: Text(UiStrings.updating)),
                    ],
                  ),
                )
              : subtitle,
        ),
      ],
    );
  }
}

class _ChipSection extends StatefulWidget {
  const new();

  @override
  State<_ChipSection> createState() => _ChipSectionState();
}

class _ChipSectionState extends State<_ChipSection> {
  static const List<String> _conventions = [
    "All",
    "Northwind Fur Meet",
    "Lakeside Pawcon",
    longConventionName,
  ];
  String _selected = "All";

  @override
  Widget build(BuildContext context) {
    return ShowcaseSection(
      title: "Chip",
      children: [
        ShowcaseExample(
          label: "Live: filter catch history by convention. Long names wrap.",
          child: Wrap(
            spacing: TokenSpacing.sm,
            runSpacing: TokenSpacing.sm,
            children: [
              for (final name in _conventions)
                FilterChip(
                  label: Text(
                    name,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  selected: _selected == name,
                  onSelected: (_) => setState(() => _selected = name),
                ),
            ],
          ),
        ),
        ShowcaseExample(
          label: "Focused (fixed)",
          child: Wrap(
            spacing: TokenSpacing.sm,
            runSpacing: TokenSpacing.sm,
            children: [
              ForcedStates(
                states: const {WidgetState.focused},
                child: FilterChip(
                  label: const Text("Lakeside Pawcon"),
                  onSelected: (_) {},
                ),
              ),
              ForcedStates(
                states: const {WidgetState.focused},
                child: FilterChip(
                  label: const Text("All"),
                  selected: true,
                  onSelected: (_) {},
                ),
              ),
            ],
          ),
        ),
        const ShowcaseExample(
          label: "Disabled, only while the list reloads",
          child: Wrap(
            spacing: TokenSpacing.sm,
            runSpacing: TokenSpacing.sm,
            children: [
              FilterChip(label: Text("All"), selected: true, onSelected: null),
              FilterChip(label: Text("Lakeside Pawcon"), onSelected: null),
            ],
          ),
        ),
      ],
    );
  }
}
