import "dart:convert";
import "dart:typed_data";

import "package:barcode_widget/barcode_widget.dart";
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:tailtag_mobile/features/fursuits/tag_badge.dart";

/// A clearly fake payload. No test holds a token-shaped value.
const fakePayload = "https://tailtag.app/t#test-payload-not-a-token";

/// The width and height in a PNG header.
(int, int) _pngSize(Uint8List bytes) {
  final header = ByteData.sublistView(bytes, 16, 24);
  return (header.getUint32(0), header.getUint32(4));
}

Future<void> _pumpBadge(WidgetTester tester, String name, GlobalKey key) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Stack(
          children: [
            TagBadgeCapture(
              boundaryKey: key,
              badge: TagBadge(payload: fakePayload, name: name, version: 3),
            ),
          ],
        ),
      ),
    ),
  );
}

void main() {
  testWidgets("the badge renders as a 2400 × 1800 PNG", (tester) async {
    final key = GlobalKey();
    await _pumpBadge(tester, "Alpha", key);

    final image = (await tester.runAsync(() => captureTagBadge(key)))!;

    expect((image.width, image.height), (2400, 1800));
    expect(_pngSize(image.bytes), (2400, 1800));
    expect(image.bytes.sublist(1, 4), utf8.encode("PNG"));
  });

  testWidgets("a 50-character name with emoji fits the badge", (tester) async {
    await _pumpBadge(tester, "${"W" * 48}🦊🐾", GlobalKey());

    expect(tester.takeException(), isNull);
    expect(find.text("${"W" * 48}🦊🐾"), findsOneWidget);
  });

  testWidgets("the QR encodes exactly the payload with level Q and a "
      "4-module quiet zone", (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: TagQr(payload: fakePayload, size: 245)),
    );

    final code = tester.widget<BarcodeWidget>(find.byType(BarcodeWidget));
    expect(utf8.decode(code.data), fakePayload);
    expect(code.barcode, same(tagBarcode));
    expect(tagQrLevel, BarcodeQRCorrectionLevel.quartile);
    // 50 bytes need version 5 (37 modules) at level Q. Levels L, M, and H
    // give 29, 33, and 41 modules, so the count proves the level.
    expect(tagQrModules("$fakePayload-xxx"), 37);
    expect(code.color, Colors.black);
    expect(code.backgroundColor, Colors.white);
    expect(
      (code.padding! as EdgeInsets).left,
      closeTo(245 * 4 / (tagQrModules(fakePayload) + 8), 0.001),
    );
  });
}
