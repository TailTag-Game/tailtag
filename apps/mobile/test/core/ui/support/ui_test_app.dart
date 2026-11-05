import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";

/// The small phone screen for text-scale tests, in logical pixels.
const Size smallPhone = Size(360, 640);

/// Wraps [child] in the TailTag theme, a [Scaffold], and [textScale].
Widget themed(Widget child, {double textScale = 1}) {
  return MaterialApp(
    theme: buildTailTagTheme(),
    home: Builder(
      builder: (context) => MediaQuery(
        data: MediaQuery.of(context)
            .copyWith(textScaler: TextScaler.linear(textScale)),
        child: Scaffold(body: child),
      ),
    ),
  );
}

/// Sets the test screen to [size] logical pixels until the test ends.
void useScreen(WidgetTester tester, Size size) {
  tester.view
    ..devicePixelRatio = 1
    ..physicalSize = size;
  addTearDown(tester.view.reset);
}

/// The [Material] that a button or chip under [control] paints.
Material materialOf(WidgetTester tester, Finder control) {
  return tester.widget<Material>(
    find.descendant(of: control, matching: find.byType(Material)).first,
  );
}
