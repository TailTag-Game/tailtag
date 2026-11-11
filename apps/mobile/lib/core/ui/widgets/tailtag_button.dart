import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";

/// The visual variant of a [TailTagButton].
enum TailTagButtonVariant {
  /// The main action on a screen or in a sheet: a solid violet pill.
  primary,

  /// Other actions: a tonal pill in the primary container colors.
  secondary,

  /// A secondary action inside a dialog or a banner: a text button with no
  /// fill. It takes its color from the nearest `TextButtonTheme`.
  secondaryText,

  /// Only the confirm action in a confirmation dialog: a solid error pill.
  destructive,
}

/// The TailTag button, with every variant and the loading state.
///
/// Features use it for every button in docs/design/components.md, so no
/// feature styles a tonal or destructive button itself.
///
/// While [loading] is true, the button is disabled and keeps its colors and
/// size. After [loadingIndicatorDelay], the label hides but keeps its space,
/// and a small spinner shows in the center. The screen reader still reads
/// the label, with the value "Loading".
class TailTagButton extends StatelessWidget {
  /// Creates a button.
  const new({
    required this.label,
    required this.onPressed,
    this.variant = TailTagButtonVariant.primary,
    this.icon,
    this.loading = false,
    super.key,
  });

  /// A verb or short verb phrase, for example "Save".
  final String label;

  /// Called on tap. When null, the button is disabled.
  final VoidCallback? onPressed;

  /// The visual variant.
  final TailTagButtonVariant variant;

  /// An optional leading icon.
  final IconData? icon;

  /// Whether the action is running.
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (Color? fill, Color text) = switch (variant) {
      TailTagButtonVariant.primary => (scheme.primary, scheme.onPrimary),
      // Flutter gives FilledButton.tonal the secondary container colors.
      // Violet owns every action, so TailTag uses the primary container.
      TailTagButtonVariant.secondary => (
        scheme.primaryContainer,
        scheme.onPrimaryContainer,
      ),
      TailTagButtonVariant.secondaryText => (
        null,
        TextButtonTheme.of(context).style?.foregroundColor?.resolve(const {}) ??
            scheme.primary,
      ),
      TailTagButtonVariant.destructive => (scheme.error, scheme.onError),
    };
    // `styleFrom` derives the pressed, hovered, and focused state layer from
    // the label color. A disabled button keeps the Material disabled colors.
    // While loading, the disabled colors are the normal colors, so the
    // button does not turn grey.
    final whileLoading = loading ? text : null;
    final content = Semantics(
      value: loading ? UiStrings.loading : null,
      child: _content(text),
    );
    final action = loading ? null : onPressed;
    if (fill == null) {
      return TextButton(
        onPressed: action,
        style: TextButton.styleFrom(
          foregroundColor: text,
          iconColor: text,
          disabledForegroundColor: whileLoading,
          disabledIconColor: whileLoading,
        ),
        child: content,
      );
    }
    return FilledButton(
      onPressed: action,
      style: FilledButton.styleFrom(
        backgroundColor: fill,
        foregroundColor: text,
        iconColor: text,
        disabledBackgroundColor: loading ? fill : null,
        disabledForegroundColor: whileLoading,
        disabledIconColor: whileLoading,
      ),
      child: content,
    );
  }

  Widget _content(Color color) {
    Widget label = Text(this.label);
    if (icon != null) {
      label = Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: TokenSize.iconSmall),
          const SizedBox(width: TokenSpacing.xs),
          Flexible(child: label),
        ],
      );
    }
    if (!loading) {
      return label;
    }
    return DelayedVisibility(
      replacement: label,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Visibility(
            visible: false,
            maintainSize: true,
            maintainAnimation: true,
            maintainState: true,
            // The hidden label still names the button for screen readers.
            maintainSemantics: true,
            child: label,
          ),
          SizedBox.square(
            dimension: TokenSize.iconSmall,
            // Stroke widths have no token. 2 suits a size.icon.small spinner.
            child: CircularProgressIndicator(strokeWidth: 2, color: color),
          ),
        ],
      ),
    );
  }
}
