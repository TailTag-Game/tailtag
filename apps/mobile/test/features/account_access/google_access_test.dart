import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";
import "package:tailtag_mobile/features/account_access/google_button.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

Finder _key(String key) => find.byKey(Key(key));

bool _enabled(WidgetTester tester, String key) {
  final button = find.descendant(
    of: _key(key),
    matching: find.byWidgetPredicate((widget) => widget is ButtonStyleButton),
  );
  return tester.widget<ButtonStyleButton>(button).onPressed != null;
}

void main() {
  testWidgets("a completed Google attempt reaches the identity bootstrap", (
    tester,
  ) async {
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(),
      network: ScriptedNetwork([200]),
    );

    expect(find.text(AccountAccessStrings.continueWithGoogle), findsOneWidget);
    await app.tap("access-google");

    expect(app.session.googleCalls, 1);
    expect(app.network.requests, 1, reason: "only GET /api/me/");
    expect(app.path, AppPaths.landing);
  });

  testWidgets("a cancelled Google attempt returns to the choices with no "
      "banner and no request", (tester) async {
    final app = await pumpApp(tester, session: FakeAuthSession());
    app.session.googleResult = const AuthAttemptCancelled();

    await app.tap("access-google");

    expect(app.path, AppPaths.access);
    expect(app.session.state, isA<AuthSignedOut>());
    expect(_key("access-provider-failure"), findsNothing);
    expect(app.network.requests, 0);
    expect(_enabled(tester, "access-google"), isTrue);
  });

  testWidgets("an unavailable provider shows a banner and keeps every "
      "choice, and a new tap retries", (tester) async {
    final app = await pumpApp(tester, session: FakeAuthSession());
    app.session.googleFailure = const AuthProviderUnavailableFailure();

    await app.tap("access-google");

    expect(app.path, AppPaths.access);
    expect(
      find.text(
        "Google sign-in is not available on this device. Add a Google "
        "account in Settings, or use email.",
      ),
      findsOneWidget,
    );
    for (final key in [
      "access-create-account",
      "access-sign-in",
      "access-google",
    ]) {
      expect(_enabled(tester, key), isTrue, reason: key);
    }

    app.session.googleFailure = null;
    app.network.enqueue(200);
    await app.tap("access-google");
    expect(app.session.googleCalls, 2);
    expect(app.path, AppPaths.landing);
  });

  testWidgets("a Google attempt that needs an email code shows the provider "
      "code screen, and Back ends the attempt", (tester) async {
    final app = await pumpApp(tester, session: FakeAuthSession());
    app.session.googleResult = const AuthAttemptNeedsEmailCode();

    await app.tap("access-google");

    expect(app.path, AppPaths.providerCode);
    expect(find.text(AccountAccessStrings.codeBodyProvider), findsOneWidget);
    expect(find.text(AccountAccessStrings.changeEmail), findsNothing);
    await tester.tap(find.text(AccountAccessStrings.back));
    await app.settle();
    expect(app.path, AppPaths.access);
    expect(app.container.read(accessFlowProvider).codeSent, isFalse);

    await app.tap("access-google");
    await tester.enterText(_key("access-code"), "123456");
    await tester.pump();
    app.network.enqueue(200);
    await app.tap("access-verify");
    expect(app.session.verifyCodeCalls, ["123456"]);
    expect(app.path, AppPaths.landing);
  });

  testWidgets("a pending Google attempt disables every access control and "
      "sends once", (tester) async {
    final app = await pumpApp(tester, session: FakeAuthSession());
    app.session
      ..googleResult = const AuthAttemptCancelled()
      ..gate = Completer<void>();

    await tester.tap(_key("access-google"));
    await tester.pump();
    await tester.tap(_key("access-google"), warnIfMissed: false);
    await tester.pump();

    expect(app.session.accessCalls, 1);
    for (final key in [
      "access-create-account",
      "access-sign-in",
      "access-google",
    ]) {
      expect(_enabled(tester, key), isFalse, reason: key);
    }
    app.session.gate!.complete();
    app.session.gate = null;
    await app.settle();
    expect(_enabled(tester, "access-google"), isTrue);
  });

  group("the Google button follows Google's branding colors", () {
    // The values of Google's sign-in branding guidelines.
    final themes = <Brightness, (int, int, int, String)>{
      Brightness.light: (
        0xFFFFFFFF,
        0xFF747775,
        0xFF1F1F1F,
        "assets/images/google/google_g_light.png",
      ),
      Brightness.dark: (
        0xFF131314,
        0xFF8E918F,
        0xFFE3E3E3,
        "assets/images/google/google_g_dark.png",
      ),
    };
    for (final MapEntry(key: brightness, value: expected) in themes.entries) {
      testWidgets(brightness.name, (tester) async {
        final (fill, stroke, text, logoAsset) = expected;
        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData(brightness: brightness),
            home: Scaffold(
              body: GoogleButton(
                label: AccountAccessStrings.continueWithGoogle,
                onPressed: () {},
              ),
            ),
          ),
        );

        final style = tester
            .widget<OutlinedButton>(find.byType(OutlinedButton))
            .style!;
        expect(style.backgroundColor!.resolve(const {}), Color(fill));
        expect(style.side!.resolve(const {})!.color, Color(stroke));
        expect(style.foregroundColor!.resolve(const {}), Color(text));
        expect(
          tester.getSize(find.byType(OutlinedButton)).height,
          greaterThanOrEqualTo(TokenSize.minTarget),
        );
        final logo = tester.widget<Image>(find.byType(Image));
        expect((logo.image as AssetImage).assetName, logoAsset);
        expect(
          find.bySemanticsLabel(AccountAccessStrings.continueWithGoogle),
          findsOneWidget,
        );
      });
    }
  });
}
