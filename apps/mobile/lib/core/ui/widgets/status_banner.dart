import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";

/// A message that stays until the problem is fixed or the player acts.
///
/// It sits at the top of the content area, below the top app bar, inset by
/// the screen side padding. It is a live region, so a screen reader reads it
/// when it shows.
class StatusBanner extends StatelessWidget {
  /// Creates a status banner.
  const new({
    required this.tone,
    required this.message,
    this.actionLabel,
    this.onAction,
    this.actionLoading = false,
    super.key,
  }) : assert(
         tone != StatusTone.success,
         "Success uses a snackbar, not a status banner.",
       );

  /// The meaning: error, warning, or neutral.
  final StatusTone tone;

  /// What happened and what to do next, in one or two sentences.
  final String message;

  /// The optional action label, for example `GenericError.actionLabel`.
  final String? actionLabel;

  /// Called when the player taps the action.
  final VoidCallback? onAction;

  /// Whether the action is running.
  final bool actionLoading;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final style = context.statusStyle(tone);
    final label = actionLabel;
    final textStyle = theme.textTheme.bodyMedium?.copyWith(
      color: style.onContainer,
    );
    // Center the icon on the first line of text at any text scale: pad
    // whichever of the two is shorter by half the difference.
    final fontSize = textStyle?.fontSize ?? 14;
    final lineHeight =
        MediaQuery.textScalerOf(context).scale(fontSize) *
        (textStyle?.height ?? 1);
    final offset = (lineHeight - TokenSize.iconMedium) / 2;
    return Semantics(
      liveRegion: true,
      container: true,
      child: Material(
        color: style.container,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(TokenRadius.large),
        ),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          // The action button brings its own padding, so the bottom edge
          // is tighter when the banner has an action.
          padding: EdgeInsets.fromLTRB(
            TokenSpacing.lg,
            TokenSpacing.lg,
            TokenSpacing.lg,
            label == null ? TokenSpacing.lg : TokenSpacing.sm,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: EdgeInsets.only(top: offset > 0 ? offset : 0),
                    child: ExcludeSemantics(
                      child: Icon(
                        style.icon,
                        color: style.onContainer,
                        size: TokenSize.iconMedium,
                      ),
                    ),
                  ),
                  const SizedBox(width: TokenSpacing.md),
                  Expanded(
                    child: Padding(
                      padding: EdgeInsets.only(top: offset < 0 ? -offset : 0),
                      child: Text(message, style: textStyle),
                    ),
                  ),
                ],
              ),
              if (label != null)
                Padding(
                  // The label text lines up with the start of the message:
                  // the icon and its gap, less the button's own padding.
                  padding: const EdgeInsetsDirectional.only(
                    start:
                        TokenSize.iconMedium +
                        TokenSpacing.md -
                        TokenSpacing.lg,
                  ),
                  child: Align(
                    alignment: AlignmentDirectional.centerStart,
                    // The action label uses the banner text color.
                    child: TextButtonTheme(
                      data: TextButtonThemeData(
                        style: TextButton.styleFrom(
                          foregroundColor: style.onContainer,
                        ).merge(TextButtonTheme.of(context).style),
                      ),
                      child: TailTagButton(
                        label: label,
                        variant: TailTagButtonVariant.secondaryText,
                        onPressed: onAction,
                        loading: actionLoading,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
