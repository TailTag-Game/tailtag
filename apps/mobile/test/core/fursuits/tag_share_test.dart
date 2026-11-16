import "dart:io";

import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/core/fursuits/tag_share.dart";

void main() {
  test("clear deletes the app's tag image and the share plugin's copies, "
      "and leaves other files", () async {
    // On Android the system temp folder is the code cache folder, and the
    // plugin copies into its sibling cache folder.
    final data = await Directory.systemTemp.createTemp("tag_share_test");
    addTearDown(() => data.delete(recursive: true));
    final root = await Directory("${data.path}/code_cache").create();
    Future<File> write(String path) async =>
        (await File("${data.path}/$path").create(recursive: true))
          ..writeAsStringSync("x");
    final own = await write("code_cache/tailtag_tag/tailtag-tag.png");
    final androidCopy = await write("cache/share_plus/tailtag-tag.png");
    final tempCopy = await write("code_cache/share_plus/tailtag-tag.png");
    final other = await write("cache/share_plus/other.png");

    await SharePlusTagShare(root: root).clear();

    expect(own.existsSync(), isFalse);
    expect(androidCopy.existsSync(), isFalse);
    expect(tempCopy.existsSync(), isFalse);
    expect(other.existsSync(), isTrue);
  });
}
