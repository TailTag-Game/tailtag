import "dart:convert";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/catches/camera_permission.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/core/ui/widgets/tailtag_button.dart";
import "package:tailtag_mobile/features/catches/catch_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

/// A token-shaped payload built at runtime, so no token literal sits in the
/// repository (#511 G14).
final String _payload = "https://tailtag.app/t#${"Z" * 43}";

const _preview = "POST /api/catches/preview/";
const _submit = "POST /api/catches/requests/";
const _selection = "GET /api/conventions/active/";

String _previewBody({int conventionId = 10}) =>
    '{"fursuit": {"id": 5, '
    '"tailtag_id": "00000000-0000-4000-8000-000000000005", '
    '"name": "Alpha", "photo_url": "https://media.test/5.jpg"}, '
    '"convention_id": $conventionId}';

String _request({String state = "pending", int conventionId = 10}) =>
    '{"id": 31, "fursuit": {"id": 5, '
    '"tailtag_id": "00000000-0000-4000-8000-000000000005", '
    '"name": "Alpha", "photo_url": "https://media.test/5.jpg"}, '
    '"convention_id": $conventionId, "state": "$state", '
    '"requested_at": "2026-11-09T15:00:00Z", '
    '"review_deadline_at": "2026-11-13T05:00:00Z"}';

ConventionReply _submission(int status, String outcome) {
  final state = outcome == "approved" ? "approved" : "pending";
  return ConventionReply(
    status: status,
    body:
        '{"outcome": "$outcome", "request": ${_request(state: state)}, '
        '"catch": null}',
  );
}

ConventionReply _error(int status, String? code) => ConventionReply(
  status: status,
  body: code == null
      ? '{"detail": "Not found."}'
      : '{"code": "$code", "detail": "x"}',
);

Finder _key(String key) => find.byKey(Key(key));

/// The location of the top screen. A pushed screen such as the scanner does
/// not change the router's main location.
String _top(AppHarness app) => app.container
    .read(routerProvider)
    .routerDelegate
    .currentConfiguration
    .last
    .matchedLocation;

/// A network whose selected convention has an open review window.
ScriptedNetwork _network() => ScriptedNetwork.withConventions(
  [200],
  const [],
  selections: [
    ConventionReply.selection(
      enrollmentJson(convention: conventionJson(reviewOpen: true)),
    ),
  ],
);

/// The app on the scanner of an open convention.
Future<AppHarness> _openScanner(
  WidgetTester tester, {
  ScriptedNetwork? network,
  FakeQrScanners? scanners,
  FakeCameraPermission? camera,
}) async {
  final app = await pumpApp(
    tester,
    session: FakeAuthSession(initial: const AuthSignedIn()),
    network: network ?? _network(),
    scanners: scanners,
    camera: camera,
  );
  await app.tap("convention-scan");
  expect(_top(app), AppPaths.scan);
  return app;
}

/// Reads [raw] through the live camera session and settles.
Future<void> _read(AppHarness app, FakeQrScanners scanners, String raw) async {
  scanners.read(raw);
  await app.settle();
}

String _result(WidgetTester tester) {
  final banner = find.descendant(
    of: _key("scan-result"),
    matching: find.byType(Text),
  );
  return tester.widget<Text>(banner.first).data!;
}

void main() {
  testWidgets("the home scan button is off with its reason while the review "
      "window is closed", (tester) async {
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
      network: ScriptedNetwork([200]),
    );

    final button = tester.widget<TailTagButton>(_key("convention-scan"));
    expect(button.onPressed, isNull);
    expect(find.text(CatchStrings.scanClosed("Test Con")), findsOneWidget);
    expect(app.path, AppPaths.home);
  });

  group("camera", () {
    testWidgets("the system prompt shows only from Turn on camera, and then "
        "the camera starts", (tester) async {
      final camera = FakeCameraPermission(access: CameraAccess.undecided);
      final scanners = FakeQrScanners();
      final app = await _openScanner(
        tester,
        camera: camera,
        scanners: scanners,
      );

      expect(find.text(CatchStrings.cameraIntro), findsOneWidget);
      expect(camera.prompts, 0);
      expect(scanners.sessions, isEmpty);

      await app.tap("scan-turn-on-camera");

      expect(camera.prompts, 1);
      expect(_key("fake-camera"), findsOneWidget);
      expect(find.bySemanticsLabel(CatchStrings.viewfinderLabel), findsOne);
    });

    testWidgets("a refused camera offers Settings, and a return with access "
        "starts the camera", (tester) async {
      final camera = FakeCameraPermission(access: CameraAccess.denied);
      final app = await _openScanner(tester, camera: camera);

      expect(find.text(CatchStrings.cameraDenied), findsOneWidget);
      await app.tap("scan-open-settings");
      expect(camera.settingsOpened, 1);

      camera.access = CameraAccess.granted;
      tester.binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
        ..handleAppLifecycleStateChanged(AppLifecycleState.paused)
        ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await app.settle();

      expect(_key("fake-camera"), findsOneWidget);
    });

    testWidgets("a refusal keeps the Settings path when Android still "
        "reports a permission it would ask for again", (tester) async {
      final camera = FakeCameraPermission(access: CameraAccess.undecided)
        ..promptAnswer = CameraAccess.denied;
      final app = await _openScanner(tester, camera: camera);

      await app.tap("scan-turn-on-camera");
      expect(find.text(CatchStrings.cameraDenied), findsOneWidget);

      // Android reports the refused permission as one it can ask for.
      camera.access = CameraAccess.undecided;
      tester.binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await app.settle();

      expect(find.text(CatchStrings.cameraDenied), findsOneWidget);
      expect(find.text(CatchStrings.cameraIntro), findsNothing);
    });

    testWidgets("the camera stops in the background and starts on return, "
        "and the flashlight label follows the torch", (tester) async {
      final scanners = FakeQrScanners();
      final app = await _openScanner(tester, scanners: scanners);
      final session = scanners.live;

      await app.tap("scan-torch");
      expect(session.torchToggles, 1);
      expect(find.byTooltip(CatchStrings.torchOff), findsOneWidget);

      tester.binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
        ..handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await app.settle();
      expect(session.stops, greaterThan(0));
      expect(find.byTooltip(CatchStrings.torchOn), findsOneWidget);

      tester.binding
        ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
        ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
        ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await app.settle();
      expect(session.starts, 1);
    });

    testWidgets("a scanner failure says it is getting ready, and Try again "
        "starts a new camera session", (tester) async {
      final scanners = FakeQrScanners();
      final app = await _openScanner(tester, scanners: scanners);

      scanners.live.fail();
      await app.settle();
      expect(find.text(CatchStrings.scannerNotReady), findsOneWidget);
      expect(scanners.sessions.single.disposed, isTrue);

      await tester.tap(find.text("Try again"));
      await app.settle();
      expect(scanners.sessions, hasLength(2));
      expect(_key("fake-camera"), findsOneWidget);
    });
  });

  testWidgets("a QR code that is not a TailTag stays on the device", (
    tester,
  ) async {
    final scanners = FakeQrScanners();
    final app = await _openScanner(tester, scanners: scanners);

    await _read(app, scanners, "WIFI:S:con-wifi;T:WPA;P:secret;;");
    await _read(app, scanners, "tailtag:catch:v1:${"Z" * 43}");

    expect(find.text(CatchStrings.notATag), findsOneWidget);
    expect(app.network.catchRequests, isEmpty);
  });

  testWidgets("a TailTag shows a preview, and confirm sends one submission "
      "with the scanned payload", (tester) async {
    final scanners = FakeQrScanners();
    final network = _network()
      ..enqueueCatch(_preview, ConventionReply(body: _previewBody()))
      ..enqueueCatch(_submit, _submission(201, "pending"));
    final app = await _openScanner(
      tester,
      network: network,
      scanners: scanners,
    );

    await _read(app, scanners, _payload);

    expect(network.catchCount(_preview), 1);
    expect(jsonDecode(network.catchRequests.single.body), {
      "payload": _payload,
    });
    expect(find.text("Alpha"), findsOneWidget);
    expect(find.text("Test Con"), findsOneWidget);
    expect(network.catchCount(_submit), 0);
    expect(_top(app), AppPaths.scan);

    await app.tap("scan-confirm");

    expect(network.catchCount(_submit), 1);
    expect(jsonDecode(network.catchRequests.last.body), {"payload": _payload});
    // The local deadline date is Nov 13, so the last review day is Nov 12.
    expect(_result(tester), CatchStrings.sent("Alpha", "Thu, Nov 12"));
    final shown = tester
        .widgetList<Text>(find.byType(Text))
        .map((text) => text.data ?? "");
    expect(shown.where((text) => text.contains("Z" * 43)), isEmpty);

    await app.tap("scan-see-requests");
    expect(_top(app), AppPaths.requests);
  });

  testWidgets("See my requests reads a request list that was already open", (
    tester,
  ) async {
    final scanners = FakeQrScanners();
    final network = _network()
      ..enqueueCatch(_preview, ConventionReply(body: _previewBody()))
      ..enqueueCatch(_submit, _submission(201, "pending"))
      ..enqueueCatch(
        "GET /api/catches/requests/",
        const ConventionReply(body: '{"results": []}'),
      )
      ..enqueueCatch(
        "GET /api/catches/requests/",
        ConventionReply(body: '{"results": [${_request()}]}'),
      );
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
      network: network,
      scanners: scanners,
    );
    await app.tap("nav-requests");
    expect(find.text(CatchStrings.requestsEmpty), findsOneWidget);
    await app.tap("nav-home");
    await app.tap("convention-scan");
    await _read(app, scanners, _payload);
    await app.tap("scan-confirm");

    await app.tap("scan-see-requests");

    expect(network.catchCount("GET /api/catches/requests/"), 2);
    expect(find.text("Waiting for review"), findsOneWidget);
  });

  group("each outcome shows its own text", () {
    final cases =
        <
          ({
            String label,
            bool atPreview,
            ConventionReply reply,
            String text,
            bool reloadsHome,
          })
        >[
          (
            label: "automatic approval",
            atPreview: false,
            reply: _submission(201, "approved"),
            text: CatchStrings.caught("Alpha"),
            reloadsHome: false,
          ),
          (
            label: "a request that already waits",
            atPreview: false,
            reply: _submission(200, "already_pending"),
            text: CatchStrings.alreadyPending("Alpha"),
            reloadsHome: false,
          ),
          (
            label: "a suit already caught",
            atPreview: false,
            reply: _submission(200, "already_caught"),
            text: CatchStrings.alreadyCaught("Alpha"),
            reloadsHome: false,
          ),
          (
            label: "a neutral refusal after a good preview, such as a block",
            atPreview: false,
            reply: _error(404, "catch_target_unavailable"),
            text: CatchStrings.unavailable,
            reloadsHome: false,
          ),
          (
            label: "the player's own suit",
            atPreview: true,
            reply: _error(409, "self_catch_not_allowed"),
            text: CatchStrings.ownSuit,
            reloadsHome: false,
          ),
          (
            label: "a closed review window",
            atPreview: false,
            reply: _error(409, "catch_requests_unavailable"),
            text: CatchStrings.closed("Test Con"),
            reloadsHome: false,
          ),
          (
            label: "a player who cannot catch here",
            atPreview: false,
            reply: _error(403, "catcher_ineligible"),
            text: CatchStrings.ineligible,
            reloadsHome: true,
          ),
          (
            label: "a server with the catch flow off",
            atPreview: true,
            reply: _error(404, null),
            text: CatchStrings.serviceOff,
            reloadsHome: false,
          ),
        ];
    for (final c in cases) {
      testWidgets(c.label, (tester) async {
        final scanners = FakeQrScanners();
        final network = _network();
        if (c.atPreview) {
          network.enqueueCatch(_preview, c.reply);
        } else {
          network
            ..enqueueCatch(_preview, ConventionReply(body: _previewBody()))
            ..enqueueCatch(_submit, c.reply);
        }
        final app = await _openScanner(
          tester,
          network: network,
          scanners: scanners,
        );

        final reads = network.count(_selection);

        await _read(app, scanners, _payload);
        if (!c.atPreview) {
          await app.tap("scan-confirm");
        }

        expect(_result(tester), c.text);
        expect(network.catchCount(_submit), c.atPreview ? 0 : 1);
        expect(network.count(_selection), reads + (c.reloadsHome ? 1 : 0));
      });
    }
  });

  testWidgets("a preview at another convention keeps its message after the "
      "home reloads, and offers only the way back home", (tester) async {
    final scanners = FakeQrScanners();
    final network = _network()
      ..enqueueCatch(
        _preview,
        ConventionReply(body: _previewBody(conventionId: 11)),
      )
      // The reload finds the convention that the server selected.
      ..enqueueSelection(
        ConventionReply.selection(
          enrollmentJson(
            id: 8,
            convention: conventionJson(
              id: 11,
              name: "Other Con",
              reviewOpen: true,
            ),
          ),
        ),
      );
    final app = await _openScanner(
      tester,
      network: network,
      scanners: scanners,
    );
    final reads = network.count(_selection);

    await _read(app, scanners, _payload);
    await app.settle();

    expect(network.count(_selection), reads + 1);
    expect(_result(tester), CatchStrings.conventionChanged);
    expect(_key("scan-confirm"), findsNothing);
    expect(_key("scan-again"), findsNothing);
    expect(scanners.sessions, hasLength(1));

    await app.tap("scan-close");
    expect(_top(app), AppPaths.home);
    expect(find.text("Other Con"), findsOneWidget);
  });

  group("a submission that the server placed at another convention says "
      "the convention changed", () {
    const caughtElsewhere =
        '{"id": 77, "caught_at": "2026-11-09T15:00:00Z", '
        '"approved_at": "2026-11-09T15:00:00Z", "convention_id": 11, '
        '"fursuit": {"id": 5, '
        '"tailtag_id": "00000000-0000-4000-8000-000000000005", '
        '"name": "Alpha", "photo_url": "https://media.test/5.jpg"}}';
    final cases = <String, String>{
      "a new request":
          '{"outcome": "pending", '
          '"request": ${_request(conventionId: 11)}, "catch": null}',
      "an earlier catch, which has no request":
          '{"outcome": '
          '"already_caught", "request": null, "catch": $caughtElsewhere}',
    };
    for (final MapEntry(key: label, value: body) in cases.entries) {
      testWidgets(label, (tester) async {
        final scanners = FakeQrScanners();
        final network = _network()
          ..enqueueCatch(_preview, ConventionReply(body: _previewBody()))
          ..enqueueCatch(_submit, ConventionReply(body: body));
        final app = await _openScanner(
          tester,
          network: network,
          scanners: scanners,
        );
        final reads = network.count(_selection);
        await _read(app, scanners, _payload);

        await app.tap("scan-confirm");

        expect(_result(tester), CatchStrings.conventionChanged);
        expect(network.count(_selection), reads + 1);
      });
    }
  });

  testWidgets("a wait counts down, and Try again sends the same submission "
      "once it ends", (tester) async {
    final scanners = FakeQrScanners();
    final network = _network()
      ..enqueueCatch(_preview, ConventionReply(body: _previewBody()))
      ..enqueueCatch(
        _submit,
        const ConventionReply(
          status: 429,
          body:
              '{"code": "rate_limited", "detail": "Try again later.", '
              '"retry_after_seconds": 3}',
          headers: {"retry-after": "3"},
        ),
      )
      ..enqueueCatch(_submit, _submission(201, "pending"));
    final app = await _openScanner(
      tester,
      network: network,
      scanners: scanners,
    );
    await _read(app, scanners, _payload);
    await tester.ensureVisible(_key("scan-confirm"));
    await tester.pump();
    await tester.tap(_key("scan-confirm"));
    // Short pumps let the response arrive before the countdown moves.
    for (var i = 0; i < 20 && _key("scan-retry").evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 10));
    }

    expect(_result(tester), CatchStrings.wait(3));
    expect(tester.widget<TailTagButton>(_key("scan-retry")).onPressed, isNull);

    await tester.pump(const Duration(seconds: 3));
    expect(_result(tester), CatchStrings.wait(0));
    expect(
      tester.widget<TailTagButton>(_key("scan-retry")).onPressed,
      isNotNull,
    );

    await app.tap("scan-retry");
    expect(network.catchCount(_submit), 2);
    expect(_result(tester), startsWith("Catch sent."));
  });

  testWidgets("an unknown outcome is sent again only from Check again, and "
      "the repeat shows the existing request", (tester) async {
    final scanners = FakeQrScanners();
    final network = _network()
      ..enqueueCatch(_preview, ConventionReply(body: _previewBody()))
      ..enqueueCatch(_submit, ConventionReply.brokenConnection)
      ..enqueueCatch(_submit, _submission(200, "already_pending"));
    final app = await _openScanner(
      tester,
      network: network,
      scanners: scanners,
    );
    await _read(app, scanners, _payload);

    await app.tap("scan-confirm");
    expect(_result(tester), CatchStrings.unknown);
    expect(network.catchCount(_submit), 1);

    await app.tap("scan-retry");
    expect(network.catchCount(_submit), 2);
    expect(
      network.catchRequests
          .where((item) => item.request == _submit)
          .map((item) => jsonDecode(item.body)),
      everyElement({"payload": _payload}),
    );
    expect(_result(tester), CatchStrings.alreadyPending("Alpha"));
  });

  testWidgets("Scan again drops the preview and starts a new camera session", (
    tester,
  ) async {
    final scanners = FakeQrScanners();
    final network = _network()
      ..enqueueCatch(_preview, ConventionReply(body: _previewBody()));
    final app = await _openScanner(
      tester,
      network: network,
      scanners: scanners,
    );
    await _read(app, scanners, _payload);
    expect(scanners.sessions.single.disposed, isTrue);

    await app.tap("scan-again");

    expect(_key("scan-preview"), findsNothing);
    expect(scanners.sessions, hasLength(2));
    expect(network.catchCount(_submit), 0);
  });

  testWidgets("a new player scope drops the shown preview, and a late "
      "preview from the old scope changes nothing", (tester) async {
    final scanners = FakeQrScanners();
    final network = _network()
      ..enqueueCatch(_preview, ConventionReply(body: _previewBody()))
      ..enqueueCatch(_preview, ConventionReply.stalled);
    final app = await _openScanner(
      tester,
      network: network,
      scanners: scanners,
    );
    final scope = app.container.read(playerScopeProvider.notifier);

    await _read(app, scanners, _payload);
    expect(_key("scan-preview"), findsOneWidget);
    scope.advance();
    await app.settle();
    expect(_key("scan-preview"), findsNothing);
    expect(_key("fake-camera"), findsOneWidget);

    scanners.read(_payload);
    await tester.pump();
    scope.advance();
    await app.settle();
    network.releaseCatch(0, ConventionReply(body: _previewBody()));
    await app.settle();
    expect(_key("scan-preview"), findsNothing);
    expect(network.catchCount(_submit), 0);
  });

  testWidgets("the preview and the result stay usable at 200% text scale", (
    tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final scanners = FakeQrScanners();
    final network = _network()
      ..enqueueCatch(_preview, ConventionReply(body: _previewBody()))
      ..enqueueCatch(_submit, _submission(201, "pending"));
    final app = await _openScanner(
      tester,
      network: network,
      scanners: scanners,
    );

    await _read(app, scanners, _payload);
    expect(tester.takeException(), isNull);
    await app.tap("scan-confirm");
    expect(tester.takeException(), isNull);
    for (final guideline in [
      androidTapTargetGuideline,
      iOSTapTargetGuideline,
      labeledTapTargetGuideline,
    ]) {
      await expectLater(tester, meetsGuideline(guideline));
    }
  });
}
