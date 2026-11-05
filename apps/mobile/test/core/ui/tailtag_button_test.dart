import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";

import "support/ui_test_app.dart";

const ColorScheme _scheme = tailTagColorScheme;

/// The fill and label colors of each variant, from components.md.
final _variantColors = <TailTagButtonVariant, (Color, Color)>{
  TailTagButtonVariant.primary: (_scheme.primary, _scheme.onPrimary),
  TailTagButtonVariant.secondary: (
    _scheme.primaryContainer,
    _scheme.onPrimaryContainer,
  ),
  TailTagButtonVariant.secondaryText: (Colors.transparent, _scheme.primary),
  TailTagButtonVariant.destructive: (_scheme.error, _scheme.onError),
};

final Finder _button = find.byType(TailTagButton);
final Finder _spinner = find.byType(CircularProgressIndicator);

/// Matches [expected] in RGB, and in alpha within the 8-bit rounding that
/// Flutter applies to a color opacity.
Matcher _near(Color? expected) {
  if (expected == null) {
    return isNull;
  }
  return isA<Color>()
      .having(
        (c) => c.withValues(alpha: 1),
        "opaque",
        expected.withValues(alpha: 1),
      )
      .having((c) => c.a, "alpha", closeTo(expected.a, 0.5 / 255 + 0.001));
}

/// The Material disabled colors: `onSurface` at 12% for a fill and 38% for
/// a label.
final Color _disabledFill = _scheme.onSurface.withValues(alpha: 0.12);
final Color _disabledLabel = _scheme.onSurface.withValues(alpha: 0.38);

void main() {
  for (final MapEntry(key: variant, value: (fill, label))
      in _variantColors.entries) {
    testWidgets("$variant has its colors and a state layer in its label "
        "color", (tester) async {
      await tester.pumpWidget(
        themed(
          TailTagButton(label: "Save", onPressed: () {}, variant: variant),
        ),
      );

      final material = materialOf(tester, _button);
      expect(material.color ?? Colors.transparent, fill);
      expect(material.textStyle?.color, label);
      expect(material.shape, isA<StadiumBorder>());
      expect(tester.getSize(_button).height, greaterThanOrEqualTo(48));

      final style = tester
          .widget<ButtonStyleButton>(
            find.descendant(
              of: _button,
              matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
            ),
          )
          .style!;
      final pressed = style.overlayColor!.resolve({WidgetState.pressed})!;
      expect(pressed, _near(label.withValues(alpha: 0.1)));
    });
  }

  // (variant, fill when disabled or loading, label when disabled or loading)
  final states = [
    (TailTagButtonVariant.primary, false, _disabledFill, _disabledLabel),
    (TailTagButtonVariant.secondaryText, false, null, _disabledLabel),
    (TailTagButtonVariant.primary, true, _scheme.primary, _scheme.onPrimary),
    (TailTagButtonVariant.secondaryText, true, null, _scheme.primary),
  ];
  for (final (variant, loading, fill, label) in states) {
    testWidgets("a ${loading ? "loading" : "disabled"} $variant "
        "${loading ? "keeps its colors" : "uses the disabled colors"}", (
      tester,
    ) async {
      await tester.pumpWidget(
        themed(
          TailTagButton(
            label: "Save",
            onPressed: loading ? () {} : null,
            variant: variant,
            loading: loading,
          ),
        ),
      );
      await tester.pump(loadingIndicatorDelay);

      final material = materialOf(tester, _button);
      expect(
        material.color == Colors.transparent ? null : material.color,
        _near(fill),
      );
      expect(material.textStyle?.color, _near(label));
    });
  }

  testWidgets("a loading button shows its spinner only after 500 ms, "
      "keeps its size, and ignores taps", (tester) async {
    var taps = 0;
    Widget button({required bool loading}) => themed(
      Center(
        child: TailTagButton(
          label: "Confirm catch",
          onPressed: () => taps++,
          loading: loading,
        ),
      ),
    );

    await tester.pumpWidget(button(loading: false));
    final idleSize = tester.getSize(_button);

    await tester.pumpWidget(button(loading: true));
    await tester.pump(loadingIndicatorDelay - const Duration(milliseconds: 1));
    expect(_spinner, findsNothing);
    expect(find.text("Confirm catch").hitTestable(), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 1));
    expect(_spinner, findsOneWidget);
    expect(find.text("Confirm catch").hitTestable(), findsNothing);
    expect(tester.getSize(_button), idleSize);

    await tester.tap(_button, warnIfMissed: false);
    expect(taps, 0);

    await tester.pumpWidget(button(loading: false));
    expect(_spinner, findsNothing);
    await tester.tap(_button);
    expect(taps, 1);
  });

  testWidgets("a loading button reads its label with the value Loading", (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    await tester.pumpWidget(
      themed(TailTagButton(label: "Save", onPressed: () {}, loading: true)),
    );
    await tester.pump(loadingIndicatorDelay);

    expect(
      tester.getSemantics(_button),
      isSemantics(
        label: "Save",
        value: "Loading",
        isButton: true,
        isEnabled: false,
      ),
    );
    semantics.dispose();
  });

  testWidgets("at 200% text scale a long label wraps and the button grows", (
    tester,
  ) async {
    useScreen(tester, smallPhone);
    await tester.pumpWidget(
      themed(
        Center(
          child: SizedBox(
            width: 160,
            child: TailTagButton(
              label: "Confirm this catch",
              icon: Icons.check,
              onPressed: () {},
            ),
          ),
        ),
        textScale: 2,
      ),
    );

    expect(tester.takeException(), isNull);
    expect(tester.getSize(_button).height, greaterThan(48));
  });
}
