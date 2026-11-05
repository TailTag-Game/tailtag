import "dart:async";
import "dart:io";
import "dart:typed_data";

import "package:flutter/widgets.dart";

/// The image URLs that the avatar examples load.
///
/// `TailTagAvatar` takes only a URL, so the showcase serves its own sample
/// image from a loopback server. It needs no image file and no external
/// host.
class ShowcaseImages extends InheritedWidget {
  /// Provides [sample] and [missing] to the examples in [child].
  const new({
    required this.sample,
    required this.missing,
    required super.child,
    super.key,
  });

  /// A URL that serves the sample image.
  final String sample;

  /// A URL that answers 404, for the image error state.
  final String missing;

  /// The images of the nearest [ShowcaseImages].
  static ShowcaseImages of(BuildContext context) {
    final images = context.dependOnInheritedWidgetOfExactType<ShowcaseImages>();
    assert(images != null, "The showcase app provides ShowcaseImages.");
    return images!;
  }

  @override
  bool updateShouldNotify(ShowcaseImages oldWidget) {
    return sample != oldWidget.sample || missing != oldWidget.missing;
  }
}

/// The path of the sample image on the loopback server.
const String sampleImagePath = "/sample.bmp";

/// Starts a server on the loopback address that serves the sample image at
/// [sampleImagePath] and answers 404 for every other path.
///
/// It runs until the app stops. It returns the two image URLs.
Future<({String sample, String missing})> startShowcaseImageServer() async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  final image = sampleImageBytes();
  server.listen((request) {
    final response = request.response;
    if (request.uri.path == sampleImagePath) {
      response
        ..headers.contentType = ContentType("image", "bmp")
        ..add(image);
    } else {
      response.statusCode = HttpStatus.notFound;
    }
    unawaited(response.close());
  });
  final origin = "http://${server.address.address}:${server.port}";
  return (sample: "$origin$sampleImagePath", missing: "$origin/missing.bmp");
}

/// A 64 by 64 BMP with a violet-to-teal gradient, made at run time.
Uint8List sampleImageBytes() {
  const size = 64;
  const headerSize = 54;
  const rowSize = size * 3;
  final bytes = ByteData(headerSize + rowSize * size)
    ..setUint8(0, 0x42)
    ..setUint8(1, 0x4D)
    ..setUint32(2, headerSize + rowSize * size, Endian.little)
    ..setUint32(10, headerSize, Endian.little)
    ..setUint32(14, 40, Endian.little)
    ..setInt32(18, size, Endian.little)
    ..setInt32(22, size, Endian.little)
    ..setUint16(26, 1, Endian.little)
    ..setUint16(28, 24, Endian.little)
    ..setUint32(34, rowSize * size, Endian.little);
  for (var y = 0; y < size; y++) {
    for (var x = 0; x < size; x++) {
      final t = (x + y) / (2 * (size - 1));
      final offset = headerSize + y * rowSize + x * 3;
      bytes
        ..setUint8(offset, (0xFF * (1 - t) + 0xA8 * t).round())
        ..setUint8(offset + 1, (0x20 * (1 - t) + 0x96 * t).round())
        ..setUint8(offset + 2, (0x69 * (1 - t) + 0x00 * t).round());
    }
  }
  return bytes.buffer.asUint8List();
}
