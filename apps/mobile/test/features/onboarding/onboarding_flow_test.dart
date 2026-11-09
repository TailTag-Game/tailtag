import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/onboarding/onboarding_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

Finder _key(String key) => find.byKey(Key(key));
final Finder _tryAgain = find.text(UiStrings.tryAgain);
final Finder _unknownOutcome = find.text(OnboardingStrings.unknownOutcome);
final Finder _genericError = find.text(GenericError.unknown.message);
const _handle = "onboarding-handle";
const _name = "onboarding-display-name";
const _continue = "onboarding-continue";
const _passkeys = "entry-manage-passkeys";
const _signOut = "entry-sign-out";

bool _buttonEnabled(WidgetTester tester, String key) =>
    tester.widget<TailTagButton>(_key(key)).onPressed != null;

TextField _field(WidgetTester tester, String key) => tester.widget<TextField>(
  find.descendant(of: _key(key), matching: find.byType(TextField)),
);

String _value(WidgetTester tester, String key) =>
    _field(tester, key).controller!.text;

/// The signed-in app on the empty form. [then] answers the later profile
/// requests, in order.
Future<AppHarness> _onForm(
  WidgetTester tester, {
  List<ProfileReply> then = const [],
  bool sessionEndsOnRecheck = false,
}) async {
  final app = await pumpApp(
    tester,
    session: FakeAuthSession(
      initial: const AuthSignedIn(),
      sessionEndsOnRecheck: sessionEndsOnRecheck,
    ),
    network: ScriptedNetwork([200], [ProfileReply.incomplete, ...then]),
  );
  expect(app.path, AppPaths.onboarding);
  return app;
}

Future<void> _fill(
  WidgetTester tester, {
  String handle = "finn_42",
  String name = "Finn",
}) async {
  await tester.enterText(_key(_handle), handle);
  await tester.enterText(_key(_name), name);
}

/// Fills the form and presses Continue. A stalled reply reaches its deadline
/// inside the longer pump.
Future<void> _submit(AppHarness app) async {
  await _fill(app.tester);
  await app.tester.tap(_key(_continue));
  await app.tester.pump();
  await app.tester.pump(const Duration(seconds: 16));
  await app.settle();
}

void main() {
  group("client rules", () {
    final cases = <({String handle, String name, int errors})>[
      (handle: "", name: "", errors: 2),
      (handle: "   ", name: "Finn", errors: 1),
      (handle: "finn_42", name: "  \n ", errors: 1),
    ];
    for (final c in cases) {
      testWidgets("empty fields send nothing: '${c.handle}', '${c.name}'", (
        tester,
      ) async {
        final app = await _onForm(tester);
        expect(find.text(OnboardingStrings.handleEmpty), findsNothing);
        await _fill(tester, handle: c.handle, name: c.name);

        await app.tap(_continue);

        expect(app.network.profilePuts, isEmpty);
        final shown =
            find.text(OnboardingStrings.handleEmpty).evaluate().length +
            find.text(OnboardingStrings.displayNameEmpty).evaluate().length;
        expect(shown, c.errors);
      });
    }

    testWidgets("validation waits for the first submit, then follows typing", (
      tester,
    ) async {
      final app = await _onForm(tester);
      final error = find.text(OnboardingStrings.handleEmpty);

      await tester.enterText(_key(_handle), "f");
      await tester.enterText(_key(_handle), "");
      await app.settle();
      expect(error, findsNothing);

      await app.tap(_continue);
      expect(error, findsOneWidget);

      await tester.enterText(_key(_handle), "finn");
      await app.settle();
      expect(error, findsNothing);

      await tester.enterText(_key(_handle), "");
      await app.settle();
      expect(error, findsOneWidget);
    });

    final limits = <({String key, int limit})>[
      (key: _handle, limit: 32),
      (key: _name, limit: 50),
    ];
    for (final c in limits) {
      testWidgets("${c.key} stops input at ${c.limit}", (tester) async {
        await _onForm(tester);

        await tester.enterText(_key(c.key), "a" * (c.limit + 9));
        await tester.pump();

        expect(_value(tester, c.key), hasLength(c.limit));
        expect(find.text("${c.limit}/${c.limit}"), findsOneWidget);
      });
    }

    testWidgets("the app sends the text exactly as typed", (tester) async {
      final app = await _onForm(tester, then: [ProfileReply.complete]);
      await _fill(tester, handle: " Finn_42 ", name: "  Finn  ");

      await app.tap(_continue);

      expect(app.network.profilePuts, [
        {"handle": " Finn_42 ", "display_name": "  Finn  "},
      ]);
    });
  });

  testWidgets("a completed save advances once with no extra read", (
    tester,
  ) async {
    final app = await _onForm(tester, then: [ProfileReply.complete]);

    await _submit(app);

    expect(app.path, AppPaths.landing);
    expect(app.network.profilePuts, hasLength(1));
    expect(app.network.profileGets, 1);
    expect(app.network.requests, 1);
  });

  testWidgets("a second tap during a save sends no second write", (
    tester,
  ) async {
    final app = await _onForm(tester, then: [ProfileReply.stalled]);
    await _fill(tester);

    await tester.tap(_key(_continue));
    await tester.tap(_key(_continue));
    await tester.pump();

    expect(app.network.profilePuts, hasLength(1));
    expect(_field(tester, _handle).enabled, isFalse);
    expect(_field(tester, _name).enabled, isFalse);
    expect(tester.widget<TailTagButton>(_key(_continue)).loading, isTrue);

    app.network.releaseProfile(0, ProfileReply.complete);
    await app.settle();
    expect(app.network.profilePuts, hasLength(1));
    expect(app.path, AppPaths.landing);
  });

  group("a 400", () {
    const taken = "This handle is already in use.";
    const badName = "Enter a display name of 1–50 characters.";

    testWidgets("shows each message under its field and keeps the values", (
      tester,
    ) async {
      final app = await _onForm(
        tester,
        then: [
          const ProfileReply(
            status: 400,
            body: '{"handle": ["$taken"], "display_name": ["$badName"]}',
          ),
        ],
      );

      await _submit(app);

      expect(app.path, AppPaths.onboarding);
      expect(
        find.descendant(of: _key(_handle), matching: find.text(taken)),
        findsOneWidget,
      );
      expect(
        find.descendant(of: _key(_name), matching: find.text(badName)),
        findsOneWidget,
      );
      expect(_value(tester, _handle), "finn_42");
      expect(_value(tester, _name), "Finn");
      expect(_buttonEnabled(tester, _continue), isTrue);
    });

    testWidgets("editing a field clears only that field's error, and a "
        "corrected form saves", (tester) async {
      final app = await _onForm(
        tester,
        then: [
          const ProfileReply(
            status: 400,
            body: '{"handle": ["$taken"], "display_name": ["$badName"]}',
          ),
          ProfileReply.complete,
        ],
      );
      await _submit(app);

      await tester.enterText(_key(_handle), "finn_43");
      await app.settle();

      expect(find.text(taken), findsNothing);
      expect(find.text(badName), findsOneWidget);

      await tester.enterText(_key(_name), "Finn the Panther");
      await app.settle();
      await app.tap(_continue);

      expect(app.network.profilePuts, hasLength(2));
      expect(app.path, AppPaths.landing);
    });

    for (final body in [
      '{"non_field_errors": ["No."]}',
      '{"other": ["No."]}',
    ]) {
      testWidgets("with no matching field shows the generic banner: $body", (
        tester,
      ) async {
        final app = await _onForm(
          tester,
          then: [ProfileReply(status: 400, body: body)],
        );

        await _submit(app);

        expect(_genericError, findsOneWidget);
        expect(_value(tester, _handle), "finn_42");
        expect(_buttonEnabled(tester, _continue), isTrue);
      });
    }
  });

  group("a 403 reads the profile once", () {
    final cases = <({String label, ProfileReply read, String path})>[
      (
        label: "disabled",
        read: ProfileReply.disabledIncomplete,
        path: AppPaths.accountUnavailable,
      ),
      (label: "complete", read: ProfileReply.complete, path: AppPaths.landing),
    ];
    for (final c in cases) {
      testWidgets("and routes when ${c.label}", (tester) async {
        final app = await _onForm(
          tester,
          then: [
            const ProfileReply(status: 403, body: "{}"),
            c.read,
          ],
        );

        await _submit(app);

        expect(app.path, c.path);
        expect(app.network.profilePuts, hasLength(1));
        expect(app.network.profileGets, 2);
      });
    }

    testWidgets("and keeps the form when still enabled and incomplete", (
      tester,
    ) async {
      final app = await _onForm(
        tester,
        then: [
          const ProfileReply(status: 403, body: "{}"),
          ProfileReply.incomplete,
        ],
      );

      await _submit(app);

      expect(app.path, AppPaths.onboarding);
      expect(_genericError, findsOneWidget);
      expect(_value(tester, _handle), "finn_42");
      expect(_buttonEnabled(tester, _continue), isTrue);
    });

    testWidgets("and shows an unknown outcome when the read fails", (
      tester,
    ) async {
      final app = await _onForm(
        tester,
        then: [
          const ProfileReply(status: 403, body: "{}"),
          const ProfileReply(status: 500, body: "{}"),
        ],
      );

      await _submit(app);

      expect(_unknownOutcome, findsOneWidget);
      expect(_buttonEnabled(tester, _continue), isFalse);
    });
  });

  group("a 401 on the save", () {
    testWidgets("rechecks once, stays on the form, and repeats no write", (
      tester,
    ) async {
      final app = await _onForm(
        tester,
        then: [
          const ProfileReply(status: 401, body: "{}"),
          ProfileReply.incomplete,
        ],
      );

      await _submit(app);

      expect(app.session.recheckCalls, 1);
      expect(app.path, AppPaths.onboarding);
      expect(find.text(OnboardingStrings.apiAccess), findsOneWidget);
      expect(_value(tester, _handle), "finn_42");
      expect(_buttonEnabled(tester, _continue), isFalse);
      expect(app.network.profilePuts, hasLength(1));
      expect(app.network.profileGets, 1);

      await tester.tap(_tryAgain);
      await app.settle();

      expect(app.network.profileGets, 2);
      expect(app.network.profilePuts, hasLength(1));
      expect(find.text(OnboardingStrings.apiAccess), findsNothing);
      expect(_buttonEnabled(tester, _continue), isTrue);
    });

    testWidgets("goes to account access when the session ended", (
      tester,
    ) async {
      final app = await _onForm(
        tester,
        sessionEndsOnRecheck: true,
        then: [const ProfileReply(status: 401, body: "{}")],
      );

      await _submit(app);

      expect(app.session.recheckCalls, 1);
      expect(app.path, AppPaths.access);
      expect(app.network.profilePuts, hasLength(1));
    });
  });

  group("each result without a definite answer is an unknown outcome", () {
    final cases = <({String label, ProfileReply reply})>[
      (label: "timeout", reply: ProfileReply.stalled),
      (label: "broken connection", reply: ProfileReply.brokenConnection),
      (label: "500", reply: const ProfileReply(status: 500, body: "{}")),
      (label: "409", reply: const ProfileReply(status: 409, body: "{}")),
      (label: "undecodable 200", reply: const ProfileReply(body: "not json")),
      (label: "200 with no completion", reply: ProfileReply.incomplete),
    ];
    for (final c in cases) {
      testWidgets(c.label, (tester) async {
        final app = await _onForm(tester, then: [c.reply]);

        await _submit(app);

        expect(app.path, AppPaths.onboarding);
        expect(_unknownOutcome, findsOneWidget);
        expect(_tryAgain, findsOneWidget);
        expect(_buttonEnabled(tester, _continue), isFalse);
        expect(_value(tester, _handle), "finn_42");
        expect(_field(tester, _handle).enabled, isTrue);
        expect(app.network.profilePuts, hasLength(1));
        expect(app.network.profileGets, 1, reason: "Retry is explicit");
      });
    }
  });

  group("the recovery read sends no write", () {
    const lost = ProfileReply(status: 500, body: "{}");

    final routes = <({String label, ProfileReply read, String path})>[
      (label: "complete", read: ProfileReply.complete, path: AppPaths.landing),
      (
        label: "disabled",
        read: ProfileReply.disabled,
        path: AppPaths.accountUnavailable,
      ),
    ];
    for (final c in routes) {
      testWidgets("${c.label} routes from the server state", (tester) async {
        final app = await _onForm(tester, then: [lost, c.read]);
        await _submit(app);

        await tester.tap(_tryAgain);
        await app.settle();

        expect(app.path, c.path);
        expect(app.network.profilePuts, hasLength(1));
      });
    }

    testWidgets("incomplete unlocks the form, and the player resubmits", (
      tester,
    ) async {
      final app = await _onForm(
        tester,
        then: [lost, ProfileReply.incomplete, ProfileReply.complete],
      );
      await _submit(app);

      await tester.tap(_tryAgain);
      await app.settle();

      expect(_unknownOutcome, findsNothing);
      expect(_value(tester, _handle), "finn_42");
      expect(_buttonEnabled(tester, _continue), isTrue);
      expect(app.network.profilePuts, hasLength(1));

      await app.tap(_continue);

      expect(app.network.profilePuts, hasLength(2));
      expect(app.path, AppPaths.landing);
    });

    final stays = <({String label, ProfileReply read, int rechecks})>[
      (
        label: "a failed read",
        read: const ProfileReply(status: 500, body: "{}"),
        rechecks: 0,
      ),
      (
        label: "a 401 with an active session",
        read: const ProfileReply(status: 401, body: "{}"),
        rechecks: 1,
      ),
    ];
    for (final c in stays) {
      testWidgets("${c.label} leaves the outcome unknown", (tester) async {
        final app = await _onForm(tester, then: [lost, c.read]);
        await _submit(app);

        await tester.tap(_tryAgain);
        await app.settle();

        expect(app.path, AppPaths.onboarding);
        expect(_unknownOutcome, findsOneWidget);
        expect(_tryAgain, findsOneWidget);
        expect(_buttonEnabled(tester, _continue), isFalse);
        expect(app.session.recheckCalls, c.rechecks);
        expect(app.network.profilePuts, hasLength(1));
      });
    }
  });

  group("Manage passkeys on the form", () {
    testWidgets("is disabled during a save, and Sign out is not", (
      tester,
    ) async {
      final app = await _onForm(tester, then: [ProfileReply.stalled]);
      await _fill(tester);

      await tester.tap(_key(_continue));
      await tester.pump();

      expect(_buttonEnabled(tester, _passkeys), isFalse);
      expect(_buttonEnabled(tester, _signOut), isTrue);
      app.network.releaseProfile(0, ProfileReply.complete);
      await app.settle();
    });

    testWidgets("is disabled during a recovery read", (tester) async {
      final app = await _onForm(
        tester,
        then: [
          const ProfileReply(status: 500, body: "{}"),
          ProfileReply.stalled,
        ],
      );
      await _submit(app);
      expect(_buttonEnabled(tester, _passkeys), isTrue);

      await tester.tap(_tryAgain);
      await tester.pump();

      expect(_buttonEnabled(tester, _passkeys), isFalse);
      expect(_field(tester, _handle).enabled, isFalse);
      app.network.releaseProfile(0, ProfileReply.incomplete);
      await app.settle();
    });

    testWidgets("opens the passkey screen, and closing derives a fresh form", (
      tester,
    ) async {
      final app = await _onForm(tester);
      await _fill(tester);

      await app.tap(_passkeys);
      expect(app.path, AppPaths.passkeys);

      app.network
        ..enqueue(200)
        ..enqueueProfile(ProfileReply.incomplete);
      await app.tap("passkeys-close");

      expect(app.path, AppPaths.onboarding);
      expect(_value(tester, _handle), isEmpty);
    });
  });

  group("session isolation", () {
    testWidgets("sign-out aborts a save, and its late answer reaches no one", (
      tester,
    ) async {
      final app = await _onForm(tester, then: [ProfileReply.stalled]);
      await _fill(tester);
      await tester.tap(_key(_continue));
      await tester.pump();

      await app.tap(_signOut);

      expect(app.path, AppPaths.access);
      expect(app.network.profileAborts, 1);

      app.network
        ..enqueue(200)
        ..enqueueProfile(ProfileReply.incomplete);
      app.session.emit(const AuthSignedIn());
      await app.settle();
      expect(app.path, AppPaths.onboarding);

      app.network.releaseProfile(0, ProfileReply.complete);
      await app.settle();

      expect(app.path, AppPaths.onboarding, reason: "the answer is stale");
      expect(_value(tester, _handle), isEmpty);
      expect(_unknownOutcome, findsNothing);
      expect(tester.widget<TailTagButton>(_key(_continue)).loading, isFalse);
    });

    testWidgets("a session end clears an unknown outcome and the values", (
      tester,
    ) async {
      final app = await _onForm(
        tester,
        then: [const ProfileReply(status: 500, body: "{}")],
      );
      await _submit(app);

      app.session.emit(const AuthSignedOut());
      await app.settle();
      app.network
        ..enqueue(200)
        ..enqueueProfile(ProfileReply.incomplete);
      app.session.emit(const AuthSignedIn());
      await app.settle();

      expect(_unknownOutcome, findsNothing);
      expect(_value(tester, _handle), isEmpty);
      expect(_buttonEnabled(tester, _continue), isTrue);
    });
  });
}
