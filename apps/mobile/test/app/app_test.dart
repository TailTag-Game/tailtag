import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/app.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/config/app_config.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/main.dart" as app;

void main() {
  testWidgets("production startup renders the root TailTag placeholder", (
    tester,
  ) async {
    app.runTailTagApp(
      AppConfig.parse({
        apiBaseUrlKey: "https://dev.tailtag.app",
        clerkPublishableKeyKey: "pk_test_abc123",
      }),
    );

    await tester.pumpAndSettle();

    final providerScope = find.byType(ProviderScope);
    final routerBackedMaterialApp = find.byWidgetPredicate(
      (widget) => widget is MaterialApp && widget.routerConfig != null,
    );

    expect(appRouter.routeInformationProvider.value.uri.path, "/");
    expect(providerScope, findsOneWidget);
    expect(routerBackedMaterialApp, findsOneWidget);
    expect(
      find.descendant(of: providerScope, matching: routerBackedMaterialApp),
      findsOneWidget,
    );
    expect(find.text("TailTag"), findsOneWidget);
  });

  testWidgets("the app uses the TailTag theme and stays light in dark mode", (
    tester,
  ) async {
    tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
    addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
    await tester.pumpWidget(const ProviderScope(child: TailTagApp()));
    await tester.pumpAndSettle();

    final theme = Theme.of(tester.element(find.text("TailTag")));
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
