import "dart:convert";

import "package:barcode_widget/barcode_widget.dart";
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/ui/ui_strings.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";
import "tag_badge_test.dart" show fakePayload;

const _list = "GET /api/fursuits/";
const _activations = "GET /api/conventions/10/fursuit-activations/";
const _readTag = "GET /api/fursuits/5/tag/";
const _replaceTag = "POST /api/fursuits/5/tag/replace/";

String _fursuit({bool enabled = true}) =>
    '{"id": 5, "tailtag_id": "00000000-0000-4000-8000-000000000005", '
    '"name": "Alpha", "photo_url": "https://media.test/5.jpg", '
    '"is_enabled": $enabled, "catch_approval_mode": "manual"}';

String _activation({bool catchable = false}) {
  final start = DateTime.now().toUtc();
  final session = catchable
      ? '{"fursuit_id": 5, "convention_id": 10, "is_active": true, '
            '"started_at": "${start.toIso8601String()}", '
            '"expires_at": '
            '"${start.add(const Duration(hours: 12)).toIso8601String()}", '
            '"ended_at": null, "end_reason": null}'
      : "null";
  return '{"fursuit_id": 5, "convention_id": 10, "is_active": true, '
      '"is_eligible": true, "activated_at": "2026-11-14T10:00:00Z", '
      '"deactivated_at": null, "catch_session": $session}';
}

ConventionReply _tag(int version, {bool revoked = false}) => ConventionReply(
  body:
      '{"fursuit_id": 5, "state": "${revoked ? "revoked" : "current"}", '
      '"tag_version": $version, '
      '"payload": ${revoked ? "null" : '"$fakePayload"'}}',
);

ConventionReply _error(int status, String code) =>
    ConventionReply(status: status, body: '{"code": "$code", "detail": "x"}');

Finder _key(String key) => find.byKey(Key(key));

String _top(AppHarness app) => app.container
    .read(routerProvider)
    .routerDelegate
    .currentConfiguration
    .last
    .matchedLocation;

int _count(AppHarness app, String request) =>
    app.network.suitRequests.where((item) => item.request == request).length;

/// The payload that the QR on screen encodes, or null.
String? _qrPayload(WidgetTester tester) {
  final codes = find.descendant(
    of: _key("tag-qr"),
    matching: find.byType(BarcodeWidget),
  );
  if (codes.evaluate().isEmpty) {
    return null;
  }
  return utf8.decode(tester.widget<BarcodeWidget>(codes).data);
}

/// The app on the suit screen of suit 5, with [later] queued for the tag
/// requests.
Future<AppHarness> _openSuit(
  WidgetTester tester, {
  bool enabled = true,
  bool catchable = false,
  List<(String, ConventionReply)> later = const [],
  FakeTagShare? share,
}) async {
  tester.view.physicalSize = const Size(1200, 5400);
  addTearDown(tester.view.resetPhysicalSize);
  final network = ScriptedNetwork([200]);
  for (var i = 0; i < 6; i++) {
    network
      ..enqueueSuit(_list, ConventionReply.list([_fursuit(enabled: enabled)]))
      ..enqueueSuit(
        _activations,
        ConventionReply.list([_activation(catchable: catchable)]),
      );
  }
  for (final (request, reply) in later) {
    network.enqueueSuit(request, reply);
  }
  final app = await pumpApp(
    tester,
    session: FakeAuthSession(initial: const AuthSignedIn()),
    network: network,
    tagShare: share,
  );
  await app.tap("convention-my-suits");
  await app.tap("suit-row-5");
  expect(_top(app), AppPaths.suit(5));
  return app;
}

/// The app on the tag screen of suit 5, after [first] answered the read.
Future<AppHarness> _openTag(
  WidgetTester tester,
  ConventionReply first, {
  bool catchable = false,
  List<(String, ConventionReply)> later = const [],
  FakeTagShare? share,
}) async {
  final app = await _openSuit(
    tester,
    catchable: catchable,
    later: [(_readTag, first), ...later],
    share: share,
  );
  await app.tap("suit-show-tag");
  expect(_top(app), AppPaths.suitTag(5));
  return app;
}

Future<void> _confirmReplace(AppHarness app) async {
  await app.tap("tag-replace");
  expect(find.text(FursuitStrings.replaceTitle), findsOneWidget);
  await app.tap("replace-confirm");
}

void main() {
  group("display", () {
    testWidgets("the suit screen opens the tag only on request, and the tag "
        "screen shows the code, the name, the version, and the session "
        "state", (tester) async {
      final app = await _openSuit(tester, later: [(_readTag, _tag(1))]);
      expect(find.text(FursuitStrings.showTagHelp), findsOneWidget);
      expect(_count(app, _readTag), 0);

      await app.tap("suit-show-tag");

      expect(_count(app, _readTag), 1);
      expect(_qrPayload(tester), fakePayload);
      expect(find.text(FursuitStrings.tagVersion(1)), findsWidgets);
      expect(find.text(FursuitStrings.tagExplain("Alpha")), findsOneWidget);
      expect(
        find.text(FursuitStrings.notOutForCatchingAt("Test Con")),
        findsOneWidget,
      );
      expect(find.text(FursuitStrings.printActualSize), findsOneWidget);
    });

    testWidgets("a catchable suit shows that it is out for catching", (
      tester,
    ) async {
      final app = await _openTag(tester, _tag(1), catchable: true);

      expect(
        find.text(FursuitStrings.outForCatchingAt("Test Con")),
        findsOneWidget,
      );
      // Disposing the container cancels the live session's expiry timer
      // before the test checks for pending timers.
      await tester.pumpWidget(const SizedBox());
      app.container.dispose();
    });

    testWidgets("a disabled suit cannot open its tag and says why", (
      tester,
    ) async {
      final app = await _openSuit(tester, enabled: false);

      final row = tester.widget<ListTile>(_key("suit-show-tag"));
      expect(row.enabled, isFalse);
      expect(
        find.descendant(
          of: _key("suit-show-tag"),
          matching: find.text(FursuitStrings.suitDisabled),
        ),
        findsOneWidget,
      );
      await app.tap("suit-show-tag");
      expect(_top(app), AppPaths.suit(5));
    });

    testWidgets("a server without tag operations shows that tags are not "
        "available, and Try again reads again", (tester) async {
      final app = await _openTag(
        tester,
        _error(404, "not_found"),
        later: [(_readTag, _tag(1))],
      );
      expect(find.text(FursuitStrings.tagsUnavailable), findsOneWidget);
      expect(_qrPayload(tester), isNull);

      await tester.tap(find.text("Try again"));
      await app.settle();

      expect(_count(app, _readTag), 2);
      expect(_qrPayload(tester), fakePayload);
      expect(find.text(FursuitStrings.tagsUnavailable), findsNothing);
    });
  });

  testWidgets("a refused read shows the generic error", (tester) async {
    await _openTag(tester, _error(403, "permission_denied"));

    expect(find.text(UiStrings.unknownError), findsOneWidget);
    expect(_qrPayload(tester), isNull);
  });

  group("tag image", () {
    testWidgets("share sends a 2400 × 1800 PNG named without the payload or "
        "the suit name, and opening the screen clears old images", (
      tester,
    ) async {
      final share = FakeTagShare();
      final app = await _openTag(tester, _tag(1), share: share);
      final clearsBefore = share.clears;
      expect(clearsBefore, greaterThan(0));

      await tester.tap(find.text(FursuitStrings.shareTagImage));
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(seconds: 1)),
      );
      await app.settle();

      expect(share.shares, [
        (
          fileName: "tailtag-tag.png",
          width: 2400,
          height: 1800,
          mimeType: "image/png",
        ),
      ]);
      expect(find.byKey(const Key("tag-banner")), findsNothing);
    });

    testWidgets("a failed share shows a banner", (tester) async {
      final share = FakeTagShare()..failNext = Exception("sheet failed");
      final app = await _openTag(tester, _tag(1), share: share);

      await tester.tap(find.text(FursuitStrings.shareTagImage));
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(seconds: 1)),
      );
      await app.settle();

      expect(find.text(FursuitStrings.shareFailed), findsOneWidget);
    });
  });

  group("replacement", () {
    testWidgets("a confirmed replacement sends the shown version, shows the "
        "new tag, and leaves the session alone", (tester) async {
      final app = await _openTag(
        tester,
        _tag(1),
        catchable: true,
        later: [(_replaceTag, _tag(2))],
      );
      final writesBefore = app.network.suitRequests
          .where((item) => item.request.startsWith("PUT"))
          .length;

      await _confirmReplace(app);

      final sent = app.network.suitRequests.singleWhere(
        (item) => item.request == _replaceTag,
      );
      expect(jsonDecode(sent.body), {"expected_version": 1});
      expect(find.text(FursuitStrings.tagReplaced), findsOneWidget);
      expect(find.text(FursuitStrings.tagVersion(2)), findsWidgets);
      expect(
        find.text(FursuitStrings.outForCatchingAt("Test Con")),
        findsOneWidget,
      );
      expect(
        app.network.suitRequests
            .where((item) => item.request.startsWith("PUT"))
            .length,
        writesBefore,
      );
      await tester.pumpWidget(const SizedBox());
      app.container.dispose();
    });

    testWidgets("a read that started before a replacement cannot bring back "
        "the old tag", (tester) async {
      final app = await _openTag(
        tester,
        _tag(1),
        later: [(_readTag, ConventionReply.stalled), (_replaceTag, _tag(2))],
      );
      // A foreground return starts a read, whose answer waits.
      app.container.read(foregroundSignalProvider.notifier).fire();
      await app.settle();

      await _confirmReplace(app);
      expect(find.text(FursuitStrings.tagVersion(2)), findsWidgets);
      // The read answers with the tag from before the replacement.
      app.network.releaseSuit(0, _tag(1));
      await app.settle();

      expect(find.text(FursuitStrings.tagVersion(2)), findsWidgets);
      expect(find.text(FursuitStrings.tagVersion(1)), findsNothing);
    });

    testWidgets("cancel in the dialog sends nothing", (tester) async {
      final app = await _openTag(tester, _tag(1));

      await app.tap("tag-replace");
      await app.tap("replace-cancel");

      expect(_count(app, _replaceTag), 0);
      expect(find.text(FursuitStrings.tagVersion(1)), findsWidgets);
    });

    final recoveries =
        <
          ({
            String label,
            ConventionReply answer,
            ConventionReply reread,
            String? banner,
            bool revoked,
          })
        >[
          (
            label: "a lost response, then a raised version",
            answer: ConventionReply.brokenConnection,
            reread: _tag(2),
            banner: FursuitStrings.tagChanged,
            revoked: false,
          ),
          (
            label: "a server error, then a raised version",
            answer: const ConventionReply(status: 502),
            reread: _tag(2),
            banner: FursuitStrings.tagChanged,
            revoked: false,
          ),
          (
            label: "a lost response, then the same version",
            answer: ConventionReply.brokenConnection,
            reread: _tag(1),
            banner: FursuitStrings.tagNotReplaced,
            revoked: false,
          ),
          (
            label: "a lost response, then a revoked tag",
            answer: ConventionReply.brokenConnection,
            reread: _tag(2, revoked: true),
            banner: null,
            revoked: true,
          ),
          (
            label: "a version conflict",
            answer: _error(409, "tag_version_conflict"),
            reread: _tag(3),
            banner: FursuitStrings.tagConflict,
            revoked: false,
          ),
        ];
    for (final c in recoveries) {
      testWidgets("${c.label} reads the tag, never sends the replacement "
          "again, and says what happened", (tester) async {
        final app = await _openTag(
          tester,
          _tag(1),
          later: [(_replaceTag, c.answer), (_readTag, c.reread)],
        );

        await _confirmReplace(app);

        expect(_count(app, _replaceTag), 1);
        expect(_count(app, _readTag), 2);
        expect(find.text(FursuitStrings.replaceTitle), findsNothing);
        expect(find.text(FursuitStrings.tagReplaced), findsNothing);
        if (c.banner case final banner?) {
          expect(find.text(banner), findsOneWidget);
          final replace = tester.widget<TailTagButton>(_key("tag-replace"));
          expect(replace.onPressed, isNotNull);
        } else {
          expect(find.byKey(const Key("tag-banner")), findsNothing);
        }
        expect(
          find.text(FursuitStrings.tagRevoked("Alpha")),
          c.revoked ? findsOneWidget : findsNothing,
        );
      });
    }

    testWidgets("a failed check after a lost response offers Try again, "
        "which only reads and then resolves the check", (tester) async {
      final app = await _openTag(
        tester,
        _tag(1),
        later: [
          (_replaceTag, ConventionReply.brokenConnection),
          (_readTag, ConventionReply.brokenConnection),
          (_readTag, _tag(2)),
        ],
      );

      await _confirmReplace(app);
      expect(find.text(FursuitStrings.tagCheckFailed), findsOneWidget);

      await tester.tap(find.text("Try again"));
      await app.settle();

      expect(_count(app, _replaceTag), 1);
      expect(find.text(FursuitStrings.tagChanged), findsOneWidget);
      expect(find.text(FursuitStrings.tagVersion(2)), findsWidgets);
    });

    testWidgets("another refusal shows a banner, keeps the tag, and claims no "
        "success", (tester) async {
      final app = await _openTag(
        tester,
        _tag(1),
        later: [(_replaceTag, _error(409, "fursuit_disabled"))],
      );

      await _confirmReplace(app);

      expect(find.text(FursuitStrings.suitDisabled), findsOneWidget);
      expect(find.text(FursuitStrings.tagReplaced), findsNothing);
      expect(_qrPayload(tester), fakePayload);
      expect(find.text(FursuitStrings.tagVersion(1)), findsWidgets);
    });
  });

  group("revoked tag", () {
    testWidgets("a revoked tag shows no code and gets a new tag at once", (
      tester,
    ) async {
      final app = await _openTag(
        tester,
        _tag(2, revoked: true),
        later: [(_replaceTag, _tag(3))],
      );
      expect(find.text(FursuitStrings.tagRevoked("Alpha")), findsOneWidget);
      expect(_qrPayload(tester), isNull);
      expect(find.text(FursuitStrings.shareTagImage), findsNothing);

      await app.tap("tag-get-new");

      final sent = app.network.suitRequests.singleWhere(
        (item) => item.request == _replaceTag,
      );
      expect(jsonDecode(sent.body), {"expected_version": 2});
      expect(find.text(FursuitStrings.replaceTitle), findsNothing);
      expect(find.text(FursuitStrings.newTagReady), findsOneWidget);
      expect(_qrPayload(tester), fakePayload);
    });
  });

  group("privacy and accessibility", () {
    testWidgets("an account change drops the payload and clears tag images", (
      tester,
    ) async {
      final share = FakeTagShare();
      final app = await _openTag(tester, _tag(1), share: share);
      final clearsBefore = share.clears;

      app.session.emit(const AuthSignedOut());
      await app.settle();

      expect(app.path, AppPaths.access);
      expect(find.byType(BarcodeWidget), findsNothing);
      expect(share.clears, greaterThan(clearsBefore));
    });

    testWidgets("the tag screen stays usable at 200% text scale, and the QR "
        "label holds no payload", (tester) async {
      final semantics = tester.ensureSemantics();
      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await _openTag(tester, _tag(1));

      expect(tester.takeException(), isNull);
      for (final guideline in [
        androidTapTargetGuideline,
        iOSTapTargetGuideline,
        textContrastGuideline,
        labeledTapTargetGuideline,
      ]) {
        await expectLater(tester, meetsGuideline(guideline));
      }
      final labels = tester.semantics
          .simulatedAccessibilityTraversal()
          .map((node) => node.getSemanticsData().label)
          .toList();
      expect(
        labels,
        containsAllInOrder([
          contains(FursuitStrings.qrLabel("Alpha")),
          contains(FursuitStrings.tagVersion(1)),
          contains(FursuitStrings.notOutForCatchingAt("Test Con")),
          contains(FursuitStrings.shareTagImage),
          contains(FursuitStrings.replaceTag),
        ]),
      );
      expect(labels.where((label) => label.contains("tailtag.app")), isEmpty);
      expect(labels.where((label) => label.contains("Scan with")), isEmpty);
      semantics.dispose();
    });
  });
}
