import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/fursuits/fursuit.dart";
import "package:tailtag_mobile/core/fursuits/photo_source.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

const _list = "GET /api/fursuits/";
const _create = "POST /api/fursuits/";
const _activations = "GET /api/conventions/10/fursuit-activations/";
const _participation = "PUT /api/conventions/10/fursuit-activations/5/";
const _session = "PUT /api/conventions/10/fursuit-activations/5/catch-session/";
const _rename = "PATCH /api/fursuits/5/";

String _fursuit({int id = 5, String name = "Alpha", bool enabled = true}) =>
    '{"id": $id, "tailtag_id": "00000000-0000-4000-8000-00000000000$id", '
    '"name": "$name", "photo_url": "https://media.test/$id.jpg", '
    '"is_enabled": $enabled, "catch_approval_mode": "manual"}';

String _sessionJson({
  required bool active,
  DateTime? started,
  DateTime? expires,
  DateTime? ended,
  String? reason,
}) {
  final start = started ?? DateTime.now().toUtc();
  final end = expires ?? start.add(const Duration(hours: 12));
  String time(DateTime? value) =>
      value == null ? "null" : '"${value.toUtc().toIso8601String()}"';
  return '{"fursuit_id": 5, "convention_id": 10, "is_active": $active, '
      '"started_at": ${time(start)}, "expires_at": ${time(end)}, '
      '"ended_at": ${time(ended)}, '
      '"end_reason": ${reason == null ? "null" : '"$reason"'}}';
}

String _activation({
  bool active = true,
  bool eligible = true,
  String? session,
}) =>
    '{"fursuit_id": 5, "convention_id": 10, "is_active": $active, '
    '"is_eligible": $eligible, "activated_at": "2026-11-14T10:00:00Z", '
    '"deactivated_at": null, "catch_session": ${session ?? "null"}}';

ConventionReply _rows(List<String> items) => ConventionReply.list(items);

/// The device picker, faked at the plugin boundary.
final class _FakePhotoSource implements PhotoSource {
  final List<Object?> results = [];
  final List<PhotoOrigin> calls = [];

  @override
  Future<PickedPhoto?> pick(PhotoOrigin origin) async {
    calls.add(origin);
    final result = results.isEmpty ? null : results.removeAt(0);
    if (result is Exception) {
      throw result;
    }
    return result as PickedPhoto?;
  }
}

const _photo = PickedPhoto(bytes: [0xFF, 0xD8, 0xFF, 0xD9], name: "suit.jpg");

Finder _key(String key) => find.byKey(Key(key));

/// The location of the top screen. A pushed screen does not change the
/// router's base location, so this reads the last match.
String _top(AppHarness app) => app.container
    .read(routerProvider)
    .routerDelegate
    .currentConfiguration
    .last
    .matchedLocation;

/// The app on the suit list of "Test Con", with [network] answers queued.
Future<AppHarness> _openSuits(
  WidgetTester tester,
  ScriptedNetwork network, {
  PhotoSource? photoSource,
  FakeAuthSession? session,
}) async {
  tester.view.physicalSize = const Size(1200, 5400);
  addTearDown(tester.view.resetPhysicalSize);
  final app = await pumpApp(
    tester,
    session: session ?? FakeAuthSession(initial: const AuthSignedIn()),
    network: network,
    photoSource: photoSource,
  );
  expect(app.path, AppPaths.home);
  await app.tap("convention-my-suits");
  expect(_top(app), AppPaths.suits);
  return app;
}

/// The app on the suit screen of suit 5, which has [activation] rows.
Future<AppHarness> _openSuit(
  WidgetTester tester, {
  String fursuit = "",
  List<String> activation = const [],
  List<(String, ConventionReply)> later = const [],
}) async {
  final suits = _rows([if (fursuit.isEmpty) _fursuit() else fursuit]);
  // The list reads on open, and the suit screen reads again on open. Later
  // reads find the same suits, with the activation rows in [later].
  final network = ScriptedNetwork([200])
    ..enqueueSuit(_activations, _rows(activation))
    ..enqueueSuit(_activations, _rows(activation));
  for (var i = 0; i < 4; i++) {
    network.enqueueSuit(_list, suits);
  }
  for (final (request, reply) in later) {
    network.enqueueSuit(request, reply);
  }
  final app = await _openSuits(tester, network);
  await app.tap("suit-row-5");
  expect(_top(app), AppPaths.suit(5));
  return app;
}

int _count(AppHarness app, String request) =>
    app.network.suitRequests.where((item) => item.request == request).length;

bool _switchValue(WidgetTester tester, String key) =>
    tester.widget<SwitchListTile>(_key(key)).value;

bool _switchEnabled(WidgetTester tester, String key) =>
    tester.widget<SwitchListTile>(_key(key)).onChanged != null;

void main() {
  group("register", () {
    testWidgets("an empty list offers registration, and a save sends the "
        "name and the photo, then opens the new suit", (tester) async {
      final photos = _FakePhotoSource()..results.add(_photo);
      final network = ScriptedNetwork([200])
        ..enqueueSuit(_list, _rows(const []))
        ..enqueueSuit(_create, ConventionReply(status: 201, body: _fursuit()))
        ..enqueueSuit(_list, _rows([_fursuit()]))
        ..enqueueSuit(_list, _rows([_fursuit()]));
      final app = await _openSuits(tester, network, photoSource: photos);
      expect(_key("suits-empty"), findsOneWidget);

      await app.tap("suits-register");
      await tester.enterText(_key("register-name"), "Alpha");
      expect(tester.testTextInput.isVisible, isTrue);
      await app.tap("register-photo");
      // The keyboard closes before the photo sheet opens.
      expect(tester.testTextInput.isVisible, isFalse);
      await app.tap("photo-choose");
      expect(photos.calls, [PhotoOrigin.library]);
      // Focus does not return to the name field when the sheet closes.
      expect(tester.testTextInput.isVisible, isFalse);
      await app.tap("register-save");

      final create = network.suitRequests.singleWhere(
        (item) => item.request == _create,
      );
      expect(create.body, contains('name="name"'));
      expect(create.body, contains("Alpha"));
      expect(create.body, contains('filename="suit.jpg"'));
      expect(_top(app), AppPaths.suit(5));
      expect(_key("suit-name"), findsOneWidget);
      expect(tester.testTextInput.isVisible, isFalse);
    });

    testWidgets("a server field error shows under its field and keeps the "
        "values", (tester) async {
      final photos = _FakePhotoSource()..results.add(_photo);
      final network = ScriptedNetwork([200])
        ..enqueueSuit(
          _create,
          const ConventionReply(
            status: 400,
            body: '{"name": ["Enter a name of 1–50 characters."]}',
          ),
        );
      final app = await _openSuits(tester, network, photoSource: photos);
      await app.tap("suits-register");
      await app.tap("register-photo");
      await app.tap("photo-choose");
      await tester.enterText(_key("register-name"), "Alpha");
      // "Done" on the keyboard saves a complete form and closes the keyboard.
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await app.settle();

      expect(_count(app, _create), 1);
      expect(tester.testTextInput.isVisible, isFalse);
      expect(find.text("Enter a name of 1–50 characters."), findsOneWidget);
      expect(find.text("Alpha"), findsOneWidget);
      expect(_key("register-photo-preview"), findsOneWidget);
      expect(_top(app), AppPaths.registerSuit);
    });

    testWidgets("a lost create response is never sent again: the list is "
        "read again and the form stays", (tester) async {
      final photos = _FakePhotoSource()..results.add(_photo);
      final network = ScriptedNetwork([200])
        ..enqueueSuit(_create, ConventionReply.brokenConnection);
      final app = await _openSuits(tester, network, photoSource: photos);
      final listReads = _count(app, _list);
      await app.tap("suits-register");
      await tester.enterText(_key("register-name"), "Alpha");
      await app.tap("register-photo");
      await app.tap("photo-choose");
      await app.tap("register-save");

      expect(find.text(FursuitStrings.createUnknownOutcome), findsOneWidget);
      expect(find.text("Alpha"), findsOneWidget);
      expect(_count(app, _create), 1);
      expect(_count(app, _list), listReads + 1);
    });

    testWidgets("a refused camera shows a message, and the library still "
        "works", (tester) async {
      final photos = _FakePhotoSource()
        ..results.addAll([const PhotoAccessDenied(PhotoOrigin.camera), _photo]);
      final app = await _openSuits(
        tester,
        ScriptedNetwork([200]),
        photoSource: photos,
      );
      await app.tap("suits-register");
      await app.tap("register-photo");
      await app.tap("photo-take");
      expect(find.text(FursuitStrings.cameraDenied), findsOneWidget);

      await app.tap("register-photo");
      await app.tap("photo-choose");

      expect(find.text(FursuitStrings.cameraDenied), findsNothing);
      expect(_key("register-photo-preview"), findsOneWidget);
    });
  });

  group("participation and session", () {
    testWidgets("turning participation on sends it and reads the list "
        "again", (tester) async {
      final app = await _openSuit(
        tester,
        later: [
          (
            _participation,
            ConventionReply(
              body: _activation().replaceAll(', "catch_session": null', ""),
            ),
          ),
          (_activations, _rows([_activation()])),
        ],
      );
      expect(find.text(FursuitStrings.badgeNotParticipating), findsOneWidget);
      expect(_switchEnabled(tester, "suit-session"), isFalse);

      await app.tap("suit-participation");

      final put = app.network.suitRequests.singleWhere(
        (item) => item.request == _participation,
      );
      expect(put.body, '{"is_active":true}');
      expect(_switchValue(tester, "suit-participation"), isTrue);
      expect(find.text(FursuitStrings.badgeParticipating), findsOneWidget);
      expect(_switchEnabled(tester, "suit-session"), isTrue);
    });

    testWidgets("turning participation off asks first, and Cancel sends "
        "nothing", (tester) async {
      final app = await _openSuit(
        tester,
        activation: [_activation()],
        later: [
          (
            _participation,
            ConventionReply(
              body: _activation(active: false)
                  .replaceAll(', "catch_session": null', ""),
            ),
          ),
          (_activations, _rows([_activation(active: false)])),
        ],
      );

      await app.tap("suit-participation");
      expect(find.text(FursuitStrings.deactivateBody), findsOneWidget);
      await app.tap("deactivate-cancel");
      expect(_count(app, _participation), 0);
      expect(_switchValue(tester, "suit-participation"), isTrue);

      await app.tap("suit-participation");
      await app.tap("deactivate-confirm");

      expect(
        app.network.suitRequests.last.request,
        _activations,
        reason: "the list is read again after the write",
      );
      expect(_count(app, _participation), 1);
      expect(_switchValue(tester, "suit-participation"), isFalse);
    });

    testWidgets("a session starts with its end time and stops at once with "
        "a snackbar", (tester) async {
      final app = await _openSuit(
        tester,
        activation: [_activation()],
        later: [
          (_session, ConventionReply(body: _sessionJson(active: true))),
          (
            _session,
            ConventionReply(
              body: _sessionJson(
                active: false,
                ended: DateTime.now(),
                reason: "owner",
              ),
            ),
          ),
        ],
      );

      await app.tap("suit-session");
      expect(find.text(FursuitStrings.badgeCatchable), findsOneWidget);
      expect(find.textContaining("Out until"), findsOneWidget);

      await app.tap("suit-session");
      expect(find.text(FursuitStrings.sessionStopped), findsOneWidget);
      expect(find.text(FursuitStrings.badgeParticipating), findsOneWidget);
      expect(_key("suit-session-note"), findsNothing);
      expect(
        app.network.suitRequests
            .where((item) => item.request == _session)
            .map((item) => item.body),
        ['{"is_active":true}', '{"is_active":false}'],
      );
    });

    testWidgets("a lost session response keeps the switch, reads again, "
        "and never resends", (tester) async {
      final app = await _openSuit(
        tester,
        activation: [_activation()],
        later: [(_session, ConventionReply.brokenConnection)],
      );
      final reads = _count(app, _activations);

      await app.tap("suit-session");

      expect(_switchValue(tester, "suit-session"), isFalse);
      expect(find.text(FursuitStrings.writeUnknownOutcome), findsOneWidget);
      expect(_count(app, _session), 1);
      expect(_count(app, _activations), reads + 1);
    });

    testWidgets("a shown live session is read again when it reaches its "
        "end", (tester) async {
      final now = DateTime.now();
      final app = await _openSuit(
        tester,
        activation: [
          _activation(
            session: _sessionJson(
              active: true,
              started: now.subtract(const Duration(hours: 12)),
              expires: now.add(const Duration(seconds: 5)),
            ),
          ),
        ],
      );
      final reads = _count(app, _activations);

      await tester.pump(const Duration(seconds: 7));
      await app.settle();

      expect(_count(app, _activations), reads + 1);
    });
  });

  group("edit", () {
    testWidgets("a new name sends only the name and shows the saved one", (
      tester,
    ) async {
      final app = await _openSuit(
        tester,
        later: [(_rename, ConventionReply(body: _fursuit(name: "Bravo")))],
      );

      await app.tap("suit-change-name");
      await tester.enterText(_key("rename-field"), "Bravo");
      await app.tap("rename-save");

      final patch = app.network.suitRequests.singleWhere(
        (item) => item.request == _rename,
      );
      expect(patch.body, '{"name":"Bravo"}');
      expect(find.text(FursuitStrings.nameSaved), findsOneWidget);
      expect(tester.widget<Text>(_key("suit-name")).data, "Bravo");
    });

    testWidgets("a lost rename response keeps the typed name, reads again, "
        "and never resends", (tester) async {
      final app = await _openSuit(
        tester,
        later: [(_rename, ConventionReply.brokenConnection)],
      );
      final reads = _count(app, _list);

      await app.tap("suit-change-name");
      await tester.enterText(_key("rename-field"), "Bravo");
      await app.tap("rename-save");

      expect(_key("rename-field"), findsOneWidget);
      expect(find.text("Bravo"), findsOneWidget);
      expect(find.text(FursuitStrings.writeUnknownOutcome), findsWidgets);
      expect(_count(app, _rename), 1);
      expect(_count(app, _list), reads + 1);
    });
  });

  group("states", () {
    final cases =
        <({String label, String fursuit, String activation, String reason})>[
          (
            label: "a suit that staff disabled",
            fursuit: _fursuit(enabled: false),
            activation: _activation(active: false),
            reason: FursuitStrings.suitDisabled,
          ),
          (
            label: "an activation the server does not allow",
            fursuit: _fursuit(),
            activation: _activation(eligible: false),
            reason: FursuitStrings.cannotParticipate,
          ),
        ];
    for (final c in cases) {
      testWidgets("${c.label} disables turning on, with its reason", (
        tester,
      ) async {
        await _openSuit(tester, fursuit: c.fursuit, activation: [c.activation]);

        expect(find.text(c.reason), findsOneWidget);
        final blocked = c.activation.contains('"is_active": false')
            ? "suit-participation"
            : "suit-session";
        expect(_switchEnabled(tester, blocked), isFalse);
      });
    }

    testWidgets("an inactive convention disables turning participation on", (
      tester,
    ) async {
      final network =
          ScriptedNetwork.withConventions(
              [200],
              [ProfileReply.complete],
              selections: [
                ConventionReply.selection(
                  enrollmentJson(convention: conventionJson(status: "paused")),
                ),
              ],
            )
            ..enqueueSuit(_list, _rows([_fursuit()]))
            ..enqueueSuit(_activations, _rows(const []))
            ..enqueueSuit(_list, _rows([_fursuit()]))
            ..enqueueSuit(_activations, _rows(const []));
      final app = await _openSuits(tester, network);
      await app.tap("suit-row-5");

      expect(find.text(FursuitStrings.conventionClosed), findsOneWidget);
      expect(_switchEnabled(tester, "suit-participation"), isFalse);
    });

    testWidgets("a timed-out session shows its note with the end time", (
      tester,
    ) async {
      final expired = DateTime.now().subtract(const Duration(minutes: 5));
      await _openSuit(
        tester,
        activation: [
          _activation(
            session: _sessionJson(
              active: false,
              started: expired.subtract(const Duration(hours: 12)),
              expires: expired,
              ended: expired,
              reason: "expired",
            ),
          ),
        ],
      );

      expect(
        find.textContaining("Your last session timed out at"),
        findsOneWidget,
      );
      expect(find.text(FursuitStrings.badgeParticipating), findsOneWidget);
    });

    testWidgets("the suit screen stays usable at 200% text scale", (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await _openSuit(
        tester,
        fursuit: _fursuit(name: "A long suit name for wrapping tests"),
        activation: [_activation()],
      );

      expect(tester.takeException(), isNull);
      for (final guideline in [
        androidTapTargetGuideline,
        iOSTapTargetGuideline,
        textContrastGuideline,
        labeledTapTargetGuideline,
      ]) {
        await expectLater(tester, meetsGuideline(guideline));
      }
      expect(
        tester.semantics.simulatedAccessibilityTraversal().map(
          (node) => node.getSemanticsData().label,
        ),
        containsAllInOrder([
          contains(FursuitStrings.changeName),
          contains(FursuitStrings.changePhoto),
          contains("At Test Con"),
          contains("Participating at Test Con"),
          contains(FursuitStrings.outForCatching),
        ]),
      );
      semantics.dispose();
    });
  });

  group("session isolation", () {
    testWidgets("an account change shows no suit of the previous player", (
      tester,
    ) async {
      final network = ScriptedNetwork([200, 200])
        ..enqueueSuit(_list, _rows([_fursuit()]))
        ..enqueueSuit(_list, _rows([_fursuit(id: 6, name: "Bravo")]));
      final app = await _openSuits(tester, network);
      expect(find.text("Alpha"), findsOneWidget);

      app.session.emit(const AuthSignedOut());
      await app.settle();
      expect(app.path, AppPaths.access);
      app.session.emit(const AuthSignedIn());
      await app.settle();
      await app.tap("convention-my-suits");

      expect(find.text("Bravo"), findsOneWidget);
      expect(find.text("Alpha"), findsNothing);
    });
  });
}
