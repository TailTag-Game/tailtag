import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/features/catches/catch_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

const _list = "GET /api/catches/requests/";

String _withdrawPath(int id) => "POST /api/catches/requests/$id/withdraw/";

String _request({
  required int id,
  String state = "pending",
  int conventionId = 10,
  String name = "Alpha",
  String requestedAt = "2026-11-09T15:00:00Z",
  String deadline = "2026-11-13T05:00:00Z",
}) =>
    '{"id": $id, "fursuit": {"id": ${id + 100}, '
    '"tailtag_id": "00000000-0000-4000-8000-000000000005", '
    '"name": "$name", "photo_url": "https://media.test/$id.jpg"}, '
    '"convention_id": $conventionId, "state": "$state", '
    '"requested_at": "$requestedAt", "review_deadline_at": "$deadline"}';

ConventionReply _requests(List<String> items) =>
    ConventionReply(body: '{"results": [${items.join(", ")}]}');

ConventionReply _error(int status, String? code) => ConventionReply(
  status: status,
  body: code == null
      ? '{"detail": "Not found."}'
      : '{"code": "$code", "detail": "x", "state": "approved"}',
);

Finder _key(String key) => find.byKey(Key(key));

/// The app on the Requests section, with the selected convention 10 and
/// its enrollment, and [lists] queued for the request reads.
Future<AppHarness> _openRequests(
  WidgetTester tester,
  List<ConventionReply> lists, {
  void Function(ScriptedNetwork network)? setUp,
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
  for (var i = 0; i < 6; i++) {
    network.enqueueEnrollments(
      ConventionReply.list([enrollmentJson(convention: convention)]),
    );
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
  await app.tap("nav-requests");
  return app;
}

void main() {
  testWidgets("requests group by convention with the selected one first, and "
      "each group shows its last review day", (tester) async {
    await _openRequests(
      tester,
      [
        _requests([
          _request(id: 1, conventionId: 11, name: "Left Con Suit"),
          _request(id: 2),
          _request(id: 3, conventionId: 12, name: "Unknown Con Suit"),
          _request(id: 4, state: "declined", name: "Beta"),
        ]),
      ],
      setUp: (network) => network.enqueueCatch(
        "GET /api/conventions/11/",
        ConventionReply(
          body: conventionJson(
            id: 11,
            name: "Left Con",
            reviewOpen: true,
            deadlineDate: "2026-11-20",
          ),
        ),
      ),
    );

    final groups = tester
        .widgetList<Padding>(
          find.byWidgetPredicate(
            (widget) =>
                widget.key is ValueKey<String> &&
                (widget.key! as ValueKey<String>).value.startsWith(
                  "requests-group-",
                ),
          ),
        )
        .map((widget) => (widget.key! as ValueKey<String>).value)
        .toList();
    expect(groups, [
      "requests-group-10",
      "requests-group-11",
      "requests-group-12",
    ]);
    expect(find.text("Test Con"), findsOneWidget);
    expect(find.text(CatchStrings.reviewUntil("Thu, Nov 12")), findsOneWidget);
    expect(find.text("Left Con"), findsOneWidget);
    expect(find.text(CatchStrings.reviewUntil("Thu, Nov 19")), findsOneWidget);
    // The app could not read convention 12, so the header is generic and
    // the deadline is the instant in device time.
    expect(find.text(CatchStrings.otherConvention), findsOneWidget);
    expect(
      find.textContaining(RegExp("^Owners can review until (?!the end)")),
      findsOneWidget,
    );

    expect(find.text("Waiting for review"), findsNWidgets(3));
    expect(find.text("Not accepted"), findsOneWidget);
    expect(_key("request-withdraw-4"), findsNothing);
    expect(_key("request-withdraw-2"), findsOneWidget);
  });

  testWidgets("withdraw asks first, Cancel sends nothing, and a confirmed "
      "withdrawal shows the new state", (tester) async {
    final app = await _openRequests(
      tester,
      [
        _requests([_request(id: 2)]),
        _requests([_request(id: 2, state: "withdrawn")]),
      ],
      setUp: (network) => network.enqueueCatch(
        _withdrawPath(2),
        ConventionReply(body: _request(id: 2, state: "withdrawn")),
      ),
    );

    await app.tap("request-withdraw-2");
    expect(find.text(CatchStrings.withdrawTitle), findsOneWidget);
    await app.tap("withdraw-cancel");
    expect(app.network.catchCount(_withdrawPath(2)), 0);

    await app.tap("request-withdraw-2");
    await app.tap("withdraw-confirm");

    expect(app.network.catchCount(_withdrawPath(2)), 1);
    expect(app.network.catchCount(_list), 2);
    expect(find.text("Withdrawn"), findsOneWidget);
    expect(find.text(CatchStrings.withdrawn), findsOneWidget);
    expect(_key("request-withdraw-2"), findsNothing);
  });

  group("a withdrawal that does not land reads the list again and never "
      "repeats", () {
    final cases = <({String label, ConventionReply reply, String banner})>[
      (
        label: "another action won",
        reply: _error(409, "request_state_changed"),
        banner: CatchStrings.requestChanged,
      ),
      (
        label: "the review window closed",
        reply: _error(409, "review_window_closed"),
        banner: CatchStrings.requestGone,
      ),
      (
        label: "cleanup deleted the request",
        reply: _error(404, "request_not_found"),
        banner: CatchStrings.requestGone,
      ),
      (
        label: "the connection broke",
        reply: ConventionReply.brokenConnection,
        banner: CatchStrings.withdrawUnknown,
      ),
    ];
    for (final c in cases) {
      testWidgets(c.label, (tester) async {
        final app = await _openRequests(tester, [
          _requests([_request(id: 2)]),
          _requests([_request(id: 2, state: "approved")]),
        ], setUp: (network) => network.enqueueCatch(_withdrawPath(2), c.reply));

        await app.tap("request-withdraw-2");
        await app.tap("withdraw-confirm");

        expect(find.text(c.banner), findsOneWidget);
        expect(app.network.catchCount(_list), 2);
        expect(app.network.catchCount(_withdrawPath(2)), 1);
        expect(find.text("Caught"), findsOneWidget);
      });
    }
  });

  testWidgets("the list and the bar stay usable at 200% text scale, and an "
      "account change clears the list", (tester) async {
    tester.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final app = await _openRequests(tester, [
      _requests([_request(id: 2), _request(id: 4, state: "declined")]),
    ]);

    expect(tester.takeException(), isNull);
    expect(_key("request-row-2"), findsOneWidget);
    for (final guideline in [
      androidTapTargetGuideline,
      iOSTapTargetGuideline,
      labeledTapTargetGuideline,
    ]) {
      await expectLater(tester, meetsGuideline(guideline));
    }

    // A new player scope drops the list while the section stays open.
    app.container.read(playerScopeProvider.notifier).advance();
    await app.settle();
    expect(_key("request-row-2"), findsNothing);
  });

  testWidgets("an empty list says how to send a request", (tester) async {
    await _openRequests(tester, [_requests(const [])]);

    expect(find.text(CatchStrings.requestsEmpty), findsOneWidget);
  });

  testWidgets("a server with the catch flow off says requests are not "
      "available", (tester) async {
    await _openRequests(tester, [_error(404, null)]);

    expect(find.text(CatchStrings.requestsOff), findsOneWidget);
  });

  testWidgets("the list reads again at the earliest deadline on screen and "
      "on each return to the section", (tester) async {
    final soon = DateTime.now().toUtc().add(const Duration(seconds: 20));
    final app = await _openRequests(tester, [
      _requests([_request(id: 2, deadline: soon.toIso8601String())]),
      _requests(const []),
      _requests(const []),
    ]);
    expect(app.network.catchCount(_list), 1);

    await tester.pump(const Duration(seconds: 22));
    await app.settle();
    expect(app.network.catchCount(_list), 2);
    expect(find.text(CatchStrings.requestsEmpty), findsOneWidget);

    await app.tap("nav-home");
    await app.tap("nav-requests");
    expect(app.network.catchCount(_list), 3);
  });
}
