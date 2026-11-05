import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";

/// How long the showcase pretends that the server takes to answer.
const Duration fakeServerDelay = Duration(milliseconds: 1500);

/// Waits like a slow server.
Future<void> fakeServer() => Future<void>.delayed(fakeServerDelay);

/// Does nothing. Examples use it so that a control is enabled.
void noop() {}

/// Replaces the current snackbar with one that says [text].
void showSnack(BuildContext context, String text) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(text)));
}

/// A long fursuit name, to show the two-line rule.
const String longFursuitName =
    "Midnight Velvet Thunderpaw the Third of the Northern Woods";

/// A long convention name, to show the chip and sheet wrapping rules.
const String longConventionName =
    "The Very Long Name Annual Mountain Fursuit Gathering";

/// The showcase section of one component from the `components.md` inventory.
///
/// Its [title] is the component name in the inventory table, for example
/// "List row". `test/showcase/showcase_test.dart` checks that the sections
/// match the inventory exactly.
class ShowcaseSection extends StatelessWidget {
  /// Creates a section.
  const new({required this.title, required this.children, super.key});

  /// The component name.
  final String title;

  /// The examples.
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ShowcaseHeading(title: title, children: children);
  }
}

/// A titled group of examples. Use [ShowcaseSection] for a component.
class ShowcaseHeading extends StatelessWidget {
  /// Creates a titled group.
  const new({required this.title, required this.children, super.key});

  /// The group title.
  final String title;

  /// The examples.
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: TokenSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.lg),
            child: Semantics(
              header: true,
              child: Text(title, style: textTheme.headlineSmall),
            ),
          ),
          const SizedBox(height: TokenSpacing.md),
          ...children,
        ],
      ),
    );
  }
}

/// One labeled example inside a [ShowcaseSection].
class ShowcaseExample extends StatelessWidget {
  /// Creates an example.
  const new({
    required this.label,
    required this.child,
    this.bleed = false,
    super.key,
  });

  /// What the example shows, for example "Pressed".
  final String label;

  /// The example.
  final Widget child;

  /// Whether the example spans the full screen width.
  ///
  /// Use it for parts that are full width in an app screen, such as list
  /// rows, switch rows, status banners, and app bars. Their own side padding
  /// then lines up with the showcase labels, as it does in the app.
  final bool bleed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    const side = EdgeInsets.symmetric(horizontal: TokenSpacing.lg);
    return Padding(
      padding: const EdgeInsets.only(bottom: TokenSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: side,
            child: Text(
              label,
              style: theme.textTheme.labelMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          const SizedBox(height: TokenSpacing.xs),
          if (bleed) child else Padding(padding: side, child: child),
        ],
      ),
    );
  }
}

/// A scrolling column of showcase sections.
class ShowcasePage extends StatelessWidget {
  /// Creates a page.
  const new({required this.children, super.key});

  /// The sections.
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.only(bottom: TokenSpacing.xxxl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: children,
      ),
    );
  }
}

/// A small caption under a state example, for example "Pressed".
class StateCaption extends StatelessWidget {
  /// Creates a caption under [child].
  const new(this.caption, {required this.child, super.key});

  /// The state name.
  final String caption;

  /// The example in that state.
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        child,
        Text(
          caption,
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

/// The Material 3 pressed state layer opacity.
const double pressedLayerOpacity = 0.1;

/// Shows the buttons, icon buttons, and chips in [child] as if they were in
/// [states], with no tap or keyboard.
///
/// It keeps the real theme. Each border side resolves the theme value for
/// the real states plus [states], so a forced `focused` shows the real focus
/// ring. Flutter draws the pressed state layer only during a real touch, so
/// for `pressed` the wrapper paints the same layer: [pressedContent] at
/// [pressedLayerOpacity], inside the stadium shape that every TailTag
/// button, icon button, and chip uses. It changes only the showcase.
class ForcedStates extends StatelessWidget {
  /// Creates the wrapper.
  const new({
    required this.states,
    required this.child,
    this.pressedContent,
    super.key,
  });

  /// The states to show.
  final Set<WidgetState> states;

  /// The content color of the control, for example `onPrimary`. Required
  /// when [states] has `pressed`.
  final Color? pressedContent;

  /// The controls.
  final Widget child;

  WidgetStateBorderSide _side(BorderSide? original) {
    return WidgetStateBorderSide.resolveWith((current) {
      return WidgetStateProperty.resolveAs<BorderSide?>(
        original,
        current.union(states),
      );
    });
  }

  ButtonStyle? _button(ButtonStyle? style) {
    if (style == null) {
      return null;
    }
    final side = style.side;
    final pressed = pressedContent;
    return style.copyWith(
      side: side == null
          ? null
          : WidgetStateProperty.resolveWith((current) {
              return side.resolve(current.union(states));
            }),
      backgroundBuilder:
          !states.contains(WidgetState.pressed) || pressed == null
          ? null
          : (context, current, child) {
              final content = child ?? const SizedBox.shrink();
              if (current.contains(WidgetState.disabled)) {
                return content;
              }
              return DecoratedBox(
                decoration: ShapeDecoration(
                  color: pressed.withValues(alpha: pressedLayerOpacity),
                  shape: const StadiumBorder(),
                ),
                child: content,
              );
            },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Theme(
      data: theme.copyWith(
        filledButtonTheme: FilledButtonThemeData(
          style: _button(theme.filledButtonTheme.style),
        ),
        textButtonTheme: TextButtonThemeData(
          style: _button(theme.textButtonTheme.style),
        ),
        iconButtonTheme: IconButtonThemeData(
          style: _button(theme.iconButtonTheme.style),
        ),
        chipTheme: theme.chipTheme.copyWith(side: _side(theme.chipTheme.side)),
      ),
      child: child,
    );
  }
}

/// The confirmation dialog pattern: a question, the consequence, Cancel, and
/// a destructive confirm button.
///
/// When [onConfirm] is set, the dialog stays open with the confirm button
/// loading until it finishes. Cancel is disabled meanwhile. The dialog
/// returns true when the action ran, and false when the player cancelled.
/// If [onConfirm] throws, the dialog closes and the error goes to the
/// caller.
class ShowcaseConfirmDialog extends StatefulWidget {
  /// Creates the dialog.
  const new({
    required this.title,
    required this.body,
    required this.confirmLabel,
    this.onConfirm,
    super.key,
  });

  /// One question that names the action.
  final String title;

  /// At most two sentences that say what happens.
  final String body;

  /// A verb, for example "Rotate code".
  final String confirmLabel;

  /// The server call to run before the dialog closes.
  final Future<void> Function()? onConfirm;

  @override
  State<ShowcaseConfirmDialog> createState() => _ShowcaseConfirmDialogState();
}

class _ShowcaseConfirmDialogState extends State<ShowcaseConfirmDialog> {
  bool _loading = false;

  Future<void> _confirm() async {
    final onConfirm = widget.onConfirm;
    Object? failure;
    if (onConfirm != null) {
      setState(() => _loading = true);
      try {
        await onConfirm();
      } on Exception catch (error) {
        failure = error;
      }
    }
    if (mounted) {
      Navigator.of(context).pop(failure ?? true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: Text(widget.body),
      actions: [
        TailTagButton(
          label: "Cancel",
          variant: TailTagButtonVariant.secondaryText,
          onPressed: _loading ? null : () => Navigator.of(context).pop(false),
        ),
        TailTagButton(
          label: widget.confirmLabel,
          variant: TailTagButtonVariant.destructive,
          loading: _loading,
          onPressed: _confirm,
        ),
      ],
    );
  }
}

/// The error that a showcase example raises to show a failed server call.
final class FakeServerFailure implements Exception {
  /// Creates the failure.
  const new();
}
