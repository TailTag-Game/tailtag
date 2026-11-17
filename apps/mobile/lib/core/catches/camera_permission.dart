import "package:permission_handler/permission_handler.dart";

/// Where the app stands with the camera permission.
enum CameraAccess {
  /// The app can still show the system prompt.
  undecided,

  /// The player allowed the camera.
  granted,

  /// The player refused, and only Settings can change it.
  denied,
}

/// Reads and asks for the camera permission. Widget tests replace it with a
/// fake, because the permission is a platform boundary.
abstract interface class CameraPermission {
  /// The current access, with no prompt.
  Future<CameraAccess> status();

  /// Shows the system prompt when it can and returns the result.
  Future<CameraAccess> request();

  /// Opens the app's page in the system settings.
  Future<void> openSettings();
}

/// The camera permission through `permission_handler`.
final class SystemCameraPermission implements CameraPermission {
  /// Creates the permission.
  const new();

  @override
  Future<CameraAccess> status() async =>
      _access(await Permission.camera.status);

  @override
  Future<CameraAccess> request() async =>
      // After a refusal at the prompt the app shows the Settings path, even
      // where Android would allow one more prompt.
      switch (await Permission.camera.request()) {
        PermissionStatus.granted ||
        PermissionStatus.limited => CameraAccess.granted,
        _ => CameraAccess.denied,
      };

  @override
  Future<void> openSettings() async {
    await openAppSettings();
  }

  /// `denied` means the prompt can still show: iOS before the first
  /// answer, and Android until the second refusal.
  static CameraAccess _access(PermissionStatus status) => switch (status) {
    PermissionStatus.granted ||
    PermissionStatus.limited ||
    PermissionStatus.provisional => CameraAccess.granted,
    PermissionStatus.denied => CameraAccess.undecided,
    PermissionStatus.permanentlyDenied ||
    PermissionStatus.restricted => CameraAccess.denied,
  };
}
