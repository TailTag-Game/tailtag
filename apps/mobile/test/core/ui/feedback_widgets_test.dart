import "package:flutter/material.dart";
import "package:flutter/rendering.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/ui/delayed_visibility.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/core/ui/widgets/empty_state.dart";
import "package:tailtag_mobile/core/ui/widgets/status_badge.dart";
import "package:tailtag_mobile/core/ui/widgets/status_banner.dart";

import "support/ui_test_app.dart";

/// The badge and banner colors and icon of each tone, from components.md.
const Map<StatusTone, (Color, Color, IconData)> _tones = {
  StatusTone.neutral: (
    TokenColors.surfaceContainerHighest,
    TokenColors.onSurfaceVariant,
    Icons.info_outlined,
  ),
  StatusTone.success: (
    TokenStatusColors.successContainer,
    TokenStatusColors.onSuccessContainer,
    Icons.check_circle_outlined,
  ),
  StatusTone.warning: (
    TokenStatusColors.warningContainer,
    TokenStatusColors.onWarningContainer,
    Icons.warning_amber_outlined,
  ),
  StatusTone.error: (
    TokenColors.errorContainer,
    TokenColors.onErrorContainer,
    Icons.error_outline,
  ),
};

void main() {
  group("StatusBadge", () {
    for (final MapEntry(key: tone, value: (fill, text, icon))
        in _tones.entries) {
      testWidgets("$tone has its colors and icon on a rounded label", (
        tester,
      ) async {
        await tester.pumpWidget(
          themed(
            Center(
              child: StatusBadge(tone: tone, label: "Out now"),
            ),
          ),
        );
        final badge = find.byType(StatusBadge);
        final ink = tester.widget<Ink>(
          find.descendant(of: badge, matching: find.byType(Ink)),
        );
        expect((ink.decoration! as ShapeDecoration).color, fill);
        expect(
          materialOf(tester, badge).shape,
          RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(TokenRadius.small),
          ),
        );
        expect(tester.widget<Text>(find.text("Out now")).maxLines, 1);
        // Neutral shows an icon only when the feature gives one.
        expect(
          find.byIcon(icon),
          tone == StatusTone.neutral ? findsNothing : findsOneWidget,
        );
        if (tone != StatusTone.neutral) {
          expect(tester.widget<Icon>(find.byIcon(icon)).color, text);
        }
      });
    }

    testWidgets("a badge has no action and its text joins its row", (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        themed(
          ListTile(
            title: const Text("Sable"),
            trailing: const StatusBadge(
              tone: StatusTone.success,
              label: "Out now",
            ),
            onTap: () {},
          ),
        ),
      );
      final row = tester.getSemantics(find.byType(ListTile));
      expect(row.label, allOf(contains("Sable"), contains("Out now")));
      // The badge has no node or action of its own.
      expect(tester.getSemantics(find.byType(StatusBadge)), same(row));
      semantics.dispose();
    });
  });

  group("a badge in a list row on a small phone", () {
    // (text scale, badge below the title, check the title is readable).
    // The test font is about twice as wide as the system font, so the title
    // check runs only where the test font gives a fair answer.
    const cases = [
      (1.0, false, true),
      (1.3, false, false),
      (1.31, true, false),
      (2.0, true, true),
    ];
    for (final (scale, below, readable) in cases) {
      testWidgets("at ${scale}x text it sits ${below ? "below" : "beside"} "
          "the title", (tester) async {
        useScreen(tester, smallPhone);
        const badge = StatusBadge(tone: StatusTone.success, label: "Out now");
        await tester.pumpWidget(
          themed(
            Builder(
              builder: (context) => ListTile(
                leading: const SizedBox.square(dimension: 40),
                title: const Text("Sable Fox"),
                subtitle: StatusBadge.rowSubtitle(
                  context,
                  badge,
                  subtitle: const Text("Arctic fox"),
                ),
                trailing: StatusBadge.rowTrailing(context, badge),
              ),
            ),
            textScale: scale,
          ),
        );

        final titleRect = tester.getRect(find.text("Sable Fox"));
        final badgeRect = tester.getRect(find.byType(StatusBadge));
        if (below) {
          expect(badgeRect.top, greaterThanOrEqualTo(titleRect.bottom));
        } else {
          expect(badgeRect.left, greaterThanOrEqualTo(titleRect.right));
        }
        if (readable) {
          final title = tester.renderObject<RenderParagraph>(
            find.text("Sable Fox"),
          );
          expect(
            title.size.width,
            greaterThanOrEqualTo(title.getMinIntrinsicWidth(double.infinity)),
            reason: "the title is squeezed",
          );
        }
      });
    }
  });

  group("StatusBanner", () {
    // The badge tests cover the colors and icon of every tone, through the
    // same statusStyle lookup.
    testWidgets("an error banner has its colors in a live region", (
      tester,
    ) async {
      final (fill, text, icon) = _tones[StatusTone.error]!;
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        themed(
          const StatusBanner(
            tone: StatusTone.error,
            message: "Something went wrong.",
          ),
        ),
      );
      expect(materialOf(tester, find.byType(StatusBanner)).color, fill);
      expect(tester.widget<Icon>(find.byIcon(icon)).color, text);
      expect(
        tester.getSemantics(find.text("Something went wrong.")),
        isSemantics(isLiveRegion: true),
      );
      semantics.dispose();
    });

    test("a success banner is refused, because success uses a snackbar", () {
      expect(
        () => StatusBanner(tone: StatusTone.success, message: "Saved"),
        throwsAssertionError,
      );
    });

    testWidgets("the action uses the banner text color and its loading state", (
      tester,
    ) async {
      var retries = 0;
      Widget banner({required bool loading}) => themed(
        StatusBanner(
          tone: StatusTone.error,
          message: "Something went wrong. Try again.",
          actionLabel: "Try again",
          onAction: () => retries++,
          actionLoading: loading,
        ),
      );

      await tester.pumpWidget(banner(loading: false));
      final action = find.widgetWithText(TextButton, "Try again");
      expect(
        materialOf(tester, action).textStyle?.color,
        TokenColors.onErrorContainer,
      );
      expect(tester.getSize(action).height, greaterThanOrEqualTo(48));
      await tester.tap(action);
      expect(retries, 1);

      await tester.pumpWidget(banner(loading: true));
      await tester.pump(loadingIndicatorDelay);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      await tester.tap(find.byType(TextButton), warnIfMissed: false);
      expect(retries, 1);
    });
  });

  group("EmptyState", () {
    testWidgets("the title is a header", (tester) async {
      final semantics = tester.ensureSemantics();
      await tester.pumpWidget(
        themed(
          const EmptyState(
            icon: Icons.pets_outlined,
            title: "No fursuits yet",
            body: "Add a fursuit to start playing.",
          ),
        ),
      );
      expect(
        tester.getSemantics(find.text("No fursuits yet")),
        isSemantics(isHeader: true),
      );
      semantics.dispose();
    });

    testWidgets("at 200% text scale in a short space, the content scrolls", (
      tester,
    ) async {
      useScreen(tester, smallPhone);
      var taps = 0;
      await tester.pumpWidget(
        themed(
          SizedBox(
            height: 300,
            child: EmptyState(
              icon: Icons.pets_outlined,
              title: "No fursuits yet at this convention",
              body: "Add a fursuit to start playing at this convention.",
              action: FilledButton(
                onPressed: () => taps++,
                child: const Text("Add fursuit"),
              ),
            ),
          ),
          textScale: 2,
        ),
      );
      expect(tester.takeException(), isNull);

      await tester.ensureVisible(find.text("Add fursuit"));
      await tester.pumpAndSettle();
      await tester.tap(find.text("Add fursuit"));
      expect(taps, 1);
    });
  });
}
