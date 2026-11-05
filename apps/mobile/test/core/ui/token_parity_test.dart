import "dart:convert";
import "dart:io";

import "package:flutter/foundation.dart";
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";

/// `docs/design/tokens.json`, read from the `apps/mobile` package root.
final File _tokensFile = File(
  ["..", "..", "docs", "design", "tokens.json"].join(Platform.pathSeparator),
);

/// `lib/core/ui/tokens.dart`, whose doc comments name each token.
final File _dartTokensFile = File(
  ["lib", "core", "ui", "tokens.dart"].join(Platform.pathSeparator),
);

/// Tokens with no Dart value, and why.
const _noDartValue = {
  // The text styles set no font family, so Flutter uses the system font.
  "font.family.system",
};

/// Each Dart token value by its `tokens.json` name.
final Map<String, Object> _dartTokens = {
  "color.scheme.primary": TokenColors.primary,
  "color.scheme.onPrimary": TokenColors.onPrimary,
  "color.scheme.primaryContainer": TokenColors.primaryContainer,
  "color.scheme.onPrimaryContainer": TokenColors.onPrimaryContainer,
  "color.scheme.primaryFixed": TokenColors.primaryFixed,
  "color.scheme.primaryFixedDim": TokenColors.primaryFixedDim,
  "color.scheme.onPrimaryFixed": TokenColors.onPrimaryFixed,
  "color.scheme.onPrimaryFixedVariant": TokenColors.onPrimaryFixedVariant,
  "color.scheme.secondary": TokenColors.secondary,
  "color.scheme.onSecondary": TokenColors.onSecondary,
  "color.scheme.secondaryContainer": TokenColors.secondaryContainer,
  "color.scheme.onSecondaryContainer": TokenColors.onSecondaryContainer,
  "color.scheme.secondaryFixed": TokenColors.secondaryFixed,
  "color.scheme.secondaryFixedDim": TokenColors.secondaryFixedDim,
  "color.scheme.onSecondaryFixed": TokenColors.onSecondaryFixed,
  "color.scheme.onSecondaryFixedVariant": TokenColors.onSecondaryFixedVariant,
  "color.scheme.tertiary": TokenColors.tertiary,
  "color.scheme.onTertiary": TokenColors.onTertiary,
  "color.scheme.tertiaryContainer": TokenColors.tertiaryContainer,
  "color.scheme.onTertiaryContainer": TokenColors.onTertiaryContainer,
  "color.scheme.tertiaryFixed": TokenColors.tertiaryFixed,
  "color.scheme.tertiaryFixedDim": TokenColors.tertiaryFixedDim,
  "color.scheme.onTertiaryFixed": TokenColors.onTertiaryFixed,
  "color.scheme.onTertiaryFixedVariant": TokenColors.onTertiaryFixedVariant,
  "color.scheme.error": TokenColors.error,
  "color.scheme.onError": TokenColors.onError,
  "color.scheme.errorContainer": TokenColors.errorContainer,
  "color.scheme.onErrorContainer": TokenColors.onErrorContainer,
  "color.scheme.surface": TokenColors.surface,
  "color.scheme.onSurface": TokenColors.onSurface,
  "color.scheme.surfaceDim": TokenColors.surfaceDim,
  "color.scheme.surfaceBright": TokenColors.surfaceBright,
  "color.scheme.surfaceContainerLowest": TokenColors.surfaceContainerLowest,
  "color.scheme.surfaceContainerLow": TokenColors.surfaceContainerLow,
  "color.scheme.surfaceContainer": TokenColors.surfaceContainer,
  "color.scheme.surfaceContainerHigh": TokenColors.surfaceContainerHigh,
  "color.scheme.surfaceContainerHighest": TokenColors.surfaceContainerHighest,
  "color.scheme.onSurfaceVariant": TokenColors.onSurfaceVariant,
  "color.scheme.outline": TokenColors.outline,
  "color.scheme.outlineVariant": TokenColors.outlineVariant,
  "color.scheme.shadow": TokenColors.shadow,
  "color.scheme.scrim": TokenColors.scrim,
  "color.scheme.inverseSurface": TokenColors.inverseSurface,
  "color.scheme.onInverseSurface": TokenColors.onInverseSurface,
  "color.scheme.inversePrimary": TokenColors.inversePrimary,
  "color.scheme.surfaceTint": TokenColors.surfaceTint,
  "color.status.success": TokenStatusColors.success,
  "color.status.onSuccess": TokenStatusColors.onSuccess,
  "color.status.successContainer": TokenStatusColors.successContainer,
  "color.status.onSuccessContainer": TokenStatusColors.onSuccessContainer,
  "color.status.warning": TokenStatusColors.warning,
  "color.status.onWarning": TokenStatusColors.onWarning,
  "color.status.warningContainer": TokenStatusColors.warningContainer,
  "color.status.onWarningContainer": TokenStatusColors.onWarningContainer,
  "spacing.xs": TokenSpacing.xs,
  "spacing.sm": TokenSpacing.sm,
  "spacing.md": TokenSpacing.md,
  "spacing.lg": TokenSpacing.lg,
  "spacing.xl": TokenSpacing.xl,
  "spacing.xxl": TokenSpacing.xxl,
  "spacing.xxxl": TokenSpacing.xxxl,
  "radius.none": TokenRadius.none,
  "radius.extraSmall": TokenRadius.extraSmall,
  "radius.small": TokenRadius.small,
  "radius.medium": TokenRadius.medium,
  "radius.large": TokenRadius.large,
  "radius.extraLarge": TokenRadius.extraLarge,
  "elevation.level0": TokenElevation.level0,
  "elevation.level1": TokenElevation.level1,
  "elevation.level2": TokenElevation.level2,
  "elevation.level3": TokenElevation.level3,
  "elevation.level4": TokenElevation.level4,
  "elevation.level5": TokenElevation.level5,
  "size.minTarget": TokenSize.minTarget,
  "size.icon.small": TokenSize.iconSmall,
  "size.icon.medium": TokenSize.iconMedium,
  "size.icon.large": TokenSize.iconLarge,
  "size.avatar.small": TokenSize.avatarSmall,
  "size.avatar.large": TokenSize.avatarLarge,
  "size.focusRing.width": TokenSize.focusRingWidth,
  "size.focusRing.gap": TokenSize.focusRingGap,
  "typography.displayLarge": TokenTypography.displayLarge,
  "typography.displayMedium": TokenTypography.displayMedium,
  "typography.displaySmall": TokenTypography.displaySmall,
  "typography.headlineLarge": TokenTypography.headlineLarge,
  "typography.headlineMedium": TokenTypography.headlineMedium,
  "typography.headlineSmall": TokenTypography.headlineSmall,
  "typography.titleLarge": TokenTypography.titleLarge,
  "typography.titleMedium": TokenTypography.titleMedium,
  "typography.titleSmall": TokenTypography.titleSmall,
  "typography.bodyLarge": TokenTypography.bodyLarge,
  "typography.bodyMedium": TokenTypography.bodyMedium,
  "typography.bodySmall": TokenTypography.bodySmall,
  "typography.labelLarge": TokenTypography.labelLarge,
  "typography.labelMedium": TokenTypography.labelMedium,
  "typography.labelSmall": TokenTypography.labelSmall,
};

/// Every token in `tokens.json` by its dotted name.
Map<String, Map<String, Object?>> _jsonTokens() {
  final tokens = <String, Map<String, Object?>>{};
  void walk(Object? node, List<String> path) {
    if (node is! Map<String, Object?>) {
      return;
    }
    if (node.containsKey(r"$value")) {
      tokens[path.join(".")] = node;
      return;
    }
    for (final MapEntry(:key, :value) in node.entries) {
      if (!key.startsWith(r"$")) {
        walk(value, [...path, key]);
      }
    }
  }

  walk(jsonDecode(_tokensFile.readAsStringSync()), []);
  return tokens;
}

/// The value of a `{"value": n, "unit": "px"}` dimension.
double _px(Object? dimension) {
  final map = dimension! as Map<String, Object?>;
  expect(map["unit"], "px");
  return (map["value"]! as num).toDouble();
}

/// Each mismatch between [dart] and the JSON [token] named [name].
List<String> _mismatches(String name, Map<String, Object?> token, Object dart) {
  final value = token[r"$value"];
  final problems = <String>[];
  void check(String what, Object? actual, Object? expected) {
    if (actual != expected) {
      problems.add("$name $what: Dart $actual, tokens.json $expected");
    }
  }

  switch (token[r"$type"]) {
    case "color":
      final color = dart as Color;
      final json = value! as Map<String, Object?>;
      final hex = (json["hex"]! as String).substring(1).toUpperCase();
      check(
        "hex",
        color.toARGB32().toRadixString(16).padLeft(8, "0").toUpperCase(),
        "FF$hex",
      );
      final components = (json["components"]! as List<Object?>)
          .map((c) => (c! as num).toDouble())
          .toList();
      final channels = [color.r, color.g, color.b];
      for (var i = 0; i < 3; i++) {
        if ((channels[i] - components[i]).abs() > 0.0005) {
          problems.add(
            "$name component $i: hex gives ${channels[i]}, "
            "components give ${components[i]}",
          );
        }
      }
    case "dimension":
      check("value", dart, _px(value));
    case "number":
      check("value", dart, (value! as num).toDouble());
    case "typography":
      final style = dart as TextStyle;
      final json = value! as Map<String, Object?>;
      check("fontFamily", json["fontFamily"], "{font.family.system}");
      check("Dart fontFamily", style.fontFamily, null);
      check("fontSize", style.fontSize, _px(json["fontSize"]));
      check("fontWeight", style.fontWeight?.value, json["fontWeight"]);
      check("letterSpacing", style.letterSpacing, _px(json["letterSpacing"]));
      check(
        "lineHeight",
        style.height,
        (json["lineHeight"]! as num).toDouble(),
      );
    default:
      problems.add("$name has the unhandled type ${token[r"$type"]}");
  }
  return problems;
}

/// The named diagnostics properties of [object], for example each
/// `ColorScheme` role.
Map<String, Object?> _properties(Diagnosticable object) {
  return {
    for (final property in object.toDiagnosticsNode().getProperties())
      property.name!: property.value,
  };
}

void main() {
  final json = _jsonTokens();

  test("every tokens.json token has a Dart value, and the reverse", () {
    final dartNames = RegExp("/// Token `([^`]+)`")
        .allMatches(_dartTokensFile.readAsStringSync())
        .map((match) => match.group(1)!)
        .toSet();
    final expected = json.keys.toSet().difference(_noDartValue);

    expect(
      _noDartValue.difference(json.keys.toSet()),
      isEmpty,
      reason: "An exempt token no longer exists in tokens.json.",
    );
    expect(
      dartNames,
      expected,
      reason: "tokens.dart doc comments must name each token exactly once.",
    );
    expect(_dartTokens.keys.toSet(), expected);
  });

  test("every Dart token value matches tokens.json", () {
    final problems = [
      for (final MapEntry(:key, :value) in _dartTokens.entries)
        ..._mismatches(key, json[key]!, value),
    ];
    expect(problems, isEmpty);
  });

  test("the theme takes each color role from tokens.json by name", () {
    final scheme = _properties(buildTailTagTheme().colorScheme);
    final problems = [
      for (final MapEntry(:key, :value) in json.entries)
        if (key.startsWith("color.scheme."))
          ..._mismatches(key, value, scheme[key.substring(13)]! as Color),
    ];
    expect(problems, isEmpty);
    expect(buildTailTagTheme().colorScheme.brightness, Brightness.light);
  });

  test("the theme takes each text style from tokens.json by name", () {
    final styles = _properties(buildTailTagTheme().textTheme);
    final problems = <String>[];
    for (final MapEntry(:key, :value) in json.entries) {
      if (!key.startsWith("typography.")) {
        continue;
      }
      // ThemeData adds the platform font family, so compare the rest.
      final style = (styles[key.substring(11)]! as TextStyle).copyWith(
        fontFamily: "",
      );
      problems.addAll(
        _mismatches(
          key,
          value,
          style.merge(const TextStyle()),
        ).where((problem) => !problem.contains("ontFamily")),
      );
    }
    expect(problems, isEmpty);
  });

  test("the status colors come from tokens.json by name", () {
    const colors = TailTagColors.light;
    final status = {
      "success": colors.success,
      "onSuccess": colors.onSuccess,
      "successContainer": colors.successContainer,
      "onSuccessContainer": colors.onSuccessContainer,
      "warning": colors.warning,
      "onWarning": colors.onWarning,
      "warningContainer": colors.warningContainer,
      "onWarningContainer": colors.onWarningContainer,
    };
    final problems = [
      for (final MapEntry(:key, :value) in json.entries)
        if (key.startsWith("color.status."))
          ..._mismatches(key, value, status[key.substring(13)]!),
    ];
    expect(problems, isEmpty);
  });
}
