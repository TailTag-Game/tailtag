import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";

/// A short label that shows the state of an item. It has no action.
///
/// Features map their states onto a [StatusTone]. The badge text joins the
/// label of the row or card around it.
///
/// The chip theme styles filter chips as pills, so this widget sets the
/// badge shape and colors on its own `Chip`.
///
/// In a `ListTile`, place the badge with [rowTrailing] and [rowSubtitle]:
///
/// ```dart
/// ListTile(
///   title: Text(fursuit.name),
///   subtitle: StatusBadge.rowSubtitle(context, badge, subtitle: species),
///   trailing: StatusBadge.rowTrailing(context, badge),
/// )
/// ```
class StatusBadge extends StatelessWidget {
  /// Creates a badge.
  const new({required this.tone, required this.label, this.icon, super.key});

  /// The largest text scale at which a row badge still fits beside the
  /// title. Above it, the badge moves below the title.
  ///
  /// 1.3 is the largest standard Android font size setting. With the
  /// platform system font, a 360 pt wide row with an avatar, a two-word
  /// title, and a two-word badge fits at 1.3. Widget tests use a test font
  /// that is about twice as wide, so they check only where the badge goes.
  static const double maxBesideTitleTextScale = 1.3;

  /// Whether a row badge moves below the title at the current text scale.
  static bool _belowTitle(BuildContext context) {
    return MediaQuery.textScalerOf(context).scale(1) > maxBesideTitleTextScale;
  }

  /// [badge] for the `trailing` slot of a row, or null when the text is too
  /// large for it to fit beside the title.
  static Widget? rowTrailing(BuildContext context, StatusBadge badge) {
    return _belowTitle(context) ? null : badge;
  }

  /// The `subtitle` slot of a row: [subtitle], with [badge] below it when
  /// the text is too large for the badge to fit beside the title.
  static Widget? rowSubtitle(
    BuildContext context,
    StatusBadge badge, {
    Widget? subtitle,
  }) {
    if (!_belowTitle(context)) {
      return subtitle;
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ?subtitle,
        if (subtitle != null) const SizedBox(height: TokenSpacing.xs),
        badge,
      ],
    );
  }

  /// The status meaning.
  final StatusTone tone;

  /// One or two words, for example "Out now". It is one line.
  final String label;

  /// An optional Outlined icon for a neutral badge. The other tones always
  /// show their status icon.
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final style = context.statusStyle(tone);
    final badgeIcon = tone == StatusTone.neutral ? icon : style.icon;
    // A Chip is its own semantics container. The badge is plain text, so
    // its label joins the row or card around it.
    return Semantics(
      label: label,
      child: ExcludeSemantics(child: _chip(context, style, badgeIcon)),
    );
  }

  Widget _chip(BuildContext context, StatusStyle style, IconData? badgeIcon) {
    return Chip(
      label: Text(label, maxLines: 1, softWrap: false),
      avatar: badgeIcon == null
          ? null
          : Icon(
              badgeIcon,
              color: style.onContainer,
              size: TokenSize.iconSmall,
            ),
      // `color` wins over the chip theme, which colors filter chips.
      color: WidgetStatePropertyAll(style.container),
      side: BorderSide.none,
      // A badge is a label, not a control, so it is not a pill.
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(TokenRadius.small),
      ),
      // `spacing.xs` at each side, and `spacing.xs` between the icon and the
      // label.
      padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.xs),
      labelStyle: Theme.of(context).textTheme.labelLarge
          ?.copyWith(color: style.onContainer),
      labelPadding: EdgeInsetsDirectional.only(
        start: badgeIcon == null ? 0 : TokenSpacing.xs,
      ),
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );
  }
}
