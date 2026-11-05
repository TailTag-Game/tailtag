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
                  ExcludeSemantics(
                    child: Icon(
                      style.icon,
                      color: style.onContainer,
                      size: TokenSize.iconMedium,
                    ),
                  ),
                  const SizedBox(width: TokenSpacing.md),
                  Expanded(
                    child: Text(
                      message,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: style.onContainer,
                      ),
                    ),
                  ),
                ],
              ),
              if (label != null)
                Align(
                  alignment: AlignmentDirectional.centerEnd,
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
            ],
          ),
        ),
      ),
    );
  }
}
