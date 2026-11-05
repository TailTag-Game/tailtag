// The V0 design token values from docs/design/tokens.json.
//
// Each value is written by hand. Its doc comment names its token. The test
// test/core/ui/token_parity_test.dart fails when a value differs from
// tokens.json, or when a token is missing on either side. Change a value in
// tokens.json first, then here.
//
// `font.family.system` has no Dart value: the text styles set no font
// family, so Flutter uses the platform system font.

import "package:flutter/painting.dart";

/// Material 3 color roles from `color.scheme`.
abstract final class TokenColors {
  /// Token `color.scheme.primary`.
  static const primary = Color(0xFF6920FF);

  /// Token `color.scheme.onPrimary`.
  static const onPrimary = Color(0xFFFFFFFF);

  /// Token `color.scheme.primaryContainer`.
  static const primaryContainer = Color(0xFFE8DEFF);

  /// Token `color.scheme.onPrimaryContainer`.
  static const onPrimaryContainer = Color(0xFF4F00D0);

  /// Token `color.scheme.primaryFixed`.
  static const primaryFixed = Color(0xFFE8DEFF);

  /// Token `color.scheme.primaryFixedDim`.
  static const primaryFixedDim = Color(0xFFCDBDFF);

  /// Token `color.scheme.onPrimaryFixed`.
  static const onPrimaryFixed = Color(0xFF20005F);

  /// Token `color.scheme.onPrimaryFixedVariant`.
  static const onPrimaryFixedVariant = Color(0xFF4F00D0);

  /// Token `color.scheme.secondary`.
  static const secondary = Color(0xFF6A5779);

  /// Token `color.scheme.onSecondary`.
  static const onSecondary = Color(0xFFFFFFFF);

  /// Token `color.scheme.secondaryContainer`.
  static const secondaryContainer = Color(0xFFF1DAFF);

  /// Token `color.scheme.onSecondaryContainer`.
  static const onSecondaryContainer = Color(0xFF514060);

  /// Token `color.scheme.secondaryFixed`.
  static const secondaryFixed = Color(0xFFF1DAFF);

  /// Token `color.scheme.secondaryFixedDim`.
  static const secondaryFixedDim = Color(0xFFD5BEE5);

  /// Token `color.scheme.onSecondaryFixed`.
  static const onSecondaryFixed = Color(0xFF241532);

  /// Token `color.scheme.onSecondaryFixedVariant`.
  static const onSecondaryFixedVariant = Color(0xFF514060);

  /// Token `color.scheme.tertiary`.
  static const tertiary = Color(0xFF78517B);

  /// Token `color.scheme.onTertiary`.
  static const onTertiary = Color(0xFFFFFFFF);

  /// Token `color.scheme.tertiaryContainer`.
  static const tertiaryContainer = Color(0xFFFFD5FF);

  /// Token `color.scheme.onTertiaryContainer`.
  static const onTertiaryContainer = Color(0xFF5E3962);

  /// Token `color.scheme.tertiaryFixed`.
  static const tertiaryFixed = Color(0xFFFFD5FF);

  /// Token `color.scheme.tertiaryFixedDim`.
  static const tertiaryFixedDim = Color(0xFFE7B7E8);

  /// Token `color.scheme.onTertiaryFixed`.
  static const onTertiaryFixed = Color(0xFF2E0D34);

  /// Token `color.scheme.onTertiaryFixedVariant`.
  static const onTertiaryFixedVariant = Color(0xFF5E3962);

  /// Token `color.scheme.error`.
  static const error = Color(0xFFBA1A1A);

  /// Token `color.scheme.onError`.
  static const onError = Color(0xFFFFFFFF);

  /// Token `color.scheme.errorContainer`.
  static const errorContainer = Color(0xFFFFDAD6);

  /// Token `color.scheme.onErrorContainer`.
  static const onErrorContainer = Color(0xFF93000A);

  /// Token `color.scheme.surface`.
  static const surface = Color(0xFFFDF7FF);

  /// Token `color.scheme.onSurface`.
  static const onSurface = Color(0xFF1D1A24);

  /// Token `color.scheme.surfaceDim`.
  static const surfaceDim = Color(0xFFDED7E6);

  /// Token `color.scheme.surfaceBright`.
  static const surfaceBright = Color(0xFFFDF7FF);

  /// Token `color.scheme.surfaceContainerLowest`.
  static const surfaceContainerLowest = Color(0xFFFFFFFF);

  /// Token `color.scheme.surfaceContainerLow`.
  static const surfaceContainerLow = Color(0xFFF8F1FF);

  /// Token `color.scheme.surfaceContainer`.
  static const surfaceContainer = Color(0xFFF2EBFA);

  /// Token `color.scheme.surfaceContainerHigh`.
  static const surfaceContainerHigh = Color(0xFFECE5F4);

  /// Token `color.scheme.surfaceContainerHighest`.
  static const surfaceContainerHighest = Color(0xFFE6E0EF);

  /// Token `color.scheme.onSurfaceVariant`.
  static const onSurfaceVariant = Color(0xFF494553);

  /// Token `color.scheme.outline`.
  static const outline = Color(0xFF7A7585);

  /// Token `color.scheme.outlineVariant`.
  static const outlineVariant = Color(0xFFCAC4D5);

  /// Token `color.scheme.shadow`.
  static const shadow = Color(0xFF000000);

  /// Token `color.scheme.scrim`.
  static const scrim = Color(0xFF000000);

  /// Token `color.scheme.inverseSurface`.
  static const inverseSurface = Color(0xFF322F3A);

  /// Token `color.scheme.onInverseSurface`.
  static const onInverseSurface = Color(0xFFF5EEFD);

  /// Token `color.scheme.inversePrimary`.
  static const inversePrimary = Color(0xFFCDBDFF);

  /// Token `color.scheme.surfaceTint`.
  static const surfaceTint = Color(0xFF6920FF);
}

/// TailTag status colors from `color.status`.
abstract final class TokenStatusColors {
  /// Token `color.status.success`.
  static const success = Color(0xFF1B6D24);

  /// Token `color.status.onSuccess`.
  static const onSuccess = Color(0xFFFFFFFF);

  /// Token `color.status.successContainer`.
  static const successContainer = Color(0xFFCFEAC7);

  /// Token `color.status.onSuccessContainer`.
  static const onSuccessContainer = Color(0xFF002204);

  /// Token `color.status.warning`.
  static const warning = Color(0xFF7E5700);

  /// Token `color.status.onWarning`.
  static const onWarning = Color(0xFFFFFFFF);

  /// Token `color.status.warningContainer`.
  static const warningContainer = Color(0xFFFFDEAC);

  /// Token `color.status.onWarningContainer`.
  static const onWarningContainer = Color(0xFF281900);
}

/// Spacing steps from `spacing`, in logical pixels.
abstract final class TokenSpacing {
  /// Token `spacing.xs`.
  static const double xs = 4;

  /// Token `spacing.sm`.
  static const double sm = 8;

  /// Token `spacing.md`.
  static const double md = 12;

  /// Token `spacing.lg`.
  static const double lg = 16;

  /// Token `spacing.xl`.
  static const double xl = 24;

  /// Token `spacing.xxl`.
  static const double xxl = 32;

  /// Token `spacing.xxxl`.
  static const double xxxl = 48;
}

/// Corner radii from `radius`, in logical pixels.
abstract final class TokenRadius {
  /// Token `radius.none`.
  static const double none = 0;

  /// Token `radius.extraSmall`.
  static const double extraSmall = 4;

  /// Token `radius.small`.
  static const double small = 8;

  /// Token `radius.medium`.
  static const double medium = 12;

  /// Token `radius.large`.
  static const double large = 16;

  /// Token `radius.extraLarge`.
  static const double extraLarge = 28;
}

/// Elevation levels from `elevation`.
abstract final class TokenElevation {
  /// Token `elevation.level0`.
  static const double level0 = 0;

  /// Token `elevation.level1`.
  static const double level1 = 1;

  /// Token `elevation.level2`.
  static const double level2 = 3;

  /// Token `elevation.level3`.
  static const double level3 = 6;

  /// Token `elevation.level4`.
  static const double level4 = 8;

  /// Token `elevation.level5`.
  static const double level5 = 12;
}

/// Sizes from `size`, in logical pixels.
abstract final class TokenSize {
  /// Token `size.minTarget`.
  static const double minTarget = 48;

  /// Token `size.icon.small`.
  static const double iconSmall = 18;

  /// Token `size.icon.medium`.
  static const double iconMedium = 24;

  /// Token `size.icon.large`.
  static const double iconLarge = 48;

  /// Token `size.avatar.small`.
  static const double avatarSmall = 40;

  /// Token `size.avatar.large`.
  static const double avatarLarge = 80;

  /// Token `size.focusRing.width`.
  static const double focusRingWidth = 2;

  /// Token `size.focusRing.gap`.
  static const double focusRingGap = 2;
}

/// Text styles from `typography`, with no font family.
///
/// The platform system font comes from the Flutter default typography.
abstract final class TokenTypography {
  /// Token `typography.displayLarge`.
  static const displayLarge = TextStyle(
    fontSize: 57,
    fontWeight: FontWeight.w400,
    letterSpacing: -0.25,
    height: 1.12,
  );

  /// Token `typography.displayMedium`.
  static const displayMedium = TextStyle(
    fontSize: 45,
    fontWeight: FontWeight.w400,
    letterSpacing: 0,
    height: 1.16,
  );

  /// Token `typography.displaySmall`.
  static const displaySmall = TextStyle(
    fontSize: 36,
    fontWeight: FontWeight.w400,
    letterSpacing: 0,
    height: 1.22,
  );

  /// Token `typography.headlineLarge`.
  static const headlineLarge = TextStyle(
    fontSize: 32,
    fontWeight: FontWeight.w400,
    letterSpacing: 0,
    height: 1.25,
  );

  /// Token `typography.headlineMedium`.
  static const headlineMedium = TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w400,
    letterSpacing: 0,
    height: 1.29,
  );

  /// Token `typography.headlineSmall`.
  static const headlineSmall = TextStyle(
    fontSize: 24,
    fontWeight: FontWeight.w600,
    letterSpacing: 0,
    height: 1.33,
  );

  /// Token `typography.titleLarge`.
  static const titleLarge = TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.w600,
    letterSpacing: 0,
    height: 1.27,
  );

  /// Token `typography.titleMedium`.
  static const titleMedium = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.15,
    height: 1.5,
  );

  /// Token `typography.titleSmall`.
  static const titleSmall = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.1,
    height: 1.43,
  );

  /// Token `typography.bodyLarge`.
  static const bodyLarge = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w400,
    letterSpacing: 0.5,
    height: 1.5,
  );

  /// Token `typography.bodyMedium`.
  static const bodyMedium = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    letterSpacing: 0.25,
    height: 1.43,
  );

  /// Token `typography.bodySmall`.
  static const bodySmall = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    letterSpacing: 0.4,
    height: 1.33,
  );

  /// Token `typography.labelLarge`.
  static const labelLarge = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.1,
    height: 1.43,
  );

  /// Token `typography.labelMedium`.
  static const labelMedium = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.5,
    height: 1.33,
  );

  /// Token `typography.labelSmall`.
  static const labelSmall = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.5,
    height: 1.45,
  );
}
