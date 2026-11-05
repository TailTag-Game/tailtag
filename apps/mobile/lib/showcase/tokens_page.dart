import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/showcase/showcase_parts.dart";
import "package:tailtag_mobile/showcase/token_catalog.dart";

/// Showcase tab for every design token, with the value that the code uses.
///
/// It reads [tokenCatalog], which the token parity test checks against
/// `docs/design/tokens.json`. The design README explains each group.
class TokensPage extends StatelessWidget {
  /// Creates the tab.
  const new({super.key});

  /// The token groups, as a name prefix and a title, in tab order.
  static const List<(String, String)> groups = [
    ("color.scheme.", "Color roles"),
    ("color.status.", "Status colors"),
    ("typography.", "Typography"),
    ("spacing.", "Spacing"),
    ("radius.", "Radius"),
    ("size.", "Size"),
    ("elevation.", "Elevation"),
  ];

  @override
  Widget build(BuildContext context) {
    return ShowcasePage(
      children: [
        for (final (prefix, title) in groups)
          ShowcaseHeading(
            title: title,
            children: [
              for (final MapEntry(:key, :value) in tokenCatalog.entries)
                if (key.startsWith(prefix))
                  _TokenRow(name: key, value: value, group: prefix),
            ],
          ),
      ],
    );
  }
}

/// A number without a trailing ".0".
String _number(double value) {
  return value == value.roundToDouble()
      ? value.toInt().toString()
      : value.toString();
}

/// The `#RRGGBB` hex value of [color].
String hexOf(Color color) {
  final rgb = color.toARGB32() & 0xFFFFFF;
  return "#${rgb.toRadixString(16).padLeft(6, "0").toUpperCase()}";
}

class _TokenRow extends StatelessWidget {
  const new({required this.name, required this.value, required this.group});

  final String name;
  final Object value;
  final String group;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final caption = theme.textTheme.bodySmall?.copyWith(
      color: scheme.onSurfaceVariant,
    );
    final (Widget sample, String detail) = switch (value) {
      final Color color => (_ColorSample(color: color), hexOf(color)),
      final TextStyle style => (
        Text("Blaze the red fox", style: style),
        "size ${_number(style.fontSize!)}, "
            "weight ${style.fontWeight!.value}, "
            "line height ${_number(style.height!)}, "
            "letter spacing ${_number(style.letterSpacing!)}",
      ),
      final double number => (
        _DimensionSample(group: group, value: number),
        _number(number),
      ),
      _ => (const SizedBox.shrink(), value.toString()),
    };
    final label = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(name, style: theme.textTheme.bodyMedium),
        Text(detail, style: caption),
      ],
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        TokenSpacing.lg,
        0,
        TokenSpacing.lg,
        TokenSpacing.md,
      ),
      // A text style sample is wide, so it goes above its name.
      child: value is TextStyle
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [sample, label],
            )
          : Row(
              children: [
                SizedBox(
                  width: TokenSize.minTarget + TokenSpacing.xxl,
                  child: Align(
                    alignment: AlignmentDirectional.centerStart,
                    child: sample,
                  ),
                ),
                const SizedBox(width: TokenSpacing.md),
                Expanded(child: label),
              ],
            ),
    );
  }
}

class _ColorSample extends StatelessWidget {
  const new({required this.color});

  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: TokenSize.minTarget,
      height: TokenSize.minTarget,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(TokenRadius.small),
        border: Border.all(color: Theme.of(context).colorScheme.outline),
      ),
    );
  }
}

class _DimensionSample extends StatelessWidget {
  const new({required this.group, required this.value});

  final String group;
  final double value;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return switch (group) {
      "spacing." => Container(
        width: value,
        height: TokenSpacing.lg,
        color: scheme.primary,
      ),
      "radius." => Container(
        width: TokenSize.minTarget,
        height: TokenSize.minTarget,
        decoration: BoxDecoration(
          color: scheme.primaryContainer,
          borderRadius: BorderRadius.circular(value),
        ),
      ),
      "elevation." => Material(
        elevation: value,
        color: scheme.surfaceContainerLowest,
        shadowColor: scheme.primary,
        borderRadius: BorderRadius.circular(TokenRadius.small),
        child: const SizedBox.square(dimension: TokenSize.minTarget),
      ),
      _ => Container(
        width: value,
        height: value,
        decoration: BoxDecoration(border: Border.all(color: scheme.primary)),
      ),
    };
  }
}
