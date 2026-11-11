import "dart:io";

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/showcase/showcase_app.dart";
import "package:tailtag_mobile/showcase/showcase_parts.dart";
import "package:tailtag_mobile/showcase/token_catalog.dart";

import "../core/ui/support/ui_test_app.dart";

/// `docs/design/components.md`, read from the `apps/mobile` package root.
final File _componentsFile = File(
  ["..", "..", "docs", "design", "components.md"].join(Platform.pathSeparator),
);

/// The component names in the Inventory table of `components.md`.
List<String> _inventory() {
  final lines = _componentsFile.readAsLinesSync();
  final start = lines.indexOf("## Inventory");
  expect(start, isNonNegative, reason: "components.md has an Inventory.");
  final names = <String>[];
  for (final line in lines.skip(start + 1)) {
    if (line.startsWith("#")) {
      break;
    }
    final name = RegExp(r"^\| \[([^\]]+)\]\(#").firstMatch(line)?.group(1);
    if (name != null) {
      names.add(name);
    }
  }
  return names;
}

/// Every request that the showcase makes through `dart:io`, by URL.
final List<Uri> _requests = [];

/// Pumps the showcase on [size] while every HTTP request is recorded and
/// fails, so no test reaches a network.
///
/// The showcase gets loopback image URLs, as `lib/showcase/main.dart` gives
/// it. The image hook must be unset before the test ends, so it is not a
/// tear-down.
Future<void> _pumpShowcase(
  WidgetTester tester,
  Future<void> Function() body, {
  Size size = smallPhone,
}) async {
  useScreen(tester, size);
  _requests.clear();
  debugNetworkImageHttpClientProvider = _RecordingHttpClient.new;
  try {
    await HttpOverrides.runZoned(() async {
      await tester.pumpWidget(
        const ShowcaseApp(
          sampleImage: "http://127.0.0.1:9/sample.bmp",
          missingImage: "http://127.0.0.1:9/missing.bmp",
        ),
      );
      await tester.pump();
      await body();
      // Let the 500 ms loading delays and the spinners run out.
      await tester.pump(const Duration(seconds: 1));
    }, createHttpClient: (_) => _RecordingHttpClient());
  } finally {
    debugNetworkImageHttpClientProvider = null;
  }
}

Future<void> _openTab(WidgetTester tester, String label) async {
  await tester.tap(
    find.descendant(of: find.byType(NavigationBar), matching: find.text(label)),
  );
  await tester.pump();
}

/// The scrolling page of the open tab.
Finder _openPage() {
  // Finders skip offstage widgets, so this finds only the open tab.
  return find.byWidgetPredicate((widget) => widget is SingleChildScrollView);
}

/// The scroll position of the open tab page, not of a list inside it.
ScrollPosition _pagePosition(WidgetTester tester) {
  return tester
      .state<ScrollableState>(
        find
            .descendant(
              of: _openPage().first,
              matching: find.byType(Scrollable),
            )
            .first,
      )
      .position;
}

void main() {
  for (final textScale in const [1, 2]) {
    for (final tab in showcaseTabs) {
      testWidgets(
        "the ${tab.label} tab builds at ${textScale * 100}% text with no "
        "app setup and no network",
        (tester) async {
          await _pumpShowcase(tester, () async {
            if (textScale == 2) {
              await tester.tap(find.byTooltip("200% text size"));
              await tester.pump();
            }
            await _openTab(tester, tab.label);
            await tester.drag(_openPage().first, const Offset(0, -2000));
            await tester.pump();
          });

          expect(tester.takeException(), isNull);
          expect(
            _requests.where((url) => url.host != "127.0.0.1"),
            isEmpty,
            reason: "The showcase must not reach a network host.",
          );
          expect(_requests, isNotEmpty, reason: "The image guard is live.");
        },
      );
    }
  }

  testWidgets("the showcase has one section for each inventory component", (
    tester,
  ) async {
    await _pumpShowcase(tester, () async {});

    final sections = tester
        .widgetList<ShowcaseSection>(
          find.byType(ShowcaseSection, skipOffstage: false),
        )
        .map((section) => section.title)
        .toList();
    final inventory = _inventory();
    expect(inventory, hasLength(17));
    expect(sections..sort(), inventory..sort());
  });

  testWidgets("the Tokens tab shows every token in the catalog", (
    tester,
  ) async {
    await _pumpShowcase(tester, () async {});

    for (final name in tokenCatalog.keys) {
      expect(find.text(name, skipOffstage: false), findsOneWidget);
    }
  });

  final guidelines = <AccessibilityGuideline>[
    androidTapTargetGuideline,
    iOSTapTargetGuideline,
    textContrastGuideline,
    labeledTapTargetGuideline,
  ];
  for (final tab in showcaseTabs) {
    testWidgets("the ${tab.label} tab meets the four accessibility "
        "guidelines", (tester) async {
      final semantics = tester.ensureSemantics();
      await _pumpShowcase(tester, () async {
        await _openTab(tester, tab.label);
        // Make the screen tall enough to show every section of the tab, so
        // the guidelines see all of it.
        final extent = _pagePosition(tester).maxScrollExtent;
        useScreen(tester, Size(smallPhone.width, smallPhone.height + extent));
        await tester.pump();
        expect(_pagePosition(tester).maxScrollExtent, 0);
        for (final guideline in guidelines) {
          await expectLater(tester, meetsGuideline(guideline));
        }
      });
      semantics.dispose();
    });
  }
}

/// An HTTP client that records each URL and fails the request.
final class _RecordingHttpClient extends Fake implements HttpClient {
  @override
  bool autoUncompress = true;

  @override
  Future<HttpClientRequest> getUrl(Uri url) async {
    _requests.add(url);
    throw const SocketException("The showcase test blocks the network.");
  }
}
