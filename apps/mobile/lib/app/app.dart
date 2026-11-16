import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/app/router.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_providers.dart";
import "package:tailtag_mobile/core/session/foreground_signal.dart";
import "package:tailtag_mobile/core/session/player_scope.dart";
import "package:tailtag_mobile/core/ui/tailtag_theme.dart";

/// Root application widget for TailTag.
class TailTagApp extends ConsumerStatefulWidget {
  /// Constructor for the TailTag widget.
  const new({super.key});

  @override
  ConsumerState<TailTagApp> createState() => _TailTagAppState();
}

class _TailTagAppState extends ConsumerState<TailTagApp> {
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    // `onShow` runs only after the app was hidden. A notification shade or
    // Face ID makes the app inactive but not hidden, so they do not fire it.
    _lifecycle = AppLifecycleListener(
      onShow: () => ref.read(foregroundSignalProvider.notifier).fire(),
    );
    // A tag image holds a QR code. Any left from an earlier run or an
    // earlier player goes at start, on sign-out, and on an account change.
    final share = ref.read(tagShareProvider);
    unawaited(share.clear());
    ref.listenManual(playerScopeProvider, (_, _) => unawaited(share.clear()));
  }

  @override
  void dispose() {
    _lifecycle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // V0 is light only, so the app stays light when the device uses dark
    // mode. See docs/design/README.md.
    return MaterialApp.router(
      title: "TailTag",
      theme: buildTailTagTheme(),
      themeMode: ThemeMode.light,
      routerConfig: ref.watch(routerProvider),
    );
  }
}
