import "package:flutter/widgets.dart";
import "package:tailtag_mobile/showcase/showcase_app.dart";
import "package:tailtag_mobile/showcase/showcase_images.dart";

/// Starts the component showcase: `task mobile-showcase DEVICE=<id>`.
///
/// This entry point is separate from `lib/main.dart`, so it needs no
/// configuration file and store builds never include it.
Future<void> main() async {
  final images = await startShowcaseImageServer();
  runApp(ShowcaseApp(sampleImage: images.sample, missingImage: images.missing));
}
