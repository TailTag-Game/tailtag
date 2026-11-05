import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";

void main() {
  testWidgets("shows the replacement until the delay ends, then the child, "
      "and starts again when it is added again", (tester) async {
    Widget build({required bool waiting}) => Directionality(
      textDirection: TextDirection.ltr,
      child: waiting
          ? const DelayedVisibility(
              replacement: Text("Idle"),
              child: Text("Loading"),
            )
          : const Text("Done"),
    );

    expect(loadingIndicatorDelay, const Duration(milliseconds: 500));

    for (var round = 0; round < 2; round++) {
      await tester.pumpWidget(build(waiting: true));
      await tester.pump(const Duration(milliseconds: 499));
      expect(find.text("Idle"), findsOneWidget);
      expect(find.text("Loading"), findsNothing);

      await tester.pump(const Duration(milliseconds: 1));
      expect(find.text("Loading"), findsOneWidget);

      // A wait that ends removes the helper and cancels its timer.
      await tester.pumpWidget(build(waiting: false));
      expect(find.text("Done"), findsOneWidget);
    }
  });
}
