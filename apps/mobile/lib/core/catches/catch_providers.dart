import "package:flutter_riverpod/flutter_riverpod.dart";
import "package:tailtag_mobile/core/api/api_providers.dart";
import "package:tailtag_mobile/core/catches/camera_permission.dart";
import "package:tailtag_mobile/core/catches/catch_repository.dart";
import "package:tailtag_mobile/core/catches/qr_scanner.dart";

/// The repository for catch attempts, requests, and the collection.
final catchRepositoryProvider = Provider<CatchRepository>(
  (ref) => CatchRepository(ref.watch(apiTransportProvider)),
);

/// Makes a camera session for the scanner. Tests override it with a fake.
final qrScannerFactoryProvider = Provider<QrScannerFactory>(
  (ref) => MobileQrScanner.new,
);

/// The camera permission. Tests override it with a fake.
final cameraPermissionProvider = Provider<CameraPermission>(
  (ref) => const SystemCameraPermission(),
);
