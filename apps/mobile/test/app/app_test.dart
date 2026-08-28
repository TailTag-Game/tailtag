import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tailtag_mobile/main.dart' as app;

void main() {
  testWidgets(
    'production startup resolves the root route to the neutral TailTag placeholder',
    (tester) async {
      app.main();

      await tester.pumpAndSettle();

      expect(find.byType(ProviderScope), findsOneWidget);
      expect(
        find.byWidgetPredicate(
          (widget) => widget is MaterialApp && widget.routerConfig != null,
        ),
        findsOneWidget,
      );
      expect(find.text('TailTag'), findsOneWidget);
    },
  );
}
