import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/entry/entry_screens.dart";
import "package:tailtag_mobile/app/entry/entry_stage.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";

import "../support/app_test_support.dart";
import "../support/auth_test_support.dart";

final Finder _landing = find.text(EntryStrings.landing);
final Finder _tryAgain = find.text(UiStrings.tryAgain);

void main() {
  group("each auth state and identity outcome shows its stage", () {
    final cases =
        <
          ({
            String label,
            AuthState state,
            List<int> statuses,
            bool sessionEndsOnRecheck,
            String path,
            Finder shows,
          })
        >[
          (
            label: "restoring",
            state: const AuthRestoring(),
            statuses: [],
            sessionEndsOnRecheck: true,
            path: AppPaths.restoring,
            shows: find.text(EntryStrings.restoring),
          ),
          (
            label: "failed",
            state: const AuthFailed(AuthConnectivityFailure()),
            statuses: [],
            sessionEndsOnRecheck: true,
            path: AppPaths.recovery,
            shows: _tryAgain,
          ),
          (
            label: "failed on an unsupported platform, with no retry",
            state: const AuthFailed(AuthUnsupportedFailure()),
            statuses: [],
            sessionEndsOnRecheck: true,
            path: AppPaths.recovery,
            shows: find.text(EntryStrings.unsupported),
          ),
          (
            label: "signed out",
            state: const AuthSignedOut(),
            statuses: [],
            sessionEndsOnRecheck: true,
            path: AppPaths.access,
            shows: find.byKey(const Key("access-create-account")),
          ),
          (
            label: "signed in with a readable identity",
            state: const AuthSignedIn(),
            statuses: [200],
            sessionEndsOnRecheck: true,
            path: AppPaths.landing,
            shows: _landing,
          ),
          (
            label: "signed in with a failed identity read",
            state: const AuthSignedIn(),
            statuses: [500],
            sessionEndsOnRecheck: true,
            path: AppPaths.identityFailed,
            shows: find.text(UiStrings.unknownError),
          ),
          (
            label: "signed in, API refuses the token, session still active",
            state: const AuthSignedIn(),
            statuses: [401],
            sessionEndsOnRecheck: false,
            path: AppPaths.identityFailed,
            shows: find.text(EntryStrings.apiAccess),
          ),
          (
            label: "signed in, API refuses the token, session ended",
            state: const AuthSignedIn(),
            statuses: [401],
            sessionEndsOnRecheck: true,
            path: AppPaths.access,
            shows: find.byKey(const Key("access-create-account")),
          ),
        ];

    for (final c in cases) {
      testWidgets(c.label, (tester) async {
        final app = await pumpApp(
          tester,
          session: FakeAuthSession(
            initial: c.state,
            sessionEndsOnRecheck: c.sessionEndsOnRecheck,
          ),
          network: ScriptedNetwork(c.statuses),
        );

        expect(app.path, c.path);
        expect(c.shows, findsOneWidget);
        if (c.path != AppPaths.landing) {
          expect(_landing, findsNothing);
        }
        final state = c.state;
        if (state is AuthFailed && state.failure is AuthUnsupportedFailure) {
          expect(_tryAgain, findsNothing);
        }
        expect(app.session.recheckCalls, c.statuses.contains(401) ? 1 : 0);
      });
    }
  });

  group("redirect keeps every location inside the stage's screens", () {
    const ready = EntryReady();
    const signedOut = EntrySignedOut();
    final cases = <({EntryStage stage, String from, bool sent, String? to})>[
      (stage: signedOut, from: AppPaths.landing, sent: false, to: "/access"),
      (stage: signedOut, from: AppPaths.authProof, sent: false, to: "/access"),
      (stage: signedOut, from: AppPaths.email, sent: false, to: null),
      (stage: signedOut, from: AppPaths.code, sent: false, to: AppPaths.email),
      (stage: signedOut, from: AppPaths.code, sent: true, to: null),
      (stage: const EntryRestoring(), from: "/", sent: false, to: "/start"),
      (stage: ready, from: AppPaths.access, sent: false, to: "/"),
      (stage: ready, from: AppPaths.authProof, sent: false, to: null),
    ];

    for (final c in cases) {
      test("${c.stage} at ${c.from} (code sent: ${c.sent})", () {
        expect(redirectFor(c.stage, c.from, codeSent: c.sent), c.to);
      });
    }

    // Each code screen opens only for a code from its own kind of attempt.
    final codeCases = <({String from, bool viaProvider, String? to})>[
      (from: AppPaths.providerCode, viaProvider: true, to: null),
      (from: AppPaths.providerCode, viaProvider: false, to: AppPaths.access),
      (from: AppPaths.code, viaProvider: true, to: AppPaths.email),
    ];
    for (final c in codeCases) {
      test("signed out at ${c.from} (provider code: ${c.viaProvider})", () {
        expect(
          redirectFor(
            signedOut,
            c.from,
            codeSent: true,
            viaProvider: c.viaProvider,
          ),
          c.to,
        );
      });
    }
  });

  testWidgets("recovery retry reloads the session through the auth "
      "boundary", (tester) async {
    final session = FakeAuthSession(
      initial: const AuthFailed(AuthUnexpectedFailure()),
    )..reloadOutcome = const AuthSignedIn();
    final app = await pumpApp(
      tester,
      session: session,
      network: ScriptedNetwork([200]),
    );

    await tester.tap(_tryAgain);
    await app.settle();

    expect(session.reloadCalls, 1);
    expect(session.signOutCalls, 0);
    expect(app.path, AppPaths.landing);
  });

  group("sign-out", () {
    Future<AppHarness> signedIn(WidgetTester tester) async {
      final app = await pumpApp(
        tester,
        session: FakeAuthSession(initial: const AuthSignedIn()),
        network: ScriptedNetwork([200]),
      );
      expect(app.path, AppPaths.landing);
      return app;
    }

    testWidgets("hides content at once, ends on account access, and Back "
        "cannot return", (tester) async {
      final app = await signedIn(tester);
      final epoch = app.container.read(playerScopeProvider).epoch;
      app.session.gate = Completer<void>();

      await tester.tap(find.byKey(const Key("entry-sign-out")));
      await tester.pump();

      expect(_landing, findsNothing);
      expect(app.path, AppPaths.signingOut);
      expect(app.container.read(playerScopeProvider).epoch, epoch + 1);

      app.session.gate!.complete();
      await app.settle();
      expect(app.path, AppPaths.access);

      await tester.binding.handlePopRoute();
      await app.settle();
      expect(_landing, findsNothing);
    });

    testWidgets("a failure with the session still active offers retry", (
      tester,
    ) async {
      final app = await signedIn(tester);
      app.session.signOutFailure = const AuthConnectivityFailure();

      await app.tap("entry-sign-out");
      expect(app.path, AppPaths.signOutFailed);
      expect(_landing, findsNothing);

      app.session.signOutFailure = null;
      await app.tap("entry-retry-sign-out");
      expect(app.session.signOutCalls, 2);
      expect(app.path, AppPaths.access);
    });

    testWidgets("Return to TailTag runs a fresh identity bootstrap", (
      tester,
    ) async {
      final app = await signedIn(tester);
      app.session.signOutFailure = const AuthConnectivityFailure();
      await app.tap("entry-sign-out");
      final epoch = app.container.read(playerScopeProvider).epoch;
      app.network.enqueue(200);

      await app.tap("entry-return");

      expect(app.network.requests, 2);
      expect(app.container.read(playerScopeProvider).epoch, epoch + 1);
      expect(app.path, AppPaths.landing);
    });

    testWidgets("a failure after the SDK ended the session shows account "
        "access", (tester) async {
      final app = await signedIn(tester);
      app.session
        ..signOutFailure = const AuthConnectivityFailure()
        ..stateAfterFailedSignOut = const AuthSignedOut();

      await app.tap("entry-sign-out");

      expect(app.path, AppPaths.access);
    });
  });

  testWidgets("a late identity response from an ended session never "
      "reaches the next session", (tester) async {
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
    );
    expect(app.path, AppPaths.identity);

    app.session.emit(const AuthSignedOut());
    await app.settle();
    app.session.emit(const AuthSignedIn());
    await app.settle();
    expect(app.network.requests, 2);

    app.network.release(0, 200);
    await app.settle();
    expect(app.path, AppPaths.identity, reason: "the first answer is stale");
    expect(_landing, findsNothing);

    app.network.release(1, 500);
    await app.settle();
    expect(app.path, AppPaths.identityFailed);
  });
}
