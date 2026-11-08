import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/auth/passkey.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";
import "package:tailtag_mobile/features/account_access/apple_button.dart";
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

/// One provider action as the account screen offers it.
typedef _Provider = ({
  String name,
  String key,
  TargetPlatform platform,
  void Function(FakeAuthSession, AuthAttemptResult) setResult,
  void Function(FakeAuthSession, AuthFailure?) setFailure,
  int Function(FakeAuthSession) calls,
  String unavailableText,
});

final _providers = <_Provider>[
  (
    name: "Google",
    key: "access-google",
    platform: TargetPlatform.android,
    setResult: (session, result) => session.googleResult = result,
    setFailure: (session, failure) => session.googleFailure = failure,
    calls: (session) => session.googleCalls,
    unavailableText:
        "Google sign-in is not available on this device. Add a Google "
        "account in Settings, or use email.",
  ),
  (
    name: "Apple",
    key: "access-apple",
    platform: TargetPlatform.iOS,
    setResult: (session, result) => session.appleResult = result,
    setFailure: (session, failure) => session.appleFailure = failure,
    calls: (session) => session.appleCalls,
    unavailableText:
        "Sign in with Apple is not available on this device. Sign in to "
        "your Apple Account in Settings, or use email.",
  ),
];

/// The account controls that a pending attempt disables on [platform].
List<String> _accessKeys(TargetPlatform platform) => [
  "access-create-account",
  "access-sign-in",
  if (platform == TargetPlatform.iOS) "access-apple",
  "access-google",
  "access-passkey",
];

void main() {
  for (final p in _providers) {
    group("${p.name} on ${p.platform.name}", () {
      final variant = TargetPlatformVariant.only(p.platform);

      testWidgets("a completed attempt reaches the identity bootstrap", (
        tester,
      ) async {
        fakePlatformViews();
        final app = await pumpApp(
          tester,
          session: FakeAuthSession(),
          network: ScriptedNetwork([200]),
        );

        await app.tap(p.key);

        expect(p.calls(app.session), 1);
        expect(app.network.requests, 1, reason: "only GET /api/me/");
        expect(app.path, AppPaths.landing);
      }, variant: variant);

      testWidgets("a cancelled attempt returns to the choices with no "
          "banner and no request", (tester) async {
        fakePlatformViews();
        final app = await pumpApp(tester, session: FakeAuthSession());
        p.setResult(app.session, const AuthAttemptCancelled());

        await app.tap(p.key);

        expect(app.path, AppPaths.access);
        expect(app.session.state, isA<AuthSignedOut>());
        expect(_key("access-provider-failure"), findsNothing);
        expect(app.network.requests, 0);
        expect(_enabled(tester, p.key), isTrue);
      }, variant: variant);

      testWidgets("an unavailable provider shows its own banner and keeps "
          "every choice, and a new tap retries", (tester) async {
        fakePlatformViews();
        final app = await pumpApp(tester, session: FakeAuthSession());
        p.setFailure(app.session, const AuthProviderUnavailableFailure());

        await app.tap(p.key);

        expect(app.path, AppPaths.access);
        expect(find.text(p.unavailableText), findsOneWidget);
        for (final key in _accessKeys(p.platform)) {
          expect(_enabled(tester, key), isTrue, reason: key);
        }

        p.setFailure(app.session, null);
        app.network.enqueue(200);
        await app.tap(p.key);
        expect(p.calls(app.session), 2);
        expect(app.path, AppPaths.landing);
      }, variant: variant);

      testWidgets("an attempt that needs an email code shows the provider "
          "code screen, and Back ends the attempt", (tester) async {
        fakePlatformViews();
        final app = await pumpApp(tester, session: FakeAuthSession());
        p.setResult(app.session, const AuthAttemptNeedsEmailCode());

        await app.tap(p.key);

        expect(app.path, AppPaths.providerCode);
        expect(
          find.text(AccountAccessStrings.codeBodyProvider),
          findsOneWidget,
        );
        expect(find.text(AccountAccessStrings.changeEmail), findsNothing);
        await tester.tap(find.text(AccountAccessStrings.back));
        await app.settle();
        expect(app.path, AppPaths.access);
        expect(app.container.read(accessFlowProvider).codeSent, isFalse);

        await app.tap(p.key);
        await tester.enterText(_key("access-code"), "123456");
        await tester.pump();
        app.network.enqueue(200);
        await app.tap("access-verify");
        expect(app.session.verifyCodeCalls, ["123456"]);
        expect(app.path, AppPaths.landing);
      }, variant: variant);

      testWidgets("a pending attempt disables every access control and "
          "sends once", (tester) async {
        fakePlatformViews();
        final app = await pumpApp(tester, session: FakeAuthSession());
        p.setResult(app.session, const AuthAttemptCancelled());
        app.session.gate = Completer<void>();

        await tester.tap(_key(p.key));
        await tester.pump();
        await tester.tap(_key(p.key), warnIfMissed: false);
        await tester.pump();

        expect(app.session.accessCalls, 1);
        for (final key in _accessKeys(p.platform)) {
          expect(_enabled(tester, key), isFalse, reason: key);
        }
        app.session.gate!.complete();
        app.session.gate = null;
        await app.settle();
        expect(_enabled(tester, p.key), isTrue);
      }, variant: variant);
    });
  }

  group("the provider section depends on the platform", () {
    testWidgets("iOS shows Apple first, then Google", (tester) async {
      fakePlatformViews();
      await pumpApp(tester, session: FakeAuthSession());

      final apple = tester.getRect(_key("access-apple"));
      final google = tester.getRect(_key("access-google"));
      expect(apple.bottom, lessThanOrEqualTo(google.top));
      expect(apple.width, google.width);
      expect(apple.height, greaterThanOrEqualTo(google.height));
      expect(
        google.bottom,
        lessThanOrEqualTo(tester.getRect(_key("access-passkey")).top),
      );
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets("on a 375 x 667 screen, the Apple button shows without "
        "scrolling", (tester) async {
      tester.view
        ..physicalSize = const Size(375, 667)
        ..devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      fakePlatformViews();
      await pumpApp(tester, session: FakeAuthSession());

      expect(
        tester.getRect(_key("access-apple")).bottom,
        lessThanOrEqualTo(667),
      );
      expect(
        tester.getRect(_key("access-passkey")).bottom,
        lessThanOrEqualTo(667),
      );
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

    testWidgets("Android shows no Apple action", (tester) async {
      await pumpApp(tester, session: FakeAuthSession());

      expect(_key("access-apple"), findsNothing);
      expect(_key("access-google"), findsOneWidget);
    }, variant: TargetPlatformVariant.only(TargetPlatform.android));
  });

  group("the Apple button uses the native button in the theme's style", () {
    // Apple's guidelines: black on light backgrounds, white on dark ones.
    final styles = <Brightness, String>{
      Brightness.light: "black",
      Brightness.dark: "white",
    };
    for (final MapEntry(key: brightness, value: style) in styles.entries) {
      testWidgets(brightness.name, (tester) async {
        fakePlatformViews();
        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData(brightness: brightness),
            home: Scaffold(body: AppleButton(onPressed: () {})),
          ),
        );

        final view = tester.widget<UiKitView>(find.byType(UiKitView));
        expect(view.viewType, appleButtonViewType);
        expect(view.creationParams, {"style": style});
        expect(
          tester.getSize(find.byType(AppleButton)).height,
          greaterThanOrEqualTo(TokenSize.minTarget),
        );
        expect(
          find.bySemanticsLabel(AccountAccessStrings.continueWithApple),
          findsOneWidget,
        );
      }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
    }
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

  group("passkey sign-in", () {
    final android = TargetPlatformVariant.only(TargetPlatform.android);

    testWidgets("ends the provider section, and a completed sign-in reaches "
        "the identity bootstrap", (tester) async {
      final app = await pumpApp(
        tester,
        session: FakeAuthSession(),
        network: ScriptedNetwork([200]),
      );
      expect(
        tester.getRect(_key("access-google")).bottom,
        lessThanOrEqualTo(tester.getRect(_key("access-passkey")).top),
      );

      await app.tap("access-passkey");

      expect(app.session.passkeySignInCalls, 1);
      expect(app.path, AppPaths.landing);
    }, variant: android);

    testWidgets("a cancelled sheet returns to the choices with no banner", (
      tester,
    ) async {
      final app = await pumpApp(tester, session: FakeAuthSession());
      app.session.passkeySignInResult = const AuthAttemptCancelled();

      await app.tap("access-passkey");

      expect(app.path, AppPaths.access);
      expect(_key("access-provider-failure"), findsNothing);
      expect(app.network.requests, 0);
    }, variant: android);

    final failures = <({AuthFailure failure, String text})>[
      (
        failure: const AuthPasskeyUnavailableFailure(),
        text:
            "This device cannot use a passkey right now. Sign in another "
            "way.",
      ),
      (
        failure: const AuthAccountNotFoundFailure(),
        text: "No TailTag account uses that passkey. Sign in another way.",
      ),
    ];
    for (final f in failures) {
      testWidgets("${f.failure.name} explains it and keeps every choice", (
        tester,
      ) async {
        final app = await pumpApp(tester, session: FakeAuthSession());
        app.session.passkeySignInFailure = f.failure;

        await app.tap("access-passkey");

        expect(app.path, AppPaths.access);
        expect(find.text(f.text), findsOneWidget);
        for (final key in _accessKeys(TargetPlatform.android)) {
          expect(_enabled(tester, key), isTrue, reason: key);
        }
        expect(app.session.passkeySignInCalls, 1, reason: "no retry");
      }, variant: android);
    }

    testWidgets("when passkeys are unavailable, a note replaces the button "
        "and the other choices stay", (tester) async {
      await pumpApp(
        tester,
        session: FakeAuthSession()
          ..availability = PasskeyAvailability.unavailable,
      );

      expect(_key("access-passkey"), findsNothing);
      expect(
        find.text(AccountAccessStrings.passkeysUnavailable),
        findsOneWidget,
      );
      expect(_key("access-google"), findsOneWidget);
      expect(_key("access-sign-in"), findsOneWidget);
    }, variant: android);
  });
}
