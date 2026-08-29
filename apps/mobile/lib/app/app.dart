import "package:flutter/material.dart";
import "package:tailtag_mobile/app/router.dart";

/// Root application widget for TailTag.
class TailTagApp extends StatelessWidget {
  /// Constructor for the TailTag widget.
  const TailTagApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(title: "TailTag", routerConfig: appRouter);
  }
}
