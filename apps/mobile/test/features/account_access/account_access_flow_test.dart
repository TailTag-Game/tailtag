import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/features/account_access/access_flow_controller.dart";
import "package:tailtag_mobile/features/account_access/account_access_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

const _email = "player+clerk_test@example.invalid";

Finder _key(String key) => find.byKey(Key(key));

String _fieldText(WidgetTester tester, String key) => tester
    .widget<EditableText>(
      find.descendant(of: _key(key), matching: find.byType(EditableText)),
    )
    .controller
    .text;

bool _readOnly(WidgetTester tester, String key) => tester
    .widget<EditableText>(
      find.descendant(of: _key(key), matching: find.byType(EditableText)),
    )
    .readOnly;

/// Opens email entry for [mode] on a signed-out app.
Future<AppHarness> _emailEntry(
  WidgetTester tester, {
  AccessMode mode = AccessMode.createAccount,
  ScriptedNetwork? network,
}) async {
  final app = await pumpApp(
    tester,
    session: FakeAuthSession(),
    network: network,
  );
  await app.tap(
    mode == AccessMode.createAccount
        ? "access-create-account"
        : "access-sign-in",
  );
  expect(app.path, AppPaths.email);
  return app;
}

/// Opens code entry after a sent code.
Future<AppHarness> _codeEntry(WidgetTester tester) async {
  final app = await _emailEntry(tester);
  await tester.enterText(_key("access-email"), _email);
  await app.tap("access-send-code");
  expect(app.path, AppPaths.code);
  return app;
}

void main() {
  testWidgets("a new player creates an account by email and reaches the "
      "identity bootstrap", (tester) async {
    final app = await _emailEntry(tester, network: ScriptedNetwork([200]));
    expect(find.text(AccountAccessStrings.createAccount), findsOneWidget);

    await tester.enterText(_key("access-email"), "not an email");
    await app.tap("access-send-code");
    expect(find.text(AccountAccessStrings.emailInvalid), findsOneWidget);
    expect(app.session.startEmailSignUpCalls, isEmpty);

    await tester.enterText(_key("access-email"), "  $_email ");
    await app.tap("access-send-code");
    expect(app.session.startEmailSignUpCalls, [_email]);
    expect(app.session.startEmailSignInCalls, isEmpty);
    expect(app.path, AppPaths.code);
    expect(find.text(AccountAccessStrings.codeBody(_email)), findsOneWidget);

    await tester.enterText(_key("access-code"), "12a34");
    await tester.pump();
    expect(_fieldText(tester, "access-code"), "1234");
    expect(
      tester
          .widget<FilledButton>(
            find.descendant(
              of: _key("access-verify"),
              matching: find.byType(FilledButton),
            ),
          )
          .onPressed,
      isNull,
      reason: "Verify needs six digits",
    );
    await tester.enterText(_key("access-code"), "123456789");
    await tester.pump();
    expect(_fieldText(tester, "access-code"), "123456");

    await app.tap("access-verify");

    expect(app.session.verifyCodeCalls, ["123456"]);
    expect(app.path, AppPaths.home);
    expect(app.container.read(accessFlowProvider).email, isEmpty);
  });

  group("email failures keep the email and offer recovery", () {
    final cases =
        <
          ({
            AuthFailure failure,
            AccessMode mode,
            String? switchLabel,
            String switchedTitle,
          })
        >[
          (
            failure: const AuthAccountExistsFailure(),
            mode: AccessMode.createAccount,
            switchLabel: AccountAccessStrings.signInInstead,
            switchedTitle: AccountAccessStrings.signIn,
          ),
          (
            failure: const AuthAccountNotFoundFailure(),
            mode: AccessMode.signIn,
            switchLabel: AccountAccessStrings.createInstead,
            switchedTitle: AccountAccessStrings.createAccount,
          ),
          (
            failure: const AuthRateLimitedFailure(),
            mode: AccessMode.signIn,
            switchLabel: null,
            switchedTitle: "",
          ),
        ];

    for (final c in cases) {
      testWidgets(c.failure.name, (tester) async {
        final app = await _emailEntry(tester, mode: c.mode);
        app.session.startFailure = c.failure;
        await tester.enterText(_key("access-email"), _email);

        await app.tap("access-send-code");

        expect(app.path, AppPaths.email);
        expect(
          find.text(AccountAccessStrings.failureMessage(c.failure)),
          findsOneWidget,
        );
        expect(_fieldText(tester, "access-email"), _email);
        final label = c.switchLabel;
        if (label == null) {
          expect(find.text(AccountAccessStrings.signInInstead), findsNothing);
          expect(find.text(AccountAccessStrings.createInstead), findsNothing);
          return;
        }
        final calls =
            app.session.startEmailSignInCalls.length +
            app.session.startEmailSignUpCalls.length;

        await tester.tap(find.text(label));
        await app.settle();

        expect(find.text(c.switchedTitle), findsOneWidget);
        expect(_fieldText(tester, "access-email"), _email);
        expect(
          app.session.startEmailSignInCalls.length +
              app.session.startEmailSignUpCalls.length,
          calls,
          reason: "switching sends nothing",
        );
      });
    }
  });

  testWidgets("code failures keep code entry, and resend runs only on "
      "tap", (tester) async {
    final app = await _codeEntry(tester);
    app.session.verifyFailure = const AuthInvalidCodeFailure();
    expect(app.session.resendCalls, 0);

    await tester.enterText(_key("access-code"), "000000");
    await tester.pump();
    await app.tap("access-verify");
    expect(app.path, AppPaths.code);
    expect(
      find.text(
        AccountAccessStrings.failureMessage(const AuthInvalidCodeFailure()),
      ),
      findsOneWidget,
    );

    await app.tap("access-resend");
    expect(app.session.resendCalls, 1);
    expect(find.text(AccountAccessStrings.codeResent), findsOneWidget);

    app.session.verifyFailure = const AuthSessionEndedFailure();
    await app.tap("access-verify");
    await tester.tap(find.text(AccountAccessStrings.changeEmail).first);
    await app.settle();
    expect(app.path, AppPaths.email);
    expect(_fieldText(tester, "access-email"), _email);
  });

  testWidgets("a pending request disables every control, sends once, and "
      "blocks Back", (tester) async {
    final app = await _emailEntry(tester);
    await tester.enterText(_key("access-email"), _email);
    app.session.gate = Completer<void>();

    await tester.tap(_key("access-send-code"));
    await tester.pump();
    await tester.tap(_key("access-send-code"), warnIfMissed: false);
    await tester.pump();
    expect(app.session.accessCalls, 1);
    expect(_readOnly(tester, "access-email"), isTrue);

    await tester.binding.handlePopRoute();
    await tester.pump();
    expect(app.path, AppPaths.email);

    app.session.gate!.complete();
    app.session.gate = null;
    await app.settle();
    expect(app.path, AppPaths.code);

    await tester.enterText(_key("access-code"), "123456");
    await tester.pump();
    app.session
      ..verifyFailure = const AuthInvalidCodeFailure()
      ..gate = Completer<void>();
    await tester.tap(_key("access-verify"));
    await tester.pump();
    await tester.binding.handlePopRoute();
    await tester.pump();
    expect(app.path, AppPaths.code, reason: "Back waits for the verify");
    expect(_readOnly(tester, "access-code"), isTrue);
    app.session.gate!.complete();
    app.session.gate = null;
    await app.settle();

    await tester.binding.handlePopRoute();
    await app.settle();
    expect(app.path, AppPaths.email, reason: "Back returns to email entry");
    expect(_fieldText(tester, "access-email"), _email);

    await app.tap("access-send-code");
    expect(_fieldText(tester, "access-code"), isEmpty);
  });

  testWidgets("sign-out clears the email flow of the ended session", (
    tester,
  ) async {
    final app = await _codeEntry(tester);
    app.session.emit(const AuthSignedIn());
    app.network.enqueue(200);
    await app.settle();
    expect(app.path, AppPaths.home);

    await app.tap("entry-sign-out");
    expect(app.path, AppPaths.access);
    expect(app.container.read(accessFlowProvider).email, isEmpty);
    expect(app.container.read(accessFlowProvider).codeSent, isFalse);
  });

  group("access and entry screens meet the accessibility rules at 200% "
      "text", () {
    final screens =
        <
          ({
            String label,
            Future<void> Function(WidgetTester) open,
            TargetPlatform platform,
          })
        >[
          (
            label: "account access",
            platform: TargetPlatform.android,
            open: (tester) => pumpApp(tester, session: FakeAuthSession()),
          ),
          (
            label: "email entry with an error",
            platform: TargetPlatform.android,
            open: (tester) async {
              final app = await _emailEntry(tester);
              app.session.startFailure = const AuthAccountExistsFailure();
              await tester.enterText(_key("access-email"), _email);
              await app.tap("access-send-code");
            },
          ),
          (
            label: "code entry",
            open: _codeEntry,
            platform: TargetPlatform.android,
          ),
          (
            label: "account access with a Google failure",
            platform: TargetPlatform.android,
            open: (tester) async {
              final app = await pumpApp(tester, session: FakeAuthSession());
              app.session.googleFailure =
                  const AuthProviderUnavailableFailure();
              await app.tap("access-google");
            },
          ),
          (
            label: "account access on iOS with an Apple failure",
            platform: TargetPlatform.iOS,
            open: (tester) async {
              fakePlatformViews();
              final app = await pumpApp(tester, session: FakeAuthSession());
              app.session.appleFailure = const AuthProviderUnavailableFailure();
              await app.tap("access-apple");
            },
          ),
          (
            label: "auth recovery",
            platform: TargetPlatform.android,
            open: (tester) => pumpApp(
              tester,
              session: FakeAuthSession(
                initial: const AuthFailed(AuthUnexpectedFailure()),
              ),
            ),
          ),
        ];

    for (final s in screens) {
      testWidgets(s.label, (tester) async {
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final semantics = tester.ensureSemantics();

        await s.open(tester);

        expect(tester.takeException(), isNull, reason: "no overflow");
        for (final guideline in [
          androidTapTargetGuideline,
          iOSTapTargetGuideline,
          labeledTapTargetGuideline,
          textContrastGuideline,
        ]) {
          await expectLater(tester, meetsGuideline(guideline));
        }
        expect(find.text(UiStrings.unknownError), findsNothing);
        semantics.dispose();
      }, variant: TargetPlatformVariant.only(s.platform));
    }
  });
}
