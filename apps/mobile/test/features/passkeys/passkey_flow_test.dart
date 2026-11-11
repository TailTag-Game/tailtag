import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_attempt_result.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/auth/passkey.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/features/passkeys/passkey_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

Finder _key(String key) => find.byKey(Key(key));

bool _enabled(WidgetTester tester, String key) {
  final widget = tester.widget(_key(key));
  if (widget is IconButton) {
    return widget.onPressed != null;
  }
  final button = find.descendant(
    of: _key(key),
    matching: find.byWidgetPredicate((widget) => widget is ButtonStyleButton),
  );
  return tester.widget<ButtonStyleButton>(button).onPressed != null;
}

/// The signed-in app on the landing, with [setUp] applied to the session.
Future<AppHarness> _signedIn(
  WidgetTester tester, {
  void Function(FakeAuthSession session)? setUp,
  List<int> statuses = const [200],
}) async {
  final session = FakeAuthSession(initial: const AuthSignedIn());
  setUp?.call(session);
  final app = await pumpApp(
    tester,
    session: session,
    network: ScriptedNetwork(statuses),
  );
  expect(app.path, AppPaths.home);
  return app;
}

/// The signed-in app on the passkey screen.
Future<AppHarness> _onPasskeys(
  WidgetTester tester, {
  void Function(FakeAuthSession session)? setUp,
}) async {
  final app = await _signedIn(tester, setUp: setUp);
  await app.tap("entry-manage-passkeys");
  expect(app.path, AppPaths.passkeys);
  return app;
}

/// Taps the remove action of the passkey [name].
Future<void> _tapRemove(AppHarness app, String name) async {
  await app.tester.tap(find.byTooltip(PasskeyStrings.removeLabel(name)));
  await app.settle();
}

void main() {
  group("the passkey stage", () {
    testWidgets("opens from the landing, and Close runs a fresh identity "
        "bootstrap", (tester) async {
      final app = await _signedIn(tester);
      final epoch = app.container.read(playerScopeProvider).epoch;

      await app.tap("entry-manage-passkeys");
      expect(app.path, AppPaths.passkeys);
      expect(app.container.read(playerScopeProvider).epoch, epoch + 1);
      expect(find.byKey(const Key("convention-home")), findsNothing);

      app.network.enqueue(200);
      await app.tap("passkeys-close");

      expect(app.network.requests, 2);
      expect(app.path, AppPaths.home);
    });

    testWidgets("system Back closes it like Close", (tester) async {
      final app = await _onPasskeys(tester);
      app.network.enqueue(200);

      await tester.binding.handlePopRoute();
      await app.settle();

      expect(app.network.requests, 2);
      expect(app.path, AppPaths.home);
    });

    testWidgets("opens from a failed identity read without a profile", (
      tester,
    ) async {
      final app = await pumpApp(
        tester,
        session: FakeAuthSession(initial: const AuthSignedIn()),
        network: ScriptedNetwork([500]),
      );
      expect(app.path, AppPaths.identityFailed);

      await app.tap("entry-manage-passkeys");
      expect(app.path, AppPaths.passkeys);

      app.network.enqueue(500);
      await app.tap("passkeys-close");
      expect(app.network.requests, 2);
      expect(app.path, AppPaths.identityFailed);
    });

    testWidgets("a session end while it is open goes to account access", (
      tester,
    ) async {
      final app = await _onPasskeys(tester);

      app.session.emit(const AuthSignedOut());
      await app.settle();

      expect(app.path, AppPaths.access);
      await tester.binding.handlePopRoute();
      await app.settle();
      expect(app.path, AppPaths.access);
    });
  });

  group("the passkey list", () {
    testWidgets("shows each verified passkey's name and dates", (tester) async {
      await _onPasskeys(
        tester,
        setUp: (session) => session
          ..addPasskey(
            name: "iCloud Keychain",
            lastUsedAt: DateTime(2026, 11, 5),
          )
          ..addPasskey(name: "Google Password Manager"),
      );

      expect(find.text("iCloud Keychain"), findsOneWidget);
      expect(
        find.text("Added Nov 1, 2026. Last used Nov 5, 2026."),
        findsOneWidget,
      );
      expect(find.text("Google Password Manager"), findsOneWidget);
      expect(find.text("Added Nov 2, 2026. Not used yet."), findsOneWidget);
      expect(find.textContaining("pk_placeholder"), findsNothing);
    });

    testWidgets("shows the empty state", (tester) async {
      await _onPasskeys(tester);

      expect(find.text(PasskeyStrings.empty), findsOneWidget);
      expect(_key("passkeys-add"), findsOneWidget);
    });

    testWidgets("a failed read offers Try again, which only reads", (
      tester,
    ) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) =>
            session.listFailures.add(const AuthConnectivityFailure()),
      );
      expect(_key("passkeys-read-failure"), findsOneWidget);
      expect(_enabled(tester, "passkeys-add"), isFalse);

      await app.tap("passkeys-retry");

      expect(app.session.listCalls, 2);
      expect(app.session.createCalls, 0);
      expect(find.text(PasskeyStrings.empty), findsOneWidget);
      expect(_enabled(tester, "passkeys-add"), isTrue);
    });

    testWidgets("when passkeys are unavailable, Add is hidden and removal "
        "still works", (tester) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) => session
          ..availability = PasskeyAvailability.unavailable
          ..addPasskey(name: "Old phone"),
      );

      expect(_key("passkeys-add"), findsNothing);
      expect(find.text(PasskeyStrings.unavailable), findsOneWidget);

      await _tapRemove(app, "Old phone");
      await app.tap("passkeys-remove-confirm");

      expect(app.session.removeCalls, hasLength(1));
      expect(find.text(PasskeyStrings.removed), findsOneWidget);
    });
  });

  group("adding a passkey", () {
    testWidgets("reports success only after a fresh read lists it", (
      tester,
    ) async {
      final app = await _onPasskeys(tester);

      await app.tap("passkeys-add");

      expect(app.session.createCalls, 1);
      expect(app.session.listCalls, 2);
      expect(find.text(PasskeyStrings.added), findsOneWidget);
      expect(find.text("Passkey 1"), findsOneWidget);
    });

    testWidgets("a cancelled sheet shows nothing and changes nothing", (
      tester,
    ) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) => session.createResult = const AuthAttemptCancelled(),
      );

      await app.tap("passkeys-add");

      expect(app.session.createCalls, 1);
      expect(app.session.listCalls, 1);
      expect(_key("passkeys-notice"), findsNothing);
      expect(_key("passkeys-change-failure"), findsNothing);
      expect(find.text(PasskeyStrings.empty), findsOneWidget);
    });

    testWidgets("reverification explains the fresh sign-in and signs out", (
      tester,
    ) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) =>
            session.createFailure = const AuthReverificationRequiredFailure(),
      );

      await app.tap("passkeys-add");
      expect(find.text(PasskeyStrings.reverification), findsOneWidget);

      await app.tap("passkeys-sign-out");

      expect(app.session.signOutCalls, 1);
      expect(app.path, AppPaths.access);
    });

    testWidgets("a lost response reads the list and reports the unknown "
        "outcome", (tester) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) => session
          ..createFailure = const AuthConnectivityFailure()
          ..createAppliesDespiteFailure = true,
      );

      await app.tap("passkeys-add");

      expect(app.session.listCalls, 2);
      expect(find.text(PasskeyStrings.unconfirmed), findsOneWidget);
      expect(find.text(PasskeyStrings.added), findsNothing);
      expect(find.text("Passkey 1"), findsOneWidget);
      expect(_enabled(tester, "passkeys-add"), isTrue);
      expect(app.session.createCalls, 1, reason: "no automatic retry");
    });

    testWidgets("after a lost response and a failed read, changes wait for "
        "a successful read", (tester) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) =>
            session.createFailure = const AuthUnexpectedFailure(),
      );
      app.session.listFailures.add(const AuthConnectivityFailure());

      await app.tap("passkeys-add");

      expect(_key("passkeys-read-failure"), findsOneWidget);
      expect(_enabled(tester, "passkeys-add"), isFalse);
      expect(_enabled(tester, "passkeys-close"), isTrue);

      await app.tap("passkeys-retry");

      expect(app.session.createCalls, 1);
      expect(find.text(PasskeyStrings.unconfirmed), findsOneWidget);
      expect(_enabled(tester, "passkeys-add"), isTrue);
    });

    testWidgets("a failed read after a completed addition keeps changes "
        "off until a read succeeds", (tester) async {
      final app = await _onPasskeys(tester);
      app.session.listFailures.add(const AuthConnectivityFailure());

      await app.tap("passkeys-add");

      expect(_key("passkeys-read-failure"), findsOneWidget);
      expect(_enabled(tester, "passkeys-add"), isFalse);

      await app.tap("passkeys-retry");

      expect(app.session.createCalls, 1);
      expect(find.text("Passkey 1"), findsOneWidget);
      expect(_enabled(tester, "passkeys-add"), isTrue);
    });

    testWidgets("Close and Back wait while a change runs", (tester) async {
      final app = await _onPasskeys(tester);
      final gate = app.session.passkeyWriteGate = Completer<void>();

      await tester.tap(_key("passkeys-add"));
      await tester.pump();
      expect(_enabled(tester, "passkeys-close"), isFalse);
      await tester.binding.handlePopRoute();
      await tester.pump();
      expect(app.path, AppPaths.passkeys);
      expect(app.network.requests, 1);

      gate.complete();
      await app.settle();
      expect(_enabled(tester, "passkeys-close"), isTrue);
    });
  });

  group("removing a passkey", () {
    testWidgets("Cancel in the confirmation sends nothing", (tester) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) => session.addPasskey(name: "iCloud Keychain"),
      );

      await _tapRemove(app, "iCloud Keychain");
      expect(
        find.text(PasskeyStrings.removeTitle("iCloud Keychain")),
        findsOne,
      );
      expect(find.text(PasskeyStrings.removeBody), findsOneWidget);
      await app.tap("passkeys-remove-cancel");

      expect(app.session.removeCalls, isEmpty);
      expect(find.text("iCloud Keychain"), findsOneWidget);
    });

    testWidgets("a confirmed removal reports success after a fresh read", (
      tester,
    ) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) => session.addPasskey(name: "iCloud Keychain"),
      );

      await _tapRemove(app, "iCloud Keychain");
      await app.tap("passkeys-remove-confirm");

      expect(app.session.removeCalls, ["pk_placeholder_1"]);
      expect(app.session.listCalls, 2);
      expect(find.text(PasskeyStrings.removed), findsOneWidget);
      expect(find.text(PasskeyStrings.empty), findsOneWidget);
    });

    for (final failure in const <AuthFailure>[
      AuthConnectivityFailure(),
      AuthUnexpectedFailure(),
    ]) {
      for (final applied in const [true, false]) {
        testWidgets("a removal that ends in ${failure.name} and "
            "${applied ? "applied" : "did not apply"} reads the list and "
            "reports the unknown outcome", (tester) async {
          final app = await _onPasskeys(
            tester,
            setUp: (session) => session
              ..addPasskey(name: "iCloud Keychain")
              ..removeFailure = failure
              ..removeAppliesDespiteFailure = applied,
          );

          await _tapRemove(app, "iCloud Keychain");
          await app.tap("passkeys-remove-confirm");

          expect(app.session.listCalls, 2);
          expect(find.text(PasskeyStrings.unconfirmed), findsOneWidget);
          expect(find.text(PasskeyStrings.removed), findsNothing);
          expect(
            find.text("iCloud Keychain"),
            applied ? findsNothing : findsOneWidget,
          );
          expect(_enabled(tester, "passkeys-add"), isTrue);
          expect(app.session.removeCalls, hasLength(1), reason: "no retry");
        });
      }
    }

    testWidgets("a removal that a fresh read still lists is unconfirmed", (
      tester,
    ) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) => session
          ..addPasskey(name: "iCloud Keychain")
          ..removeTakesEffect = false,
      );

      await _tapRemove(app, "iCloud Keychain");
      await app.tap("passkeys-remove-confirm");

      expect(find.text(PasskeyStrings.unconfirmed), findsOneWidget);
      expect(find.text(PasskeyStrings.removed), findsNothing);
      expect(find.text("iCloud Keychain"), findsOneWidget);
    });

    testWidgets("reverification on a removal keeps the passkey and offers "
        "the fresh sign-in", (tester) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) => session
          ..addPasskey(name: "iCloud Keychain")
          ..removeFailure = const AuthReverificationRequiredFailure(),
      );

      await _tapRemove(app, "iCloud Keychain");
      await app.tap("passkeys-remove-confirm");

      expect(find.text(PasskeyStrings.reverification), findsOneWidget);
      expect(_key("passkeys-sign-out"), findsOneWidget);
      expect(find.text("iCloud Keychain"), findsOneWidget);
    });

    testWidgets("the last-method rule keeps the passkey and explains why", (
      tester,
    ) async {
      final app = await _onPasskeys(
        tester,
        setUp: (session) => session
          ..addPasskey(name: "iCloud Keychain")
          ..removeFailure = const AuthLastMethodRequiredFailure(),
      );

      await _tapRemove(app, "iCloud Keychain");
      await app.tap("passkeys-remove-confirm");

      expect(
        find.text(
          PasskeyStrings.changeFailure(const AuthLastMethodRequiredFailure()),
        ),
        findsOneWidget,
      );
      expect(find.text("iCloud Keychain"), findsOneWidget);
      expect(find.text(PasskeyStrings.removed), findsNothing);
    });
  });
}
