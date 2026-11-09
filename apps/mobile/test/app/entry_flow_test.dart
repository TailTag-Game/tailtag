import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/entry/entry_controller.dart";
import "package:tailtag_mobile/app/entry/entry_screens.dart";
import "package:tailtag_mobile/app/entry/entry_stage.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_failure.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/conventions/convention.dart";
import "package:tailtag_mobile/core/session/player_profile.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";

import "../support/app_test_support.dart";
import "../support/auth_test_support.dart";

final Finder _landing = find.byKey(const Key("convention-home"));
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
            path: AppPaths.home,
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
        if (c.path != AppPaths.home) {
          expect(_landing, findsNothing);
        }
        final state = c.state;
        if (state is AuthFailed && state.failure is AuthUnsupportedFailure) {
          expect(_tryAgain, findsNothing);
        }
        expect(app.session.recheckCalls, c.statuses.contains(401) ? 1 : 0);
        if (!c.statuses.contains(200)) {
          expect(app.network.profileGets, 0);
        }
      });
    }
  });

  group("the profile read selects the stage after the identity read", () {
    final cases =
        <
          ({
            String label,
            ProfileReply profile,
            bool sessionEndsOnRecheck,
            String path,
            int rechecks,
          })
        >[
          (
            label: "enabled and complete",
            profile: ProfileReply.complete,
            sessionEndsOnRecheck: true,
            path: AppPaths.home,
            rechecks: 0,
          ),
          (
            label: "enabled and incomplete",
            profile: ProfileReply.incomplete,
            sessionEndsOnRecheck: true,
            path: AppPaths.onboarding,
            rechecks: 0,
          ),
          (
            label: "disabled and complete",
            profile: ProfileReply.disabled,
            sessionEndsOnRecheck: true,
            path: AppPaths.accountUnavailable,
            rechecks: 0,
          ),
          (
            label: "disabled and incomplete",
            profile: ProfileReply.disabledIncomplete,
            sessionEndsOnRecheck: true,
            path: AppPaths.accountUnavailable,
            rechecks: 0,
          ),
          (
            label: "failed read",
            profile: const ProfileReply(status: 500, body: "{}"),
            sessionEndsOnRecheck: true,
            path: AppPaths.identityFailed,
            rechecks: 0,
          ),
          (
            label: "401 with an active session",
            profile: const ProfileReply(status: 401, body: "{}"),
            sessionEndsOnRecheck: false,
            path: AppPaths.identityFailed,
            rechecks: 1,
          ),
          (
            label: "401 with an ended session",
            profile: const ProfileReply(status: 401, body: "{}"),
            sessionEndsOnRecheck: true,
            path: AppPaths.access,
            rechecks: 1,
          ),
        ];

    for (final c in cases) {
      testWidgets(c.label, (tester) async {
        final app = await pumpApp(
          tester,
          session: FakeAuthSession(
            initial: const AuthSignedIn(),
            sessionEndsOnRecheck: c.sessionEndsOnRecheck,
          ),
          network: ScriptedNetwork([200], [c.profile]),
        );

        expect(app.path, c.path);
        expect(app.network.log, [
          "GET /api/me/",
          "GET /api/profile/",
          if (c.path == AppPaths.home) "GET /api/conventions/active/",
        ]);
        expect(app.network.profilePuts, isEmpty);
        expect(app.session.recheckCalls, c.rechecks);
      });
    }
  });

  group("the account-loading screen", () {
    testWidgets("offers Sign out, which ends the wait", (tester) async {
      final app = await pumpApp(
        tester,
        session: FakeAuthSession(initial: const AuthSignedIn()),
      );
      expect(app.path, AppPaths.identity);

      await app.tap("entry-sign-out");

      expect(app.session.signOutCalls, 1);
      expect(app.path, AppPaths.access);
      app.network.release(0, 200);
      await app.settle();
      expect(app.path, AppPaths.access);
    });

    testWidgets("is the only loading screen with Sign out", (tester) async {
      await pumpApp(
        tester,
        session: FakeAuthSession(initial: const AuthRestoring()),
      );

      expect(find.byKey(const Key("entry-sign-out")), findsNothing);
    });
  });

  group("the account-unavailable screen", () {
    Future<AppHarness> disabled(WidgetTester tester) async {
      final app = await pumpApp(
        tester,
        session: FakeAuthSession(initial: const AuthSignedIn()),
        network: ScriptedNetwork([200], [ProfileReply.disabledIncomplete]),
      );
      expect(app.path, AppPaths.accountUnavailable);
      return app;
    }

    testWidgets("offers no write", (tester) async {
      final app = await disabled(tester);

      expect(find.text(EntryStrings.accountUnavailable), findsOneWidget);
      expect(find.text(EntryStrings.refresh), findsOneWidget);
      expect(find.byKey(const Key("entry-manage-passkeys")), findsOneWidget);
      expect(find.byKey(const Key("entry-sign-out")), findsOneWidget);
      expect(find.byType(TextField), findsNothing);
      expect(app.network.profilePuts, isEmpty);
    });

    final refreshes = <({String label, ProfileReply read, String path})>[
      (
        label: "an enabled incomplete profile opens the form",
        read: ProfileReply.incomplete,
        path: AppPaths.onboarding,
      ),
      (
        label: "an enabled complete profile opens the landing",
        read: ProfileReply.complete,
        path: AppPaths.home,
      ),
      (
        label: "a failed read shows the read failure",
        read: const ProfileReply(status: 500, body: "{}"),
        path: AppPaths.identityFailed,
      ),
    ];
    for (final c in refreshes) {
      testWidgets("Refresh: ${c.label}", (tester) async {
        final app = await disabled(tester);
        app.network
          ..enqueue(200)
          ..enqueueProfile(c.read);

        await app.tap("entry-refresh");

        expect(app.network.requests, 2);
        expect(app.network.profileGets, 2);
        expect(app.path, c.path);
      });
    }

    testWidgets("keeps auth-only passkey controls, and closing derives the "
        "stage again", (tester) async {
      final app = await disabled(tester);

      await app.tap("entry-manage-passkeys");
      expect(app.path, AppPaths.passkeys);

      app.network
        ..enqueue(200)
        ..enqueueProfile(ProfileReply.disabledIncomplete);
      await app.tap("passkeys-close");

      expect(app.path, AppPaths.accountUnavailable);
      expect(app.network.profilePuts, isEmpty);
    });
  });

  testWidgets("Back cannot reopen a completed form", (tester) async {
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
      network: ScriptedNetwork([200], [ProfileReply.incomplete]),
    );
    await tester.enterText(find.byKey(const Key("onboarding-handle")), "finn");
    await tester.enterText(
      find.byKey(const Key("onboarding-display-name")),
      "Finn",
    );
    await app.tap("onboarding-continue");
    expect(app.path, AppPaths.home);

    await tester.binding.handlePopRoute();
    await app.settle();

    expect(app.path, AppPaths.home);
    expect(find.byType(TextField), findsNothing);
  });

  group("the new screens stay usable", () {
    final cases = <({String label, ProfileReply profile})>[
      (label: "onboarding form", profile: ProfileReply.incomplete),
      (label: "account unavailable", profile: ProfileReply.disabled),
      (label: "convention home", profile: ProfileReply.complete),
      (label: "convention picker", profile: ProfileReply.complete),
    ];
    for (final c in cases) {
      testWidgets("${c.label} at 200% text scale", (tester) async {
        final semantics = tester.ensureSemantics();
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);

        await pumpApp(
          tester,
          session: FakeAuthSession(initial: const AuthSignedIn()),
          network: ScriptedNetwork.withConventions(
            [200],
            [c.profile],
            selections: [
              if (c.label == "convention picker")
                ConventionReply.selection(null),
            ],
            conventions: [
              ConventionReply.list([
                conventionJson(id: 1, name: "A long convention name " * 6),
              ]),
            ],
          ),
        );

        expect(tester.takeException(), isNull);
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
        semantics.dispose();
      });
    }
  });

  group("the coordinator takes a resolved profile only in its own scope and "
      "stage", () {
    const complete = PlayerProfile(onboardingComplete: true, isEnabled: true);
    const disabled = PlayerProfile(onboardingComplete: true, isEnabled: false);

    testWidgets("a closed scope changes nothing", (tester) async {
      final app = await pumpApp(
        tester,
        session: FakeAuthSession(initial: const AuthSignedIn()),
        network: ScriptedNetwork([200], [ProfileReply.incomplete]),
      );
      final closed = app.container.read(playerScopeProvider);
      app.container.read(playerScopeProvider.notifier).advance();

      app.container
          .read(entryControllerProvider.notifier)
          .acceptProfile(closed, complete);
      await app.settle();

      expect(app.path, AppPaths.onboarding);
    });

    testWidgets("another stage changes nothing", (tester) async {
      final app = await pumpApp(
        tester,
        session: FakeAuthSession(initial: const AuthSignedIn()),
        network: ScriptedNetwork([200], [ProfileReply.complete]),
      );

      app.container
          .read(entryControllerProvider.notifier)
          .acceptProfile(app.container.read(playerScopeProvider), disabled);
      await app.settle();

      expect(app.path, AppPaths.home);
    });
  });

  testWidgets("a late profile response from an ended session never reaches "
      "the next session", (tester) async {
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
      network: ScriptedNetwork([200], [ProfileReply.stalled]),
    );
    expect(app.path, AppPaths.identity);

    app.session.emit(const AuthSignedOut());
    await app.settle();
    expect(app.network.profileAborts, 1);
    app.network
      ..enqueue(200)
      ..enqueueProfile(ProfileReply.stalled);
    app.session.emit(const AuthSignedIn());
    await app.settle();

    app.network.releaseProfile(0, ProfileReply.complete);
    await app.settle();
    expect(app.path, AppPaths.identity, reason: "the first answer is stale");

    app.network.releaseProfile(1, ProfileReply.incomplete);
    await app.settle();
    expect(app.path, AppPaths.onboarding);
  });

  group("redirect keeps every location inside the stage's screens", () {
    final ready = EntryConventionHome(
      ConventionEnrollment(
        id: 7,
        convention: Convention(
          id: 10,
          name: "Test Con",
          status: ConventionStatus.active,
          startDate: DateTime(2026, 11, 8),
          endDate: DateTime(2026, 11, 10),
        ),
        isSelected: true,
      ),
    );
    const picker = EntryConventionPicker();
    const signedOut = EntrySignedOut();
    final cases = <({EntryStage stage, String from, bool sent, String? to})>[
      (stage: signedOut, from: AppPaths.home, sent: false, to: "/access"),
      (stage: signedOut, from: AppPaths.authProof, sent: false, to: "/access"),
      (stage: signedOut, from: AppPaths.email, sent: false, to: null),
      (stage: signedOut, from: AppPaths.code, sent: false, to: AppPaths.email),
      (stage: signedOut, from: AppPaths.code, sent: true, to: null),
      (stage: const EntryRestoring(), from: "/", sent: false, to: "/start"),
      (stage: ready, from: AppPaths.access, sent: false, to: "/"),
      (stage: ready, from: AppPaths.authProof, sent: false, to: null),
      (stage: ready, from: AppPaths.passkeys, sent: false, to: "/"),
      (
        stage: const EntryPasskeys(),
        from: AppPaths.home,
        sent: false,
        to: AppPaths.passkeys,
      ),
      (
        stage: const EntryOnboarding(),
        from: AppPaths.home,
        sent: false,
        to: AppPaths.onboarding,
      ),
      (
        stage: const EntryAccountUnavailable(),
        from: AppPaths.onboarding,
        sent: false,
        to: AppPaths.accountUnavailable,
      ),
      (stage: ready, from: AppPaths.onboarding, sent: false, to: "/"),
      (stage: ready, from: AppPaths.conventionPicker, sent: false, to: "/"),
      (stage: picker, from: AppPaths.home, sent: false, to: "/conventions"),
      (stage: picker, from: AppPaths.authProof, sent: false, to: null),
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
    expect(app.path, AppPaths.home);
  });

  group("sign-out", () {
    Future<AppHarness> signedIn(WidgetTester tester) async {
      final app = await pumpApp(
        tester,
        session: FakeAuthSession(initial: const AuthSignedIn()),
        network: ScriptedNetwork([200]),
      );
      expect(app.path, AppPaths.home);
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
      expect(app.path, AppPaths.home);
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
