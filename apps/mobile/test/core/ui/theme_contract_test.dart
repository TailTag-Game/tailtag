import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";

const ColorScheme _scheme = tailTagColorScheme;

/// Resolves [property] for [states].
T? _at<T>(
  WidgetStateProperty<T>? property, [
  Set<WidgetState> states = const {},
]) => property?.resolve(states);

void main() {
  final theme = buildTailTagTheme();
  final focusRing = focusRingSide(_scheme.primary);

  // Each TailTag choice in components.md that differs from the Material 3
  // default. The token values themselves are in token_parity_test.dart.
  final cases = <String, (Object? Function(), Matcher)>{
    "filled buttons are stadium pills at least size.minTarget high": (
      () => (
        _at(theme.filledButtonTheme.style?.shape),
        _at(theme.filledButtonTheme.style?.minimumSize),
        _at(theme.filledButtonTheme.style?.textStyle),
      ),
      equals((
        const StadiumBorder(),
        const Size(TokenSize.minTarget, TokenSize.minTarget),
        TokenTypography.titleMedium,
      )),
    ),
    "text buttons are pills with spacing.lg side padding": (
      () => (
        _at(theme.textButtonTheme.style?.shape),
        _at(theme.textButtonTheme.style?.padding),
      ),
      equals((
        const StadiumBorder(),
        const EdgeInsets.symmetric(horizontal: TokenSpacing.lg),
      )),
    ),
    "focused buttons and icon buttons draw the offset primary ring": (
      () => [
        _at(theme.filledButtonTheme.style?.side, {WidgetState.focused}),
        _at(theme.textButtonTheme.style?.side, {WidgetState.focused}),
        _at(theme.iconButtonTheme.style?.side, {WidgetState.focused}),
        _at(theme.outlinedButtonTheme.style?.side, {WidgetState.focused}),
      ],
      everyElement(focusRing),
    ),
    "focused filter chips draw the offset primary ring": (
      () => WidgetStateProperty.resolveAs<BorderSide?>(theme.chipTheme.side, {
        WidgetState.focused,
      }),
      equals(focusRing),
    ),
    "selected chips are solid primary with no border": (
      () => (
        _at(theme.chipTheme.color, {WidgetState.selected}),
        WidgetStateProperty.resolveAs<BorderSide?>(theme.chipTheme.side, {
          WidgetState.selected,
        }),
        theme.chipTheme.shape,
      ),
      equals((_scheme.primary, BorderSide.none, const StadiumBorder())),
    ),
    "text fields are white boxes with a thicker primary focused border": (
      () => (
        theme.inputDecorationTheme.filled,
        theme.inputDecorationTheme.fillColor,
        theme.inputDecorationTheme.focusedBorder,
      ),
      equals((
        true,
        _scheme.surfaceContainerLowest,
        OutlineInputBorder(
          borderRadius: BorderRadius.circular(TokenRadius.medium),
          borderSide: BorderSide(
            color: _scheme.primary,
            width: TokenSize.focusRingWidth,
          ),
        ),
      )),
    ),
    "cards are white card stock with a primary shadow": (
      () => (
        theme.cardTheme.color,
        theme.cardTheme.shadowColor,
        theme.cardTheme.elevation,
        theme.cardTheme.shape,
      ),
      equals((
        _scheme.surfaceContainerLowest,
        _scheme.primary,
        TokenElevation.level1,
        RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(TokenRadius.large),
        ),
      )),
    ),
    "a selected choice row is primaryContainer with a rounded shape": (
      () => (
        theme.listTileTheme.selectedTileColor,
        theme.listTileTheme.selectedColor,
        theme.listTileTheme.shape,
      ),
      equals((
        _scheme.primaryContainer,
        _scheme.onPrimaryContainer,
        RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(TokenRadius.large),
        ),
      )),
    ),
    "the switch thumb shows a check when on and a cross when off": (
      () => (
        _at(theme.switchTheme.thumbIcon, {WidgetState.selected})?.icon,
        _at(theme.switchTheme.thumbIcon)?.icon,
      ),
      equals((Icons.check, Icons.close)),
    ),
    "the app bar title starts at the leading edge on every platform": (
      () => theme.appBarTheme.centerTitle,
      isFalse,
    ),
    "the app bar is surface, and surfaceContainer when scrolled under": (
      () => (
        _at(theme.appBarTheme.backgroundColor as WidgetStateColor?),
        _at(theme.appBarTheme.backgroundColor as WidgetStateColor?, {
          WidgetState.scrolledUnder,
        }),
        theme.appBarTheme.scrolledUnderElevation,
      ),
      equals((
        _scheme.surface,
        _scheme.surfaceContainer,
        TokenElevation.level2,
      )),
    ),
    "the navigation bar selects with a solid primary pill": (
      () => (
        theme.navigationBarTheme.indicatorColor,
        theme.navigationBarTheme.indicatorShape,
        theme.navigationBarTheme.labelBehavior,
        _at(theme.navigationBarTheme.iconTheme, {WidgetState.selected})?.color,
      ),
      equals((
        _scheme.primary,
        const StadiumBorder(),
        NavigationDestinationLabelBehavior.alwaysShow,
        _scheme.onPrimary,
      )),
    ),
    "dialogs and sheets are white with extraLarge corners": (
      () => (
        theme.dialogTheme.backgroundColor,
        theme.bottomSheetTheme.backgroundColor,
        theme.bottomSheetTheme.showDragHandle,
      ),
      equals((
        _scheme.surfaceContainerLowest,
        _scheme.surfaceContainerLowest,
        true,
      )),
    ),
    "snackbars float in inverseSurface": (
      () => (theme.snackBarTheme.behavior, theme.snackBarTheme.backgroundColor),
      equals((SnackBarBehavior.floating, _scheme.inverseSurface)),
    ),
    "spinners are primary with round ends": (
      () => (
        theme.progressIndicatorTheme.color,
        theme.progressIndicatorTheme.strokeCap,
      ),
      equals((_scheme.primary, StrokeCap.round)),
    ),
  };

  for (final MapEntry(key: name, value: (actual, matcher)) in cases.entries) {
    test(name, () => expect(actual(), matcher));
  }

  testWidgets(
    "the back button uses the adaptive back icon on iOS",
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
    (tester) async {
      final navigator = GlobalKey<NavigatorState>();
      await tester.pumpWidget(
        MaterialApp(
          navigatorKey: navigator,
          theme: buildTailTagTheme(),
          home: const Scaffold(body: Text("Home")),
        ),
      );
      navigator.currentState!.push(
        MaterialPageRoute<void>(
          builder: (_) => Scaffold(appBar: AppBar(title: const Text("Detail"))),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.arrow_back_ios), findsOneWidget);
    },
  );
}
