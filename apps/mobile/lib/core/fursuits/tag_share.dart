import "dart:io";
import "dart:typed_data";
import "dart:ui";

import "package:share_plus/share_plus.dart";

/// A rendered tag badge, ready to share.
final class TagImage {
  /// Creates an image from its PNG [bytes] and pixel size.
  const new({
    required this.bytes,
    required this.width,
    required this.height,
    this.fileName = tagImageFileName,
    this.mimeType = tagImageMimeType,
  });

  /// The encoded PNG. It holds the QR code, so it is as secret as the
  /// payload.
  final Uint8List bytes;

  /// The width in pixels.
  final int width;

  /// The height in pixels.
  final int height;

  /// The name of the shared file. It holds no payload and no suit name.
  final String fileName;

  /// The MIME type of the shared file.
  final String mimeType;
}

/// The file name of a shared tag image. It holds no payload and no suit
/// name.
const String tagImageFileName = "tailtag-tag.png";

/// The MIME type of a shared tag image.
const String tagImageMimeType = "image/png";

/// The seam between the app and the system share sheet.
abstract interface class TagShare {
  /// Writes [image] to a file and opens the share sheet for it. The sheet
  /// points at [origin] on a tablet. It returns when the sheet closes.
  Future<void> share(TagImage image, {Rect? origin});

  /// Deletes every tag image file that the app or the share plugin left.
  Future<void> clear();
}

/// [TagShare] over the `share_plus` plugin.
///
/// The image goes into a folder that the app owns under the system temp
/// folder. On Android, `share_plus` also copies each shared file into a
/// `share_plus` folder inside the app cache folder. The system temp folder
/// there is the code cache folder, a sibling of the cache folder, so
/// [clear] looks in both places. The file is not deleted right after the
/// share, because the receiving app can still be reading it.
final class SharePlusTagShare implements TagShare {
  /// Creates the share over [root], the system temp folder by default.
  new({Directory? root}) : _root = root ?? Directory.systemTemp;

  final Directory _root;

  Directory get _folder => Directory("${_root.path}/tailtag_tag");

  /// Where `share_plus` can leave a copy: the Android cache folder, which
  /// is a sibling of the code cache folder, and the temp folder itself.
  List<File> get _pluginCopies => [
    File("${_root.parent.path}/cache/share_plus/$tagImageFileName"),
    File("${_root.path}/share_plus/$tagImageFileName"),
  ];

  @override
  Future<void> share(TagImage image, {Rect? origin}) async {
    await clear();
    final folder = await _folder.create(recursive: true);
    final file = File("${folder.path}/${image.fileName}");
    await file.writeAsBytes(image.bytes, flush: true);
    await SharePlus.instance.share(
      ShareParams(
        files: [XFile(file.path, mimeType: image.mimeType)],
        sharePositionOrigin: origin,
      ),
    );
  }

  @override
  Future<void> clear() async {
    // A failed delete leaves a file that the next clear tries again. It
    // never blocks the screen.
    try {
      if (_folder.existsSync()) {
        await _folder.delete(recursive: true);
      }
      for (final copy in _pluginCopies) {
        if (copy.existsSync()) {
          await copy.delete();
        }
      }
    } on FileSystemException {
      return;
    }
  }
}
