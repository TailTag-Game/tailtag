import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";
import "package:tailtag_mobile/showcase/bars_page.dart";
import "package:tailtag_mobile/showcase/content_page.dart";
import "package:tailtag_mobile/showcase/controls_page.dart";
import "package:tailtag_mobile/showcase/feedback_page.dart";
import "package:tailtag_mobile/showcase/showcase_images.dart";
import "package:tailtag_mobile/showcase/tokens_page.dart";

/// The development-only showcase of the V0 shared components and tokens.
///
/// It uses the app theme and the shared widgets, and nothing else from the
/// app: no configuration, API, Clerk session, or providers. See
/// `lib/core/ui/README.md`.
class ShowcaseApp extends StatelessWidget {
  /// Creates the showcase with the avatar image URLs.
  const new({required this.sampleImage, required this.missingImage, super.key});

  /// A URL that serves the sample image.
  final String sampleImage;

  /// A URL that answers 404.
  final String missingImage;

  @override
  Widget build(BuildContext context) {
    // V0 is light only, like TailTagApp.
    return ShowcaseImages(
      sample: sampleImage,
      missing: missingImage,
      child: MaterialApp(
        title: "TailTag showcase",
        theme: buildTailTagTheme(),
        themeMode: ThemeMode.light,
        home: const ShowcaseScreen(),
      ),
    );
  }
}

/// One showcase tab.
typedef ShowcaseTab = ({
  String label,
  IconData icon,
  IconData selectedIcon,
  Widget page,
});

/// The showcase tabs, in navigation bar order.
const List<ShowcaseTab> showcaseTabs = [
  (
    label: "Controls",
    icon: Icons.tune_outlined,
    selectedIcon: Icons.tune,
    page: ControlsPage(),
  ),
  (
    label: "Content",
    icon: Icons.view_agenda_outlined,
    selectedIcon: Icons.view_agenda,
    page: ContentPage(),
  ),
  (
    label: "Feedback",
    icon: Icons.feedback_outlined,
    selectedIcon: Icons.feedback,
    page: FeedbackPage(),
  ),
  (
    label: "Bars",
    icon: Icons.web_asset_outlined,
    selectedIcon: Icons.web_asset,
    page: BarsPage(),
  ),
  (
    label: "Tokens",
    icon: Icons.palette_outlined,
    selectedIcon: Icons.palette,
    page: TokensPage(),
  ),
];

/// The showcase screen: a page per tab, and a 200% text scale switch.
class ShowcaseScreen extends StatefulWidget {
  /// Creates the screen.
  const new({super.key});

  @override
  State<ShowcaseScreen> createState() => _ShowcaseScreenState();
}

class _ShowcaseScreenState extends State<ShowcaseScreen> {
  int _tab = 0;
  bool _largeText = false;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    return MediaQuery(
      data: media.copyWith(
        textScaler: _largeText ? const TextScaler.linear(2) : media.textScaler,
      ),
      child: Scaffold(
        appBar: AppBar(
          title: const Text("Showcase"),
          actions: [
            IconButton(
              tooltip: _largeText ? "Normal text size" : "200% text size",
              isSelected: _largeText,
              icon: const Icon(Icons.text_increase_outlined),
              selectedIcon: const Icon(Icons.text_decrease),
              onPressed: () => setState(() => _largeText = !_largeText),
            ),
          ],
        ),
        // Keyboard focus visits the whole page before the navigation bar.
        // Without the group, reading order mixes them.
        body: FocusTraversalGroup(
          child: IndexedStack(
            index: _tab,
            children: [for (final tab in showcaseTabs) tab.page],
          ),
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (index) => setState(() => _tab = index),
          destinations: [
            for (final tab in showcaseTabs)
              NavigationDestination(
                icon: Icon(tab.icon),
                selectedIcon: Icon(tab.selectedIcon),
                label: tab.label,
              ),
          ],
        ),
      ),
    );
  }
}
