import "dart:ui" as ui;

import "package:barcode_widget/barcode_widget.dart";
import "package:flutter/material.dart";
import "package:flutter/rendering.dart";
import "package:tailtag_mobile/core/fursuits/tag_share.dart";
import "package:tailtag_mobile/features/fursuits/fursuit_strings.dart";

/// The QR error correction level of every tag. Level Q survives a scuffed
/// or laminated badge.
const BarcodeQRCorrectionLevel tagQrLevel = BarcodeQRCorrectionLevel.quartile;

/// The QR quiet zone, in modules, on every side.
const int tagQrQuietModules = 4;

/// The QR encoder of every tag.
final Barcode tagBarcode = Barcode.qrCode(errorCorrectLevel: tagQrLevel);

/// The number of modules on each side of the QR code of [payload], without
/// the quiet zone. Each element of a 2D code is one module high.
int tagQrModules(String payload) {
  final first = tagBarcode.make(payload, width: 1, height: 1).first;
  return (1 / first.height).round();
}

/// A QR code of [payload]: black on white in every theme, with a quiet zone
/// of [tagQrQuietModules] modules. It shows no text, and it leaves the
/// screen reader label to its parent.
class TagQr extends StatelessWidget {
  /// Creates the code at [size], quiet zone included.
  const new({required this.payload, required this.size, super.key});

  /// The printed string. It is never logged.
  final String payload;

  /// The side length, quiet zone included.
  final double size;

  @override
  Widget build(BuildContext context) {
    final modules = tagQrModules(payload);
    final quiet = size * tagQrQuietModules / (modules + 2 * tagQrQuietModules);
    return BarcodeWidget(
      barcode: tagBarcode,
      data: payload,
      width: size,
      height: size,
      padding: EdgeInsets.all(quiet),
      drawText: false,
      // The bars use the default black.
      backgroundColor: Colors.white,
    );
  }
}

/// The badge size in logical pixels. One logical pixel is 0.01 in, so the
/// badge is 4 × 3 in.
const Size tagBadgeSize = Size(400, 300);

/// The capture scale: 6 pixels per logical pixel gives 600 dpi, which
/// makes a 2400 × 1800 px image.
const double tagBadgePixelRatio = 6;

const double _perMillimeter = 100 / 25.4;
const double _padding = 16;
const double _qrSide = 60 * _perMillimeter;
const double _scaleLine = 50 * _perMillimeter;

/// The printable badge of a tag, laid out at its true size of 4 × 3 in.
///
/// The text uses the device fonts, so emoji and non-Latin names show. The
/// text scale is fixed, because the print has a fixed size.
class TagBadge extends StatelessWidget {
  /// Creates the badge.
  const new({
    required this.payload,
    required this.name,
    required this.version,
    super.key,
  });

  /// The printed string.
  final String payload;

  /// The suit name.
  final String name;

  /// The tag version.
  final int version;

  @override
  Widget build(BuildContext context) {
    const black = Colors.black;
    return MediaQuery(
      data: MediaQuery.of(context).copyWith(textScaler: TextScaler.noScaling),
      child: DefaultTextStyle(
        style: const TextStyle(color: black, fontSize: 12, height: 1.2),
        child: Container(
          width: tagBadgeSize.width,
          height: tagBadgeSize.height,
          padding: const EdgeInsets.all(_padding),
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border.all(color: const Color(0xFF9E9E9E), width: 0.5),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            spacing: 12,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                spacing: 6,
                children: [
                  TagQr(payload: payload, size: _qrSide),
                  const _ScaleLine(),
                ],
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  spacing: 8,
                  children: [
                    const FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.topLeft,
                      child: Text(
                        FursuitStrings.wordmark,
                        maxLines: 1,
                        style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.w800,
                          height: 1,
                        ),
                      ),
                    ),
                    // A long name wraps at the column width, then shrinks
                    // to fit the space left. It is never clipped.
                    Expanded(
                      child: LayoutBuilder(
                        builder: (context, box) => FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.topLeft,
                          child: SizedBox(
                            width: box.maxWidth,
                            child: Text(
                              name,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                    Text(FursuitStrings.tagVersion(version)),
                    const Text(FursuitStrings.scanWithApp),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A 50 mm line with end ticks, so the owner can check the print size.
class _ScaleLine extends StatelessWidget {
  const new();

  @override
  Widget build(BuildContext context) {
    const side = BorderSide(width: 0.5);
    return SizedBox(
      width: _scaleLine,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        spacing: 2,
        children: [
          Container(
            height: 4,
            decoration: const BoxDecoration(
              border: Border(left: side, right: side, bottom: side),
            ),
          ),
          const Text(FursuitStrings.scaleLine, style: TextStyle(fontSize: 8)),
        ],
      ),
    );
  }
}

/// Holds a [TagBadge] off screen, so [captureTagBadge] can render it.
///
/// It paints but sits outside the visible area, and it is hidden from
/// screen readers and touches. Put it in a [Stack] that is not inside a
/// scrollable, because a scrollable does not paint off-screen children.
class TagBadgeCapture extends StatelessWidget {
  /// Creates the holder with [boundaryKey] on its repaint boundary.
  const new({required this.boundaryKey, required this.badge, super.key});

  /// The key that [captureTagBadge] reads.
  final GlobalKey boundaryKey;

  /// The badge to render.
  final TagBadge badge;

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: -tagBadgeSize.width - 100,
      top: 0,
      width: tagBadgeSize.width,
      height: tagBadgeSize.height,
      child: ExcludeSemantics(
        child: IgnorePointer(
          child: RepaintBoundary(key: boundaryKey, child: badge),
        ),
      ),
    );
  }
}

/// Renders the badge under [boundaryKey] as a 600 dpi PNG.
Future<TagImage> captureTagBadge(GlobalKey boundaryKey) async {
  final boundary =
      boundaryKey.currentContext!.findRenderObject()! as RenderRepaintBoundary;
  final image = await boundary.toImage(pixelRatio: tagBadgePixelRatio);
  try {
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    if (data == null) {
      throw StateError("The badge could not be encoded.");
    }
    return TagImage(
      bytes: data.buffer.asUint8List(),
      width: image.width,
      height: image.height,
    );
  } finally {
    image.dispose();
  }
}
