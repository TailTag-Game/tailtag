import "package:flutter/material.dart";
import "package:flutter/rendering.dart";
import "package:flutter/services.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";

import "support/component_fixture.dart";
import "support/ui_test_app.dart";

/// The four accessibility checks named in docs/design/README.md.
final _guidelines = <AccessibilityGuideline>[
  androidTapTargetGuideline,
  iOSTapTargetGuideline,
  textContrastGuideline,
  labeledTapTargetGuideline,
];

Future<void> _meetsAllGuidelines(WidgetTester tester) async {
  for (final guideline in _guidelines) {
    await expectLater(tester, meetsGuideline(guideline));
  }
}

// The fixture spinner never settles, so the tests pump a fixed time.

/// Presses Tab until keyboard focus is inside [control], as a keyboard or
/// switch access user would.
Future<void> _focus(WidgetTester tester, Finder control) async {
  bool focused() {
    final focus = FocusManager.instance.primaryFocus?.context;
    return focus != null &&
        find
            .descendant(
              of: control,
              matching: find.byElementPredicate((e) => identical(e, focus)),
            )
            .evaluate()
            .isNotEmpty;
  }

  for (var i = 0; i < 60 && !focused(); i++) {
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
  }
  expect(focused(), isTrue, reason: "Tab never reached the control");
  await tester.pump(const Duration(seconds: 1));
}

/// The number of see-through fills that the ink layer around [control]
/// paints. A focus state layer adds one.
int _stateLayers(WidgetTester tester, Finder control) {
  final response = find.descendant(
    of: control,
    matching: find.byWidgetPredicate((widget) => widget is InkResponse),
  );
  final ink = Material.of(tester.element(response.first)) as RenderObject;
  final canvas = TestRecordingCanvas();
  ink.paint(TestRecordingPaintingContext(canvas), Offset.zero);
  return canvas.invocations.where((call) {
    return call.invocation.positionalArguments.whereType<Paint>().any(
      (paint) => paint.color.a > 0 && paint.color.a < 1,
    );
  }).length;
}

void main() {
  final taps = <String>[];
  setUp(taps.clear);

  testWidgets("every component meets the four accessibility guidelines", (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    useScreen(tester, const Size(360, 2600));
    await tester.pumpWidget(ComponentFixture(onTap: taps.add));
    await _meetsAllGuidelines(tester);
    semantics.dispose();
  });

  final overlays = <String, void Function(BuildContext)>{
    "dialog": (context) => showDialog<void>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text("Rotate this QR code?"),
        content: const Text("Players can no longer catch with the old code."),
        actions: [
          TailTagButton(
            label: "Cancel",
            variant: TailTagButtonVariant.secondaryText,
            onPressed: () {},
          ),
          TailTagButton(
            label: "Rotate code",
            variant: TailTagButtonVariant.destructive,
            onPressed: () {},
          ),
        ],
      ),
    ),
    "bottom sheet": (context) => showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      builder: (_) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (final name in ["FurCon 2026", "Howl Fest"])
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: TokenSpacing.sm),
              child: ListTile(
                title: Text(name),
                selected: name == "FurCon 2026",
                onTap: () {},
              ),
            ),
        ],
      ),
    ),
    "snackbar": (context) =>
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text("Catch confirmed"))),
  };
  for (final MapEntry(key: name, value: open) in overlays.entries) {
    testWidgets("the $name meets the four accessibility guidelines", (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(ComponentFixture(onTap: taps.add));
      open(tester.element(find.byType(SingleChildScrollView).first));
      await tester.pump(const Duration(seconds: 1));
      await _meetsAllGuidelines(tester);
      semantics.dispose();
    });
  }

  testWidgets("at 200% text scale on a small phone nothing clips and every "
      "control can still be tapped", (tester) async {
    useScreen(tester, smallPhone);
    // A control whose label is squeezed to nothing still takes a tap, so a
    // tap that misses its label fails the test.
    WidgetController.hitTestWarningShouldBeFatal = true;
    addTearDown(() => WidgetController.hitTestWarningShouldBeFatal = false);
    await tester.pumpWidget(ComponentFixture(onTap: taps.add, textScale: 2));
    expect(tester.takeException(), isNull);

    // The app bar title stays on one line and ends with an ellipsis.
    final title = tester.renderObject<RenderParagraph>(find.text(fixtureTitle));
    final lineHeight =
        TokenTypography.titleLarge.fontSize! *
        2 *
        TokenTypography.titleLarge.height!;
    expect(title.size.height, lessThanOrEqualTo(lineHeight + 1));
    expect(title.overflow, TextOverflow.ellipsis);
    expect(
      title.getMaxIntrinsicWidth(double.infinity),
      greaterThan(title.size.width),
      reason: "the long title must be cut, so the ellipsis shows",
    );

    // The navigation labels fit on screen without clipping.
    for (final label in fixtureNavLabels) {
      final paragraph = tester.renderObject<RenderParagraph>(find.text(label));
      expect(paragraph.didExceedMaxLines, isFalse, reason: label);
      final rect = tester.getRect(find.text(label));
      expect(rect.left, greaterThanOrEqualTo(0), reason: label);
      expect(rect.right, lessThanOrEqualTo(smallPhone.width), reason: label);
      expect(
        paragraph.size.width,
        greaterThanOrEqualTo(paragraph.getMaxIntrinsicWidth(double.infinity)),
        reason: "$label is cut off",
      );
    }

    for (final MapEntry(key: id, value: label) in fixtureControls.entries) {
      final control = find.text(label).first;
      await tester.ensureVisible(control);
      await tester.pump(const Duration(seconds: 1));
      await tester.tap(control);
      await tester.pump(const Duration(seconds: 1));
      expect(taps, contains(id), reason: "$label could not be tapped");
    }
  });

  testWidgets("selected and toggled controls report their state", (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    useScreen(tester, const Size(360, 2600));
    await tester.pumpWidget(ComponentFixture(onTap: taps.add));

    final cases = <String, Matcher>{
      "All": isSemantics(isSelected: true, hasSelectedState: true),
      "FurCon": isSemantics(isSelected: false, hasSelectedState: true),
      "FurCon 2026": isSemantics(isSelected: true),
      "Home": isSemantics(isSelected: true),
      "Catches": isSemantics(isSelected: false),
      "Out for catching": isSemantics(hasToggledState: true, isToggled: true),
    };
    for (final MapEntry(key: label, value: matcher) in cases.entries) {
      expect(
        tester.getSemantics(find.text(label).first),
        matcher,
        reason: label,
      );
    }
    semantics.dispose();
  });

  group("focus", () {
    setUp(() {
      FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.alwaysTraditional;
    });
    tearDown(() {
      FocusManager.instance.highlightStrategy =
          FocusHighlightStrategy.automatic;
    });

    final ring = focusRingSide(tailTagColorScheme.primary);
    final ringControls = <String, Finder>{
      "a button": find.widgetWithText(TailTagButton, "Save"),
      "an icon button": find.byWidgetPredicate(
        (widget) => widget is IconButton && widget.tooltip == "Share QR code",
      ),
      "a filter chip": find.widgetWithText(FilterChip, "FurCon"),
    };
    for (final MapEntry(key: name, value: control) in ringControls.entries) {
      testWidgets("$name shows the offset focus ring only when focused", (
        tester,
      ) async {
        useScreen(tester, const Size(360, 2600));
        await tester.pumpWidget(ComponentFixture(onTap: taps.add));
        OutlinedBorder shape() =>
            materialOf(tester, control).shape! as OutlinedBorder;

        expect(shape().side, isNot(ring));
        await _focus(tester, control);
        expect(shape().side, ring);
      });
    }

    testWidgets("a text field shows a thicker primary border when focused", (
      tester,
    ) async {
      useScreen(tester, const Size(360, 2600));
      await tester.pumpWidget(ComponentFixture(onTap: taps.add));
      final field = find.byType(TextFormField);
      await _focus(tester, field);

      final decorator = tester.widget<InputDecorator>(
        find.descendant(of: field, matching: find.byType(InputDecorator)),
      );
      expect(decorator.isFocused, isTrue);
      expect(
        decorator.decoration.focusedBorder?.borderSide,
        BorderSide(
          color: tailTagColorScheme.primary,
          width: TokenSize.focusRingWidth,
        ),
      );
    });

    final layerControls = <String, Finder>{
      "a list row": find.widgetWithText(ListTile, "Sable"),
      "a tappable card": find.byType(Card),
      "a switch row": find.byType(SwitchListTile),
      "a navigation destination": find.byType(NavigationDestination).at(1),
    };
    for (final MapEntry(key: name, value: control) in layerControls.entries) {
      testWidgets("$name shows the Material focus state layer when focused", (
        tester,
      ) async {
        useScreen(tester, const Size(360, 2600));
        await tester.pumpWidget(ComponentFixture(onTap: taps.add));
        final before = _stateLayers(tester, control);

        await _focus(tester, control);
        expect(_stateLayers(tester, control), greaterThan(before));
      });
    }
  });
}
