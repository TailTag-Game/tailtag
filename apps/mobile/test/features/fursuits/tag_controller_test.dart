import "dart:async";
import "dart:typed_data";

import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_providers.dart";
import "package:tailtag_mobile/core/fursuits/fursuit_repository.dart";
import "package:tailtag_mobile/core/fursuits/tag_share.dart";
import "package:tailtag_mobile/features/fursuits/tag_controller.dart";

import "../../support/api_test_support.dart";
import "../../support/app_test_support.dart";
import "tag_badge_test.dart" show fakePayload;

ConventionReply _tag(int version) => ConventionReply(
  body:
      '{"fursuit_id": 5, "state": "current", "tag_version": $version, '
      '"payload": "$fakePayload"}',
);

void main() {
  test("an image that rendered before the tag changed is not shared", () async {
    final network = ScriptedNetwork()
      ..enqueueSuit("GET /api/fursuits/5/tag/", _tag(1))
      ..enqueueSuit("GET /api/fursuits/5/tag/", _tag(2));
    final share = FakeTagShare();
    final container = ProviderContainer(
      overrides: [
        fursuitRepositoryProvider.overrideWithValue(
          FursuitRepository(createTestTransport(network)),
        ),
        tagShareProvider.overrideWithValue(share),
      ],
    );
    addTearDown(container.dispose);
    container.listen(tagControllerProvider(5), (_, _) {});
    final controller = container.read(tagControllerProvider(5).notifier);
    await controller.read();

    // The render waits while a foreground read brings a new tag.
    final render = Completer<TagImage>();
    final sharing = controller.share(() => render.future);
    await controller.read();
    render.complete(
      TagImage(bytes: Uint8List.fromList([1]), width: 2400, height: 1800),
    );
    await sharing;

    expect(share.shares, isEmpty);
    final state = container.read(tagControllerProvider(5));
    expect(state.tag?.version, 2);
    expect(state.sharing, isFalse);
  });
}
