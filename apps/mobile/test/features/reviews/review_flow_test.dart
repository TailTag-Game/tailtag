import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/features/reviews/review_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

const _list = "GET /api/catches/incoming-requests/";
const _summary = "GET /api/catches/incoming-requests/summary/";

String _action(int id, String name) =>
    "POST /api/catches/incoming-requests/$id/$name/";

String _unblock(int id) => "DELETE /api/catches/incoming-requests/$id/block/";

String _owner({
  required int id,
  String state = "pending",
  int conventionId = 10,
  String handle = "sam",
  String name = "Sam",
  int suit = 5,
  String suitName = "Alpha",
  int prior = 0,
  bool blocked = false,
  bool paused = false,
  String requestedAt = "2026-11-09T15:00:00Z",
}) =>
    '{"id": $id, "fursuit": {"id": $suit, '
    '"tailtag_id": "00000000-0000-4000-8000-000000000005", '
    '"name": "$suitName", "photo_url": "https://media.test/$suit.jpg"}, '
    '"convention_id": $conventionId, '
    '"player": {"display_name": "$name", "handle": "$handle"}, '
    '"state": "$state", "requested_at": "$requestedAt", '
    '"undo_available_until": null, "prior_decline_count": $prior, '
    '"player_blocked": $blocked, "approval_paused": $paused, '
    '"review_deadline_at": "2026-11-13T05:00:00Z"}';

ConventionReply _rows(List<String> items) =>
    ConventionReply(body: '{"results": [${items.join(", ")}]}');

ConventionReply _one(String request) => ConventionReply(body: request);

ConventionReply _approval(String request) => ConventionReply(
  body:
      '{"request": $request, "catch": {"id": 900, '
      '"caught_at": "2026-11-09T15:00:00Z", "convention_id": 10, '
      '"approved_at": "2026-11-09T15:05:00Z", "fursuit": {"id": 5, '
      '"tailtag_id": "00000000-0000-4000-8000-000000000005", '
      '"name": "Alpha", "photo_url": "https://media.test/5.jpg"}}}',
);

ConventionReply _error(int status, String code) => ConventionReply(
  status: status,
  body: '{"code": "$code", "detail": "x", "state": "approved"}',
);

ConventionReply _count(int count) => ConventionReply(
  body:
      '{"pending_count": $count, "fursuits": '
      '${count == 0 ? "[]" : '[{"fursuit_id": 5, "pending_count": $count}]'}}',
);

Finder _key(String key) => find.byKey(Key(key));

/// The app on the review screen, opened from the home row. The selected
/// convention is 10. [lists] answer the list reads in order. The home row
/// needs a count above 0, so every summary read answers [pending].
Future<AppHarness> _openReview(
  WidgetTester tester,
  List<ConventionReply> lists, {
  int pending = 2,
  void Function(ScriptedNetwork network)? setUp,
  Future<void> Function(AppHarness app)? onHome,
}) async {
  tester.view.physicalSize = const Size(1200, 7200);
  addTearDown(tester.view.resetPhysicalSize);
  final convention = conventionJson(reviewOpen: true);
  final network = ScriptedNetwork.withConventions(
    [200],
    const [],
    selections: [
      ConventionReply.selection(enrollmentJson(convention: convention)),
    ],
  );
  for (var i = 0; i < 8; i++) {
    network
      ..enqueueEnrollments(
        ConventionReply.list([enrollmentJson(convention: convention)]),
      )
      ..enqueueCatch(_summary, _count(pending));
  }
  for (final reply in lists) {
    network.enqueueCatch(_list, reply);
  }
  setUp?.call(network);
  final app = await pumpApp(
    tester,
    session: FakeAuthSession(initial: const AuthSignedIn()),
    network: network,
  );
  expect(find.text(ReviewStrings.toReview(pending)), findsOneWidget);
  await onHome?.call(app);
  await app.tap("home-review");
  expect(app.path, AppPaths.requests);
  expect(find.byKey(const Key("requests-segment")), findsOneWidget);
  return app;
}

void main() {
  testWidgets("requests group by convention with waiting ones first, and "
      "only the newest row of a player and suit offers Restore or Remove "
      "block", (tester) async {
    await _openReview(
      tester,
      [
        _rows([
          _owner(id: 1, conventionId: 11, handle: "lee", name: "Lee"),
          _owner(id: 2, prior: 2),
          _owner(id: 3, state: "declined"),
          _owner(
            id: 4,
            state: "declined",
            handle: "kai",
            name: "Kai",
            prior: 1,
            blocked: true,
          ),
          _owner(id: 5, handle: "ash", name: "Ash", paused: true),
        ]),
      ],
      setUp: (network) => network.enqueueCatch(
        "GET /api/conventions/11/",
        ConventionReply(
          body: conventionJson(id: 11, name: "Left Con", reviewOpen: true),
        ),
      ),
    );

    final tops = [
      for (final key in [
        "review-group-10",
        "review-row-2",
        "review-row-5",
        "review-row-3",
        "review-row-4",
        "review-group-11",
        "review-row-1",
      ])
        tester.getTopLeft(_key(key)).dy,
    ];
    expect(tops, orderedEquals([...tops]..sort()));
    expect(find.text(ReviewStrings.toReviewPart), findsNWidgets(2));
    expect(find.text(ReviewStrings.decidedPart), findsOneWidget);
    expect(
      find.text(ReviewStrings.reviewUntil("Thu, Nov 12")),
      findsNWidgets(2),
    );
    expect(find.text("@sam · Alpha"), findsNWidgets(2));
    expect(find.text(ReviewStrings.priorDeclines(2)), findsOneWidget);
    expect(find.text("Declined 1 time before here"), findsOneWidget);
    expect(_key("review-blocked-4"), findsOneWidget);

    // Row 3 is an older request of the same player and suit as row 2.
    expect(_key("review-restore-3"), findsNothing);
    expect(_key("review-restore-4"), findsOneWidget);
    expect(_key("review-unblock-4"), findsOneWidget);
    expect(_key("review-approve-3"), findsNothing);

    expect(_key("review-paused-5"), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(
            find.descendant(
              of: _key("review-approve-5"),
              matching: find.byType(FilledButton),
            ),
          )
          .onPressed,
      isNull,
    );
  });

  testWidgets("approve shows no success until the server confirms it, then "
      "a snackbar, and the list reads again", (tester) async {
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
        _rows([_owner(id: 2, state: "approved")]),
      ],
      setUp: (network) =>
          network.enqueueCatch(_action(2, "approve"), ConventionReply.stalled),
    );

    await app.tap("review-approve-2");
    expect(find.text("Waiting for review"), findsOneWidget);
    expect(find.text(ReviewStrings.approved), findsNothing);

    app.network.releaseCatch(0, _approval(_owner(id: 2, state: "approved")));
    await app.settle();

    expect(find.text(ReviewStrings.approved), findsOneWidget);
    expect(find.text("Approved"), findsOneWidget);
    expect(app.network.catchCount(_action(2, "approve")), 1);
    expect(app.network.catchCount(_list), 2);
  });

  testWidgets("an action that ends after the owner left the screen still "
      "reads the list again and refreshes the counts", (tester) async {
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
        _rows([_owner(id: 2, state: "approved")]),
      ],
      setUp: (network) =>
          network.enqueueCatch(_action(2, "approve"), ConventionReply.stalled),
    );
    await app.tap("review-approve-2");
    final summaries = app.network.catchCount(_summary);

    await app.tap("nav-home");
    app.network.releaseCatch(0, _approval(_owner(id: 2, state: "approved")));
    await app.settle();

    expect(app.network.catchCount(_list), 2);
    expect(app.network.catchCount(_summary), greaterThan(summaries));
  });

  group("a refused or unknown action reads the list again and never "
      "repeats", () {
    final cases =
        <
          ({
            String label,
            String key,
            String request,
            ConventionReply reply,
            String banner,
          })
        >[
          (
            label: "another action won",
            key: "review-approve-2",
            request: _action(2, "approve"),
            reply: _error(409, "request_state_changed"),
            banner: ReviewStrings.changed,
          ),
          (
            label: "approval is paused",
            key: "review-approve-2",
            request: _action(2, "approve"),
            reply: _error(409, "approval_paused"),
            banner: ReviewStrings.paused,
          ),
          (
            label: "a catch already exists",
            key: "review-approve-2",
            request: _action(2, "approve"),
            reply: _error(409, "request_superseded"),
            banner: ReviewStrings.alreadyCaught,
          ),
          (
            label: "a newer request stops a restore",
            key: "review-restore-4",
            request: _action(4, "restore"),
            reply: _error(409, "request_superseded"),
            banner: ReviewStrings.cannotRestore,
          ),
          (
            label: "the review window closed",
            key: "review-approve-2",
            request: _action(2, "approve"),
            reply: _error(409, "review_window_closed"),
            banner: ReviewStrings.gone,
          ),
          (
            label: "cleanup deleted the request",
            key: "review-approve-2",
            request: _action(2, "approve"),
            reply: _error(404, "request_not_found"),
            banner: ReviewStrings.gone,
          ),
          (
            label: "the connection broke",
            key: "review-approve-2",
            request: _action(2, "approve"),
            reply: ConventionReply.brokenConnection,
            banner: ReviewStrings.unknown,
          ),
          (
            label: "a server error",
            key: "review-restore-4",
            request: _action(4, "restore"),
            reply: const ConventionReply(status: 503),
            banner: ReviewStrings.unknown,
          ),
        ];
    for (final c in cases) {
      testWidgets(c.label, (tester) async {
        final rows = _rows([
          _owner(id: 2),
          _owner(id: 4, state: "declined", handle: "kai"),
        ]);
        final app = await _openReview(tester, [
          rows,
          rows,
        ], setUp: (network) => network.enqueueCatch(c.request, c.reply));

        await app.tap(c.key);

        expect(find.text(c.banner), findsOneWidget);
        expect(app.network.catchCount(c.request), 1);
        expect(app.network.catchCount(_list), 2);
      });
    }
  });

  testWidgets("a 403 reads the home state again", (tester) async {
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
      ],
      setUp: (network) => network.enqueueCatch(
        _action(2, "approve"),
        _error(403, "permission_denied"),
      ),
    );
    final before = app.network.count("GET /api/conventions/active/");

    await app.tap("review-approve-2");

    expect(
      app.network.count("GET /api/conventions/active/"),
      greaterThan(before),
    );
  });

  testWidgets("a plain decline offers Undo, which returns the request to "
      "waiting", (tester) async {
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
        _rows([_owner(id: 2, state: "declined")]),
        _rows([_owner(id: 2)]),
      ],
      setUp: (network) => network
        ..enqueueCatch(
          _action(2, "decline"),
          _one(_owner(id: 2, state: "declined")),
        )
        ..enqueueCatch(_action(2, "undo-decline"), _one(_owner(id: 2))),
    );

    await app.tap("review-decline-2");
    expect(find.text(ReviewStrings.declineAndBlock), findsOneWidget);
    expect(
      find.text(ReviewStrings.blockHelp("Alpha", "Test Con")),
      findsOneWidget,
    );
    await app.tap("review-decline-plain");

    expect(
      app.network.catchRequests
          .singleWhere((item) => item.request == _action(2, "decline"))
          .body,
      '{"block":false}',
    );
    expect(find.text(ReviewStrings.declined), findsOneWidget);
    await tester.tap(_key("review-undo"));
    await app.settle();

    expect(app.network.catchCount(_action(2, "undo-decline")), 1);
    expect(find.text("Waiting for review"), findsOneWidget);
    // The undo time and the controller's keep-alive end.
    await tester.pump(const Duration(seconds: 11));
  });

  testWidgets("a decline with a block confirms the block and offers no "
      "Undo", (tester) async {
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
        _rows([_owner(id: 2, state: "declined", blocked: true)]),
      ],
      setUp: (network) => network.enqueueCatch(
        _action(2, "decline"),
        _one(_owner(id: 2, state: "declined", blocked: true)),
      ),
    );

    await app.tap("review-decline-2");
    await app.tap("review-decline-block");

    expect(
      app.network.catchRequests
          .singleWhere((item) => item.request == _action(2, "decline"))
          .body,
      '{"block":true}',
    );
    expect(find.text(ReviewStrings.blockedDone), findsOneWidget);
    expect(_key("review-undo"), findsNothing);
    expect(_key("review-blocked-2"), findsOneWidget);
    expect(_key("review-restore-2"), findsOneWidget);
  });

  testWidgets("Undo closes 10 seconds after the app sent the decline, even "
      "when the answer came late", (tester) async {
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
        _rows([_owner(id: 2, state: "declined")]),
      ],
      setUp: (network) =>
          network.enqueueCatch(_action(2, "decline"), ConventionReply.stalled),
    );

    await app.tap("review-decline-2");
    await app.tap("review-decline-plain");
    // [AppHarness.tap] settles for about 1.6 seconds after the tap. The
    // answer arrives about 3 seconds after the app sent the decline.
    await tester.pump(const Duration(milliseconds: 1400));
    app.network.releaseCatch(0, _one(_owner(id: 2, state: "declined")));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(_key("review-undo"), findsOneWidget);

    // 9 seconds after the send, Undo still shows.
    await tester.pump(const Duration(milliseconds: 5500));
    expect(_key("review-undo"), findsOneWidget);

    // Past 10 seconds, the snackbar is gone.
    await tester.pump(const Duration(milliseconds: 1500));
    await tester.pump(const Duration(seconds: 1));
    expect(_key("review-undo"), findsNothing);
    // The controller's keep-alive runs 10 seconds from the late answer.
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets("Undo after the server's limit shows the restore hint", (
    tester,
  ) async {
    final declined = _rows([_owner(id: 2, state: "declined")]);
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
        declined,
        declined,
      ],
      setUp: (network) => network
        ..enqueueCatch(
          _action(2, "decline"),
          _one(_owner(id: 2, state: "declined")),
        )
        ..enqueueCatch(_action(2, "undo-decline"), _error(409, "undo_expired")),
    );

    await app.tap("review-decline-2");
    await app.tap("review-decline-plain");
    await tester.tap(_key("review-undo"));
    await app.settle();

    expect(find.text(ReviewStrings.tooLateToUndo), findsOneWidget);
    expect(_key("review-restore-2"), findsOneWidget);
    await tester.pump(const Duration(seconds: 11));
  });

  testWidgets("restore and remove block confirm with a snackbar", (
    tester,
  ) async {
    final blocked = _owner(id: 4, state: "declined", blocked: true, prior: 1);
    final app = await _openReview(
      tester,
      [
        _rows([blocked]),
        _rows([_owner(id: 4, blocked: true)]),
        _rows([_owner(id: 4)]),
      ],
      setUp: (network) => network
        ..enqueueCatch(
          _action(4, "restore"),
          _one(_owner(id: 4, blocked: true)),
        )
        ..enqueueCatch(
          _unblock(4),
          const ConventionReply(status: 204, body: ""),
        ),
    );

    expect(find.text(ReviewStrings.priorDeclines(1)), findsOneWidget);

    await app.tap("review-restore-4");
    expect(find.text(ReviewStrings.restored), findsOneWidget);
    expect(find.text("Waiting for review"), findsOneWidget);
    // The list read after the restore gives the new count.
    expect(find.text(ReviewStrings.priorDeclines(1)), findsNothing);

    await app.tap("review-unblock-4");
    expect(find.text(ReviewStrings.unblocked), findsOneWidget);
    expect(app.network.catchCount(_unblock(4)), 1);
    expect(_key("review-unblock-4"), findsNothing);
  });

  testWidgets("with catch review off, the home row hides and the review "
      "screen says so", (tester) async {
    tester.view.physicalSize = const Size(1200, 7200);
    addTearDown(tester.view.resetPhysicalSize);
    final convention = conventionJson(reviewOpen: true);
    const off = ConventionReply(status: 404, body: '{"detail": "x"}');
    final network = ScriptedNetwork.withConventions(
      [200],
      const [],
      selections: [
        ConventionReply.selection(enrollmentJson(convention: convention)),
      ],
    );
    for (var i = 0; i < 4; i++) {
      network
        ..enqueueCatch(_summary, off)
        ..enqueueCatch(_list, off);
    }
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
      network: network,
    );
    expect(app.network.catchCount(_summary), greaterThan(0));
    expect(_key("home-review"), findsNothing);

    app.container.read(routerProvider).go(AppPaths.review);
    await app.settle();

    expect(find.text(ReviewStrings.serviceOff), findsOneWidget);
  });

  testWidgets("the home row and nav badge hide when nothing waits", (
    tester,
  ) async {
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
      network: ScriptedNetwork([200]),
    );
    expect(app.network.catchCount(_summary), greaterThan(0));
    expect(_key("home-review"), findsNothing);
    expect(
      tester.widget<Badge>(_key("nav-requests-badge")).isLabelVisible,
      isFalse,
    );
  });

  testWidgets("the nav badge shows pending count and Requests defaults to "
      "Received when pending reviews exist", (tester) async {
    final convention = conventionJson(reviewOpen: true);
    final network = ScriptedNetwork.withConventions(
      [200],
      const [],
      selections: [
        ConventionReply.selection(enrollmentJson(convention: convention)),
      ],
    );
    for (var i = 0; i < 6; i++) {
      network
        ..enqueueEnrollments(
          ConventionReply.list([enrollmentJson(convention: convention)]),
        )
        ..enqueueCatch(_summary, _count(3));
    }
    network.enqueueCatch(_list, _rows([_owner(id: 2)]));
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
      network: network,
    );

    final badge = tester.widget<Badge>(_key("nav-requests-badge"));
    expect(badge.isLabelVisible, isTrue);
    expect(find.text("3"), findsOneWidget);

    await app.tap("nav-requests");
    expect(find.text("Received (3)"), findsOneWidget);
    expect(find.text("Sam"), findsOneWidget);

    await app.tap("requests-tab-sent");
    expect(_key("requests-list"), findsOneWidget);
  });

  testWidgets("an account change shows no request of the previous player, "
      "and a late list changes nothing", (tester) async {
    final app = await _openReview(tester, [
      _rows([_owner(id: 2)]),
      ConventionReply.stalled,
    ]);
    expect(find.text("Sam"), findsOneWidget);
    // A foreground return reads the list again, and that read stalls.
    tester.binding
      ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
      ..handleAppLifecycleStateChanged(AppLifecycleState.hidden)
      ..handleAppLifecycleStateChanged(AppLifecycleState.inactive)
      ..handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await app.settle();

    app.session.emit(const AuthSignedOut());
    await app.settle();
    app.network.releaseCatch(0, _rows([_owner(id: 2)]));
    await app.settle();
    expect(app.path, AppPaths.access);

    app.network
      ..enqueue(200)
      ..enqueueCatch(_list, _rows([_owner(id: 7, name: "Robin")]));
    app.session.emit(const AuthSignedIn());
    await app.settle();
    app.container.read(routerProvider).go(AppPaths.review);
    await app.settle();

    expect(find.text("Robin"), findsOneWidget);
    expect(find.text("Sam"), findsNothing);
  });

  testWidgets("an account change clears the counts of the previous player", (
    tester,
  ) async {
    final convention = conventionJson(reviewOpen: true);
    final network = ScriptedNetwork.withConventions(
      [200, 200],
      const [],
      selections: [
        ConventionReply.selection(enrollmentJson(convention: convention)),
      ],
    )..enqueueCatch(_summary, _count(2));
    final app = await pumpApp(
      tester,
      session: FakeAuthSession(initial: const AuthSignedIn()),
      network: network,
    );
    expect(find.text(ReviewStrings.toReview(2)), findsOneWidget);

    app.session.emit(const AuthSignedOut());
    await app.settle();
    app.session.emit(const AuthSignedIn());
    await app.settle();

    expect(app.path, AppPaths.home);
    expect(_key("home-review"), findsNothing);
  });

  testWidgets("Undo does nothing after the player signed out", (tester) async {
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
        _rows([_owner(id: 2, state: "declined")]),
      ],
      setUp: (network) => network.enqueueCatch(
        _action(2, "decline"),
        _one(_owner(id: 2, state: "declined")),
      ),
    );
    await app.tap("review-decline-2");
    await app.tap("review-decline-plain");
    expect(_key("review-undo"), findsOneWidget);

    app.session.emit(const AuthSignedOut());
    await tester.pump();
    await tester.tap(_key("review-undo"), warnIfMissed: false);
    await app.settle();

    expect(app.network.catchCount(_action(2, "undo-decline")), 0);
    await tester.pump(const Duration(seconds: 11));
  });

  testWidgets("the home row and the decline sheet stay usable at 200% text "
      "scale", (tester) async {
    final semantics = tester.ensureSemantics();
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    Future<void> meetsGuidelines() async {
      expect(tester.takeException(), isNull);
      for (final guideline in [
        androidTapTargetGuideline,
        iOSTapTargetGuideline,
        textContrastGuideline,
        labeledTapTargetGuideline,
      ]) {
        await expectLater(tester, meetsGuideline(guideline));
      }
    }

    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
      ],
      onHome: (_) async {
        expectHoldsText(tester, _key("home-review"), [
          find.text(ReviewStrings.toReview(2)),
        ]);
        await meetsGuidelines();
      },
    );

    await app.tap("review-decline-2");
    expectHoldsText(tester, _key("review-decline-plain"), [
      find.text(ReviewStrings.decline).last,
    ]);
    expectHoldsText(tester, _key("review-decline-block"), [
      find.text(ReviewStrings.declineAndBlock),
      find.text(ReviewStrings.blockHelp("Alpha", "Test Con")),
    ]);
    await meetsGuidelines();
    expect(
      tester.semantics.simulatedAccessibilityTraversal().map(
        (node) => node.getSemanticsData().label,
      ),
      containsAllInOrder([
        contains(ReviewStrings.decline),
        allOf(
          contains(ReviewStrings.declineAndBlock),
          contains(ReviewStrings.blockHelp("Alpha", "Test Con")),
        ),
      ]),
    );
    semantics.dispose();
  });

  testWidgets("the review screen stays usable at 200% text scale, and each "
      "row reads as one node", (tester) async {
    final semantics = tester.ensureSemantics();
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await _openReview(tester, [
      _rows([_owner(id: 2, prior: 1, blocked: true)]),
    ]);

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
        startsWith("Test Con"),
        allOf(
          startsWith("Sam, @sam, Alpha, Test Con, "),
          contains("Waiting for review, Declined 1 time before here, Blocked"),
        ),
        contains(ReviewStrings.approveFor("Sam")),
        contains(ReviewStrings.declineFor("Sam")),
        contains(ReviewStrings.removeBlockFor("Sam")),
      ]),
    );
    semantics.dispose();
  });

  testWidgets("reopening the Home review action reapplies Received after "
      "switching to Sent", (tester) async {
    final app = await _openReview(
      tester,
      [
        _rows([_owner(id: 2)]),
        _rows([_owner(id: 2)]),
      ],
      setUp: (network) => network.enqueueCatch(
        "GET /api/catches/requests/",
        const ConventionReply(body: '{"results": []}'),
      ),
    );

    expect(_key("review-row-2"), findsOneWidget);

    await app.tap("requests-tab-sent");
    expect(_key("requests-empty"), findsOneWidget);

    await app.tap("nav-home");
    await app.tap("home-review");

    expect(_key("review-row-2"), findsOneWidget);
    expect(_key("requests-empty"), findsNothing);
  });
}
