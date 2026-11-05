import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";

/// Status meanings that badges and status banners show.
enum StatusTone {
  /// No status meaning, for example an informational note.
  neutral,

  /// A completed action.
  success,

  /// A state that needs attention but is not an error.
  warning,

  /// A failure.
  error,
}

/// The colors and icon of one [StatusTone].
@immutable
class StatusStyle {
  /// Creates a status style.
  const new({
    required this.container,
    required this.onContainer,
    required this.icon,
  });

  /// The background color.
  final Color container;

  /// The text and icon color on [container].
  final Color onContainer;

  /// The status icon. A neutral style has the info icon.
  final IconData icon;
}

/// TailTag colors that the Material [ColorScheme] has no role for.
@immutable
class TailTagColors extends ThemeExtension<TailTagColors> {
  /// Creates the TailTag colors.
  const new({
    required this.success,
    required this.onSuccess,
    required this.successContainer,
    required this.onSuccessContainer,
    required this.warning,
    required this.onWarning,
    required this.warningContainer,
    required this.onWarningContainer,
  });

  /// The V0 light values from `tokens.json`.
  static const light = TailTagColors(
    success: TokenStatusColors.success,
    onSuccess: TokenStatusColors.onSuccess,
    successContainer: TokenStatusColors.successContainer,
    onSuccessContainer: TokenStatusColors.onSuccessContainer,
    warning: TokenStatusColors.warning,
    onWarning: TokenStatusColors.onWarning,
    warningContainer: TokenStatusColors.warningContainer,
    onWarningContainer: TokenStatusColors.onWarningContainer,
  );

  /// Token `color.status.success`.
  final Color success;

  /// Token `color.status.onSuccess`.
  final Color onSuccess;

  /// Token `color.status.successContainer`.
  final Color successContainer;

  /// Token `color.status.onSuccessContainer`.
  final Color onSuccessContainer;

  /// Token `color.status.warning`.
  final Color warning;

  /// Token `color.status.onWarning`.
  final Color onWarning;

  /// Token `color.status.warningContainer`.
  final Color warningContainer;

  /// Token `color.status.onWarningContainer`.
  final Color onWarningContainer;

  /// The colors and icon for [tone], using [scheme] for the Material roles.
  StatusStyle status(StatusTone tone, ColorScheme scheme) {
    return switch (tone) {
      StatusTone.neutral => StatusStyle(
        container: scheme.surfaceContainerHighest,
        onContainer: scheme.onSurfaceVariant,
        icon: Icons.info_outlined,
      ),
      StatusTone.success => StatusStyle(
        container: successContainer,
        onContainer: onSuccessContainer,
        icon: Icons.check_circle_outlined,
      ),
      StatusTone.warning => StatusStyle(
        container: warningContainer,
        onContainer: onWarningContainer,
        icon: Icons.warning_amber_outlined,
      ),
      StatusTone.error => StatusStyle(
        container: scheme.errorContainer,
        onContainer: scheme.onErrorContainer,
        // Icons.error_outlined draws a filled disc. This glyph matches the
        // outline icons of the other tones.
        icon: Icons.error_outline,
      ),
    };
  }

  @override
  TailTagColors copyWith({
    Color? success,
    Color? onSuccess,
    Color? successContainer,
    Color? onSuccessContainer,
    Color? warning,
    Color? onWarning,
    Color? warningContainer,
    Color? onWarningContainer,
  }) {
    return TailTagColors(
      success: success ?? this.success,
      onSuccess: onSuccess ?? this.onSuccess,
      successContainer: successContainer ?? this.successContainer,
      onSuccessContainer: onSuccessContainer ?? this.onSuccessContainer,
      warning: warning ?? this.warning,
      onWarning: onWarning ?? this.onWarning,
      warningContainer: warningContainer ?? this.warningContainer,
      onWarningContainer: onWarningContainer ?? this.onWarningContainer,
    );
  }

  @override
  TailTagColors lerp(TailTagColors? other, double t) {
    if (other == null) {
      return this;
    }
    Color mix(Color a, Color b) => Color.lerp(a, b, t)!;
    return TailTagColors(
      success: mix(success, other.success),
      onSuccess: mix(onSuccess, other.onSuccess),
      successContainer: mix(successContainer, other.successContainer),
      onSuccessContainer: mix(onSuccessContainer, other.onSuccessContainer),
      warning: mix(warning, other.warning),
      onWarning: mix(onWarning, other.onWarning),
      warningContainer: mix(warningContainer, other.warningContainer),
      onWarningContainer: mix(onWarningContainer, other.onWarningContainer),
    );
  }
}

/// The width of the focus ring around a focused control.
const double focusRingWidth = TokenSize.focusRingWidth;

/// The space between the control edge and its focus ring.
///
/// The gap keeps a `primary` ring visible next to a `primary` or `error`
/// fill.
const double focusRingGap = TokenSize.focusRingGap;

/// The focus ring side: [focusRingWidth] wide, [focusRingGap] outside the
/// control edge, in [color].
///
/// A `strokeAlign` above 1 moves the stroke past the outside of the edge.
BorderSide focusRingSide(Color color) {
  return BorderSide(
    color: color,
    width: focusRingWidth,
    strokeAlign: 1 + 2 * focusRingGap / focusRingWidth,
  );
}

/// The V0 color scheme, built from `tokens.json` values.
///
/// It does not call `ColorScheme.fromSeed`, so a Flutter upgrade cannot
/// change the palette.
const ColorScheme tailTagColorScheme = ColorScheme(
  brightness: Brightness.light,
  primary: TokenColors.primary,
  onPrimary: TokenColors.onPrimary,
  primaryContainer: TokenColors.primaryContainer,
  onPrimaryContainer: TokenColors.onPrimaryContainer,
  primaryFixed: TokenColors.primaryFixed,
  primaryFixedDim: TokenColors.primaryFixedDim,
  onPrimaryFixed: TokenColors.onPrimaryFixed,
  onPrimaryFixedVariant: TokenColors.onPrimaryFixedVariant,
  secondary: TokenColors.secondary,
  onSecondary: TokenColors.onSecondary,
  secondaryContainer: TokenColors.secondaryContainer,
  onSecondaryContainer: TokenColors.onSecondaryContainer,
  secondaryFixed: TokenColors.secondaryFixed,
  secondaryFixedDim: TokenColors.secondaryFixedDim,
  onSecondaryFixed: TokenColors.onSecondaryFixed,
  onSecondaryFixedVariant: TokenColors.onSecondaryFixedVariant,
  tertiary: TokenColors.tertiary,
  onTertiary: TokenColors.onTertiary,
  tertiaryContainer: TokenColors.tertiaryContainer,
  onTertiaryContainer: TokenColors.onTertiaryContainer,
  tertiaryFixed: TokenColors.tertiaryFixed,
  tertiaryFixedDim: TokenColors.tertiaryFixedDim,
  onTertiaryFixed: TokenColors.onTertiaryFixed,
  onTertiaryFixedVariant: TokenColors.onTertiaryFixedVariant,
  error: TokenColors.error,
  onError: TokenColors.onError,
  errorContainer: TokenColors.errorContainer,
  onErrorContainer: TokenColors.onErrorContainer,
  surface: TokenColors.surface,
  onSurface: TokenColors.onSurface,
  surfaceDim: TokenColors.surfaceDim,
  surfaceBright: TokenColors.surfaceBright,
  surfaceContainerLowest: TokenColors.surfaceContainerLowest,
  surfaceContainerLow: TokenColors.surfaceContainerLow,
  surfaceContainer: TokenColors.surfaceContainer,
  surfaceContainerHigh: TokenColors.surfaceContainerHigh,
  surfaceContainerHighest: TokenColors.surfaceContainerHighest,
  onSurfaceVariant: TokenColors.onSurfaceVariant,
  outline: TokenColors.outline,
  outlineVariant: TokenColors.outlineVariant,
  shadow: TokenColors.shadow,
  scrim: TokenColors.scrim,
  inverseSurface: TokenColors.inverseSurface,
  onInverseSurface: TokenColors.onInverseSurface,
  inversePrimary: TokenColors.inversePrimary,
  surfaceTint: TokenColors.surfaceTint,
);

/// The V0 text theme. Each style has no font family, so the platform system
/// font from the Flutter default typography stays.
const TextTheme tailTagTextTheme = TextTheme(
  displayLarge: TokenTypography.displayLarge,
  displayMedium: TokenTypography.displayMedium,
  displaySmall: TokenTypography.displaySmall,
  headlineLarge: TokenTypography.headlineLarge,
  headlineMedium: TokenTypography.headlineMedium,
  headlineSmall: TokenTypography.headlineSmall,
  titleLarge: TokenTypography.titleLarge,
  titleMedium: TokenTypography.titleMedium,
  titleSmall: TokenTypography.titleSmall,
  bodyLarge: TokenTypography.bodyLarge,
  bodyMedium: TokenTypography.bodyMedium,
  bodySmall: TokenTypography.bodySmall,
  labelLarge: TokenTypography.labelLarge,
  labelMedium: TokenTypography.labelMedium,
  labelSmall: TokenTypography.labelSmall,
);

/// The focus ring from [focusRingSide] in [color] while focused, and
/// [otherwise] in every other state.
WidgetStateBorderSide focusRing(Color color, {BorderSide? otherwise}) {
  return WidgetStateBorderSide.resolveWith((states) {
    if (states.contains(WidgetState.focused) &&
        !states.contains(WidgetState.disabled)) {
      return focusRingSide(color);
    }
    return otherwise;
  });
}

/// Reads the TailTag theme parts that Material has no role for.
extension TailTagThemeContext on BuildContext {
  /// The TailTag status colors of the current theme.
  TailTagColors get tailTag => Theme.of(this).extension<TailTagColors>()!;

  /// The colors and icon of [tone] in the current theme.
  StatusStyle statusStyle(StatusTone tone) {
    return tailTag.status(tone, Theme.of(this).colorScheme);
  }
}

/// Builds the V0 light theme from docs/design/components.md.
///
/// The "Con badge" direction: every pressable control is a pill whose
/// visible shape fills `size.minTarget`, so a player can hit it with fursuit
/// paws. Raised surfaces are white card stock on the tinted screen, and a
/// selected control is solid violet.
ThemeData buildTailTagTheme() {
  const scheme = tailTagColorScheme;
  const stadium = StadiumBorder();
  final outline = BorderSide(color: scheme.outline);

  // Pressable pills are at least size.minTarget high, with the label in
  // titleMedium. The shape is the touch target.
  const buttonMinimumSize = WidgetStatePropertyAll(
    Size(TokenSize.minTarget, TokenSize.minTarget),
  );
  const buttonPadding = WidgetStatePropertyAll(
    EdgeInsets.symmetric(horizontal: TokenSpacing.xl),
  );
  const buttonText = WidgetStatePropertyAll(TokenTypography.titleMedium);

  OutlineInputBorder inputBorder(Color color, {double width = 1}) {
    return OutlineInputBorder(
      borderRadius: BorderRadius.circular(TokenRadius.medium),
      borderSide: BorderSide(color: color, width: width),
    );
  }

  return ThemeData(
    colorScheme: scheme,
    textTheme: tailTagTextTheme,
    extensions: const [TailTagColors.light],
    filledButtonTheme: FilledButtonThemeData(
      style: ButtonStyle(
        shape: const WidgetStatePropertyAll(stadium),
        minimumSize: buttonMinimumSize,
        padding: buttonPadding,
        textStyle: buttonText,
        iconSize: const WidgetStatePropertyAll(TokenSize.iconSmall),
        side: focusRing(scheme.primary),
      ),
    ),
    // V0 components use no outlined button. The theme stays so that debug
    // screens that still use one match the other buttons.
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: ButtonStyle(
        shape: const WidgetStatePropertyAll(stadium),
        minimumSize: buttonMinimumSize,
        padding: buttonPadding,
        textStyle: buttonText,
        iconSize: const WidgetStatePropertyAll(TokenSize.iconSmall),
        side: WidgetStateBorderSide.resolveWith((states) {
          if (states.contains(WidgetState.disabled)) {
            return BorderSide(color: scheme.onSurface.withValues(alpha: 0.12));
          }
          if (states.contains(WidgetState.focused)) {
            return focusRingSide(scheme.primary);
          }
          return outline;
        }),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: ButtonStyle(
        shape: const WidgetStatePropertyAll(stadium),
        minimumSize: buttonMinimumSize,
        padding: const WidgetStatePropertyAll(
          EdgeInsets.symmetric(horizontal: TokenSpacing.lg),
        ),
        textStyle: buttonText,
        iconSize: const WidgetStatePropertyAll(TokenSize.iconSmall),
        side: focusRing(scheme.primary),
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: ButtonStyle(
        foregroundColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.disabled)) {
            return scheme.onSurface.withValues(alpha: 0.38);
          }
          return scheme.onSurfaceVariant;
        }),
        iconSize: const WidgetStatePropertyAll(TokenSize.iconMedium),
        side: focusRing(scheme.primary),
      ),
    ),
    inputDecorationTheme: InputDecorationThemeData(
      // A white write-in box on the tinted screen.
      filled: true,
      fillColor: scheme.surfaceContainerLowest,
      border: inputBorder(scheme.outline),
      enabledBorder: inputBorder(scheme.outline),
      focusedBorder: inputBorder(scheme.primary, width: focusRingWidth),
      errorBorder: inputBorder(scheme.error),
      focusedErrorBorder: inputBorder(scheme.error, width: focusRingWidth),
      disabledBorder: inputBorder(scheme.onSurface.withValues(alpha: 0.12)),
      helperMaxLines: 3,
      errorMaxLines: 3,
    ),
    // Card stock: a white card with a violet-tinted shadow on the tinted
    // screen.
    cardTheme: CardThemeData(
      color: scheme.surfaceContainerLowest,
      elevation: TokenElevation.level1,
      shadowColor: scheme.primary,
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(TokenRadius.large),
      ),
    ),
    listTileTheme: ListTileThemeData(
      contentPadding: const EdgeInsets.symmetric(horizontal: TokenSpacing.lg),
      horizontalTitleGap: TokenSpacing.md,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(TokenRadius.large),
      ),
      titleTextStyle: TokenTypography.titleMedium.copyWith(
        color: scheme.onSurface,
      ),
      subtitleTextStyle: TokenTypography.bodyMedium.copyWith(
        color: scheme.onSurfaceVariant,
      ),
      iconColor: scheme.onSurfaceVariant,
      selectedColor: scheme.onPrimaryContainer,
      selectedTileColor: scheme.primaryContainer,
    ),
    chipTheme: ChipThemeData(
      shape: stadium,
      padding: const EdgeInsets.symmetric(
        horizontal: TokenSpacing.sm,
        vertical: TokenSpacing.xs,
      ),
      labelStyle: TokenTypography.labelLarge.copyWith(
        color: WidgetStateColor.resolveWith((states) {
          if (states.contains(WidgetState.disabled)) {
            return scheme.onSurface.withValues(alpha: 0.38);
          }
          if (states.contains(WidgetState.selected)) {
            return scheme.onPrimary;
          }
          return scheme.onSurfaceVariant;
        }),
      ),
      color: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return states.contains(WidgetState.disabled)
              ? scheme.onSurface.withValues(alpha: 0.12)
              : scheme.primary;
        }
        return scheme.surfaceContainerLowest;
      }),
      checkmarkColor: scheme.onPrimary,
      iconTheme: const IconThemeData(size: TokenSize.iconSmall),
      side: WidgetStateBorderSide.resolveWith((states) {
        if (states.contains(WidgetState.focused) &&
            !states.contains(WidgetState.disabled)) {
          return focusRingSide(scheme.primary);
        }
        if (states.contains(WidgetState.selected)) {
          return BorderSide.none;
        }
        if (states.contains(WidgetState.disabled)) {
          return BorderSide(color: scheme.onSurface.withValues(alpha: 0.12));
        }
        return outline;
      }),
    ),
    switchTheme: SwitchThemeData(
      // The thumb icon is the non-color cue for on and off.
      thumbIcon: WidgetStateProperty.resolveWith((states) {
        return Icon(
          states.contains(WidgetState.selected) ? Icons.check : Icons.close,
        );
      }),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: scheme.surfaceContainerLowest,
      elevation: TokenElevation.level3,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(TokenRadius.extraLarge),
      ),
      titleTextStyle: TokenTypography.headlineSmall.copyWith(
        color: scheme.onSurface,
      ),
      contentTextStyle: TokenTypography.bodyMedium.copyWith(
        color: scheme.onSurfaceVariant,
      ),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: scheme.surfaceContainerLowest,
      elevation: TokenElevation.level1,
      showDragHandle: true,
      dragHandleColor: scheme.onSurfaceVariant,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(TokenRadius.extraLarge),
        ),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: scheme.inverseSurface,
      contentTextStyle: TokenTypography.bodyMedium.copyWith(
        color: scheme.onInverseSurface,
      ),
      insetPadding: const EdgeInsets.all(TokenSpacing.lg),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(TokenRadius.medium),
      ),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: scheme.primary,
      strokeCap: StrokeCap.round,
    ),
    appBarTheme: AppBarThemeData(
      // The Material look on both platforms: the title starts at the leading
      // edge on iOS too.
      centerTitle: false,
      backgroundColor: WidgetStateColor.resolveWith((states) {
        if (states.contains(WidgetState.scrolledUnder)) {
          return scheme.surfaceContainer;
        }
        return scheme.surface;
      }),
      foregroundColor: scheme.onSurface,
      elevation: TokenElevation.level0,
      scrolledUnderElevation: TokenElevation.level2,
      surfaceTintColor: Colors.transparent,
      titleTextStyle: TokenTypography.titleLarge.copyWith(
        color: scheme.onSurface,
      ),
      actionsIconTheme: IconThemeData(
        color: scheme.onSurfaceVariant,
        size: TokenSize.iconMedium,
      ),
    ),
    actionIconTheme: ActionIconThemeData(
      backButtonIconBuilder: (context) => Icon(Icons.adaptive.arrow_back),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surfaceContainer,
      elevation: TokenElevation.level2,
      surfaceTintColor: Colors.transparent,
      // A selected destination is solid violet, like a selected chip.
      indicatorColor: scheme.primary,
      indicatorShape: stadium,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        return TokenTypography.labelMedium.copyWith(
          color: states.contains(WidgetState.selected)
              ? scheme.primary
              : scheme.onSurfaceVariant,
        );
      }),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        return IconThemeData(
          size: TokenSize.iconMedium,
          color: states.contains(WidgetState.selected)
              ? scheme.onPrimary
              : scheme.onSurfaceVariant,
        );
      }),
    ),
  );
}
