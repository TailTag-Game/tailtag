import "dart:async";

import "package:flutter/material.dart";
import "package:mobile_scanner/mobile_scanner.dart";

/// One live camera session that reports QR code text.
///
/// The scanner screen makes a new session for each scan, so a code that an
/// earlier session already reported can be read again. Widget tests replace
/// it with a fake, because the camera is a platform boundary.
abstract interface class QrScanner {
  /// The live camera view. It calls [onCode] with the raw text of each new
  /// QR code, and [onError] when the camera or the code reader fails.
  Widget buildView({
    required ValueChanged<String> onCode,
    required VoidCallback onError,
  });

  /// Turns the flashlight on or off.
  Future<void> toggleTorch();

  /// Stops the camera while the app is in the background.
  Future<void> stop();

  /// Starts the camera again on return to the foreground.
  Future<void> start();

  /// Stops the camera and frees it.
  Future<void> dispose();
}

/// Makes one [QrScanner] session.
typedef QrScannerFactory = QrScanner Function();

/// The `mobile_scanner` session. It reads QR codes only and reports each
/// code once.
final class MobileQrScanner implements QrScanner {
  /// Creates a session. The camera starts when the view shows.
  new()
    : _controller = MobileScannerController(
        detectionSpeed: DetectionSpeed.noDuplicates,
        formats: const [BarcodeFormat.qrCode],
      );

  final MobileScannerController _controller;

  @override
  Widget buildView({
    required ValueChanged<String> onCode,
    required VoidCallback onError,
  }) {
    return MobileScanner(
      controller: _controller,
      onDetect: (capture) {
        for (final barcode in capture.barcodes) {
          final text = barcode.rawValue;
          if (text != null) {
            onCode(text);
          }
        }
      },
      // The error can hold the scanned text, so it is never logged.
      onDetectError: (_, _) => onError(),
      errorBuilder: (context, _) {
        WidgetsBinding.instance.addPostFrameCallback((_) => onError());
        return const ColoredBox(color: Colors.black);
      },
    );
  }

  @override
  Future<void> toggleTorch() => _controller.toggleTorch();

  @override
  Future<void> stop() => _controller.stop();

  @override
  Future<void> start() => _controller.start();

  @override
  Future<void> dispose() => _controller.dispose();
}
