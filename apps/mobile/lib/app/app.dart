import "package:flutter/material.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";

/// Root application widget for TailTag.
class TailTagApp extends StatelessWidget {
  /// Constructor for the TailTag widget.
  const new({super.key});

  @override
  Widget build(BuildContext context) {
    // V0 is light only, so the app stays light when the device uses dark
    // mode. See docs/design/README.md.
    return MaterialApp.router(
      title: "TailTag",
      theme: buildTailTagTheme(),
      themeMode: ThemeMode.light,
      routerConfig: appRouter,
    );
  }
}
