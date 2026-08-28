import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tailtag_mobile/app/router.dart';
import 'package:tailtag_mobile/main.dart' as app;

void main() {
  testWidgets(
    'production startup renders the root TailTag placeholder',
    (tester) async {
      app.main();

      await tester.pumpAndSettle();

      final providerScope = find.byType(ProviderScope);
      final routerBackedMaterialApp = find.byWidgetPredicate(
        (widget) => widget is MaterialApp && widget.routerConfig != null,
      );

      expect(appRouter.routeInformationProvider.value.uri.path, '/');
      expect(providerScope, findsOneWidget);
      expect(routerBackedMaterialApp, findsOneWidget);
      expect(
        find.descendant(of: providerScope, matching: routerBackedMaterialApp),
        findsOneWidget,
      );
      expect(find.text('TailTag'), findsOneWidget);
    },
  );
}
