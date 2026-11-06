import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/app.dart";
import "package:tailtag_mobile/app/entry/entry_screens.dart";
import "package:tailtag_mobile/core/auth/auth_providers.dart";
import "package:tailtag_mobile/core/config/app_config.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/main.dart" as app;

import "../support/auth_test_support.dart";

void main() {
  testWidgets("production startup renders the entry coordinator's first "
      "stage", (tester) async {
    app.runTailTagApp(
      AppConfig.parse({
        apiBaseUrlKey: "https://dev.tailtag.app",
        clerkPublishableKeyKey: "pk_test_abc123",
      }),
    );

    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    final providerScope = find.byType(ProviderScope);
    final routerBackedMaterialApp = find.byWidgetPredicate(
      (widget) => widget is MaterialApp && widget.routerConfig != null,
    );

    expect(providerScope, findsOneWidget);
    expect(routerBackedMaterialApp, findsOneWidget);
    expect(
      find.descendant(of: providerScope, matching: routerBackedMaterialApp),
      findsOneWidget,
    );
    // The native SDK has not reported a state yet, so the coordinator shows
    // the restoring stage and no protected content.
    expect(find.text(EntryStrings.restoring), findsOneWidget);
    expect(find.text(EntryStrings.landing), findsNothing);
  });

  testWidgets("the app uses the TailTag theme and stays light in dark mode", (
    tester,
  ) async {
    tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [authSessionProvider.overrideWithValue(FakeAuthSession())],
        child: const TailTagApp(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    final theme = Theme.of(tester.element(find.byType(Scaffold).first));
    expect(theme.brightness, Brightness.light);
    expect(theme.colorScheme, tailTagColorScheme);
    expect(theme.extension<TailTagColors>(), same(TailTagColors.light));
  });

  test("production main fails fast naming both keys without dart-defines", () {
    expect(
      app.main,
      throwsA(
        isA<AppConfigException>().having(
          (e) => e.toString(),
          "toString",
          allOf(contains(apiBaseUrlKey), contains(clerkPublishableKeyKey)),
        ),
      ),
    );
  });
}
