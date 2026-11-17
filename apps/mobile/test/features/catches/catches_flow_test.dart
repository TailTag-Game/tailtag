import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/auth/auth_state.dart";
import "package:tailtag_mobile/features/catches/catch_strings.dart";

import "../../support/app_test_support.dart";
import "../../support/auth_test_support.dart";

const _history = "GET /api/catches/";

String _catch(
  int id, {
  int conventionId = 10,
  String convention = "Test Con",
}) =>
    '{"id": $id, "fursuit": {"id": ${id + 100}, "name": "Suit $id", '
    '"photo_url": "https://media.test/$id.jpg"}, '
    '"convention": {"id": $conventionId, "name": "$convention"}, '
    '"caught_at": "2026-11-09T15:00:00Z"}';

ConventionReply _page(List<String> items, {bool next = false}) {
  final link = next ? '"https://dev.tailtag.app/api/catches/?page=2"' : "null";
  return ConventionReply(
    body:
        '{"catch_count": ${items.length}, "next": $link, '
        '"previous": null, "results": [${items.join(", ")}]}',
  );
}

/// The history reads that were sent, as their query strings.
List<String> _queries(AppHarness app) => [
  for (final item in app.network.catchRequests)
    if (item.request.split("?").first == _history)
      if (item.request.contains("?")) item.request.split("?").last else "",
];

/// The app on the Catches section, enrolled in conventions 10 and 11.
Future<AppHarness> _openCatches(
  WidgetTester tester,
  List<ConventionReply> pages,
) async {
  tester.view.physicalSize = const Size(1200, 7200);
  addTearDown(tester.view.resetPhysicalSize);
  final selected = conventionJson(reviewOpen: true);
  final network = ScriptedNetwork.withConventions(
    [200],
    const [],
    selections: [
      ConventionReply.selection(enrollmentJson(convention: selected)),
    ],
  );
  for (var i = 0; i < 6; i++) {
    network.enqueueEnrollments(
      ConventionReply.list([
        enrollmentJson(convention: selected),
        enrollmentJson(
          id: 8,
          convention: conventionJson(id: 11, name: "Older Con"),
          selected: false,
        ),
      ]),
    );
  }
  for (final page in pages) {
    network.enqueueCatch(_history, page);
  }
  final app = await pumpApp(
    tester,
    session: FakeAuthSession(initial: const AuthSignedIn()),
    network: network,
  );
  await app.tap("nav-catches");
  return app;
}

void main() {
  testWidgets("the collection starts at the selected convention and loads "
      "the next page at the end of the list", (tester) async {
    final app = await _openCatches(tester, [
      _page([_catch(1), _catch(2)], next: true),
      _page([_catch(3)]),
    ]);

    final all = tester.widget<FilterChip>(
      find.byKey(const Key("catches-chip-all")),
    );
    final selected = tester.widget<FilterChip>(
      find.byKey(const Key("catches-chip-10")),
    );
    expect(all.selected, isFalse);
    expect(selected.selected, isTrue);
    expect(find.byKey(const Key("catches-chip-11")), findsOneWidget);
    expect(_queries(app), [
      allOf(contains("convention_id=10"), contains("page=1")),
      allOf(contains("convention_id=10"), contains("page=2")),
    ]);
    for (final id in [1, 2, 3]) {
      expect(find.text("Suit $id"), findsOneWidget);
    }
  });

  testWidgets("a failed next page is not loaded again until Try again", (
    tester,
  ) async {
    final app = await _openCatches(tester, [
      _page([_catch(1), _catch(2)], next: true),
      const ConventionReply(status: 500),
      const ConventionReply(status: 500),
      const ConventionReply(status: 500),
    ]);
    for (var i = 0; i < 5; i++) {
      await app.settle();
    }

    expect(_queries(app), hasLength(2));
    expect(find.byKey(const Key("catches-banner")), findsOneWidget);
    expect(find.text("Suit 2"), findsOneWidget);
  });

  testWidgets("All shows every convention and names each catch's "
      "convention", (tester) async {
    final app = await _openCatches(tester, [
      _page([_catch(1)]),
      _page([_catch(1), _catch(4, conventionId: 11, convention: "Older Con")]),
    ]);

    await app.tap("catches-chip-all");

    expect(_queries(app).last, isNot(contains("convention_id")));
    expect(find.textContaining("Older Con\n"), findsOneWidget);
    expect(find.textContaining("Test Con\n"), findsOneWidget);
  });

  testWidgets("an empty collection says how to catch a suit", (tester) async {
    await _openCatches(tester, [_page(const [])]);

    expect(find.text(CatchStrings.catchesEmpty), findsOneWidget);
    expect(find.text(CatchStrings.catchesEmptyBody), findsOneWidget);
  });
}
