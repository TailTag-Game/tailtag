import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/debug/auth_proof_screen.dart";
import "package:tailtag_mobile/app/entry/entry_screens.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/ui/generic_error.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/conventions/convention_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

const _getProfile = "GET /api/profile/";
const _getMe = "GET /api/me/";
const _getActive = "GET /api/conventions/active/";
const _getConventions = "GET /api/conventions/";
const _getEnrollments = "GET /api/conventions/enrollments/";
const _post = "POST /api/conventions/enrollments/";
const _put = "PUT /api/conventions/active/";

const _passkeys = "entry-manage-passkeys";
const _signOut = "entry-sign-out";
const _change = "convention-change";
const _closeKey = "conventions-close";

Finder _key(String key) => find.byKey(Key(key));
Finder _text(String text) => find.text(text);
final Finder _tryAgain = find.text(UiStrings.tryAgain);
final Finder _home = _key("convention-home");

String _action(int id) => "convention-action-$id";

bool _enabled(WidgetTester tester, String key) =>
    tester.widget<TailTagButton>(_key(key)).onPressed != null;

final String _fresh = conventionJson(id: 1, name: "Fresh Con");
final String _joined = conventionJson(id: 2, name: "Joined Con");
final String _current = conventionJson(id: 3, name: "Current Con");

String _joinedEnrollment() =>
    enrollmentJson(id: 22, convention: _joined, selected: false);
String _currentEnrollment() => enrollmentJson(id: 33, convention: _current);

ConventionReply _conventions() =>
    ConventionReply.list([_fresh, _joined, _current]);
ConventionReply _enrollments() =>
    ConventionReply.list([_joinedEnrollment(), _currentEnrollment()]);
ConventionReply _selected() => ConventionReply.selection(_currentEnrollment());

/// A tall window, so every row is on screen and can take a tap.
void _tallWindow(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 5400);
  addTearDown(tester.view.resetPhysicalSize);
}

Future<AppHarness> _pump(
  WidgetTester tester,
  ScriptedNetwork network, {
  bool sessionEndsOnRecheck = false,
}) async {
  _tallWindow(tester);
  return await pumpApp(
    tester,
    session: FakeAuthSession(
      initial: const AuthSignedIn(),
      sessionEndsOnRecheck: sessionEndsOnRecheck,
    ),
    network: network,
  );
}

/// The app on the home of "Current Con".
Future<AppHarness> _onHome(
  WidgetTester tester, {
  List<ProfileReply> profiles = const [],
  bool sessionEndsOnRecheck = false,
}) async {
  final app = await _pump(
    tester,
    ScriptedNetwork.withConventions(
      [200],
      [ProfileReply.complete, ...profiles],
      selections: [_selected()],
    ),
    sessionEndsOnRecheck: sessionEndsOnRecheck,
  );
  expect(app.path, AppPaths.home);
  return app;
}

/// The app on the picker, opened from the home, with three rows. Writes
/// answer with [writes], and later list reads with [conventions] and
/// [enrollments].
Future<AppHarness> _onPickerFromHome(
  WidgetTester tester, {
  List<ProfileReply> profiles = const [],
  List<ConventionReply> writes = const [],
  List<ConventionReply> conventions = const [],
  List<ConventionReply> enrollments = const [],
  bool sessionEndsOnRecheck = false,
}) async {
  final app = await _pump(
    tester,
    ScriptedNetwork.withConventions(
      [200],
      [ProfileReply.complete, ...profiles],
      selections: [_selected()],
      conventions: [_conventions(), ...conventions],
      enrollments: [_enrollments(), ...enrollments],
      writes: writes,
    ),
    sessionEndsOnRecheck: sessionEndsOnRecheck,
  );
  await app.tap(_change);
  expect(app.path, AppPaths.conventionPicker);
  return app;
}

/// The app on the picker of a player with no selection.
Future<AppHarness> _onFirstPicker(
  WidgetTester tester, {
  List<ConventionReply> conventions = const [],
  List<ConventionReply> enrollments = const [],
  List<ConventionReply> writes = const [],
  List<ProfileReply> profiles = const [],
}) async {
  final app = await _pump(
    tester,
    ScriptedNetwork.withConventions(
      [200],
      [ProfileReply.complete, ...profiles],
      selections: [ConventionReply.selection(null)],
      conventions: conventions,
      enrollments: enrollments,
      writes: writes,
    ),
  );
  expect(app.path, AppPaths.conventionPicker);
  return app;
}

/// Moves the app to the background and back.
Future<void> _foreground(AppHarness app) async {
  app.tester.binding
    ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
    ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
    ..handleAppLifecycleStateChanged(AppLifecycleState.paused)
    ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
    ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
    ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
  await app.settle();
}

/// Lets a stalled request reach its deadline, so no timer outlives the test.
Future<void> _drain(AppHarness app) async {
  await app.tester.pump(const Duration(seconds: 16));
  await app.settle();
}

/// Taps a row, and lets a stalled write reach its deadline.
Future<void> _enterAndWait(AppHarness app, int id) async {
  await app.tester.tap(_key(_action(id)));
  await app.tester.pump();
  await app.tester.pump(const Duration(seconds: 16));
  await app.settle();
}

void main() {
  group("the selection read in the bootstrap", () {
    testWidgets("a failure shows the failed stage, and Try again runs the "
        "whole bootstrap", (tester) async {
      final app = await _pump(
        tester,
        ScriptedNetwork.withConventions(
          [200, 200],
          [ProfileReply.complete, ProfileReply.complete],
          selections: [ConventionReply.brokenConnection, _selected()],
        ),
      );
      expect(app.path, AppPaths.identityFailed);
      expect(_key(_passkeys), findsOneWidget);

      await tester.tap(_tryAgain);
      await app.settle();

      expect(app.path, AppPaths.home);
      expect(app.network.count(_getMe), 2);
    });

    final unauthorized = <({String label, bool ended, String path})>[
      (label: "active", ended: false, path: AppPaths.identityFailed),
      (label: "ended", ended: true, path: AppPaths.access),
    ];
    for (final c in unauthorized) {
      testWidgets("a 401 with an ${c.label} session rechecks once", (
        tester,
      ) async {
        final app = await _pump(
          tester,
          ScriptedNetwork.withConventions(
            [200],
            [ProfileReply.complete],
            selections: [const ConventionReply(status: 401)],
          ),
          sessionEndsOnRecheck: c.ended,
        );

        expect(app.path, c.path);
        expect(app.session.recheckCalls, 1);
      });
    }
  });

  group("the picker", () {
    testWidgets("marks rows from both lists in server order and hides "
        "enrollments that are not listed", (tester) async {
      final app = await _pump(
        tester,
        ScriptedNetwork.withConventions(
          [200],
          [ProfileReply.complete],
          selections: [_selected()],
          conventions: [_conventions()],
          enrollments: [
            ConventionReply.list([
              _joinedEnrollment(),
              _currentEnrollment(),
              enrollmentJson(
                id: 99,
                convention: conventionJson(
                  id: 9,
                  name: "Paused Con",
                  status: "paused",
                ),
                selected: false,
              ),
            ]),
          ],
        ),
      );

      await app.tap(_change);

      expect(
        tester.widget<TailTagButton>(_key(_action(1))).label,
        ConventionStrings.joinAndEnter,
      );
      expect(
        tester.widget<TailTagButton>(_key(_action(2))).label,
        ConventionStrings.enterConvention,
      );
      expect(_key(_action(3)), findsNothing);
      expect(_text(ConventionStrings.joined), findsOneWidget);
      expect(_text(ConventionStrings.selected), findsOneWidget);
      expect(_text("Paused Con"), findsNothing);
      final top = tester.getTopLeft(_text("Fresh Con")).dy;
      expect(top, lessThan(tester.getTopLeft(_text("Joined Con")).dy));
      expect(
        tester.getTopLeft(_text("Joined Con")).dy,
        lessThan(tester.getTopLeft(_text("Current Con")).dy),
      );
      expect(app.network.count(_getActive), 1, reason: "no separate read");
      expect(app.network.conventionWrites, isEmpty);
    });

    testWidgets("never selects the only option", (tester) async {
      final app = await _onFirstPicker(
        tester,
        conventions: [
          ConventionReply.list([_fresh]),
        ],
      );

      expect(app.network.conventionWrites, isEmpty);
      expect(_key(_closeKey), findsNothing);
      expect(_text("Fresh Con"), findsOneWidget);
    });

    testWidgets("shows a labelled wait", (tester) async {
      final app = await _onFirstPicker(
        tester,
        conventions: [ConventionReply.stalled],
      );

      expect(_text(ConventionStrings.loading), findsOneWidget);
      await _drain(app);
    });

    testWidgets("shows an empty state with Refresh, passkeys, and sign-out", (
      tester,
    ) async {
      final app = await _onFirstPicker(tester);
      expect(_text(ConventionStrings.emptyTitle), findsOneWidget);
      expect(_tryAgain, findsNothing);
      expect(_key(_passkeys), findsOneWidget);
      expect(_key(_signOut), findsOneWidget);
      app.network.enqueueConventions(ConventionReply.list([_fresh]));

      await app.tap("conventions-refresh");

      expect(_text("Fresh Con"), findsOneWidget);
    });

    final failures = <({String label, bool conventionsFail})>[
      (label: "conventions", conventionsFail: true),
      (label: "enrollments", conventionsFail: false),
    ];
    for (final c in failures) {
      testWidgets("a failed ${c.label} read shows no partial list", (
        tester,
      ) async {
        final app = await _onFirstPicker(
          tester,
          conventions: [
            if (c.conventionsFail)
              ConventionReply.brokenConnection
            else
              ConventionReply.list([_fresh]),
          ],
          enrollments: [
            if (c.conventionsFail)
              ConventionReply.list(const [])
            else
              ConventionReply.brokenConnection,
          ],
        );
        expect(_text(GenericError.noConnection.message), findsOneWidget);
        expect(_text("Fresh Con"), findsNothing);
        expect(_text(ConventionStrings.emptyTitle), findsNothing);
        app.network
          ..enqueueConventions(ConventionReply.list([_fresh]))
          ..enqueueEnrollments(ConventionReply.list(const []));

        await tester.tap(_tryAgain);
        await app.settle();

        expect(_text("Fresh Con"), findsOneWidget);
      });
    }

    testWidgets("reloads on a pull", (tester) async {
      final app = await _onFirstPicker(
        tester,
        conventions: [
          ConventionReply.list([_fresh]),
        ],
      );
      final before = app.network.count(_getConventions);
      app.network
        ..enqueueConventions(ConventionReply.list([_fresh]))
        ..enqueueEnrollments(ConventionReply.list(const []));

      await tester.fling(_text("Fresh Con"), const Offset(0, 500), 1000);
      await app.settle();

      expect(app.network.count(_getConventions), before + 1);
    });
  });

  group("a successful write goes home from its response", () {
    final cases =
        <
          ({
            String label,
            int row,
            ConventionReply reply,
            String request,
            Map<String, Object?> body,
          })
        >[
          (
            label: "Join and enter with 201",
            row: 1,
            reply: ConventionReply(
              status: 201,
              body: enrollmentJson(convention: _fresh),
            ),
            request: _post,
            body: {"convention_id": 1, "set_active": true},
          ),
          (
            label: "Join and enter with a retried 200",
            row: 1,
            reply: ConventionReply(body: enrollmentJson(convention: _fresh)),
            request: _post,
            body: {"convention_id": 1, "set_active": true},
          ),
          (
            label: "Enter convention",
            row: 2,
            reply: ConventionReply.selection(
              enrollmentJson(id: 22, convention: _joined),
            ),
            request: _put,
            body: {"convention_id": 2},
          ),
        ];
    for (final c in cases) {
      testWidgets(c.label, (tester) async {
        final app = await _onPickerFromHome(tester, writes: [c.reply]);

        await app.tap(_action(c.row));

        expect(app.path, AppPaths.home);
        expect(app.network.conventionWrites, hasLength(1));
        expect(app.network.conventionWrites.single.request, c.request);
        expect(app.network.conventionWrites.single.body, c.body);
        expect(app.network.log.last, c.request, reason: "no read follows");
        expect(_text(c.row == 1 ? "Fresh Con" : "Joined Con"), findsOneWidget);
      });
    }
  });

  testWidgets("during a write, one request runs and the player cannot leave "
      "except by signing out", (tester) async {
    final app = await _onPickerFromHome(
      tester,
      writes: [ConventionReply.stalled],
    );

    await tester.tap(_key(_action(1)));
    await tester.pump();
    await tester.tap(_key(_action(1)), warnIfMissed: false);
    await tester.pump();

    expect(app.network.conventionWrites, hasLength(1));
    expect(_enabled(tester, _action(2)), isFalse);
    expect(_enabled(tester, _passkeys), isFalse);
    expect(_enabled(tester, _signOut), isTrue);
    expect(tester.widget<IconButton>(_key(_closeKey)).onPressed, isNull);
    await tester.binding.handlePopRoute();
    await tester.pump();
    expect(app.path, AppPaths.conventionPicker);
    await _drain(app);
  });

  group("a definite refusal", () {
    for (final status in [400, 404]) {
      testWidgets("$status explains, reads again, and keeps the selection", (
        tester,
      ) async {
        final app = await _onPickerFromHome(
          tester,
          writes: [
            ConventionReply(
              status: status,
              body: '{"convention_id": ["Closed."]}',
            ),
          ],
          conventions: [
            ConventionReply.list([_joined, _current]),
          ],
          enrollments: [_enrollments()],
        );

        await app.tap(_action(1));

        expect(app.path, AppPaths.conventionPicker);
        expect(_text(ConventionStrings.entryFailed), findsOneWidget);
        expect(_text("Closed."), findsNothing);
        expect(_text("Fresh Con"), findsNothing, reason: "the list is fresh");
        expect(_enabled(tester, _action(2)), isTrue);
        expect(app.network.conventionWrites, hasLength(1));

        await app.tap(_closeKey);
        expect(app.path, AppPaths.home);
        expect(_text("Current Con"), findsOneWidget);
      });
    }

    testWidgets("a failed read after it locks actions until a read succeeds", (
      tester,
    ) async {
      final app = await _onPickerFromHome(
        tester,
        writes: [const ConventionReply(status: 400)],
        conventions: [ConventionReply.brokenConnection, _conventions()],
        enrollments: [_enrollments(), _enrollments()],
      );

      await app.tap(_action(1));

      expect(_text(ConventionStrings.entryFailed), findsNothing);
      expect(_text(GenericError.noConnection.message), findsOneWidget);
      expect(_enabled(tester, _action(2)), isFalse);

      await tester.tap(_tryAgain);
      await app.settle();

      expect(_enabled(tester, _action(2)), isTrue);
      expect(app.network.conventionWrites, hasLength(1));
    });

    final forbidden =
        <({String label, ProfileReply profile, String path, Finder shows})>[
          (
            label: "a disabled profile",
            profile: ProfileReply.disabled,
            path: AppPaths.accountUnavailable,
            shows: _text(EntryStrings.accountUnavailable),
          ),
          (
            label: "an incomplete profile",
            profile: ProfileReply.incomplete,
            path: AppPaths.onboarding,
            shows: _key("onboarding-handle"),
          ),
          (
            label: "an eligible profile",
            profile: ProfileReply.complete,
            path: AppPaths.conventionPicker,
            shows: _text(GenericError.unknown.message),
          ),
          (
            label: "a failed read",
            profile: ProfileReply.brokenConnection,
            path: AppPaths.conventionPicker,
            shows: _text(GenericError.noConnection.message),
          ),
        ];
    for (final c in forbidden) {
      testWidgets("403 then ${c.label}", (tester) async {
        final app = await _onPickerFromHome(
          tester,
          writes: [const ConventionReply(status: 403)],
          profiles: [c.profile],
          conventions: [_conventions()],
          enrollments: [_enrollments()],
        );

        await app.tap(_action(1));

        expect(app.path, c.path);
        expect(c.shows, findsOneWidget);
        expect(app.network.conventionWrites, hasLength(1));
      });
    }

    testWidgets("401 with an ended session goes to the account screen", (
      tester,
    ) async {
      final app = await _onPickerFromHome(
        tester,
        writes: [const ConventionReply(status: 401)],
        sessionEndsOnRecheck: true,
      );

      await app.tap(_action(1));

      expect(app.path, AppPaths.access);
      expect(app.session.recheckCalls, 1);
      expect(app.network.conventionWrites, hasLength(1));
    });

    testWidgets("401 with an active session locks and reads on Try again", (
      tester,
    ) async {
      final app = await _onPickerFromHome(
        tester,
        writes: [const ConventionReply(status: 401)],
        conventions: [_conventions()],
        enrollments: [_enrollments()],
      );

      await app.tap(_action(1));

      expect(_text(ConventionStrings.apiAccess), findsOneWidget);
      expect(_enabled(tester, _action(2)), isFalse);
      expect(app.session.recheckCalls, 1);

      await tester.tap(_tryAgain);
      await app.settle();

      expect(_text(ConventionStrings.notJoined), findsOneWidget);
      expect(_enabled(tester, _action(1)), isTrue);
      expect(app.network.conventionWrites, hasLength(1));
    });
  });

  group("an unknown outcome", () {
    final outcomes = <({String label, ConventionReply reply})>[
      (label: "timeout", reply: ConventionReply.stalled),
      (label: "connectivity", reply: ConventionReply.brokenConnection),
      (label: "409", reply: const ConventionReply(status: 409)),
      (label: "500", reply: const ConventionReply(status: 500)),
      (label: "an undecodable 201", reply: const ConventionReply(status: 201)),
      (
        label: "a 201 that is not selected",
        reply: ConventionReply(
          status: 201,
          body: enrollmentJson(convention: _fresh, selected: false),
        ),
      ),
    ];
    for (final c in outcomes) {
      testWidgets("${c.label} locks writes and repeats nothing", (
        tester,
      ) async {
        final app = await _onPickerFromHome(tester, writes: [c.reply]);

        await _enterAndWait(app, 1);

        expect(app.path, AppPaths.conventionPicker);
        expect(_text(ConventionStrings.unknownOutcome), findsOneWidget);
        expect(_tryAgain, findsOneWidget);
        expect(_enabled(tester, _action(1)), isFalse);
        expect(_enabled(tester, _action(2)), isFalse);
        expect(app.network.conventionWrites, hasLength(1));
      });
    }

    final selectedFresh = enrollmentJson(id: 11, convention: _fresh);
    final joinedFresh = enrollmentJson(
      id: 11,
      convention: _fresh,
      selected: false,
    );
    final recoveries =
        <
          ({
            String label,
            ConventionReply enrollments,
            String? path,
            String? banner,
            String? action,
          })
        >[
          (
            label: "the target is selected",
            enrollments: ConventionReply.list([selectedFresh]),
            path: AppPaths.home,
            banner: null,
            action: null,
          ),
          (
            label: "the target is joined but not selected",
            enrollments: ConventionReply.list([joinedFresh]),
            path: null,
            banner: ConventionStrings.notEntered,
            action: ConventionStrings.enterConvention,
          ),
          (
            label: "the target is not joined",
            enrollments: ConventionReply.list([_joinedEnrollment()]),
            path: null,
            banner: ConventionStrings.notJoined,
            action: ConventionStrings.joinAndEnter,
          ),
        ];
    for (final c in recoveries) {
      testWidgets("recovery when ${c.label}", (tester) async {
        final app = await _onPickerFromHome(
          tester,
          writes: [ConventionReply.brokenConnection],
          conventions: [_conventions()],
          enrollments: [c.enrollments],
        );
        await _enterAndWait(app, 1);

        await tester.tap(_tryAgain);
        await app.settle();

        expect(app.network.conventionWrites, hasLength(1));
        if (c.path != null) {
          expect(app.path, c.path);
          expect(_text("Fresh Con"), findsOneWidget);
          return;
        }
        expect(_text(c.banner!), findsOneWidget);
        expect(tester.widget<TailTagButton>(_key(_action(1))).label, c.action);
        expect(_enabled(tester, _action(1)), isTrue);
      });
    }

    testWidgets("recovery when the target is no longer listed", (tester) async {
      final app = await _onPickerFromHome(
        tester,
        writes: [ConventionReply.brokenConnection],
        conventions: [
          ConventionReply.list([_joined, _current]),
        ],
        enrollments: [_enrollments()],
      );
      await _enterAndWait(app, 1);

      await tester.tap(_tryAgain);
      await app.settle();

      expect(_text(ConventionStrings.entryFailed), findsOneWidget);
      expect(_enabled(tester, _action(2)), isTrue);
      expect(app.network.conventionWrites, hasLength(1));
    });

    testWidgets("a pull does not run the recovery read", (tester) async {
      final app = await _onPickerFromHome(
        tester,
        writes: [ConventionReply.brokenConnection],
      );
      await _enterAndWait(app, 1);
      final before = app.network.log.length;

      await tester.fling(_text("Fresh Con"), const Offset(0, 500), 1000);
      await app.settle();

      expect(app.network.log.length, before);
      expect(_text(ConventionStrings.unknownOutcome), findsOneWidget);
    });

    final unresolved = <({String label, ConventionReply read, int rechecks})>[
      (
        label: "a failed read",
        read: ConventionReply.brokenConnection,
        rechecks: 0,
      ),
      (
        label: "a 401 on an active session",
        read: const ConventionReply(status: 401),
        rechecks: 1,
      ),
    ];
    for (final c in unresolved) {
      testWidgets("${c.label} keeps the outcome unknown", (tester) async {
        final app = await _onPickerFromHome(
          tester,
          writes: [ConventionReply.brokenConnection],
          conventions: [c.read],
          enrollments: [_enrollments()],
        );
        await _enterAndWait(app, 1);

        await tester.tap(_tryAgain);
        await app.settle();

        expect(_text(ConventionStrings.unknownOutcome), findsOneWidget);
        expect(_tryAgain, findsOneWidget);
        expect(_enabled(tester, _action(2)), isFalse);
        expect(app.session.recheckCalls, c.rechecks);
        expect(app.network.conventionWrites, hasLength(1));
      });
    }
  });

  group("Change convention", () {
    testWidgets("Close returns at once with no read", (tester) async {
      final app = await _onPickerFromHome(tester);
      final before = app.network.log.length;

      await app.tap(_closeKey);

      expect(app.path, AppPaths.home);
      expect(_text("Current Con"), findsOneWidget);
      expect(app.network.log.length, before);
    });

    testWidgets("Close during a read drops the late lists", (tester) async {
      final app = await _pump(
        tester,
        ScriptedNetwork.withConventions(
          [200],
          [ProfileReply.complete],
          selections: [_selected()],
          conventions: [ConventionReply.stalled],
        ),
      );
      await app.tap(_change);

      await app.tap(_closeKey);
      app.network.releaseConvention(0, _conventions());
      await app.settle();

      expect(app.path, AppPaths.home);
      expect(_text("Current Con"), findsOneWidget);
    });

    testWidgets("system Back closes it like Close", (tester) async {
      final app = await _onPickerFromHome(tester);

      await tester.binding.handlePopRoute();
      await app.settle();

      expect(app.path, AppPaths.home);
    });

    testWidgets("Close after an unknown outcome runs a fresh bootstrap", (
      tester,
    ) async {
      final app = await _onPickerFromHome(
        tester,
        writes: [ConventionReply.brokenConnection],
      );
      await _enterAndWait(app, 1);
      app.network
        ..enqueue(200)
        ..enqueueSelection(
          ConventionReply.selection(enrollmentJson(id: 11, convention: _fresh)),
        );

      await app.tap(_closeKey);

      expect(app.path, AppPaths.home);
      expect(_text("Fresh Con"), findsOneWidget);
      expect(app.network.count(_getMe), 2);
    });
  });

  group("the home", () {
    final statuses = <({String wire, String label, bool banner})>[
      (wire: "active", label: "Active", banner: false),
      (wire: "paused", label: "Paused", banner: true),
      (wire: "completed", label: "Completed", banner: true),
      (wire: "cancelled", label: "Cancelled", banner: true),
      (wire: "draft", label: "Not open", banner: true),
    ];
    for (final c in statuses) {
      testWidgets("shows real values for ${c.wire}, with no write", (
        tester,
      ) async {
        final app = await _pump(
          tester,
          ScriptedNetwork.withConventions(
            [200],
            [ProfileReply.complete],
            selections: [
              ConventionReply.selection(
                enrollmentJson(convention: conventionJson(status: c.wire)),
              ),
            ],
          ),
        );

        expect(app.network.log, [_getMe, _getProfile, _getActive]);
        expect(_text("Test Con"), findsOneWidget);
        expect(_text("Nov 8, 2026 to Nov 10, 2026"), findsOneWidget);
        expect(_text(c.label), findsOneWidget);
        expect(
          _text(ConventionStrings.inactive),
          c.banner ? findsOneWidget : findsNothing,
        );
        expect(_key(_change), findsOneWidget);
        expect(_key("convention-refresh"), findsOneWidget);
        expect(_key(_passkeys), findsOneWidget);
        expect(_key(_signOut), findsOneWidget);
      });
    }

    testWidgets("shows one date when the convention lasts one day", (
      tester,
    ) async {
      await _pump(
        tester,
        ScriptedNetwork.withConventions(
          [200],
          [ProfileReply.complete],
          selections: [
            ConventionReply.selection(
              enrollmentJson(convention: conventionJson(end: "2026-11-08")),
            ),
          ],
        ),
      );

      expect(_text("Nov 8, 2026"), findsOneWidget);
    });

    testWidgets("Refresh runs the silent read path", (tester) async {
      final app = await _onHome(tester);
      app.network.enqueueSelection(
        ConventionReply.selection(enrollmentJson(convention: _joined)),
      );

      await app.tap("convention-refresh");

      expect(_text("Joined Con"), findsOneWidget);
      expect(app.network.count(_getMe), 1);
      expect(app.network.conventionWrites, isEmpty);
    });

    testWidgets("Refresh shows a busy state", (tester) async {
      final app = await _onHome(tester, profiles: [ProfileReply.stalled]);

      await tester.tap(_key("convention-refresh"));
      await tester.pump();

      expect(
        tester.widget<TailTagButton>(_key("convention-refresh")).loading,
        isTrue,
      );
      await _drain(app);
    });

    testWidgets("offers the debug entry in debug builds", (tester) async {
      final app = await _onHome(tester);

      await app.tap("entry-auth-proof");

      expect(find.byType(AuthProofScreen), findsOneWidget);
    });
  });

  group("the foreground reload", () {
    testWidgets("runs after a hidden state, not after an inactive one", (
      tester,
    ) async {
      final app = await _onHome(tester);
      final before = app.network.log.length;

      tester.binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await app.settle();
      expect(app.network.log.length, before);

      await _foreground(app);

      expect(app.network.log.sublist(before), [_getProfile, _getActive]);
      expect(app.network.conventionWrites, isEmpty);
      expect(app.path, AppPaths.home);
    });

    testWidgets("on account unavailable reads only the profile", (
      tester,
    ) async {
      final app = await _pump(
        tester,
        ScriptedNetwork([200], [ProfileReply.disabled, ProfileReply.disabled]),
      );
      final before = app.network.log.length;

      await _foreground(app);

      expect(app.network.log.sublist(before), [_getProfile]);
      expect(app.path, AppPaths.accountUnavailable);
    });

    testWidgets("on the picker reads the profile, then both lists", (
      tester,
    ) async {
      final app = await _onFirstPicker(
        tester,
        conventions: [
          ConventionReply.list([_fresh]),
          ConventionReply.list([_joined]),
        ],
      );
      final before = app.network.log.length;

      await _foreground(app);

      expect(app.network.log.sublist(before).first, _getProfile);
      expect(app.network.log.sublist(before).skip(1).toSet(), {
        _getConventions,
        _getEnrollments,
      });
      expect(_text("Joined Con"), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets("does nothing on the identity-failed stage", (tester) async {
      final app = await _pump(tester, ScriptedNetwork([500]));
      final before = app.network.log.length;

      await _foreground(app);

      expect(app.network.log.length, before);
    });

    testWidgets("does nothing on the passkey screen", (tester) async {
      final app = await _onHome(tester);
      await app.tap(_passkeys);
      final before = app.network.log.length;

      await _foreground(app);

      expect(app.network.log.length, before);
      expect(app.path, AppPaths.passkeys);
    });

    final results =
        <
          ({
            String label,
            ProfileReply profile,
            ConventionReply? selection,
            String path,
            Finder shows,
          })
        >[
          (
            label: "a disabled profile",
            profile: ProfileReply.disabled,
            selection: null,
            path: AppPaths.accountUnavailable,
            shows: _text(EntryStrings.accountUnavailable),
          ),
          (
            label: "an incomplete profile",
            profile: ProfileReply.incomplete,
            selection: null,
            path: AppPaths.onboarding,
            shows: _key("onboarding-handle"),
          ),
          (
            label: "no selection",
            profile: ProfileReply.complete,
            selection: ConventionReply.selection(null),
            path: AppPaths.conventionPicker,
            shows: _text(ConventionStrings.pickerTitle),
          ),
          (
            label: "another selection",
            profile: ProfileReply.complete,
            selection: ConventionReply.selection(
              enrollmentJson(convention: _joined),
            ),
            path: AppPaths.home,
            shows: _text("Joined Con"),
          ),
        ];
    for (final c in results) {
      testWidgets("routes the home for ${c.label}", (tester) async {
        final app = await _onHome(tester, profiles: [c.profile]);
        if (c.selection != null) {
          app.network.enqueueSelection(c.selection!);
        }

        await _foreground(app);

        expect(app.path, c.path);
        expect(c.shows, findsOneWidget);
        expect(app.network.conventionWrites, isEmpty);
      });
    }

    testWidgets("an enabled profile leaves account unavailable", (
      tester,
    ) async {
      final app = await _pump(
        tester,
        ScriptedNetwork([200], [ProfileReply.disabled, ProfileReply.complete]),
      );

      await _foreground(app);

      expect(app.path, AppPaths.home);
    });

    testWidgets(
      "account unavailable stays during a selection read that fails",
      (tester) async {
        final app = await _pump(
          tester,
          ScriptedNetwork.withConventions(
            [200],
            [ProfileReply.disabled, ProfileReply.complete],
            selections: [ConventionReply.stalled],
          ),
        );

        await _foreground(app);

        // The reload shows no loading stage while the selection read runs.
        expect(app.path, AppPaths.accountUnavailable);

        await _drain(app);

        expect(app.path, AppPaths.accountUnavailable);
        expect(_text(EntryStrings.accountUnavailable), findsOneWidget);
        expect(_text(EntryStrings.refresh), findsOneWidget);
      },
    );

    testWidgets("routes the picker for a disabled profile", (tester) async {
      final app = await _onFirstPicker(
        tester,
        profiles: [ProfileReply.disabled],
      );

      await _foreground(app);

      expect(app.path, AppPaths.accountUnavailable);
    });

    testWidgets("a failed read keeps the home and offers Try again", (
      tester,
    ) async {
      final app = await _onHome(
        tester,
        profiles: [ProfileReply.brokenConnection],
      );

      await _foreground(app);

      expect(app.path, AppPaths.home);
      expect(_text("Current Con"), findsOneWidget);
      expect(_text(GenericError.noConnection.message), findsOneWidget);
      expect(find.text(ConventionStrings.inactive), findsNothing);

      await tester.tap(_tryAgain);
      await app.settle();

      expect(_tryAgain, findsNothing);
      expect(_text("Test Con"), findsOneWidget, reason: "the default reply");
    });

    testWidgets("a failed read keeps the rows and locks the picker", (
      tester,
    ) async {
      final app = await _onFirstPicker(
        tester,
        conventions: [
          ConventionReply.list([_fresh]),
          ConventionReply.brokenConnection,
        ],
      );
      expect(_enabled(tester, _action(1)), isTrue);

      await _foreground(app);

      expect(_text("Fresh Con"), findsOneWidget);
      expect(_text(GenericError.noConnection.message), findsOneWidget);
      expect(_enabled(tester, _action(1)), isFalse);
      final before = app.network.count(_getProfile);

      await _foreground(app);

      expect(app.network.count(_getProfile), before, reason: "locked: skip");
    });

    final unauthorized = <({String label, bool ended, String path})>[
      (label: "an active session", ended: false, path: AppPaths.home),
      (label: "an ended session", ended: true, path: AppPaths.access),
    ];
    for (final c in unauthorized) {
      testWidgets("a 401 with ${c.label} rechecks once", (tester) async {
        final app = await _onHome(
          tester,
          profiles: [const ProfileReply(status: 401, body: "{}")],
          sessionEndsOnRecheck: c.ended,
        );

        await _foreground(app);

        expect(app.path, c.path);
        expect(app.session.recheckCalls, 1);
        if (!c.ended) {
          expect(_text(ConventionStrings.apiAccess), findsOneWidget);
          expect(_text("Current Con"), findsOneWidget);
        }
      });
    }

    testWidgets("a 401 on the picker locks it and keeps the rows", (
      tester,
    ) async {
      final app = await _onFirstPicker(
        tester,
        conventions: [
          ConventionReply.list([_fresh]),
        ],
        profiles: [const ProfileReply(status: 401, body: "{}")],
      );

      await _foreground(app);

      expect(_text(ConventionStrings.apiAccess), findsOneWidget);
      expect(_text("Fresh Con"), findsOneWidget);
      expect(_enabled(tester, _action(1)), isFalse);
      expect(app.session.recheckCalls, 1);
    });

    testWidgets("a 401 on account unavailable shows the API-access text", (
      tester,
    ) async {
      final app = await _pump(
        tester,
        ScriptedNetwork(
          [200],
          [ProfileReply.disabled, const ProfileReply(status: 401, body: "{}")],
        ),
      );

      await _foreground(app);

      expect(app.path, AppPaths.accountUnavailable);
      expect(_text(EntryStrings.apiAccess), findsOneWidget);
      expect(_key("entry-refresh"), findsOneWidget);
      expect(_text(UiStrings.tryAgain), findsOneWidget);
      expect(_text(EntryStrings.refresh), findsNothing);
      expect(app.session.recheckCalls, 1);
    });

    testWidgets("runs one at a time", (tester) async {
      final app = await _onHome(tester, profiles: [ProfileReply.stalled]);
      final before = app.network.count(_getProfile);

      await _foreground(app);
      await _foreground(app);

      expect(app.network.count(_getProfile), before + 1);
      await _drain(app);
    });

    testWidgets("drops a late result after the player leaves the home", (
      tester,
    ) async {
      final app = await _onHome(tester, profiles: [ProfileReply.stalled]);
      await _foreground(app);
      await app.tap(_change);

      app.network.releaseProfile(0, ProfileReply.disabled);
      await app.settle();

      expect(app.path, AppPaths.conventionPicker);
    });

    testWidgets("drops a late result after a write lands", (tester) async {
      final app = await _onFirstPicker(
        tester,
        conventions: [
          ConventionReply.list([_fresh]),
        ],
        profiles: [ProfileReply.stalled],
        writes: [
          ConventionReply(
            status: 201,
            body: enrollmentJson(convention: _fresh),
          ),
        ],
      );
      await _foreground(app);
      await app.tap(_action(1));
      expect(app.path, AppPaths.home);

      app.network.releaseProfile(0, ProfileReply.disabled);
      await app.settle();

      expect(app.path, AppPaths.home);
      expect(_text("Fresh Con"), findsOneWidget);
    });

    testWidgets("skips while a write runs", (tester) async {
      final app = await _onPickerFromHome(
        tester,
        writes: [ConventionReply.stalled],
      );
      await tester.tap(_key(_action(1)));
      await tester.pump();
      final before = app.network.count(_getProfile);

      await _foreground(app);

      expect(app.network.count(_getProfile), before);
      await _drain(app);
    });

    group("on the onboarding form", () {
      Future<AppHarness> onForm(
        WidgetTester tester,
        List<ProfileReply> then,
      ) async {
        final app = await _pump(
          tester,
          ScriptedNetwork([200], [ProfileReply.incomplete, ...then]),
        );
        await tester.enterText(_key("onboarding-handle"), "finn_42");
        return app;
      }

      String typed(WidgetTester tester) => tester
          .widget<TextField>(
            find.descendant(
              of: _key("onboarding-handle"),
              matching: find.byType(TextField),
            ),
          )
          .controller!
          .text;

      testWidgets("keeps typed values and sends no save", (tester) async {
        final app = await onForm(tester, [ProfileReply.incomplete]);

        await _foreground(app);

        expect(app.path, AppPaths.onboarding);
        expect(typed(tester), "finn_42");
        expect(app.network.profilePuts, isEmpty);
        expect(app.network.profileGets, 2);
      });

      final moves = <({String label, ProfileReply profile, String path})>[
        (
          label: "a profile completed elsewhere",
          profile: ProfileReply.complete,
          path: AppPaths.home,
        ),
        (
          label: "a disabled profile",
          profile: ProfileReply.disabled,
          path: AppPaths.accountUnavailable,
        ),
      ];
      for (final c in moves) {
        testWidgets("moves for ${c.label}", (tester) async {
          final app = await onForm(tester, [c.profile]);

          await _foreground(app);

          expect(app.path, c.path);
          expect(app.network.profilePuts, isEmpty);
        });
      }

      testWidgets("a failed read changes nothing", (tester) async {
        final app = await onForm(tester, [ProfileReply.brokenConnection]);

        await _foreground(app);

        expect(app.path, AppPaths.onboarding);
        expect(typed(tester), "finn_42");
        expect(_tryAgain, findsNothing);
      });

      testWidgets("a 401 rechecks once and leaves the form alone", (
        tester,
      ) async {
        final app = await onForm(tester, [
          const ProfileReply(status: 401, body: "{}"),
        ]);

        await _foreground(app);

        expect(app.session.recheckCalls, 1);
        expect(app.path, AppPaths.onboarding);
        expect(typed(tester), "finn_42");
        expect(_key("onboarding-banner"), findsNothing);
      });

      testWidgets("drops a read that started before a save", (tester) async {
        final app = await onForm(tester, [
          ProfileReply.stalled,
          ProfileReply.stalled,
        ]);
        await _foreground(app);
        await tester.enterText(_key("onboarding-display-name"), "Finn");
        await tester.tap(_key("onboarding-continue"));
        await tester.pump();
        expect(app.network.profilePuts, hasLength(1));

        app.network.releaseProfile(0, ProfileReply.complete);
        await app.settle();

        expect(app.path, AppPaths.onboarding);
        await _drain(app);
      });

      testWidgets("skips during a save", (tester) async {
        final app = await onForm(tester, [ProfileReply.stalled]);
        await tester.enterText(_key("onboarding-display-name"), "Finn");
        await tester.tap(_key("onboarding-continue"));
        await tester.pump();
        expect(app.network.profilePuts, hasLength(1));
        final before = app.network.profileGets;

        await _foreground(app);

        expect(app.network.profileGets, before);
        await _drain(app);
      });
    });
  });

  group("Manage passkeys", () {
    testWidgets("opens from the picker and derives the stage on close", (
      tester,
    ) async {
      final app = await _onFirstPicker(tester);
      expect(_text(EntryStrings.managePasskeys), findsOneWidget);
      await app.tap(_passkeys);
      expect(app.path, AppPaths.passkeys);
      app.network
        ..enqueue(200)
        ..enqueueSelection(ConventionReply.selection(null));

      await app.tap("passkeys-close");

      expect(app.path, AppPaths.conventionPicker);
      expect(app.network.count(_getMe), 2);
    });

    testWidgets("opens from the home and derives the stage on close", (
      tester,
    ) async {
      final app = await _onHome(tester);
      expect(_text(EntryStrings.managePasskeys), findsOneWidget);
      await app.tap(_passkeys);
      app.network.enqueue(200);

      await app.tap("passkeys-close");

      expect(app.path, AppPaths.home);
      expect(app.network.count(_getMe), 2);
    });
  });

  group("session isolation", () {
    testWidgets("a late list from an ended session never reaches the next", (
      tester,
    ) async {
      final app = await _onFirstPicker(
        tester,
        conventions: [ConventionReply.stalled],
      );

      app.session.emit(const AuthSignedOut());
      await app.settle();
      expect(app.network.conventionAborts, 1);
      app.network
        ..enqueue(200)
        ..enqueueSelection(ConventionReply.selection(null))
        ..enqueueConventions(ConventionReply.list([_joined]));
      app.session.emit(const AuthSignedIn());
      await app.settle();

      app.network.releaseConvention(0, ConventionReply.list([_fresh]));
      await app.settle();

      expect(_text("Joined Con"), findsOneWidget);
      expect(_text("Fresh Con"), findsNothing);
    });

    testWidgets("sign-out during a write cancels it with no banner", (
      tester,
    ) async {
      final app = await _onPickerFromHome(
        tester,
        writes: [ConventionReply.stalled],
      );
      await tester.tap(_key(_action(1)));
      await tester.pump();

      await app.tap(_signOut);

      expect(app.path, AppPaths.access);
      expect(app.network.conventionAborts, 1);
      expect(_text(ConventionStrings.unknownOutcome), findsNothing);
      expect(app.network.conventionWrites, hasLength(1));
    });

    testWidgets("Back after sign-out cannot show the convention", (
      tester,
    ) async {
      final app = await _onHome(tester);

      await app.tap(_signOut);
      await tester.binding.handlePopRoute();
      await app.settle();

      expect(app.path, AppPaths.access);
      expect(_home, findsNothing);
    });
  });
}
