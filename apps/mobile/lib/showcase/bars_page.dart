import "package:flutter/material.dart";
import "package:tailtag_mobile/core/ui/tokens.dart";
import "package:tailtag_mobile/showcase/showcase_parts.dart";

/// Showcase tab for the top app bar and the bottom navigation bar.
class BarsPage extends StatelessWidget {
  /// Creates the tab.
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    return ShowcasePage(
      children: [
        ShowcaseSection(
          title: "Top app bar",
          children: [
            ShowcaseExample(
              label: "Back, a long title, two actions, and an overflow menu",
              bleed: true,
              child: AppBar(
                primary: false,
                // Show the normal look even while the showcase page scrolls.
                notificationPredicate: (_) => false,
                leading: const BackButton(onPressed: noop),
                title: const Text(longFursuitName),
                actions: [
                  IconButton(
                    tooltip: "Share QR code",
                    icon: Icon(Icons.adaptive.share),
                    onPressed: noop,
                  ),
                  const IconButton(
                    tooltip: "Edit fursuit",
                    icon: Icon(Icons.edit_outlined),
                    onPressed: noop,
                  ),
                  PopupMenuButton<String>(
                    icon: Icon(Icons.adaptive.more),
                    tooltip: "More",
                    itemBuilder: (context) => const [
                      PopupMenuItem(
                        value: "rotate",
                        child: Text("Rotate QR code"),
                      ),
                      PopupMenuItem(value: "off", child: Text("Turn off")),
                    ],
                  ),
                ],
              ),
            ),
            const ShowcaseExample(
              label: "Scrolled under: content sits under this bar",
              bleed: true,
              child: _ScrolledUnderBar(),
            ),
          ],
        ),
        const ShowcaseSection(
          title: "Bottom navigation bar",
          children: [
            ShowcaseExample(
              label:
                  "The showcase tabs below use it, with the selected "
                  "destination. Press and hold a destination for the pressed "
                  "layer. Use Tab on a keyboard for the focus layer.",
              child: SizedBox.shrink(),
            ),
          ],
        ),
      ],
    );
  }
}

/// A real app bar over a list that starts scrolled, so the bar shows its
/// scrolled-under look with no gesture.
class _ScrolledUnderBar extends StatefulWidget {
  const new();

  @override
  State<_ScrolledUnderBar> createState() => _ScrolledUnderBarState();
}

class _ScrolledUnderBarState extends State<_ScrolledUnderBar> {
  final _controller = ScrollController();

  @override
  void initState() {
    super.initState();
    // The app bar changes on a scroll update, so scroll after the first
    // frame instead of setting an initial offset.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_controller.hasClients) {
        _controller.jumpTo(TokenSpacing.xxxl);
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final textScale = MediaQuery.textScalerOf(context).scale(1);
    // Stop the list scroll here, so it does not reach the showcase app bar.
    return NotificationListener<ScrollNotification>(
      onNotification: (_) => true,
      child: SizedBox(
        height: 200 * textScale,
        child: Scaffold(
          primary: false,
          appBar: AppBar(primary: false, title: const Text("Catches")),
          body: ListView(
            controller: _controller,
            children: [
              for (var i = 1; i <= 12; i++) ListTile(title: Text("Catch $i")),
            ],
          ),
        ),
      ),
    );
  }
}
